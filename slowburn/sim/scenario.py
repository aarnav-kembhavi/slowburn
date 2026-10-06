"""Day-by-day simulation of one machine: benign churn plus an optional slow, partial attack.

The simulator yields one ``Day`` at a time so retention policies can be run online, exactly as
they would be in deployment (they never see the future). Ground truth (attack start, which files
were damaged on which day) is recorded on the ``Scenario`` for evaluation only.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field

import numpy as np

from slowburn.sim.content import WHOLE_FILE_REWRITE_TYPES, chunk_bytes, generate_file
from slowburn.sim.damage import DamageSource, apply_damage
from slowburn.store.snapshot import chunk_hash


@dataclass(frozen=True)
class ScenarioConfig:
    n_files: int = 40
    file_types: tuple[str, ...] = ("txt", "csv", "bin", "docx", "zip", "png", "jpg", "mp3")
    file_kib: tuple[int, int] = (16, 96)
    chunk_size: int = 4096
    days: int = 60
    # mean number of benign file edits per day, scaled by the weekday multiplier (Mon..Sun)
    edits_per_day: float = 4.0
    weekday_multipliers: tuple[float, ...] = (1.0, 1.0, 1.0, 1.0, 1.0, 0.3, 0.2)
    # attack: None = clean run
    attack_start: int | None = 40
    attack_files_per_day: float = 1.0
    damage_model: str = "striped"
    damage_fraction: float = 0.1
    stripe_bytes: int = 16
    # file types the attacker damages; None = all types
    attack_target_types: tuple[str, ...] | None = None

    @classmethod
    def from_dict(cls, d: dict) -> ScenarioConfig:
        d = dict(d)
        for k in ("file_types", "file_kib", "weekday_multipliers"):
            if k in d:
                d[k] = tuple(d[k])
        targets = d.get("attack_target_types")
        if targets is None or targets == "all":
            d["attack_target_types"] = None
        else:
            d["attack_target_types"] = tuple(targets)
        return cls(**d)


@dataclass(frozen=True)
class ChangedChunk:
    file_id: str
    file_type: str
    index: int
    data: bytes
    damage: float  # fraction of bytes damaged (ground truth; 0 = benign)

    @property
    def label(self) -> int:
        return int(self.damage > 0)


@dataclass
class Day:
    day: int
    files: dict[str, list[bytes]]  # full current state, for snapshotting
    changed: list[ChangedChunk]


@dataclass
class Scenario:
    cfg: ScenarioConfig
    file_types: dict[str, str] = field(default_factory=dict)
    damaged_on: dict[str, int] = field(default_factory=dict)  # file id -> day damaged

    def run(self, rng: np.random.Generator, source: DamageSource) -> Iterator[Day]:
        cfg = self.cfg
        files: dict[str, list[bytes]] = {}
        damage: dict[str, np.ndarray] = {}
        for i in range(cfg.n_files):
            fid = f"f{i:04d}"
            ftype = cfg.file_types[i % len(cfg.file_types)]
            self.file_types[fid] = ftype
            files[fid] = self._new_content(ftype, rng)
            damage[fid] = np.zeros(len(files[fid]))
        prev_hashes = {fid: set() for fid in files}  # day 0: everything is "changed"

        for day in range(cfg.days):
            if day > 0:
                self._benign_edits(day, files, damage, rng)
                if cfg.attack_start is not None and day >= cfg.attack_start:
                    self._attack(day, files, damage, rng, source)
            changed = []
            for fid, chunks in files.items():
                for idx, c in enumerate(chunks):
                    if chunk_hash(c) not in prev_hashes[fid]:
                        changed.append(
                            ChangedChunk(fid, self.file_types[fid], idx, c, float(damage[fid][idx]))
                        )
                prev_hashes[fid] = {chunk_hash(c) for c in chunks}
            yield Day(day, {k: list(v) for k, v in files.items()}, changed)

    def _new_content(self, ftype: str, rng: np.random.Generator) -> list[bytes]:
        lo, hi = self.cfg.file_kib
        size = int(rng.integers(lo, hi + 1)) * 1024
        return chunk_bytes(generate_file(ftype, rng, size), self.cfg.chunk_size)

    def _benign_edits(self, day, files, damage, rng) -> None:
        cfg = self.cfg
        lam = cfg.edits_per_day * cfg.weekday_multipliers[day % 7]
        candidates = [f for f in files if f not in self.damaged_on]
        n = min(len(candidates), int(rng.poisson(lam)))
        for fid in rng.choice(candidates, size=n, replace=False) if n else []:
            ftype = self.file_types[fid]
            if ftype in WHOLE_FILE_REWRITE_TYPES:
                files[fid] = self._new_content(ftype, rng)  # a save rewrites the stream
            else:
                fresh = self._new_content(ftype, rng)
                k = int(rng.integers(1, min(3, len(files[fid])) + 1))
                for idx in rng.choice(len(files[fid]), size=k, replace=False):
                    files[fid][idx] = fresh[idx % len(fresh)]
            damage[fid] = np.zeros(len(files[fid]))

    def _attack(self, day, files, damage, rng, source) -> None:
        cfg = self.cfg
        allowed = cfg.attack_target_types
        targets = [
            f
            for f in files
            if f not in self.damaged_on and (allowed is None or self.file_types[f] in allowed)
        ]
        n = min(len(targets), int(rng.poisson(cfg.attack_files_per_day)))
        if day == cfg.attack_start:
            n = min(len(targets), max(n, 1))  # start day := first day with damage
        for fid in rng.choice(targets, size=n, replace=False) if n else []:
            res = apply_damage(
                b"".join(files[fid]),
                cfg.damage_model,
                cfg.damage_fraction,
                cfg.chunk_size,
                rng,
                source,
                file_key=fid,
                stripe_bytes=cfg.stripe_bytes,
            )
            files[fid] = chunk_bytes(res.data, cfg.chunk_size)
            damage[fid] = res.chunk_damage
            self.damaged_on[fid] = day
