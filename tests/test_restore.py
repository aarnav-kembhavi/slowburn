"""C: selective restore with a lower posterior quantile; residual damaged files."""

import numpy as np
import pytest

from slowburn.store.restore import (
    FileHistory,
    lower_quantile_start,
    selective_restore,
    snapshots_scanned,
    version_day_at,
)


def _post(t, mass):
    """Posterior over days 0..t plus not-started, from a {day: mass} dict."""
    p = np.zeros(t + 2)
    for d, m in mass.items():
        p[d] = m
    p[-1] = 1 - p.sum()
    return p


def test_lower_quantile_start_ignores_not_started():
    post = _post(20, {10: 0.1, 12: 0.2, 15: 0.1})
    assert lower_quantile_start(post, 0.2) == 10  # P(<=10 | started) = 0.25
    assert lower_quantile_start(post, 0.5) == 12
    assert lower_quantile_start(post, 0.9) == 15


def test_version_day_at():
    h = FileHistory((0, 5, 9), None)
    assert [version_day_at(h, d) for d in (0, 4, 5, 8, 9, 20)] == [0, 0, 5, 5, 9, 9]


HIST = {
    "a": FileHistory((0, 3, 12), damaged_day=12),  # damaged on day 12
    "b": FileHistory((0, 14), damaged_day=14),  # damaged on day 14
    "c": FileHistory((0, 11, 13), None),  # benign edits after the start
    "d": FileHistory((0, 2), None),  # untouched since day 2
}


def test_correct_estimate_restores_everything_clean():
    post = _post(20, {12: 1.0})
    r = selective_restore([5, 10, 11, 20], post, 20, HIST, true_start=12, quantile=0.1)
    assert r["estimated_start"] == 12 and r["restore_point"] == 11
    assert r["residual_damaged_files"] == 0 and r["clean_recovery"] == 1
    assert r["files_restored"] == 3  # a, b, c changed on or after day 12
    assert r["work_lost_selective_file_hours"] == 1 * 24  # c's day-13 edit is discarded
    assert r["work_lost_whole_system_hours"] == (20 - 11) * 24
    assert r["start_gap_days"] == 0


def test_late_estimate_leaves_residual_damage():
    post = _post(20, {14: 1.0})  # estimate two days late
    r = selective_restore([5, 10, 13, 20], post, 20, HIST, true_start=12, quantile=0.1)
    assert r["restore_point"] == 13  # dirty: a was damaged on day 12
    assert r["restore_point_clean"] == 0
    assert r["residual_damaged_files"] == 1  # a is not restored (last change day 12 < 14)
    assert r["clean_recovery"] == 0
    assert r["work_lost_whole_system_hours"] == 20 * 24  # unrecovered -> worst case


def test_no_snapshot_before_estimate_falls_back_to_oldest():
    post = _post(20, {12: 1.0})
    r = selective_restore([15, 20], post, 20, HIST, true_start=12, quantile=0.1)
    assert r["restore_point"] == 15 and r["clean_recovery"] == 0


def test_snapshots_scanned():
    assert snapshots_scanned([5, 10, 13, 20], true_start=12) == 3  # 20, 13 dirty; 10 clean
    assert snapshots_scanned([5, 10, 13, 20], true_start=12, first_choice=10) == 1
    assert snapshots_scanned([13, 20], true_start=12) is None
    with pytest.raises(TypeError):
        snapshots_scanned()


# ---- D29: restore-time verification ------------------------------------------------------

from slowburn.store.restore import p_clean, verified_restore  # noqa: E402

VHIST = {
    "a": FileHistory((0, 3, 12), damaged_day=12, flagged_days=frozenset({12})),  # detected
    "b": FileHistory((0, 14), damaged_day=14),  # damaged on 14, MISSED by the detector
    "c": FileHistory((0, 11, 13), None),
    "d": FileHistory((0, 2), None),
}


def test_p_clean():
    post = _post(20, {10: 0.25, 12: 0.25})
    assert p_clean(post, [9, 10, 11, 12, 20]).tolist() == [1.0, 0.5, 0.5, 0.0, 0.0]


def test_verification_skips_snapshot_with_flagged_version():
    post = _post(20, {12: 0.5, 14: 0.5})  # diffuse
    r = verified_restore([5, 10, 13, 20], post, 20, VHIST, true_start=12, gate=0.0)
    # 20 and 13 hold a's flagged day-12 version -> rejected; 10 verifies
    assert r["restore_point"] == 10 and r["verified"] == 1 and r["snapshots_scanned"] == 3
    assert r["clean_recovery"] == 1 and r["restore_matches_dp_model"] == 1


def test_missed_damage_passes_verification():
    hist = {**VHIST, "a": FileHistory((0, 3), None)}  # only b's missed damage remains
    post = _post(20, {14: 1.0})
    r = verified_restore([5, 10, 15, 20], post, 20, hist, true_start=14, gate=0.0)
    assert r["restore_point"] == 20 and r["clean_recovery"] == 0  # deterministic miss
    assert r["restore_matches_dp_model"] == 0  # the DP assumed reliable verification


def test_gate_skips_unlikely_clean_snapshots_and_fallback():
    hist = {**VHIST, "a": FileHistory((0, 3), None)}
    post = _post(20, {8: 0.5, 14: 0.5})
    r = verified_restore([5, 10, 15, 20], post, 20, hist, true_start=14, gate=0.9)
    assert r["gate_candidates"] == 1 and r["restore_point"] == 5  # only day 5 has P_clean 1
    assert r["gate_day"] == 7 and r["restore_p_clean"] == 1.0  # logged gate: days <= 7 admitted
    r = verified_restore([10, 15, 20], post, 20, hist, true_start=14, gate=0.9)
    assert r["gate_candidates"] == 0 and r["verified"] == 0 and r["restore_point"] == 10
    assert r["gate_day"] == 7 and r["restore_p_clean"] == 0.5  # fallback restores outside gate
    r = verified_restore([5, 10, 15, 20], post, 20, hist, true_start=14, gate=0.5)
    assert r["gate_day"] == 13 and r["gate_candidates"] == 2  # 5 and 10 are <= 13


def test_benign_flag_causes_false_rejection():
    hist = {"c": FileHistory((0, 11, 13), None, flagged_days=frozenset({13}))}
    post = _post(20, {15: 1.0})
    r = verified_restore([5, 12, 14, 20], post, 20, hist, true_start=15, gate=0.5, scan_eps=0.0)
    # 14 holds c's flagged day-13 version (benign validation failure) -> rejected; 12 verifies
    assert r["snapshots_scanned"] == 2 and r["restore_point"] == 12
    assert r["restore_point_clean"] == 1 and r["restore_matches_dp_model"] == 0


# ---- D60: method v4 walk-back ------------------------------------------------------------

from slowburn.store.restore import deep_damage, walkback_restore  # noqa: E402

NULL0 = (0.5, 1e4 + 0.5)  # fleet prior of a benign rate of ~0


def _whist():
    # attack starts on day 8; damage on 8 (detected) and 9 (missed); a hard-bound posterior
    # placing the start on 16 admits the damaged snapshot 15 and its scan window misses both
    return {
        "a": FileHistory((0, 8), damaged_day=8, flagged_days=frozenset({8})),
        "b": FileHistory((0, 9), damaged_day=9),
        "c": FileHistory((0, 3, 16), None),
        "d": FileHistory((0, 2), None),
    }


def test_deep_damage_window_and_benign_rate():
    h = _whist()
    assert deep_damage(h, 15, 5, NULL0, 0.05) == (True, 1, 2)  # a@8, b@9 scanned; c@3 is <= 5
    assert deep_damage(h, 5, 2, NULL0, 0.05) == (False, 0, 1)
    # a high fleet benign rate explains one flag out of two: no damage found
    assert deep_damage(h, 15, 5, (50.0, 50.0), 0.05)[0] is False


def test_walkback_rescues_beyond_the_bound():
    post = _post(20, {16: 1.0})
    h = _whist()
    v2 = verified_restore([5, 15, 20], post, 20, h, true_start=8, gate=0.8)
    assert v2["restore_point"] == 15 and v2["verified"] == 1 and v2["clean_recovery"] == 0
    r = walkback_restore([5, 15, 20], post, 20, h, true_start=8, gate=0.8, null_prior=NULL0)
    assert r["walkback_from"] == 15 and r["walkback_steps"] == 1 and r["restore_point"] == 5
    assert r["clean_recovery"] == 1 and r["residual_damaged_files"] == 0
    assert r["work_lost_whole_system_hours"] == 15 * 24


def test_walkback_is_v2_when_nothing_is_flagged():
    post = _post(20, {16: 1.0})
    h = {**_whist(), "a": FileHistory((0, 8), damaged_day=8)}  # q = 0: nothing detected
    v2 = verified_restore([5, 15, 20], post, 20, h, true_start=8, gate=0.8)
    r = walkback_restore([5, 15, 20], post, 20, h, true_start=8, gate=0.8, null_prior=NULL0)
    assert r["walkback_steps"] == 0 and r["files_scanned"] == v2["files_scanned"] + 2
    assert {k: r[k] for k in v2 if k != "files_scanned"} == {
        k: v for k, v in v2.items() if k != "files_scanned"
    }


def test_walkback_stops_at_oldest_kept():
    post = _post(20, {16: 1.0})
    h = {**_whist(), "e": FileHistory((0, 10), damaged_day=10, flagged_days=frozenset({10}))}
    r = walkback_restore([9, 15, 20], post, 20, h, true_start=8, gate=0.8, null_prior=NULL0)
    # 15 holds e's flagged day-10 version; 9 is the oldest kept, so the walk ends there although
    # it holds a's day-8 damage (written before the oldest kept snapshot: nothing can undo it)
    assert r["restore_point"] == 9 and r["walkback_steps"] == 1 and r["clean_recovery"] == 0
    r = walkback_restore([12, 15, 20], post, 20, _whist(), true_start=8, gate=0.8,
                         null_prior=NULL0)  # fmt: skip
    assert r["walkback_steps"] == 0  # all damage predates the oldest kept snapshot
