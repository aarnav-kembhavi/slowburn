"""M1 experiment: train + calibrate chunk detectors, evaluate per-type AUROC vs damaged fraction.

Detector variants (config ``variants``):
    base           LightGBM on the 260 chunk features
    validity       LightGBM on the chunk features + whole-file format validity
    validity_rule  format validity alone (no learning)
"""

from __future__ import annotations

import json
import pickle
import time

import numpy as np
import pandas as pd

from slowburn.detector.calibrate import CalibratedDetector
from slowburn.detector.dataset import build_chunk_dataset
from slowburn.detector.evaluate import GROUP_PREFIX, auroc_table, calibration_table
from slowburn.detector.features import FEATURE_NAMES_WITH_VALIDITY
from slowburn.detector.model import ChunkClassifier, ValidityRule
from slowburn.utils.config import resolve_path
from slowburn.utils.seed import child_rng

VARIANTS = ("base", "validity", "validity_rule")


def make_variant(variant: str, model_params: dict, seed: int):
    if variant in ("base", "validity"):
        return ChunkClassifier(model_params, seed=seed, feature_set=variant)
    if variant == "validity_rule":
        return ValidityRule()
    raise ValueError(f"unknown detector variant {variant!r}; known: {VARIANTS}")


def validity_rates(meta: pd.DataFrame) -> pd.DataFrame:
    """Per file version: share flagged invalid, by type x damage model x fraction (test files)."""
    files = meta.drop_duplicates(["file_id", "damage_model", "fraction"])
    files = files[files.file_valid >= 0]
    return (
        files.assign(invalid=(files.file_valid == 0).astype(float))
        .groupby(["file_type", "damage_model", "fraction"])
        .agg(invalid_rate=("invalid", "mean"), n_files=("invalid", "size"))
        .reset_index()
    )


def run_detector_experiment(cfg: dict) -> dict:
    seed = int(cfg["seed"])
    out = resolve_path(cfg["output_dir"])
    out.mkdir(parents=True, exist_ok=True)
    variants = list(cfg.get("variants", ["base"]))
    default = cfg.get("default_variant", variants[0])
    weights_spec = cfg["eval"].get("type_weights", "uniform")
    timings = {}

    t = time.perf_counter()
    ds = build_chunk_dataset(cfg)
    timings["build_dataset_s"] = time.perf_counter() - t
    m, X = ds.meta, ds.X
    masks = {s: (m.split == s).to_numpy() for s in ("train", "calib", "test")}
    y = m.label.to_numpy()
    ftypes = m.file_type.to_numpy()
    tr, ca, te = masks["train"], masks["calib"], masks["test"]
    alphas = list(cfg["calibration"]["conformal_alphas"])
    ev = cfg["eval"]

    aurocs, calibs, importances = [], [], []
    for variant in variants:
        t = time.perf_counter()
        clf = make_variant(variant, cfg["model"], seed).fit(X[tr], y[tr])
        fver = (m.file_id + "|" + m.damage_model + "|" + m.fraction.astype(str)).to_numpy()
        det = CalibratedDetector(clf).fit(X[ca], y[ca], groups=ftypes[ca], file_ids=fver[ca])
        timings[f"train_{variant}_s"] = time.perf_counter() - t
        t = time.perf_counter()
        raw = det.raw_scores(X[te])
        pv = {"marginal": det.pvalues(X[te]),
              "type_conditional": det.pvalues(X[te], groups=ftypes[te])}  # fmt: skip
        timings[f"score_{variant}_us_per_chunk"] = 1e6 * (time.perf_counter() - t) / te.sum()
        rng = child_rng(seed, "bootstrap", variant)
        aurocs.append(auroc_table(m[te], raw, pv, alphas, ev["n_bootstrap"], ev["ci"], rng,
                                  weights_spec).assign(detector=det.name))  # fmt: skip
        calibs.append(calibration_table(m[te], pv, alphas, weights_spec).assign(
            detector=det.name))  # fmt: skip
        if isinstance(clf, ChunkClassifier):
            names = FEATURE_NAMES_WITH_VALIDITY[: clf._cols(X[:1]).shape[1]]
            importances.append(pd.DataFrame({
                "detector": det.name, "feature": names,
                "gain": clf.model.booster_.feature_importance("gain"),
            }).sort_values("gain", ascending=False))  # fmt: skip
        with (out / f"detector_{variant}.pkl").open("wb") as fh:
            pickle.dump(det, fh)
        if variant == default:
            with (out / "detector.pkl").open("wb") as fh:
                pickle.dump(det, fh)

    auroc = pd.concat(aurocs, ignore_index=True)
    calib = pd.concat(calibs, ignore_index=True)
    importance = pd.concat(importances, ignore_index=True) if importances else pd.DataFrame()
    counts = m.groupby(["split", "file_type", "label"]).size().rename("n_chunks").reset_index()
    vrates = validity_rates(m[te])

    auroc.to_csv(out / "auroc_by_fraction.csv", index=False)
    calib.to_csv(out / "calibration.csv", index=False)
    counts.to_csv(out / "dataset_counts.csv", index=False)
    importance.to_csv(out / "feature_importance.csv", index=False)
    vrates.to_csv(out / "validity_rates.csv", index=False)
    info = {
        "config": cfg.get("_config_path"),
        "seed": seed,
        "variants": variants,
        "default_variant": default,
        "type_weights": weights_spec,
        "n_chunks": int(len(m)),
        "n_files": int(m.file_id.nunique()),
        "n_test_chunks": int(te.sum()),
        **{k: round(v, 3) for k, v in timings.items()},
    }
    (out / "run_info.json").write_text(json.dumps(info, indent=2))
    return {"auroc": auroc, "calibration": calib, "counts": counts, "info": info,
            "importance": importance, "validity_rates": vrates}  # fmt: skip


def load_detector(path) -> CalibratedDetector:
    with resolve_path(path).open("rb") as fh:
        return pickle.load(fh)


def headline_summary(auroc: pd.DataFrame) -> pd.DataFrame:
    """Chunk AUROC weighted averages per detector, damage model and fraction."""
    sub = auroc[(auroc.level == "chunk") & auroc.file_type.str.startswith(GROUP_PREFIX)]
    tbl = sub.pivot_table(index=["detector", "damage_model", "fraction"], columns="file_type",
                          values="auroc").sort_index(ascending=[True, True, False])  # fmt: skip
    return tbl.round(4).replace({np.nan: None})
