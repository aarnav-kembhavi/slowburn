"""Bayesian Online Changepoint Detection (Adams & MacKay, 2007) with constant hazard.

Convention: before each observation the current segment may end (probability ``hazard``),
starting a new segment that the observation then belongs to. After T observations the returned
array ``rl`` has rl[r] = P(the current segment contains the last r observations), r = 1..T
(rl[0] = 0). This is exactly the posterior obtained by enumerating every segmentation with
independent changepoints of probability ``hazard`` and conjugate per-segment marginals (tested).
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
from scipy import stats
from scipy.special import logsumexp


class BetaBinomialConj:
    """Segment exceedance rate q ~ Beta(a0, b0); observations x = (k, n)."""

    def __init__(self, a0: float, b0: float):
        self.a0, self.b0 = a0, b0

    def init(self):
        return np.array([self.a0]), np.array([self.b0])

    def logpred(self, x, st) -> np.ndarray:
        k, n = x
        a, b = st
        return stats.betabinom.logpmf(k, n, a, b)

    def update(self, st, x):
        k, n = x
        a, b = st
        return a + k, b + (n - k)

    def prepend_prior(self, st):
        a, b = st
        return np.r_[self.a0, a], np.r_[self.b0, b]


class NormalInvGammaConj:
    """Unknown segment mean and variance, Normal-Inverse-Gamma prior; Student-t predictive."""

    def __init__(self, mu0: float = 0.0, kappa0: float = 1.0, alpha0: float = 2.0,
                 beta0: float = 1.0):  # fmt: skip
        self.p0 = (mu0, kappa0, alpha0, beta0)

    def init(self):
        return tuple(np.array([v], dtype=float) for v in self.p0)

    def logpred(self, x, st) -> np.ndarray:
        mu, kappa, alpha, beta = st
        scale = np.sqrt(beta * (kappa + 1) / (alpha * kappa))
        return stats.t.logpdf(x, df=2 * alpha, loc=mu, scale=scale)

    def update(self, st, x):
        mu, kappa, alpha, beta = st
        return (
            (kappa * mu + x) / (kappa + 1),
            kappa + 1,
            alpha + 0.5,
            beta + kappa * (x - mu) ** 2 / (2 * (kappa + 1)),
        )

    def prepend_prior(self, st):
        return tuple(np.r_[p, s] for p, s in zip(self.p0, st, strict=True))


def bocpd_run_length(xs: Sequence, model, hazard: float) -> np.ndarray:
    """Run-length posterior after all observations; see module docstring for the convention."""
    T = len(xs)
    if T == 0:
        return np.array([1.0])
    log_h, log_1h = np.log(hazard), np.log1p(-hazard)
    log_r = np.array([0.0])  # before x_0: a segment with 0 observations, probability 1
    st = model.init()
    for t, x in enumerate(xs):
        if t > 0:
            log_r = np.r_[logsumexp(log_r) + log_h, log_r + log_1h]
            st = model.prepend_prior(st)
        log_r = log_r + model.logpred(x, st)
        log_r -= logsumexp(log_r)
        st = model.update(st, x)
    # entry i now holds segments with i + 1 observations
    return np.r_[0.0, np.exp(log_r)]
