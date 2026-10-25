"""D73: a forkable, day-by-day machine simulator.

``MachineSim`` steps exactly what ``Scenario.run`` plus the trace loop of
``retention_experiment.simulate`` do, one day per ``step()``, but keeps its state in plain
fields so a benign machine can be ``fork``ed at day s into the same machine attacked from day s.
That is exact because benign edits and attack draws share one random stream: before the start,
the attacked machine consumes exactly the benign draws (tests/test_fleet.py checks both the
match with ``simulate`` and fork == fresh simulation). Snapshot chunk sets and AMOEBA writes are
not kept (D73 needs neither).
"""

from __future__ import annotations

import copy
from dataclasses import replace

import numpy as np

from slowburn.inference.daily import make_aggregator
from slowburn.inference.pipeline import AbstractFileDetector, score_day
from slowburn.sim.damage import RandomDamageSource
from slowburn.sim.scenario import ChangedChunk, Day, Scenario, ScenarioConfig
from slowburn.store.restore import FileHistory
from slowburn.store.snapshot import chunk_hash
from slowburn.utils.seed import child_rng


class MachineSim:
    def __init__(self, cfg: dict, params: dict, key: tuple, days: int,
                 keep_snapshots: bool = False):  # fmt: skip
        """``params``: scenario fields plus the evidence keys of a retention task (as in
        ``simulate``); ``key``: the machine's seed key; ``days``: days to simulate at most;
        ``keep_snapshots``: also record each day's chunk set (needed by ``evaluate_trace``)."""
        from slowburn.bench.retention_experiment import SCENARIO_FIELDS, _load_detector, _napierone

        p = params
        scen_params = {k: v for k, v in p.items() if k in SCENARIO_FIELDS}
        evidence = p.get("evidence", "abstract")
        content = "bytes" if evidence == "detector" else "tokens"
        self.scen = Scenario(ScenarioConfig.from_dict({**scen_params, "days": days,
                                                       "content": content}))  # fmt: skip
        self.damage_source = RandomDamageSource(child_rng(*key, "damage"))
        if p.get("data_source", "synthetic") == "napierone":
            self.scen.content_pool, self.damage_source = _napierone(
                p["napierone_dir"], p.get("napierone_pool", "v1")
            )
        if p.get("benign_churn", "poisson") != "poisson":
            raise ValueError("D73 machines use Poisson churn")
        self.evidence = evidence
        if evidence == "detector":
            self.det = _load_detector(p["detector_path"])
            self.flag_alpha = float(p["flag_alpha"])
            self.agg = make_aggregator("file_exceed", alpha=self.flag_alpha)
        else:
            self.det = AbstractFileDetector(float(p.get("detect_prob", 0.0)),
                                            child_rng(*key, "detector"))  # fmt: skip
            self.agg = make_aggregator("file_exceed", alpha=0.5)
            self.flag_alpha = 0.0
        self.rng, self.aux_rng = child_rng(*key), child_rng(*key, "benign_invalid")
        cfg_s = self.scen.cfg
        if cfg_s.benign_invalid_rate > 0 and self.aux_rng is None:
            raise ValueError("benign_invalid_rate > 0 needs aux_rng")
        self.files: dict[str, list[bytes]] = {}
        self.damage: dict[str, np.ndarray] = {}
        for i in range(cfg_s.n_files):
            fid = f"f{i:04d}"
            ftype = cfg_s.file_types[i % len(cfg_s.file_types)]
            self.scen.file_types[fid] = ftype
            self.files[fid] = self.scen._new_content(ftype, self.rng)
            self.damage[fid] = np.zeros(len(self.files[fid]))
        self.prev_hashes: dict[str, set] = {fid: set() for fid in self.files}
        self.day = 0  # next day to simulate
        self.obs: list = []
        self.versions: dict[str, tuple] = {}
        self.change_days: dict[str, list[int]] = {}
        self.flagged_days: dict[str, set[int]] = {}
        self.snapshots: list[frozenset] | None = [] if keep_snapshots else None

    @property
    def start(self) -> int | None:
        return self.scen.cfg.attack_start

    def fork(self, start: int | None, **attack) -> MachineSim:
        """The same machine with the attack starting on ``start`` (>= the next day); ``attack``
        may override attack fields of the scenario (D74: rate, damage fraction, target types)."""
        if start is not None and start < self.day:
            raise ValueError("cannot fork into the past")
        bad = set(attack) - {"attack_files_per_day", "damage_fraction", "attack_target_types",
                             "damage_model", "attack_fixed_per_day"}  # fmt: skip
        if bad:
            raise ValueError(f"not an attack field: {sorted(bad)}")
        new = copy.copy(self)
        new.scen = replace(self.scen, cfg=replace(self.scen.cfg, attack_start=start, **attack),
                           file_types=dict(self.scen.file_types),
                           damaged_on=dict(self.scen.damaged_on))  # fmt: skip
        new.rng, new.aux_rng = copy.deepcopy(self.rng), copy.deepcopy(self.aux_rng)
        if isinstance(self.damage_source, RandomDamageSource):
            new.damage_source = copy.deepcopy(self.damage_source)
        if isinstance(self.det, AbstractFileDetector):
            new.det = copy.deepcopy(self.det)
        new.files = {f: list(c) for f, c in self.files.items()}
        new.damage = {f: d.copy() for f, d in self.damage.items()}
        new.prev_hashes = {f: set(h) for f, h in self.prev_hashes.items()}
        new.obs = list(self.obs)
        new.versions = dict(self.versions)
        new.change_days = {f: list(d) for f, d in self.change_days.items()}
        new.flagged_days = {f: set(d) for f, d in self.flagged_days.items()}
        new.snapshots = None if self.snapshots is None else list(self.snapshots)
        return new

    def step(self) -> None:
        """Simulate day ``self.day`` (Scenario.run body, then simulate's trace update)."""
        scen, cfg, day = self.scen, self.scen.cfg, self.day
        files, damage = self.files, self.damage
        if day > 0:
            scen._benign_edits(day, files, damage, self.rng)
            if cfg.attack_start is not None and day >= cfg.attack_start:
                scen._attack(day, files, damage, self.rng, self.damage_source)
        changed = []
        for fid, chunks in files.items():
            for idx, c in enumerate(chunks):
                if chunk_hash(c) not in self.prev_hashes[fid]:
                    changed.append(ChangedChunk(fid, scen.file_types[fid], idx, c,
                                                float(damage[fid][idx])))  # fmt: skip
            self.prev_hashes[fid] = {chunk_hash(c) for c in chunks}
        invalid: frozenset[str] = frozenset()
        if cfg.benign_invalid_rate > 0:
            clean = sorted({c.file_id for c in changed if c.damage == 0}
                           - {c.file_id for c in changed if c.damage > 0})  # fmt: skip
            draws = self.aux_rng.random(len(clean)) < cfg.benign_invalid_rate
            invalid = frozenset(f for f, d in zip(clean, draws, strict=True) if d)
        d = Day(day, {k: list(v) for k, v in files.items()}, changed, invalid)
        if self.snapshots is not None:
            self.snapshots.append(frozenset(c for chunks in d.files.values() for c in chunks))
        scores = score_day(self.det, d) if self.evidence == "detector" else self.det.score_day(d)
        self.obs.append(self.agg(scores))
        for f, pv in (scores.file_pvals or {}).items():
            if pv <= self.flag_alpha:
                self.flagged_days.setdefault(f, set()).add(day)
        for fid, chunks in d.files.items():
            v = tuple(chunks)
            if self.versions.get(fid) != v:
                self.versions[fid] = v
                self.change_days.setdefault(fid, []).append(day)
        self.day += 1

    def run_to(self, day: int) -> MachineSim:
        """Step until days 0..day - 1 are simulated."""
        while self.day < day:
            self.step()
        return self

    def trace(self):
        """A ``MachineTrace`` of the days simulated so far (needs ``keep_snapshots``)."""
        from slowburn.bench.retention_experiment import MachineTrace

        if self.snapshots is None:
            raise ValueError("trace() needs keep_snapshots=True")
        return MachineTrace(self.start, self.day, list(self.snapshots), list(self.obs),
                            self.histories(), [[] for _ in range(self.day)],
                            self.scen.cfg.chunk_size, dict(self.scen.file_types))  # fmt: skip

    def histories(self) -> dict[str, FileHistory]:
        return {f: FileHistory(tuple(d), self.scen.damaged_on.get(f),
                               frozenset(self.flagged_days.get(f, ())))
                for f, d in self.change_days.items()}  # fmt: skip
