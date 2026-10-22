"""Labelled chunk dataset for training and evaluating the detector.

Construction (all seeded from the config):
1. generate ``files_per_type`` benign files per type and split them by FILE (stratified by type)
   into train / calib / test, so no file contributes chunks to two splits;
2. benign rows: a capped random subset of each file's chunks (label 0);
3. for every damage model and fraction, damage a copy of the file and add its *changed* chunks
   (label 1). Striped damage reuses the benign rows' chunk positions, so positives and negatives
   are paired; whole-chunk damage only adds the chunks it actually hit.

Every row also carries ``file_valid``: whether the whole file version the chunk came from still
decodes as its declared type. ``X`` therefore has the base features plus that column.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from slowburn.detector.datasets import NapierOneDamageSource
from slowburn.detector.features import features_batch, with_file_validity
from slowburn.detector.napierone import (
    benign_splits,
    encrypted_samples,
    family_splits,
    read_benign,
)
from slowburn.detector.validity import file_validity
from slowburn.sim.content import chunk_bytes, generate_file
from slowburn.sim.damage import DamageSource, RandomDamageSource, apply_damage
from slowburn.utils.config import resolve_path
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
    benign = d.get("benign_source", "synthetic")
    if benign not in ("synthetic", "napierone"):
        raise ValueError(f"unknown benign_source {benign!r}")
    cs, min_bytes, cap = d["chunk_size"], d["min_chunk_bytes"], d["max_chunks_per_file"]
    lo, hi = d["file_kib"]

    files = []
    if benign == "napierone":  # D67: fixed per-type splits of real files (seed 202)
        root = str(resolve_path(d["napierone_dir"]))
        sp = benign_splits(root)
        split = {}
        for ftype in d["file_types"]:
            for s in SPLITS:
                for i, nf in enumerate(sp[ftype][s]):
                    fid = f"{ftype}_{s}_{i:03d}"
                    files.append({"file_id": fid, "file_type": ftype, "napierone": nf})
                    split[fid] = s
    else:
        for ftype in d["file_types"]:
            for i in range(d["files_per_type"]):
                files.append({"file_id": f"{ftype}_{i:04d}", "file_type": ftype})
        split = split_files(pd.DataFrame(files), d["split"], child_rng(seed, "split"))
    if d.get("damage_source") == "napierone":  # D67: each split takes its own families
        root_e = resolve_path(d["napierone_dir"])
        fams = family_splits(root_e)
        sources = {s: NapierOneDamageSource(root_e, samples=encrypted_samples(root_e, fams[s]))
                   for s in SPLITS}  # fmt: skip
    else:
        sources = dict.fromkeys(SPLITS, make_damage_source(d, seed))

    rows, bufs, types, starts = [], [], [], []

    def add(chunk: bytes, f: dict, idx: int, model: str, frac: float, dmg: float,
            valid: float) -> None:  # fmt: skip
        rows.append({
            "file_id": f["file_id"], "file_type": f["file_type"], "split": split[f["file_id"]],
            "chunk_index": idx, "damage_model": model, "fraction": frac,
            "damaged_byte_frac": dmg, "label": int(dmg > 0), "file_valid": valid,
            "benign_source": benign,
            "damage_source": sources[split[f["file_id"]]].name if dmg > 0 else "none",
        })  # fmt: skip
        bufs.append(chunk)
        types.append(f["file_type"])
        starts.append(idx == 0)

    for f in files:
        rng = child_rng(seed, "file", f["file_id"])
        source = sources[split[f["file_id"]]]
        if benign == "napierone":
            data = read_benign(root, f["napierone"])
        else:
            data = generate_file(f["file_type"], rng, int(rng.integers(lo, hi + 1)) * 1024)
        chunks = chunk_bytes(data, cs)
        eligible = [i for i, c in enumerate(chunks) if len(c) >= min_bytes]
        if not eligible:
            continue
        keep = sorted(rng.choice(eligible, size=min(cap, len(eligible)), replace=False))
        valid = file_validity(data, f["file_type"])
        for i in keep:
            add(chunks[i], f, i, "none", 0.0, 0.0, valid)
        for model in d["damage_models"]:
            for frac in d["fractions"]:
                res = apply_damage(
                    data, model, frac, cs, rng, source, f["file_id"], d.get("stripe_bytes", 16)
                )
                dchunks = chunk_bytes(res.data, cs)
                dvalid = file_validity(res.data, f["file_type"])
                if model == "striped":
                    candidates = keep
                else:
                    hit = [i for i in eligible if res.chunk_damage[i] > 0]
                    candidates = sorted(rng.choice(hit, size=min(cap, len(hit)), replace=False))
                for i in candidates:
                    if res.chunk_damage[i] > 0:
                        add(dchunks[i], f, i, model, frac, float(res.chunk_damage[i]), dvalid)

    meta = pd.DataFrame(rows)
    X = with_file_validity(features_batch(bufs, types, starts), meta.file_valid.to_numpy())
    return ChunkDataset(meta, X)
