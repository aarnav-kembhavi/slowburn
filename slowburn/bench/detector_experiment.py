"""M1 experiment: train + calibrate the chunk detector, evaluate AUROC vs damaged fraction."""

from __future__ import annotations

import json
import pickle
import time

import numpy as np
import pandas as pd

from slowburn.detector.calibrate import CalibratedDetector
from slowburn.detector.dataset import build_chunk_dataset
from slowburn.detector.evaluate import auroc_table, calibration_table
from slowburn.detector.features import FEATURE_NAMES
from slowburn.detector.model import ChunkClassifier
from slowburn.utils.config import resolve_path
from slowburn.utils.seed import child_rng


def run_detector_experiment(cfg: dict) -> dict[str, pd.DataFrame]:
    seed = int(cfg["seed"])
    out = resolve_path(cfg["output_dir"])
    out.mkdir(parents=True, exist_ok=True)
    timings = {}

    t = time.perf_counter()
    ds = build_chunk_dataset(cfg)
    timings["build_dataset_s"] = time.perf_counter() - t
    m, X = ds.meta, ds.X
    masks = {s: (m.split == s).to_numpy() for s in ("train", "calib", "test")}
    y = m.label.to_numpy()

    t = time.perf_counter()
    clf = ChunkClassifier(cfg["model"], seed=seed).fit(X[masks["train"]], y[masks["train"]])
    ftypes = m.file_type.to_numpy()
    ca = masks["calib"]
    det = CalibratedDetector(clf).fit(X[ca], y[ca], groups=ftypes[ca])
    timings["train_s"] = time.perf_counter() - t

    te = masks["test"]
    t = time.perf_counter()
    raw = det.raw_scores(X[te])
    pv = {"marginal": det.pvalues(X[te]), "mondrian": det.pvalues(X[te], groups=ftypes[te])}
    timings["score_test_us_per_chunk"] = 1e6 * (time.perf_counter() - t) / max(1, te.sum())

    alphas = list(cfg["calibration"]["conformal_alphas"])
    ev = cfg["eval"]
    auroc = auroc_table(
        m[te], raw, pv, alphas, ev["n_bootstrap"], ev["ci"], child_rng(seed, "bootstrap")
    )
    calib = calibration_table(m[te], pv, alphas)
    counts = m.groupby(["split", "file_type", "label"]).size().rename("n_chunks").reset_index()
    importance = pd.DataFrame(
        {"feature": FEATURE_NAMES, "gain": clf.model.booster_.feature_importance("gain")}
    )
    importance = importance.sort_values("gain", ascending=False)

    auroc.to_csv(out / "auroc_by_fraction.csv", index=False)
    calib.to_csv(out / "calibration.csv", index=False)
    counts.to_csv(out / "dataset_counts.csv", index=False)
    importance.to_csv(out / "feature_importance.csv", index=False)
    with (out / "detector.pkl").open("wb") as fh:
        pickle.dump(det, fh)
    meta = {
        "config": cfg.get("_config_path"),
        "seed": seed,
        "n_chunks": int(len(m)),
        "n_files": int(m.file_id.nunique()),
        "n_test_chunks": int(te.sum()),
        **{k: round(v, 3) for k, v in timings.items()},
    }
    (out / "run_info.json").write_text(json.dumps(meta, indent=2))
    return {
        "auroc": auroc,
        "calibration": calib,
        "counts": counts,
        "info": meta,
        "importance": importance,
    }


def load_detector(path) -> CalibratedDetector:
    with resolve_path(path).open("rb") as fh:
        return pickle.load(fh)


def headline_summary(auroc: pd.DataFrame) -> pd.DataFrame:
    """Compact table for the console / CHANGELOG: chunk AUROC, ALL and HIGH_ENTROPY types."""
    sub = auroc[
        (auroc.level == "chunk") & auroc.file_type.isin(["ALL", "HIGH_ENTROPY", "LOW_ENTROPY"])
    ]
    tbl = sub.pivot_table(
        index=["damage_model", "fraction"], columns="file_type", values="auroc"
    ).sort_index(ascending=[True, False])
    return tbl.round(3).replace({np.nan: None})
