"""Labelled chunk dataset for training and evaluating the detector.

Construction (all seeded from the config):
1. generate ``files_per_type`` benign files per type and split them by FILE (stratified by type)
   into train / calib / test, so no file contributes chunks to two splits;
2. benign rows: a capped random subset of each file's chunks (label 0);
3. for every damage model and fraction, damage a copy of the file and add its *changed* chunks
   (label 1). Striped damage reuses the benign rows' chunk positions, so positives and negatives
   are paired; whole-chunk damage only adds the chunks it actually hit.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from slowburn.detector.datasets import NapierOneDamageSource
from slowburn.detector.features import features_batch
from slowburn.sim.content import chunk_bytes, generate_file
from slowburn.sim.damage import DamageSource, RandomDamageSource, apply_damage
from slowburn.utils.seed import child_rng

SPLITS = ("train", "calib", "test")


@dataclass
class ChunkDataset:
    meta: pd.DataFrame  # one row per chunk
    X: np.ndarray  # features, aligned with meta


def split_files(files: pd.DataFrame, fractions: dict, rng: np.random.Generator) -> dict[str, str]:
    """Map file_id -> split, stratified by file_type."""
    out = {}
    cuts = np.cumsum([fractions[s] for s in SPLITS])
    cuts = cuts / cuts[-1]
    for _, grp in files.groupby("file_type", sort=True):
        ids = grp["file_id"].to_numpy()
        ids = ids[rng.permutation(len(ids))]
        bounds = np.round(cuts * len(ids)).astype(int)
        for i, fid in enumerate(ids):
            out[fid] = SPLITS[int(np.searchsorted(bounds, i, side="right"))]
    return out


def make_damage_source(data_cfg: dict, seed: int) -> DamageSource:
    kind = data_cfg.get("damage_source", "synthetic_random")
    if kind == "synthetic_random":
        return RandomDamageSource(child_rng(seed, "damage_bytes"))
    if kind == "napierone":
        return NapierOneDamageSource(
            data_cfg["napierone_dir"], data_cfg.get("encrypted_glob", "encrypted/**/*")
        )
    raise ValueError(f"unknown damage_source {kind!r}")


def build_chunk_dataset(cfg: dict) -> ChunkDataset:
    seed = int(cfg["seed"])
    d = cfg["data"]
    if d.get("benign_source", "synthetic") != "synthetic":
        raise NotImplementedError(
            "benign_source=napierone needs the confirmed NapierOne layout (OPEN_QUESTIONS.md)"
        )
    cs, min_bytes, cap = d["chunk_size"], d["min_chunk_bytes"], d["max_chunks_per_file"]
    lo, hi = d["file_kib"]
    source = make_damage_source(d, seed)

    files = []
    for ftype in d["file_types"]:
        for i in range(d["files_per_type"]):
            files.append({"file_id": f"{ftype}_{i:04d}", "file_type": ftype})
    split = split_files(pd.DataFrame(files), d["split"], child_rng(seed, "split"))

    rows, bufs, types, starts = [], [], [], []

    def add(chunk: bytes, f: dict, idx: int, model: str, frac: float, dmg: float) -> None:
        rows.append({
            "file_id": f["file_id"], "file_type": f["file_type"], "split": split[f["file_id"]],
            "chunk_index": idx, "damage_model": model, "fraction": frac,
            "damaged_byte_frac": dmg, "label": int(dmg > 0),
            "benign_source": "synthetic",
            "damage_source": source.name if dmg > 0 else "none",
        })  # fmt: skip
        bufs.append(chunk)
        types.append(f["file_type"])
        starts.append(idx == 0)

    for f in files:
        rng = child_rng(seed, "file", f["file_id"])
        data = generate_file(f["file_type"], rng, int(rng.integers(lo, hi + 1)) * 1024)
        chunks = chunk_bytes(data, cs)
        eligible = [i for i, c in enumerate(chunks) if len(c) >= min_bytes]
        if not eligible:
            continue
        keep = sorted(rng.choice(eligible, size=min(cap, len(eligible)), replace=False))
        for i in keep:
            add(chunks[i], f, i, "none", 0.0, 0.0)
        for model in d["damage_models"]:
            for frac in d["fractions"]:
                res = apply_damage(
                    data, model, frac, cs, rng, source, f["file_id"], d.get("stripe_bytes", 16)
                )
                dchunks = chunk_bytes(res.data, cs)
                if model == "striped":
                    candidates = keep
                else:
                    hit = [i for i in eligible if res.chunk_damage[i] > 0]
                    candidates = sorted(rng.choice(hit, size=min(cap, len(hit)), replace=False))
                for i in candidates:
                    if res.chunk_damage[i] > 0:
                        add(dchunks[i], f, i, model, frac, float(res.chunk_damage[i]))

    X = features_batch(bufs, types, starts)
    return ChunkDataset(pd.DataFrame(rows), X)
