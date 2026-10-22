"""D66 product retention rules and the point-in-time restore (docs/baselines.md)."""

import numpy as np
import pytest

from slowburn.retention import products as pr
from slowburn.store.restore import (
    FileHistory,
    clean_point_held,
    point_in_time_restore,
    verified_restore,
)


def test_keep_versions_time_window_is_point_in_time():
    v = [0, 10, 50, 95]  # versions; at td = 100, version 10 was current on days 10..49
    assert pr.keep_versions(100, v, superseded_within=30) == [50, 95]  # 10 superseded on day 50
    assert pr.keep_versions(100, v, superseded_within=51) == [10, 50, 95]
    assert pr.keep_versions(100, v, created_within=30) == [95]  # 50 was written 50 days ago


def test_keep_versions_count_limits():
    v = list(range(30))
    assert pr.keep_versions(29, v, max_versions=25) == list(range(5, 30))  # current included
    g = pr.keep_versions(149, list(range(150)), max_versions=100)  # Google count part
    assert g == list(range(50, 150))  # dropped once 100 newer versions exist
    assert pr.keep_versions(5, [3], max_versions=1) == [3]  # the current version always stays


def test_restic_documented_presets():
    k = pr.restic_dwmy(400)
    assert set(range(394, 401)) <= k  # 7 dailies
    assert len(k) <= 7 + 5 + 12 + 75 and len(k) >= 7 + 11  # weekly/monthly overlap the dailies
    months = {(pr._date(d).year, pr._date(d).month) for d in k}
    assert len(months) >= 12
    assert pr.SNAPSHOT["restic_keep_last_1"](10, {}) == {10}
    assert pr.SNAPSHOT["restic_keep_within_7d"](10, {}) == set(range(3, 11))
    w = pr.restic_within(400)
    assert min(w) >= 400 - 366 - 1  # nothing older than a year back (weeks/months within 1y)


def test_netapp_locks_the_day_before_the_first_flagged_damage():
    h = {"a": FileHistory((0, 20), 20, frozenset({20})), "b": FileHistory((0, 25), 25)}
    assert pr.netapp_arpai(40, h) == {40, 39, 19}
    blind = {"a": FileHistory((0, 20), 20), "b": FileHistory((0, 25), 25)}
    assert pr.netapp_arpai(40, blind) == {40, 39}


def _machine(seed, n_files=12, n_days=60, start=30, flag_damage=True):
    rng = np.random.default_rng(seed)
    hist = {}
    for i in range(n_files):
        k = rng.integers(0, 6)
        days = sorted({0, *rng.choice(np.arange(1, n_days), size=k, replace=False)})
        dmg = None
        if i < 4:
            dmg = int(rng.integers(start, n_days))
            days = sorted({d for d in days if d < dmg} | {dmg})
        flags = {d for d in days[1:] if rng.random() < 0.05}
        if dmg is not None and flag_damage:
            flags.add(dmg)
        hist[f"f{i}"] = FileHistory(tuple(days), dmg, frozenset(flags))
    return hist


@pytest.mark.parametrize("seed", range(8))
@pytest.mark.parametrize("gate", [0.0, 0.8])
def test_point_in_time_restore_equals_verify_snap_when_everything_is_kept(seed, gate):
    """With every version retained, every day is a snapshot: the per-file restore must agree
    with verify_snap over all daily snapshots exactly."""
    hist = _machine(seed, flag_damage=seed % 2 == 0)
    td, start = 59, 30
    post = np.random.default_rng(seed).dirichlet(np.ones(td + 2))
    retained = {f: [d for d in h.change_days if d <= td] for f, h in hist.items()}
    a = point_in_time_restore(retained, post, td, hist, start, gate)
    b = verified_restore(list(range(td + 1)), post, td, hist, start, gate, 0.001, "verify_snap")
    for k in (
        "restore_point",
        "clean_recovery",
        "residual_damaged_files",
        "work_lost_whole_system_hours",
        "work_lost_selective_file_hours",
        "verified",
    ):
        assert a[k] == b[k], k


def test_clean_point_held_detects_expired_clean_versions():
    h = {"a": FileHistory((0, 40), 40)}  # damaged on day 40; clean version 0 superseded on 40
    keep_all = {"a": [0, 40]}
    assert clean_point_held(keep_all, h, 40, 100) == 1
    expired = {"a": pr.keep_versions(100, [0, 40], superseded_within=30)}
    assert expired == {"a": [40]} and clean_point_held(expired, h, 40, 100) == 0
