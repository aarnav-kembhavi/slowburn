"""M0 placeholder start-day posterior; replaced by BOCPD / single-changepoint models in M2."""

from __future__ import annotations

import numpy as np


def naive_start_posterior(x: np.ndarray, warmup: int = 7) -> np.ndarray:
    """P(start = t) over t = 0..len(x) for a mean-shift, from standardised cumulative evidence.

    The final entry is the probability that no attack has started yet. Crude on purpose: it only
    exists so the pipeline runs end to end before M2.
    """
    x = np.asarray(x, dtype=float)
    n = len(x)
    if n == 0:
        return np.array([1.0])
    ref = x[: max(1, min(warmup, n))]
    mu, sd = ref.mean(), ref.std() + 1e-6
    z = (x - mu) / sd
    # log-evidence for "started at t" ~ sum of z after t minus a per-day drift penalty
    tail = np.concatenate([np.cumsum(z[::-1])[::-1], [0.0]])
    loglik = tail - 1.0 * (n - np.arange(n + 1))
    loglik[:warmup] = -np.inf  # warm-up days are assumed clean
    if not np.isfinite(loglik).any():
        loglik[-1] = 0.0
    p = np.exp(loglik - np.max(loglik))
    return p / p.sum()
