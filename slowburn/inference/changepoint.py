"""Posterior over the attack start day.

Output convention shared by all models: for a series of T daily observations, an array ``post``
of length T + 1 where post[d] = P(attack started on day d) for d < T and post[T] = P(no attack
has started yet). Days inside the warm-up window are assumed clean (post[d] = 0 there): the
benign model is fitted on them.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
from scipy.special import logsumexp

from slowburn.inference.bocpd import BetaBinomialConj, NormalInvGammaConj, bocpd_run_length
from slowburn.inference.daily import DailyObs
from slowburn.inference.obsmodels import BetaBinomialExceedance, GaussianWeekday


def null_window(obs: Sequence[DailyObs], warmup: int) -> Sequence[DailyObs]:
    """Warm-up days used to fit the benign model, excluding day 0.

    Day 0 is the initial full backup: every chunk is "changed" (n is ~20x a normal day) and its
    file-type mix is the whole disk rather than the daily churn, so it is not a typical benign day.
    """
    return obs[1:warmup] if warmup > 1 else obs[:warmup]


def geometric_log_prior(T: int, hazard: float, warmup: int = 0) -> np.ndarray:
    """log P(start = d) for d < T, and log P(not started) in the last entry.

    Constant daily hazard after warm-up: P(start = d) = h (1 - h)^(d - warmup).
    """
    lp = np.full(T + 1, -np.inf)
    w = min(warmup, T)
    d = np.arange(w, T)
    lp[w:T] = np.log(hazard) + (d - w) * np.log1p(-hazard)
    lp[T] = (T - w) * np.log1p(-hazard)
    return lp


def uniform_log_prior(T: int, warmup: int = 0) -> np.ndarray:
    """Flat prior over post-warm-up start days and "not started" (the "suspicion only" ablation)."""
    lp = np.full(T + 1, -np.inf)
    w = min(warmup, T)
    lp[w:] = -np.log(T + 1 - w)
    return lp


def single_changepoint_posterior(
    ll0: np.ndarray,
    ll1: np.ndarray,
    logw1: np.ndarray,
    log_prior: np.ndarray,
    logw0: np.ndarray | None = None,
) -> np.ndarray:
    """Exact posterior for one benign -> attack switch.

    1-D form: ll0 (T,), ll1 (T, G).  Null-grid form: ll0 (T, H), ll1 (T, H, G), logw0 (H,).
    log L(tau) = log sum_h w0_h [ prod_{t<tau} p0(x_t|h) * sum_g w1_g prod_{t>=tau} p1(x_t|h,g) ]
    computed in O(T * H * G) with prefix / suffix sums.
    """
    if ll0.ndim == 1:
        ll0, ll1, logw0 = ll0[:, None], ll1[:, None, :], np.zeros(1)
    T = ll0.shape[0]
    prefix0 = np.vstack([np.zeros((1, ll0.shape[1])), np.cumsum(ll0, axis=0)])  # (T+1, H)
    suffix1 = np.concatenate(
        [np.cumsum(ll1[::-1], axis=0)[::-1], np.zeros((1, *ll1.shape[1:]))], axis=0
    )  # (T+1, H, G)
    inner = logsumexp(logw1[None, None, :] + suffix1, axis=2)  # (T+1, H)
    log_like = logsumexp(logw0[None, :] + prefix0 + inner, axis=1)
    log_post = log_prior + log_like
    if not np.isfinite(log_post).any():
        out = np.zeros(T + 1)
        out[T] = 1.0
        return out
    return np.exp(log_post - logsumexp(log_post))


class SingleChangepoint:
    """Exact single-changepoint model (the default candidate)."""

    name = "single_cp"

    def __init__(self, obs_model, hazard: float, warmup: int, use_data: bool = True,
                 prior: str = "geometric"):  # fmt: skip
        if prior not in ("geometric", "uniform"):
            raise ValueError("prior must be 'geometric' or 'uniform'")
        self.obs_model = obs_model
        self.hazard = hazard
        self.warmup = warmup
        self.use_data = use_data  # False = "prior only" ablation (no detector evidence)
        self.prior = prior  # "uniform" = "suspicion only" ablation (no timing prior)

    def log_prior(self, T: int) -> np.ndarray:
        if self.prior == "uniform":
            return uniform_log_prior(T, self.warmup)
        return geometric_log_prior(T, self.hazard, self.warmup)

    def posterior(self, obs: Sequence[DailyObs]) -> np.ndarray:
        T = len(obs)
        lp = self.log_prior(T)
        if not self.use_data or T <= self.warmup:
            return np.exp(lp - logsumexp(lp))
        self.obs_model.fit_null(null_window(obs, self.warmup))
        ll0, ll1, logw0, logw1 = self.obs_model.loglik(obs)
        return single_changepoint_posterior(ll0, ll1, logw1, lp, logw0)


class BOCPDStart:
    """BOCPD run-length posterior mapped to the start-day convention.

    The most recent changepoint is read as the attack start. BOCPD allows any number of
    changepoints, in either direction, which is its known weakness here.
    """

    name = "bocpd"

    def __init__(self, statistic: str, hazard: float, warmup: int):
        if statistic not in ("exceed", "gaussian"):
            raise ValueError("statistic must be 'exceed' or 'gaussian'")
        self.statistic = statistic
        self.hazard = hazard
        self.warmup = warmup

    def posterior(self, obs: Sequence[DailyObs]) -> np.ndarray:
        T = len(obs)
        out = np.zeros(T + 1)
        if T <= self.warmup:
            out[T] = 1.0
            return out
        warm = null_window(obs, self.warmup)
        if self.statistic == "exceed":
            null = BetaBinomialExceedance().fit_null(warm)
            conc = (1 - null.rho) / null.rho
            model = BetaBinomialConj(null.null_rate * conc, (1 - null.null_rate) * conc)
            xs = [(o.k, o.n) for o in obs]
        else:
            null = GaussianWeekday().fit_null(warm)
            model = NormalInvGammaConj()
            xs = list(null.standardise(obs))
        rl = bocpd_run_length(xs, model, self.hazard)  # rl[r], r = 1..T
        starts = T - np.arange(1, T + 1)  # start day for run length r
        mass = rl[1:]
        late = starts >= self.warmup
        out[starts[late]] = mass[late]
        out[T] = mass[~late].sum()  # segment began inside warm-up: no attack yet
        return out / out.sum()


# named variants used in experiment configs; the last two are the agreed ablations
START_MODELS = ("single_cp", "bocpd", "single_cp_uniform", "prior_only")


def make_start_model(kind: str, statistic: str, obs_model_name: str, hazard: float,
                     warmup: int):  # fmt: skip
    """``statistic`` is the daily-statistic name (only used for logging by callers)."""
    from slowburn.inference.obsmodels import make_obs_model

    if kind == "single_cp":
        return SingleChangepoint(make_obs_model(obs_model_name), hazard, warmup)
    if kind == "single_cp_uniform":  # ablation: suspicion only, no timing prior
        return SingleChangepoint(make_obs_model(obs_model_name), hazard, warmup, prior="uniform")
    if kind == "prior_only":  # ablation: timing prior only, no detector evidence
        return SingleChangepoint(make_obs_model(obs_model_name), hazard, warmup, use_data=False)
    if kind == "bocpd":
        return BOCPDStart("exceed" if obs_model_name == "betabinom" else "gaussian", hazard, warmup)
    raise ValueError(f"unknown inference model {kind!r}; known: {START_MODELS}")
