"""Observation models for the single-changepoint posterior.

Each model is fitted on clean warm-up days and returns, for a series of daily observations:
    ll0[t, h]      log p(x_t | benign, null-parameter grid point h)
    ll1[t, h, g]   log p(x_t | attack active, null point h, effect grid point g)
    logw0[h], logw1[g]   log prior weights (each sums to 1)

Benign parameters are *not* plugged in: warm-up is short (two weeks), and a plug-in null that
is slightly too low makes every later day look mildly suspicious. The null grid carries the
warm-up uncertainty, and the pre-attack days after warm-up keep refining it.

Attacks are slow and intermittent: on many attack days no new file is damaged. The attack-regime
likelihood is therefore a per-day mixture  pi * f_effect + (1 - pi) * f_benign  with the activity
rate pi on the effect grid too. Effects are upward only (an attack never lowers suspicion).
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
from scipy import stats

from slowburn.inference.daily import DailyObs

ACTIVITY_GRID = (0.25, 0.5, 0.75, 1.0)


def fit_betabinom_rho(k: np.ndarray, n: np.ndarray) -> tuple[float, float]:
    """Method-of-moments mean and intra-day correlation rho of a Beta-Binomial.

    Var(k_i) = n_i m (1-m) (1 + (n_i - 1) rho). rho > 0 captures chunks of one file being
    flagged together (overdispersion relative to independent chunks).
    """
    k, n = np.asarray(k, float), np.asarray(n, float)
    keep = n > 0
    k, n = k[keep], n[keep]
    if n.sum() == 0:
        return 0.0, 1e-3
    m = k.sum() / n.sum()
    v = m * (1 - m)
    den = (n * (n - 1) * v).sum()
    rho = ((k - n * m) ** 2 - n * v).sum() / den if den > 0 else 0.0
    return float(m), float(np.clip(rho, 1e-3, 0.5))


def _mixture(ll_effect: np.ndarray, ll0: np.ndarray, pis: Sequence[float]) -> np.ndarray:
    """(T, E) effect log-likelihoods -> (T, E*P) mixture log-likelihoods over activity rates."""
    cols = []
    for pi in pis:
        if pi >= 1.0:
            cols.append(ll_effect)
        else:
            cols.append(np.logaddexp(np.log(pi) + ll_effect, np.log1p(-pi) + ll0[:, None]))
    return np.concatenate(cols, axis=1)


def _uniform_logw(n: int) -> np.ndarray:
    return np.full(n, -np.log(n))


def _quantile_points(n: int) -> np.ndarray:
    return (np.arange(n) + 0.5) / n


class BetaBinomialExceedance:
    """Daily exceedance counts k_t out of n_t changed chunks (statistic ``exceed``)."""

    # overdispersion cannot be estimated from two weeks of warm-up; broad log-uniform grid
    RHO_GRID = (0.002, 0.006, 0.02, 0.06, 0.15)

    def __init__(self, n_effect: int = 6, activity: Sequence[float] = ACTIVITY_GRID,
                 n_null: int = 9, min_rate: float = 1e-3):  # fmt: skip
        self.n_effect = n_effect
        self.activity = tuple(activity)
        self.n_null = n_null
        self.min_rate = min_rate

    def fit_null(self, warmup: Sequence[DailyObs]) -> BetaBinomialExceedance:
        k = np.array([o.k for o in warmup], float)
        n = np.array([o.n for o in warmup], float)
        m, rho = fit_betabinom_rho(k, n)
        self.rho = rho
        # warm-up posterior of the benign rate, with the sample size shrunk by the design effect
        n_bar = float(n[n > 0].mean()) if (n > 0).any() else 1.0
        deff = 1.0 + (n_bar - 1.0) * rho
        a = k.sum() / deff + 0.5
        b = (n.sum() - k.sum()) / deff + 0.5
        self.null_rates = np.clip(
            stats.beta.ppf(_quantile_points(self.n_null), a, b), self.min_rate, 0.5
        )
        self.null_rate = float(np.clip(m, self.min_rate, 0.5))
        self.effects = np.geomspace(0.01, 0.95, self.n_effect)  # fraction of the way to 1
        # joint null grid: (benign rate, overdispersion)
        self.null_grid = [(q, r) for q in self.null_rates for r in self.RHO_GRID]
        return self

    @staticmethod
    def _logpmf(k, n, rate, rho) -> np.ndarray:
        c = (1 - rho) / rho
        return stats.betabinom.logpmf(k, n, rate * c, (1 - rate) * c)

    def loglik(self, obs: Sequence[DailyObs]):
        k = np.array([o.k for o in obs])
        n = np.array([o.n for o in obs])
        ll0 = np.column_stack([self._logpmf(k, n, q, r) for q, r in self.null_grid])
        ll1 = np.stack(
            [
                _mixture(
                    np.column_stack([self._logpmf(k, n, q + (1 - q) * u, r) for u in self.effects]),
                    ll0[:, h],
                    self.activity,
                )
                for h, (q, r) in enumerate(self.null_grid)
            ],
            axis=1,
        )
        return ll0, ll1, _uniform_logw(ll0.shape[1]), _uniform_logw(ll1.shape[2])


class GaussianWeekday:
    """Score-based daily statistic (e.g. trimmed mean) with weekday baselines.

    x_t ~ N(mu_{weekday(t)}, tau^2 / n_t): the benign mean differs by weekday (the mix of file
    types edited changes over the week) and the noise shrinks with the number of changed chunks.
    Predictive variance adds the standard error of the weekday mean; tau carries a scaled-chi2
    uncertainty grid with the residual degrees of freedom.
    """

    def __init__(self, n_effect: int = 6, activity: Sequence[float] = ACTIVITY_GRID,
                 n_null: int = 7, min_per_weekday: int = 2):  # fmt: skip
        self.n_effect = n_effect
        self.activity = tuple(activity)
        self.n_null = n_null
        self.min_per_weekday = min_per_weekday

    def fit_null(self, warmup: Sequence[DailyObs]) -> GaussianWeekday:
        obs = [o for o in warmup if o.n > 0]
        x = np.array([o.value for o in obs])
        n = np.array([o.n for o in obs], float)
        wd = np.array([o.weekday for o in obs], int)
        pooled = float(np.average(x, weights=n)) if len(x) else 0.0
        self.mu = np.full(7, pooled)
        self.mu_weight = np.full(7, max(n.sum(), 1.0))  # chunks behind each weekday mean
        n_params = 1
        for d in range(7):
            sel = wd == d
            if sel.sum() >= self.min_per_weekday:
                self.mu[d] = np.average(x[sel], weights=n[sel])
                self.mu_weight[d] = n[sel].sum()
                n_params += 1
        dof = max(len(x) - n_params, 1)
        resid2 = (n * (x - self.mu[wd]) ** 2).sum() if len(x) else 0.0
        self.tau = float(np.sqrt(max(resid2 / dof, 1e-10)))
        self.dof = dof
        # scaled-inverse-chi2 posterior of tau^2 -> quantile grid of tau
        q = _quantile_points(self.n_null)
        self.taus = self.tau * np.sqrt(dof / stats.chi2.ppf(1 - q, dof))
        n_typ = float(np.median(n)) if len(n) else 1.0
        self.shift_units = np.geomspace(0.5, 30, self.n_effect) / np.sqrt(n_typ)
        return self

    def loglik(self, obs: Sequence[DailyObs]):
        x = np.array([o.value for o in obs])
        n = np.array([max(o.n, 1) for o in obs], float)
        has = np.array([o.n > 0 for o in obs])
        w = np.array([o.weekday for o in obs])
        mu = self.mu[w]
        ll0_cols, ll1_blocks = [], []
        for tau in self.taus:
            sd = tau * np.sqrt(1.0 / n + 1.0 / self.mu_weight[w])
            l0 = np.where(has, stats.norm.logpdf(x, mu, sd), 0.0)
            eff = np.column_stack(
                [np.where(has, stats.norm.logpdf(x, mu + s * tau, sd), 0.0)
                 for s in self.shift_units]
            )  # fmt: skip
            ll0_cols.append(l0)
            ll1_blocks.append(_mixture(eff, l0, self.activity))
        ll0 = np.column_stack(ll0_cols)
        ll1 = np.stack(ll1_blocks, axis=1)
        return ll0, ll1, _uniform_logw(ll0.shape[1]), _uniform_logw(ll1.shape[2])

    def standardise(self, obs: Sequence[DailyObs]) -> np.ndarray:
        """Residuals z_t = (x_t - mu_wd) / sd_t, ~N(0, 1) on benign days (for BOCPD)."""
        w = np.array([o.weekday for o in obs])
        n = np.array([max(o.n, 1) for o in obs], float)
        x = np.array([o.value for o in obs])
        return (x - self.mu[w]) / (self.tau * np.sqrt(1.0 / n + 1.0 / self.mu_weight[w]))


OBS_MODELS = {"betabinom": BetaBinomialExceedance, "gaussian_weekday": GaussianWeekday}


def make_obs_model(name: str, **params):
    try:
        return OBS_MODELS[name](**params)
    except KeyError:
        raise ValueError(
            f"unknown observation model {name!r}; known: {sorted(OBS_MODELS)}"
        ) from None
