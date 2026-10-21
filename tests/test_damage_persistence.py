"""D62: a damaged file stays damaged until restored (docs/threat_model.md), and with a perfect
detector (q = 1) a snapshot holding a damaged version must never verify clean."""

import numpy as np
import pytest

from slowburn.bench.retention_experiment import RetentionTask, simulate
from slowburn.store.restore import FileHistory, verified_restore, version_day_at
from slowburn.utils.config import load_config


def _still_damaged(histories, j):
    """Files whose version held in snapshot j is damaged (D62: damage persists)."""
    return [f for f, h in histories.items()
            if h.damaged_day is not None and version_day_at(h, j) >= h.damaged_day]  # fmt: skip


def test_simulated_damage_persists_and_is_flagged_at_q1():
    cfg = load_config("configs/retention_smoke.yaml")
    p = {**cfg["scenario"], "detect_prob": 1.0, "benign_invalid_rate": 0.0}
    tr = simulate(cfg, RetentionTask("dev", "eval", p, 0))
    damaged = {f: h for f, h in tr.histories.items() if h.damaged_day is not None}
    assert damaged
    for h in damaged.values():
        assert max(h.change_days) == h.damaged_day  # never edited or overwritten afterwards
        assert h.damaged_day in h.flagged_days  # q = 1: the damaged version is flagged
        for j in range(h.damaged_day, tr.n_days):
            assert version_day_at(h, j) == h.damaged_day  # held, damaged, by every later snapshot


def _post(T, mass):
    p = np.zeros(T + 2)
    for d, m in mass.items():
        p[d] = m
    return p


@pytest.mark.xfail(strict=True, reason="D62: the D29 restore (skip) never scans versions "
                   "older than L; D64a verify_snap passes (tests below)")  # fmt: skip
def test_q1_verification_never_passes_a_still_damaged_snapshot():
    # true start day 8; a hard-bound posterior puts the start on day 16 (delay under-estimated)
    hist = {
        "a": FileHistory((0, 8), damaged_day=8, flagged_days=frozenset({8})),
        "b": FileHistory((0, 9), damaged_day=9, flagged_days=frozenset({9})),
        "c": FileHistory((0, 3, 16), None),
    }
    r = verified_restore([5, 15, 20], _post(20, {16: 1.0}), 20, hist, true_start=8, gate=0.8)
    assert not (r["verified"] and _still_damaged(hist, r["restore_point"]))


def test_d62_diagnostic_options():
    hist = {
        "a": FileHistory((0, 8), damaged_day=8, flagged_days=frozenset({8})),
        "b": FileHistory((0, 9), damaged_day=9, flagged_days=frozenset({9})),
        "c": FileHistory((0, 3, 16), None),
    }
    post = _post(20, {16: 1.0})
    skip = verified_restore([5, 15, 20], post, 20, hist, true_start=8, gate=0.8)
    assert skip["restore_point"] == 15 and skip["clean_recovery"] == 0
    # select: same point, damaged files restored to their (still damaged) versions in 15
    sel = verified_restore([5, 15, 20], post, 20, hist, 8, 0.8, old_flags="select")
    assert sel["restore_point"] == 15 and sel["clean_recovery"] == 0
    # verify: 15 is rejected, the oldest kept (5) is clean and every flagged file is restored
    ver = verified_restore([5, 15, 20], post, 20, hist, 8, 0.8, old_flags="verify")
    assert ver["restore_point"] == 5 and ver["clean_recovery"] == 1
    # clean point already, damage before L: select alone restores the flagged files
    sel = verified_restore([5, 20], _post(20, {16: 1.0}), 20, hist, 8, 0.8, old_flags="select")
    skip = verified_restore([5, 20], _post(20, {16: 1.0}), 20, hist, 8, 0.8)
    assert sel["restore_point"] == skip["restore_point"] == 5
    assert skip["clean_recovery"] == 0 and sel["clean_recovery"] == 1


# ---- D64a: restore-time verification of every version, shared per-version draws -----------

D64_HIST = {
    "a": FileHistory((0, 8), damaged_day=8, flagged_days=frozenset({8})),
    "b": FileHistory((0, 9), damaged_day=9, flagged_days=frozenset({9})),
    "c": FileHistory((0, 3, 16), None),
}


def test_q1_verify_snap_never_passes_a_still_damaged_snapshot():
    """Item 3b under D64a: with q = 1 (every damaged version flagged when written) no snapshot
    holding a damaged version verifies clean, whatever the kept set."""
    for kept in ([5, 15, 20], [9, 15, 20], [12, 15, 20], [5, 20], [15, 20]):
        r = verified_restore(kept, _post(20, {16: 1.0}), 20, D64_HIST, 8, 0.8,
                             old_flags="verify_snap")  # fmt: skip
        assert not (r["verified"] and _still_damaged(D64_HIST, r["restore_point"]))


def test_verify_snap_uses_the_write_time_draw():
    """One draw per version: a damaged version missed when written stays missed (q < 1)."""
    hist = {**D64_HIST, "a": FileHistory((0, 8), damaged_day=8)}  # a missed at write time
    r = verified_restore([5, 15, 20], _post(20, {16: 1.0}), 20, hist, 8, 0.8,
                         old_flags="verify_snap")  # fmt: skip
    assert r["restore_point"] == 5  # 15 is still rejected through b's flag
    hist = {**hist, "b": FileHistory((0, 9), damaged_day=9)}  # both missed: 15 passes
    r = verified_restore([5, 15, 20], _post(20, {16: 1.0}), 20, hist, 8, 0.8,
                         old_flags="verify_snap")  # fmt: skip
    assert r["restore_point"] == 15 and r["verified"] == 1 and r["clean_recovery"] == 0


def test_select_rollback_of_a_wrongly_flagged_clean_file_counts_as_work_lost():
    """D64a (3): a clean file with a false-positive version older than L is rolled back by
    select; the selective metric counts its lost edit, the whole-system metric already does."""
    hist = {"a": FileHistory((0, 17), damaged_day=17, flagged_days=frozenset({17})),
            "c": FileHistory((0, 3, 10), None, flagged_days=frozenset({10})),
            "d": FileHistory((0, 2, 12), None)}  # fmt: skip
    skip = verified_restore([5, 20], _post(20, {16: 1.0}), 20, hist, 8, 0.8)
    sel = verified_restore([5, 20], _post(20, {16: 1.0}), 20, hist, 8, 0.8, old_flags="select")
    assert skip["files_restored"] == 1 and sel["files_restored"] == 2
    assert skip["work_lost_selective_file_hours"] == 0
    assert sel["work_lost_selective_file_hours"] == 24
    assert skip["work_lost_whole_system_hours"] == sel["work_lost_whole_system_hours"] == 360


def test_verify_snap_end_to_end_q1_under_estimated_delay():
    """Simulated machines, hard bound 14 days, true delays up to 60, q = 1: a restore that
    verifies is always from a snapshot before the true start."""
    from slowburn.bench.retention_experiment import RetentionTask, evaluate_trace, simulate

    cfg = load_config("configs/retention_smoke.yaml")
    cfg = {**cfg, "discovery_delay": [7, 30, 60], "budgets": [4, 8]}
    hp = {**cfg["hp"], "assumed_discovery": {"kind": "uniform", "max_days": 14},
          "old_flags": "verify_snap", "restore_rule": "verified"}  # fmt: skip
    n = 0
    for rep in range(3):
        p = {**cfg["scenario"], "detect_prob": 1.0, "benign_invalid_rate": 0.05}
        task = RetentionTask("dev", "eval", p, rep)
        for r in evaluate_trace(cfg, task, simulate(cfg, task), hp, ("prior_only", "gfs")):
            n += 1
            assert not (r["verified"] and r["restore_point"] >= r["true_start"])
    assert n
