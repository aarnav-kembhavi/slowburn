"""End-to-end retention benchmark: simulate -> score -> daily statistic -> posterior -> retain.

One row per (scenario, policy). Every row records where its benign and damaged bytes came from,
so synthetic and real-data results are never mixed silently.
"""

from __future__ import annotations

import itertools
import time
from dataclasses import fields
from pathlib import Path

import numpy as np
import pandas as pd

from slowburn.bench.metrics import recovery_metrics
from slowburn.detector.base import Detector, EntropyDetector
from slowburn.detector.features import features_batch
from slowburn.inference.aggregate import make_aggregator
from slowburn.inference.placeholder import naive_start_posterior
from slowburn.retention.base import KeepLastN, RetentionContext, RetentionPolicy
from slowburn.sim.damage import RandomDamageSource
from slowburn.sim.scenario import Scenario, ScenarioConfig
from slowburn.store.snapshot import SnapshotStore
from slowburn.utils.config import resolve_path
from slowburn.utils.seed import child_rng

_SCENARIO_KEYS = {f.name for f in fields(ScenarioConfig)}


def make_policies(names: list[str]) -> list[RetentionPolicy]:
    registry = {"keep_last_n": KeepLastN}
    out = []
    for n in names:
        if n not in registry:
            raise ValueError(f"unknown policy {n!r}; known: {sorted(registry)}")
        out.append(registry[n]())
    return out


def make_detector(cfg: dict) -> Detector:
    kind = cfg.get("kind", "entropy_placeholder")
    if kind == "entropy_placeholder":
        return EntropyDetector()
    raise ValueError(f"unknown detector kind {kind!r}")


def expand_sweep(base: dict, sweep: dict) -> list[dict]:
    """Cartesian product of sweep values over the base parameters."""
    if not sweep:
        return [dict(base)]
    keys = list(sweep)
    return [
        dict(base, **dict(zip(keys, vals, strict=True)))
        for vals in itertools.product(*(sweep[k] for k in keys))
    ]


def run_one(
    params: dict,
    policy: RetentionPolicy,
    detector: Detector,
    agg_cfg: dict,
    budget: int,
    seed: int,
    rep: int,
) -> dict:
    delay = int(params["discovery_delay"])
    scen_params = {k: v for k, v in params.items() if k in _SCENARIO_KEYS}
    start = scen_params.get("attack_start", ScenarioConfig.attack_start)
    discovery_day = start + delay
    scfg = ScenarioConfig.from_dict({**scen_params, "days": discovery_day + 1})
    # same seed per (scenario, rep) for every policy: policies are compared on identical data
    key = (seed, "scenario", rep, *(str(v) for v in sorted(scen_params.items())))
    rng = child_rng(*key)
    source = RandomDamageSource(child_rng(*key, "damage"))
    agg = make_aggregator(agg_cfg["name"], **agg_cfg.get("params", {}))

    scen = Scenario(scfg)
    store = SnapshotStore()
    stats, backup_secs = [], []
    for day in scen.run(rng, source):
        t0 = time.perf_counter()
        snap = store.add(day.day, day.files)
        X = features_batch(
            [c.data for c in day.changed],
            [c.file_type for c in day.changed],
            [c.index == 0 for c in day.changed],
        )
        stats.append(agg(detector.score_features(X)))
        posterior = naive_start_posterior(np.array(stats))
        ctx = RetentionContext(
            day=day.day,
            snapshot_days={s.id: s.day for s in store.snapshots.values()},
            budget=budget,
            daily_stat=np.array(stats),
            start_posterior=posterior,
        )
        store.retain_only(policy.decide(ctx))
        backup_secs.append(time.perf_counter() - t0)
        assert snap.day == day.day

    row = {
        **params,
        "rep": rep,
        "policy": policy.name,
        "detector": detector.name,
        "budget": budget,
        "benign_source": "synthetic",
        "damage_source": source.name,
        "runtime_per_backup_ms": 1000 * float(np.mean(backup_secs)),
        "retained_unique_bytes": store.unique_bytes,
        "start_estimate": int(np.argmax(posterior)),
        "start_estimate_error_days": abs(int(np.argmax(posterior)) - start),
    }
    row.update(recovery_metrics(store.days(), true_start=start, discovery_day=discovery_day))
    return row


def run_benchmark(cfg: dict) -> pd.DataFrame:
    seed = int(cfg["seed"])
    detector = make_detector(cfg.get("detector", {}))
    policies = make_policies(cfg.get("policies", ["keep_last_n"]))
    grid = expand_sweep(cfg.get("scenario", {}), cfg.get("sweep", {}))
    rows = []
    for params in grid:
        for rep in range(int(cfg.get("reps", 1))):
            for pol in policies:
                rows.append(
                    run_one(params, pol, detector, cfg["aggregator"], cfg["budget"], seed, rep)
                )
    df = pd.DataFrame(rows)
    out = resolve_path(cfg["output_dir"])
    out.mkdir(parents=True, exist_ok=True)
    df.to_csv(out / "results.csv", index=False)
    return df


def output_dir(cfg: dict) -> Path:
    return resolve_path(cfg["output_dir"])
