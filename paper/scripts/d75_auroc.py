"""D75: the NapierOne detector AUROC table on the enlarged pools. The detector is unchanged
(results/detector_napierone/detector.pkl, the D71b rebuild); it is scored on (a) its own held-out
test files (reproduces the D71b table) and (b) the new D75 DEV pool files, with the same damage
models, fractions and the held-out damage families. Run from the repo root:

    uv run python paper/scripts/d75_auroc.py
"""

import pickle
from pathlib import Path

import numpy as np
import pandas as pd

from slowburn.detector.datasets import NapierOneDamageSource
from slowburn.detector.evaluate import auroc_table
from slowburn.detector.features import features_batch, with_file_validity
from slowburn.detector.napierone import benign_splits, encrypted_samples, family_splits, read_benign
from slowburn.detector.validity import file_validity
from slowburn.sim.content import chunk_bytes
from slowburn.sim.damage import apply_damage
from slowburn.utils.config import load_config, resolve_path
from slowburn.utils.seed import child_rng

CFG = "configs/detector_napierone.yaml"
OUT = Path("results/detector_napierone/d75_auroc_old_vs_new_pools.csv")


def rows_for(files, d, source, seed):
    """The build_chunk_dataset rows for test-split files (same seeds per file id)."""
    cs, min_bytes, cap = d["chunk_size"], d["min_chunk_bytes"], d["max_chunks_per_file"]
    meta, bufs, types, starts = [], [], [], []

    def add(chunk, fid, ftype, idx, model, frac, dmg, valid):
        meta.append({"file_id": fid, "file_type": ftype, "split": "test", "chunk_index": idx,
                     "damage_model": model, "fraction": frac, "damaged_byte_frac": dmg,
                     "label": int(dmg > 0), "file_valid": valid, "benign_source": "napierone",
                     "damage_source": source.name if dmg > 0 else "none"})  # fmt: skip
        bufs.append(chunk)
        types.append(ftype)
        starts.append(idx == 0)

    for fid, ftype, data in files:
        rng = child_rng(seed, "file", fid)
        chunks = chunk_bytes(data, cs)
        eligible = [i for i, c in enumerate(chunks) if len(c) >= min_bytes]
        if not eligible:
            continue
        keep = sorted(rng.choice(eligible, size=min(cap, len(eligible)), replace=False))
        valid = file_validity(data, ftype)
        for i in keep:
            add(chunks[i], fid, ftype, i, "none", 0.0, 0.0, valid)
        for model in d["damage_models"]:
            for frac in d["fractions"]:
                res = apply_damage(data, model, frac, cs, rng, source, fid,
                                   d.get("stripe_bytes", 16))  # fmt: skip
                dchunks = chunk_bytes(res.data, cs)
                dvalid = file_validity(res.data, ftype)
                if model == "striped":
                    cands = keep
                else:
                    hit = [i for i in eligible if res.chunk_damage[i] > 0]
                    cands = sorted(rng.choice(hit, size=min(cap, len(hit)), replace=False))
                for i in cands:
                    if res.chunk_damage[i] > 0:
                        add(dchunks[i], fid, ftype, i, model, frac, float(res.chunk_damage[i]),
                            dvalid)  # fmt: skip
    m = pd.DataFrame(meta)
    X = with_file_validity(features_batch(bufs, types, starts), m.file_valid.to_numpy())
    return m, X


def score(det, m, X, cfg, tag):
    ft = m.file_type.to_numpy()
    raw = det.raw_scores(X)
    pv = {"marginal": det.pvalues(X), "type_conditional": det.pvalues(X, groups=ft)}
    ev = cfg["eval"]
    t = auroc_table(m, raw, pv, list(cfg["calibration"]["conformal_alphas"]), ev["n_bootstrap"],
                    ev["ci"], child_rng(int(cfg["seed"]), "bootstrap", "d75", tag),
                    ev.get("type_weights", "uniform"))  # fmt: skip
    return t.assign(pool=tag, n_files=m.file_id.nunique())


def main():
    cfg = load_config(CFG)
    d, seed = cfg["data"], int(cfg["seed"])
    root = str(resolve_path(d["napierone_dir"]))
    with open("results/detector_napierone/detector.pkl", "rb") as fh:
        det = pickle.load(fh)
    fams = family_splits(root)
    source = NapierOneDamageSource(root, samples=encrypted_samples(root, fams["test"]))
    sp = benign_splits(root)
    old = [(f"{t}_test_{i:03d}", t, read_benign(root, nf))
           for t in d["file_types"] for i, nf in enumerate(sp[t]["test"])]  # fmt: skip
    v2 = Path(root) / "benign_v2"
    new = [(f"{t}_d75dev_{p.name}", t, p.read_bytes())
           for t in d["file_types"] for p in sorted((v2 / t / "dev").iterdir())]  # fmt: skip
    tabs = []
    for tag, files in (("v1_heldout_test", old), ("v2_new_dev", new)):
        m, X = rows_for(files, d, source, seed)
        tabs.append(score(det, m, X, cfg, tag))
        print(tag, len(files), "files", len(m), "chunks", flush=True)
    t = pd.concat(tabs, ignore_index=True)
    keys = ["damage_model", "fraction", "file_type", "level"]
    w = t.pivot_table(index=keys, columns="pool", values="auroc").reset_index()
    w["diff"] = w["v2_new_dev"] - w["v1_heldout_test"]
    w.to_csv(OUT, index=False)
    s = w[(w.damage_model == "striped") & (w.fraction == 0.1)]
    print(s.round(3).to_string(index=False))
    print("largest |diff|:", float(np.nanmax(np.abs(w["diff"]))))


if __name__ == "__main__":
    main()
