"""Numerical checks of Theorem 2 (docs/theory.md). Theorem 3: tests/test_retention_dp.py.
Proposition 1: tests/test_retention_policies.py."""

import numpy as np
import pytest

from slowburn.bench.theory_checks import lower_bound_K, min_ages_brute, toh_guarantee_table


@pytest.mark.parametrize("K", [4, 5, 6, 8])
def test_theorem_2a_tower_of_hanoi_guarantee_holds_everywhere(K):
    tab = toh_guarantee_table(K, n_days=600)
    assert len(tab) > 1000
    assert tab.clean.all()  # a clean snapshot is always held within the horizon
    assert tab.within_bound.all()  # W <= max(1, 3d)
    assert (tab[tab.d == 0].W == 1).all()


def test_theorem_2a_bound_is_attained_or_close():
    tab = toh_guarantee_table(6, n_days=600)
    pos = tab[tab.d >= 1]
    ratio = (pos.W / (3 * pos.d)).max()
    assert 0.5 < ratio <= 1.0  # the 3d bound is not loose by more than 2x


def test_theorem_2a_horizon_is_needed():
    """Beyond the horizon ToH can hold no clean snapshot (d = 2^(K-1) at a multiple)."""
    from slowburn.retention.base import TowerOfHanoi, replay

    K = 5
    kept = replay(TowerOfHanoi(), 200, K)
    misses = 0
    for t in range(64, 200):
        d = 2 ** (K - 1)
        s = t - d
        if not any(j < s for j in kept[t]):
            misses += 1
    assert misses > 0


@pytest.mark.parametrize("c", [2.0, 3.0, 4.0])
def test_theorem_2b_lower_bound_never_exceeds_exhaustive_minimum(c):
    for D in range(0, 13):
        k_min = min_ages_brute(D, c) + 1  # + today's snapshot
        assert k_min >= lower_bound_K(D, c) - 1e-9
        assert k_min <= np.ceil(lower_bound_K(D, c)) + 1  # and the bound is tight to within 1
