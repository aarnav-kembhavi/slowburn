"""Retention policy interface and the keep-last-N baseline."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np


@dataclass(frozen=True)
class RetentionContext:
    day: int
    snapshot_days: dict[int, int]  # retained snapshot id -> day it was taken (incl. today's)
    budget: int  # max snapshots retained
    daily_stat: np.ndarray  # suspicion statistic for days 0..day
    # P(start = t) for t = 0..day, plus a final entry for "not started yet"
    start_posterior: np.ndarray


class RetentionPolicy(Protocol):
    name: str

    def decide(self, ctx: RetentionContext) -> set[int]:
        """Ids of snapshots to keep (at most ``ctx.budget``)."""
        ...


class KeepLastN:
    name = "keep_last_n"

    def decide(self, ctx: RetentionContext) -> set[int]:
        newest = sorted(ctx.snapshot_days, key=ctx.snapshot_days.get, reverse=True)
        return set(newest[: ctx.budget])
