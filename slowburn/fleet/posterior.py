"""D73: per-machine start likelihoods and the hierarchical fleet start posterior.

Every machine keeps the D72 evidence model (Beta-Binomial exceedance, method v2 blind weight,
fleet-pooled benign null prior). ``MachineLik`` stores its prefix sums once, so the log
likelihood of "start = s" after the first T days is O(H G) per s. Only starts inside the
assumed discovery window matter for retention and restore (the assumed delay is at most M days,
so a start more than M days back has survival 0), which keeps the fleet coupling cheap.

Fleet model (OPEN_QUESTIONS D73): fleet start a with the frozen geometric prior; each machine is
infected with probability rho and starts at a + L, L ~ truncated Geometric(mean mu); rho and mu
are integrated over fixed grids. ``fleet_marginals`` returns, for every machine i and start s in
the window, log P(s_i = s, evidence, conditioning on a) up to the common normaliser, plus that
normaliser, so retention (survival of t - a) and restore (delay pmf of t - a) share one routine.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
from scipy.special import logsumexp

from slowburn.inference.changepoint import null_window
from slowburn.inference.obsmodels import BetaBinomialExceedance

RHO_GRID = (0.02, 0.05, 0.1, 0.2, 0.35, 0.5)  # D73, weights ~ Beta(1, 3) density
MU_GRID = (0.5, 2.0, 5.0, 10.0)  # D73, equal weights
MAX_LAG = 45  # D73: lateral delay truncation (days)


def _lse(x: np.ndarray, axis: int) -> np.ndarray:
    """logsumexp along ``axis`` (numpy only; scipy's call overhead dominated the fleet loop)."""
    m = np.max(x, axis=axis, keepdims=True)
    m = np.where(np.isfinite(m), m, 0.0)
    with np.errstate(divide="ignore"):
        return np.squeeze(m, axis=axis) + np.log(np.sum(np.exp(x - m), axis=axis))


def rho_log_weights(grid=RHO_GRID) -> np.ndarray:
    w = 3.0 * (1.0 - np.asarray(grid)) ** 2  # Beta(1, 3) density
    return np.log(w / w.sum())


def lag_log_pmf(mu: float, max_lag: int = MAX_LAG) -> np.ndarray:
    """Geometric on {0, 1, ...} with mean ``mu``, truncated to {0..max_lag}, renormalised."""
    p = 1.0 / (1.0 + mu)
    lp = np.log(p) + np.arange(max_lag + 1) * np.log1p(-p)
    return lp - logsumexp(lp)


class MachineLik:
    """Single-changepoint log likelihoods of one machine's daily observations (D72 model)."""

    def __init__(self, obs: Sequence, warmup: int, null_prior, blind_weight: float):
        self.warmup = warmup
        m = BetaBinomialExceedance(null_prior=tuple(null_prior), blind_weight=blind_weight)
        m.fit_null(null_window(obs, warmup))
        ll0, ll1, logw0, logw1 = m.loglik(obs)
        self.cum0 = np.vstack([np.zeros((1, ll0.shape[1])), np.cumsum(ll0, axis=0)])
        self.cum1 = np.concatenate([np.zeros((1, *ll1.shape[1:])), np.cumsum(ll1, axis=0)])
        self.logw0, self.logw1 = logw0, logw1

    def loglik(self, T: int, taus: np.ndarray) -> np.ndarray:
        """log L(tau) after the first T days for each tau in ``taus`` (tau = T: not started).
        Matches ``single_changepoint_posterior`` (prefix of benign, suffix of attack)."""
        taus = np.asarray(taus)
        if T <= self.warmup:
            return np.zeros(len(taus))  # posterior_path uses the prior alone here
        suffix = self.cum1[T][None] - self.cum1[taus]  # (n, H, G)
        inner = _lse(self.logw1[None, None, :] + suffix, axis=2)
        return _lse(self.logw0[None, :] + self.cum0[taus] + inner, axis=1)

    def ratio(self, T: int, days: np.ndarray) -> np.ndarray:
        """log L(s) - log L(not started) for start days ``days`` (all < T)."""
        ll = self.loglik(T, np.r_[days, T])
        return ll[:-1] - ll[-1]


def fleet_marginals(ratios: np.ndarray, days: np.ndarray, log_ca: np.ndarray, log_c_none: float,
                    rho_grid=RHO_GRID, mu_grid=MU_GRID, max_lag: int = MAX_LAG):  # fmt: skip
    """Hierarchical marginals.

    ``ratios`` (N, D): log L_i(s) - log L_i(not started) for the D consecutive start days
    ``days`` (the last day is today, t); starts after t are "not started" (ratio 0).
    ``log_ca`` (D,): log of the fleet-start weight of a = days[k] (prior times the discovery
    conditioning); fleet starts before days[0] must have weight 0. ``log_c_none``: log weight of
    "no fleet attack" (-inf at a restore).
    Returns (logP (N, D): log P(s_i = days[k], .), logZ): P(s_i = s | .) = exp(logP - logZ).
    """
    N, D = ratios.shape
    lrw = rho_log_weights(rho_grid)
    lmw = np.log(np.full(len(mu_grid), 1.0 / len(mu_grid)))
    pad = np.concatenate([ratios, np.zeros((N, max_lag))], axis=1)  # s > t: not started
    terms_z = [log_c_none]
    acc = np.full((N, D), -np.inf)
    for mu, lm in zip(mu_grid, lmw, strict=True):
        lg = lag_log_pmf(mu, max_lag)
        # conv[i, k] = log sum_L g(L) Lambda_i(days[k] + L)
        idx = np.arange(D)[:, None] + np.arange(max_lag + 1)[None, :]
        conv = _lse(pad[:, idx] + lg[None, None, :], axis=2)  # (N, D)
        for rho, lr in zip(rho_grid, lrw, strict=True):
            logM = np.logaddexp(np.log1p(-rho), np.log(rho) + conv)  # (N, D)
            ssum = logM.sum(axis=0)  # (D,)
            base = log_ca + ssum + lr + lm  # fleet start weight, every machine integrated
            terms_z.append(float(_lse(base, axis=0)))
            # machine i started on s = a + L: replace its factor by rho g(L) Lambda_i(s)
            b = base[None, :] - logM + np.log(rho)  # (N, D) over a
            lag = np.arange(D)[:, None] - np.arange(D)[None, :]  # s index - a index
            ok = (lag >= 0) & (lag <= max_lag)
            w = np.where(ok, lg[np.clip(lag, 0, max_lag)], -np.inf)  # (D_s, D_a)
            part = _lse(b[:, None, :] + w[None, :, :], axis=2) + ratios  # (N, D_s)
            acc = np.logaddexp(acc, part)
    return acc, float(logsumexp(terms_z))


def to_pi(logP_i: np.ndarray, logZ: float, days: np.ndarray, t: int) -> np.ndarray:
    """A machine's start distribution as a length t + 1 array over days 0..t (mass outside
    ``days`` is 0); sums to P(started by t) under the conditioning."""
    pi = np.zeros(t + 1)
    pi[days] = np.exp(logP_i - logZ)
    return pi
