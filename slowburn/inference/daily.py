"""Daily aggregation: one machine-day of per-chunk scores -> one observation ``DailyObs``.

Aggregators are registered by name (pluggable from config). Every observation carries the number
of changed chunks ``n`` so that observation models can normalise by churn volume, and the weekday
so they can model the benign weekly cycle.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
from scipy import stats


@dataclass(frozen=True)
class DayScores:
    day: int
    probs: np.ndarray  # calibrated P(damaged) per changed chunk
    pvals: np.ndarray  # conformal p-values per changed chunk (type-conditional by default)
    file_ids: tuple[str, ...] = ()  # file of each changed chunk (needed by file-level stats)


@dataclass(frozen=True)
class DailyObs:
    day: int
    value: float  # the daily statistic
    k: int  # exceedance count (0 for score-based aggregators)
    n: int  # number of changed units that day (chunks, or files for file-level statistics)

    @property
    def weekday(self) -> int:
        return self.day % 7


Aggregator = Callable[[DayScores], DailyObs]
AGGREGATORS: dict[str, Callable[..., Aggregator]] = {}


def register(name: str):
    def deco(factory):
        AGGREGATORS[name] = factory
        return factory

    return deco


def _score_agg(fn) -> Aggregator:
    def agg(d: DayScores) -> DailyObs:
        n = len(d.probs)
        return DailyObs(d.day, float(fn(d.probs)) if n else 0.0, 0, n)

    return agg


@register("mean")
def mean() -> Aggregator:
    return _score_agg(np.mean)


@register("trimmed_mean")
def trimmed_mean(proportion: float = 0.1) -> Aggregator:
    return _score_agg(lambda s: stats.trim_mean(s, proportion))


@register("frac_above")
def frac_above(reference: float = 0.5) -> Aggregator:
    """Fraction of changed chunks whose calibrated probability exceeds a low reference level."""
    return _score_agg(lambda s: np.mean(s > reference))


@register("exceed")
def exceed(alpha: float = 0.05) -> Aggregator:
    """Count of changed chunks with conformal p <= alpha; benign rate is ~alpha by construction."""

    def agg(d: DayScores) -> DailyObs:
        n = len(d.pvals)
        k = int(np.sum(d.pvals <= alpha))
        return DailyObs(d.day, k / n if n else 0.0, k, n)

    return agg


def file_pvalues(d: DayScores) -> dict[str, float]:
    """Per changed file: the minimum p-value over its changed chunks.

    No multiplicity correction: conformal p-values cannot go below 1/(n_cal + 1) (~0.003 with
    our per-type calibration sets), so a Bonferroni factor of n_chunks would make any file with
    more than a few chunks unflaggable. The resulting benign file-flag rate is not alpha; it is
    estimated from warm-up days by the observation model (decision D9), so alpha only has to be
    a sensible operating point."""
    if len(d.file_ids) != len(d.pvals):
        raise ValueError("file-level statistics need DayScores.file_ids for every chunk")
    out: dict[str, float] = {}
    for fid, p in zip(d.file_ids, d.pvals, strict=True):
        out[fid] = min(out.get(fid, 1.0), float(p))
    return out


@register("file_exceed")
def file_exceed(alpha: float = 0.01) -> Aggregator:
    """Flagged files out of changed files (binomial normalisation): heavy benign churn raises n,
    not the expected rate, so it does not look like an attack."""

    def agg(d: DayScores) -> DailyObs:
        fp = file_pvalues(d)
        n = len(fp)
        k = sum(p <= alpha for p in fp.values())
        return DailyObs(d.day, k / n if n else 0.0, int(k), n)

    return agg


def make_aggregator(name: str, **params) -> Aggregator:
    try:
        return AGGREGATORS[name](**params)
    except KeyError:
        raise ValueError(f"unknown aggregator {name!r}; known: {sorted(AGGREGATORS)}") from None
