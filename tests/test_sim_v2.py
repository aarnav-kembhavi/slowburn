"""Simulator v2: generating start worlds (D45) and byte budgets (D46)."""

import numpy as np
import pandas as pd
import pytest

from slowburn.bench.retention_experiment import (
    RetentionTask,
    build_tasks,
    evaluate_trace,
    simulate,
    task_cache_key,
    task_seed_key,
)
from slowburn.retention.base import KeepLastN, RetentionContext
from slowburn.retention.bytes import ByteIndex, enforce_byte_budget
from slowburn.sim.worlds import draw_start, world_start
from slowburn.utils.config import load_config
from slowburn.utils.seed import child_rng

WORLDS = [
    {"name": "uniform", "kind": "uniform", "window": [28, 280]},
    {"name": "early", "kind": "beta", "a": 1, "b": 3, "window": [28, 280]},
    {"name": "late", "kind": "beta", "a": 3, "b": 1, "window": [28, 280]},
    {"name": "bursty", "kind": "clusters", "centres": [60, 150, 230], "sd": 3,
     "window": [28, 280]},
]  # fmt: skip


@pytest.fixture(scope="module")
def cfg():
    return load_config("configs/retention_smoke.yaml")


@pytest.fixture(scope="module")
def trace(cfg):
    return simulate(cfg, RetentionTask("dev", "eval", {**cfg["scenario"]}, 0))


def test_byte_index_matches_set_union(trace):
    idx = ByteIndex(trace.snapshots, trace.chunk_size)
    rng = np.random.default_rng(0)
    n = trace.n_days
    for _ in range(200):
        days = sorted(rng.choice(n, size=int(rng.integers(1, min(n, 15))), replace=False))
        union = frozenset().union(*(trace.snapshots[d] for d in days))
        assert idx.unique_bytes(days) == len(union) * trace.chunk_size
    assert idx.size(3) == len(trace.snapshots[3]) * trace.chunk_size


def test_byte_index_exact_union_when_a_chunk_reappears():
    snaps = [frozenset({b"a"}), frozenset({b"b"}), frozenset({b"a", b"c"})]
    idx = ByteIndex(snaps, 2)
    assert idx.bits is not None
    assert idx.unique_bytes([0, 2]) == 4  # the interval formula would give 6
    assert idx.unique_bytes([0, 1, 2]) == 6
    assert idx.size(2) == 4 and idx.unique_bytes([]) == 0


def test_enforce_byte_budget_uses_the_policy_rule(trace):
    idx = ByteIndex(trace.snapshots, trace.chunk_size)
    t = 20
    held = {d: d for d in range(t + 1)}
    budget = idx.unique_bytes(range(t - 4, t + 1))  # exactly the newest five
    pol = KeepLastN()

    def decide(h, k):
        ctx = RetentionContext(day=t, snapshot_days=h, budget=k, daily_stat=np.zeros(t + 1),
                               start_posterior=np.r_[np.zeros(t + 1), 1.0])  # fmt: skip
        return pol.decide(ctx)

    out = enforce_byte_budget(held, budget, idx, decide)
    assert sorted(out.values()) == list(range(t - 4, t + 1))
    assert enforce_byte_budget({t: t}, 0, idx, decide) == {t: t}  # today is always kept


def test_worlds_draw_inside_window_and_differ():
    rng = child_rng(0, "w")
    draws = {w["name"]: np.array([draw_start(w, rng) for _ in range(4000)]) for w in WORLDS}
    for d in draws.values():
        assert d.min() >= 28 and d.max() <= 280
    assert draws["early"].mean() < draws["uniform"].mean() < draws["late"].mean()
    near = np.min(np.abs(draws["bursty"][:, None] - np.array([60, 150, 230])), axis=1)
    assert np.quantile(near, 0.99) <= 12
    assert world_start(1, "dev", WORLDS[0], 3) == world_start(1, "dev", WORLDS[0], 3)


def test_world_tasks_are_paired_across_evidence(cfg):
    c = {**cfg, "worlds": WORLDS[:2], "reps": 3, "vault_calib_machines": 2,
         "policies": ["prior_only", "gfs"]}  # fmt: skip
    tasks = build_tasks(c, "dev", log=lambda *a: None)
    assert all("amoeba_weights" not in t.params for t in tasks)
    by = {}
    for t in tasks:
        by.setdefault((t.params["world"], t.rep), set()).add(t.params["attack_start"])
    assert all(len(v) == 1 for v in by.values())  # same start in every evidence cell
    seed = int(c["seed"])
    a = next(t for t in tasks if t.params["world"] == "uniform")
    b = RetentionTask(a.split, a.family, {**a.params, "world": "early"}, a.rep)
    assert task_seed_key(seed, a) == task_seed_key(seed, b)  # same start -> same machine
    assert task_cache_key(seed, a) != task_cache_key(seed, b)  # but rows labelled apart


def test_byte_budget_rows_fit_and_count_rows_unchanged(cfg, trace):
    params = {**cfg["scenario"], "detect_prob": 0.5, "benign_invalid_rate": 0.01,
              "null_prior": (0.5, 100.5)}  # fmt: skip
    task = RetentionTask("dev", "eval", params, 0)
    pols = ("slowburn", "prior_only", "gfs", "tower_of_hanoi", "keep_last_n", "oracle")
    base = pd.DataFrame(evaluate_trace(cfg, task, trace, cfg["hp"], pols))
    task_b = RetentionTask("dev", "eval", {**params, "byte_budget_mult": {4: 1.15, 8: 1.4}}, 0)
    both = pd.DataFrame(evaluate_trace(cfg, task_b, trace, cfg["hp"], pols))
    cnt = both[both.budget_kind == "count"].reset_index(drop=True)
    cols = ["policy", "budget", "discovery_delay", "restore_point", "clean_recovery",
            "retained_unique_bytes", "gate_day"]  # fmt: skip
    assert cnt[cols].equals(base[cols])
    byt = both[both.budget_kind == "bytes"]
    assert set(byt.budget) == {4, 8} and len(byt) == len(pols) * 2 * len(cfg["discovery_delay"])
    fits = (byt.retained_unique_bytes <= byt.budget_bytes) | (byt.snapshots_retained == 1)
    assert fits.all()


def test_world_summary_and_worst_case_timing():
    from slowburn.bench.retention_experiment import world_summary, worst_case_timing

    rows = [{"world": "u", "budget_kind": "count", "budget": 4, "detect_prob": 0.0,
             "policy": "gfs", "attack_start": s, "discovery_delay": d,
             "clean_recovery": r, "work_lost_whole_system_hours": w, "work_lost_ideal_hours": 1,
             "clean_snapshot_retained": 1}
            for s, d, r, w in ((10, 7, 1, 5), (10, 7, 1, 7), (11, 7, 0, 9),
                               (11, 14, 1, 3))]  # fmt: skip
    df = pd.DataFrame(rows)
    ws = world_summary(df).iloc[0]
    assert ws.recovery == 0.75 and ws.work_lost_h == 6.0 and ws.rows == 4
    wc = worst_case_timing(df).iloc[0]
    assert wc.recovery_worst == 0 and wc.worst_start == 11 and wc.worst_delay == 7
    assert wc.work_lost_worst == 9 and wc.timing_cells == 3
    assert wc.recovery_avg == pytest.approx(2 / 3)
