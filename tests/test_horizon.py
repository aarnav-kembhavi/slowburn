"""D68 equal-horizon schedules and the D69 oracle restore."""

import pytest

from slowburn.retention import horizon as hz
from slowburn.retention.base import GFS, TowerOfHanoi, replay
from slowburn.store.restore import FileHistory, oracle_restore


@pytest.mark.parametrize("K", [4, 6, 8])
def test_base2_horizon_is_theorem_2a(K):
    assert hz.horizon(hz.TowerOfHanoiBase(2), K) == 2 ** (K - 2) - 1
    assert hz.horizon(TowerOfHanoi(), K) == 2 ** (K - 2) - 1  # same rotation as the baseline


def test_gfs_tiers_reproduce_current_gfs_and_respect_the_contract():
    for K in (4, 6, 8, 12):
        a = replay(GFS(), 300, K)
        d = -(-K // 2)
        m = 1 if K >= 3 else 0
        b = replay(hz.GFSTiers(d, K - d - m, m, 0), 300, K)  # gfs_split as explicit tiers
        assert a == b
    replay(hz.GFSTiers(1, 1, 1, 1), 400, 4)  # contract (<= K, today kept) checked by replay


def test_equal_horizon_choice_and_infeasible_cells():
    assert hz.choose("toh", 8, 60) == (2,)
    assert hz.choose("toh", 4, 7) is None  # base 2 covers 3 days at K = 4; no base does better
    pol = hz.EqualHorizon("gfs", 60)
    assert not pol.supports(6) and pol.supports(12)
    assert hz.horizon(hz.GFSTiers(*hz.choose("gfs", 12, 60)), 12) >= 60


def test_oracle_restore_uses_newest_clean_kept_snapshot():
    h = {"a": FileHistory((0, 5, 12), 12), "b": FileHistory((0, 8), None)}
    r = oracle_restore([3, 7, 10, 14], 14, h, true_start=12)
    assert r["restore_point"] == 10 and r["clean_recovery"] == 1
    r = oracle_restore([12, 14], 14, h, true_start=12)  # nothing clean kept
    assert r["restore_point"] == 12 and r["clean_recovery"] == 0
