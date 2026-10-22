"""Paired statistics for comparing SlowBurn with each baseline (agreed protocol).

* clean recovery (binary, paired by seed): exact McNemar test on the discordant pairs, plus the
  risk difference with a paired bootstrap 95% CI;
* work lost (continuous, paired): Wilcoxon signed-rank test plus the matched-pairs rank-biserial
  correlation as effect size; unrecovered runs are scored with the penalty value by the caller;
* Holm step-down correction across the baselines of one comparison family.
"""

from __future__ import annotations

import numpy as np
from scipy import stats


def mcnemar_exact(a: np.ndarray, b: np.ndarray) -> dict:
    """Exact two-sided McNemar test for paired binary outcomes ``a`` (method) and ``b`` (baseline).

    Under H0 the discordant pairs split 50/50: p = P(Binom(n01 + n10, 1/2) as extreme).
    """
    a, b = np.asarray(a, bool), np.asarray(b, bool)
    if a.shape != b.shape:
        raise ValueError("paired arrays must have the same shape")
    n10 = int(np.sum(a & ~b))  # method succeeds, baseline fails
    n01 = int(np.sum(~a & b))
    n = n10 + n01
    p = 1.0 if n == 0 else float(stats.binomtest(n10, n, 0.5, alternative="two-sided").pvalue)
    return {"n_method_only": n10, "n_baseline_only": n01, "p_value": p}


def risk_difference(a: np.ndarray, b: np.ndarray, n_boot: int = 2000, ci: float = 0.95,
                    rng: np.random.Generator | None = None) -> dict:  # fmt: skip
    """mean(a) - mean(b) for paired binary outcomes, with a paired (resample-pairs) bootstrap CI."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    rng = rng if rng is not None else np.random.default_rng(0)
    d = a - b
    idx = rng.integers(0, len(d), size=(n_boot, len(d)))
    boots = d[idx].mean(axis=1)
    q = (1 - ci) / 2
    return {"risk_difference": float(d.mean()), "ci_low": float(np.quantile(boots, q)),
            "ci_high": float(np.quantile(boots, 1 - q))}  # fmt: skip


def wilcoxon_rank_biserial(x: np.ndarray, y: np.ndarray) -> dict:
    """Wilcoxon signed-rank test of paired ``x`` (method) vs ``y`` (baseline), two-sided, plus
    the matched-pairs rank-biserial correlation r = (W+ - W-) / (W+ + W-) over non-zero
    differences (r > 0: method larger). Zero differences are dropped (Wilcoxon's convention)."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    d = x - y
    nz = d[d != 0]
    if len(nz) == 0:
        return {"n_nonzero": 0, "p_value": 1.0, "rank_biserial": 0.0, "median_difference": 0.0}
    ranks = stats.rankdata(np.abs(nz))
    w_pos, w_neg = ranks[nz > 0].sum(), ranks[nz < 0].sum()
    p = float(stats.wilcoxon(nz, zero_method="wilcox", alternative="two-sided").pvalue)
    return {"n_nonzero": int(len(nz)), "p_value": p,
            "rank_biserial": float((w_pos - w_neg) / (w_pos + w_neg)),
            "median_difference": float(np.median(d))}  # fmt: skip


def holm(p_values: list[float] | np.ndarray) -> np.ndarray:
    """Holm-adjusted p-values (step-down, monotone, capped at 1)."""
    p = np.asarray(p_values, float)
    m = len(p)
    order = np.argsort(p)
    adj = np.empty(m)
    running = 0.0
    for rank, i in enumerate(order):
        running = max(running, (m - rank) * p[i])
        adj[i] = min(1.0, running)
    return adj


def bootstrap_mean_ci(
    x: np.ndarray, n_boot: int = 2000, ci: float = 0.95, rng: np.random.Generator | None = None
) -> tuple[float, float, float]:
    """Mean with a percentile bootstrap CI (for per-policy rates and work lost)."""
    x = np.asarray(x, float)
    rng = rng if rng is not None else np.random.default_rng(0)
    boots = x[rng.integers(0, len(x), size=(n_boot, len(x)))].mean(axis=1)
    q = (1 - ci) / 2
    return float(x.mean()), float(np.quantile(boots, q)), float(np.quantile(boots, 1 - q))


def cluster_bootstrap_ratio(num, den, clusters, n_boot: int = 2000, ci: float = 0.95,
                            seed: int = 0) -> tuple[float, float, float]:  # fmt: skip
    """sum(num) / sum(den) with a percentile CI from resampling whole clusters (D64b): pass
    den = 1 for a mean, (new - old, old) for a relative change."""
    num, den = np.asarray(num, float), np.asarray(den, float)
    codes = np.unique(np.asarray(clusters), return_inverse=True)[1].ravel()
    n = int(codes.max()) + 1
    s_num, s_den = np.bincount(codes, num, n), np.bincount(codes, den, n)
    w = np.random.default_rng(seed).multinomial(n, np.full(n, 1 / n), size=n_boot)
    boots = (w @ s_num) / (w @ s_den)
    q = (1 - ci) / 2
    return (float(s_num.sum() / s_den.sum()), float(np.quantile(boots, q)),
            float(np.quantile(boots, 1 - q)))  # fmt: skip
