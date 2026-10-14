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
