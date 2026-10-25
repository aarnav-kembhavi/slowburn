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


def test_d79_held_age_and_age_capped_slowburn():
    import numpy as np

    from slowburn.retention.base import PosteriorDP
    from slowburn.retention.dp import discovery_survival, retention_posterior

    assert hz.held_age("gfs", 12, 60) == 104
    assert (hz.held_age("toh", 8, 60), hz.held_age("toh", 12, 60)) == (127, 255)
    assert hz.held_age("gfs", 8, 60) is None
    S = discovery_survival("uniform", 400)

    def extra(day):  # near-flat prior over a long window: the DP wants to reach far back
        h = 0.001
        post = np.r_[h * (1 - h) ** np.arange(day + 1), 0.0]
        post[-1] = 1 - post[:-1].sum()
        pi = retention_posterior(post, day, S)
        return {"start_posterior": post, "retention_pi": pi, "prior_retention_pi": pi}

    inner = PosteriorDP(90.0, gate=0.8, backbone=0.25)
    capped = hz.AgeCapped(PosteriorDP(90.0, gate=0.8, backbone=0.25), "toh", 60, "x")
    assert capped.supports(8) and not capped.supports(6)
    free = replay(inner, 300, 8, extra)
    hist = replay(capped, 300, 8, extra)
    assert max(t - min(h) for t, h in enumerate(free)) > 127  # the cap binds here
    assert all(t - min(h) <= 127 for t, h in enumerate(hist))
    assert all(len(h) <= 8 and t in h for t, h in enumerate(hist))
