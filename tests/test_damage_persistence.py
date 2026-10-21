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
                   "older than L; D64 verify_snap passes (tests below)")  # fmt: skip
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


# ---- D64: faithful restore-time verification ("verify_snap") -------------------------------

from slowburn.store.restore import VersionScanner  # noqa: E402

D64_HIST = {
    "a": FileHistory((0, 8), damaged_day=8, flagged_days=frozenset()),  # missed when written
    "b": FileHistory((0, 9), damaged_day=9, flagged_days=frozenset({9})),
    "c": FileHistory((0, 3, 16), None, flagged_days=frozenset({3})),  # stale benign day flag
}


@pytest.mark.parametrize("b", [0.0, 0.05, 0.5])
def test_q1_verify_snap_never_passes_a_still_damaged_snapshot(b):
    """Item 3b under D64: with q = 1 no snapshot holding a damaged version verifies clean."""
    for kept in ([5, 15, 20], [9, 15, 20], [12, 15, 20], [5, 20]):
        sc = VersionScanner((1, "t"), 1.0, b)
        r = verified_restore(kept, _post(20, {16: 1.0}), 20, D64_HIST, 8, 0.8,
                             old_flags="verify_snap", scanner=sc)  # fmt: skip
        assert not (r["verified"] and _still_damaged(D64_HIST, r["restore_point"]))


def test_verify_snap_scanner_is_per_version_fresh_and_paired():
    h = D64_HIST["c"]
    hi, lo = VersionScanner((7, "m"), 1.0, 0.9), VersionScanner((7, "m"), 0.5, 0.3)
    assert hi("c", h, 3) == hi("c", h, 3)  # same version, same answer
    # write-time flags are ignored: a's damaged version was missed when written, found now
    assert VersionScanner((7, "m"), 1.0, 0.0)("a", D64_HIST["a"], 8)
    assert not VersionScanner((7, "m"), 0.0, 0.0)("c", h, 3)  # stale day flag not reused
    # one draw per version shared across rates: flags at lower rates are a subset
    for v in range(40):
        assert not lo("c", h, v) or hi("c", h, v)
    with pytest.raises(ValueError, match="scanner"):
        verified_restore([5, 20], _post(20, {16: 1.0}), 20, D64_HIST, 8, 0.8,
                         old_flags="verify_snap")  # fmt: skip


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
