"""D31: fleet-level (pooled) benign flag-rate prior vs the per-machine warm-up prior."""

import numpy as np
import pytest

from slowburn.inference.daily import DailyObs
from slowburn.inference.obsmodels import BetaBinomialExceedance, fit_pooled_null_prior


def test_pooled_prior_recovers_fleet_rate_and_caps_concentration():
    rng = np.random.default_rng(0)
    n = np.full(40, 400)
    k = rng.binomial(n, 0.01)  # same rate on every machine: binomial spread only
    a, b = fit_pooled_null_prior(k, n)
    assert a / (a + b) == pytest.approx(0.01, abs=0.002)
    assert a + b > 1000  # tight: only sampling noise in the between-machine spread
    a0, b0 = fit_pooled_null_prior(np.zeros(10), np.full(10, 300))
    assert a0 == 0.5 and b0 > 1000  # zero rate stays a proper prior


def test_pooled_prior_widens_with_between_machine_spread():
    rng = np.random.default_rng(1)
    n = np.full(40, 400)
    k = rng.binomial(n, rng.beta(2, 98, size=40))
    a, b = fit_pooled_null_prior(k, n)
    assert 20 < a + b < 1000


def _obs(k, n):
    return [
        DailyObs(day=i, k=ki, n=ni, value=ki / max(ni, 1))
        for i, (ki, ni) in enumerate(zip(k, n, strict=True))
    ]


def test_pooled_prior_narrows_the_null_grid():
    warm = _obs([0] * 13, [4] * 13)  # ~50 files, no flags
    per_machine = BetaBinomialExceedance().fit_null(warm)
    pooled = BetaBinomialExceedance(null_prior=(0.5, 10000.5)).fit_null(warm)
    assert per_machine.null_rates.max() > 0.03  # 50 files cannot rule out a few % benign flags
    assert pooled.null_rates.max() <= 0.0011  # clipped at min_rate: the fleet knows better
