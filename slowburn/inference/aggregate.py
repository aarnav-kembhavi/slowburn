"""Daily aggregators: many per-chunk scores for one machine-day -> one suspicion statistic.

Aggregators are registered by name so experiments select them from config.
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np
from scipy import stats

Aggregator = Callable[[np.ndarray], float]
AGGREGATORS: dict[str, Callable[..., Aggregator]] = {}


def register(name: str):
    def deco(factory):
        AGGREGATORS[name] = factory
        return factory

    return deco


@register("mean")
def mean() -> Aggregator:
    return lambda s: float(np.mean(s)) if len(s) else 0.0


@register("trimmed_mean")
def trimmed_mean(proportion: float = 0.1) -> Aggregator:
    return lambda s: float(stats.trim_mean(s, proportion)) if len(s) else 0.0


@register("frac_above")
def frac_above(reference: float = 0.5) -> Aggregator:
    """Fraction of the day's changed chunks scoring above a low reference level."""
    return lambda s: float(np.mean(s > reference)) if len(s) else 0.0


def make_aggregator(name: str, **params) -> Aggregator:
    try:
        return AGGREGATORS[name](**params)
    except KeyError:
        raise ValueError(f"unknown aggregator {name!r}; known: {sorted(AGGREGATORS)}") from None
