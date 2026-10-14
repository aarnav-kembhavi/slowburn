"""Snapshot retention policies behind one interface.

Every policy sees the same ``RetentionContext`` once per day, after today's snapshot was added,
and returns the snapshot ids to keep (at most ``budget``; today's snapshot is always kept, as in
normal backup practice). Deleted snapshots never come back, so every policy is online.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

import numpy as np

from slowburn.retention.dp import dp_select


@dataclass(frozen=True)
class RetentionContext:
    day: int
    snapshot_days: dict[int, int]  # retained snapshot id -> day it was taken (incl. today's)
    budget: int  # max snapshots retained
    daily_stat: np.ndarray  # daily suspicion statistic for days 0..day (flagged-file fraction)
    # P(start = s) for s = 0..day plus a final entry for "not started yet" (evidence posterior)
    start_posterior: np.ndarray
    # the same conditioned on "not discovered yet", over days 0..day (see retention.dp)
    retention_pi: np.ndarray | None = None
    prior_retention_pi: np.ndarray | None = None  # prior-only version (no detector evidence)
    oracle_start: int | None = None  # ground truth; only the Oracle may read it
    extra: dict = field(default_factory=dict)


class RetentionPolicy(Protocol):
    name: str

    def decide(self, ctx: RetentionContext) -> set[int]:
        """Ids of snapshots to keep (at most ``ctx.budget``)."""
        ...


def _newest(ctx: RetentionContext) -> int:
    return max(ctx.snapshot_days, key=ctx.snapshot_days.get)


def _ids_for_days(ctx: RetentionContext, days) -> set[int]:
    wanted = set(days)
    return {sid for sid, d in ctx.snapshot_days.items() if d in wanted}


class KeepLastN:
    name = "keep_last_n"

    def decide(self, ctx: RetentionContext) -> set[int]:
        newest = sorted(ctx.snapshot_days, key=ctx.snapshot_days.get, reverse=True)
        return set(newest[: ctx.budget])


def gfs_split(budget: int) -> tuple[int, int, int]:
    """Deterministic (daily, weekly, monthly) split of a budget: half daily (rounded up), at
    least one monthly once budget >= 3, the rest weekly."""
    daily = max(1, -(-budget // 2))
    monthly = 1 if budget >= 3 else 0
    weekly = budget - daily - monthly
    return daily, weekly, monthly


class GFS:
    """Grandfather-father-son: the newest ``daily`` snapshots, plus the last snapshot of each of
    the ``weekly`` most recent COMPLETED weeks (7-day blocks) and of the ``monthly`` most recent
    completed months (28-day blocks), restricted to what is still held. A block whose last
    snapshot is already kept is covered without using a slot."""

    name = "gfs"

    def decide(self, ctx: RetentionContext) -> set[int]:
        daily, weekly, monthly = gfs_split(ctx.budget)
        by_day = sorted(ctx.snapshot_days.items(), key=lambda kv: kv[1], reverse=True)
        keep: list[int] = [sid for sid, _ in by_day[:daily]]

        def add_completed_blocks(size: int, count: int) -> None:
            current, seen, added = ctx.day // size, set(), 0
            for sid, d in by_day:  # newest first: the first one seen is the block's last
                block = d // size
                if added >= count:
                    break
                if block >= current or block in seen:
                    continue
                seen.add(block)
                if sid not in keep:
                    keep.append(sid)
                    added += 1

        add_completed_blocks(7, weekly)
        add_completed_blocks(28, monthly)
        return set(keep[: ctx.budget])


class TowerOfHanoi:
    """Tower of Hanoi rotation with ``budget`` media: day n (1-based) is written to medium
    min(trailing_zeros(n), budget - 1); each medium holds its latest snapshot."""

    name = "tower_of_hanoi"

    def decide(self, ctx: RetentionContext) -> set[int]:
        K = ctx.budget
        latest: dict[int, tuple[int, int]] = {}
        for sid, d in ctx.snapshot_days.items():
            n = d + 1
            level = min((n & -n).bit_length() - 1, K - 1)
            if level not in latest or d > latest[level][1]:
                latest[level] = (sid, d)
        keep = {sid for sid, _ in latest.values()}
        keep.add(_newest(ctx))
        if len(keep) > K:  # today's medium already counted unless it was overwritten
            keep = set(sorted(keep, key=ctx.snapshot_days.get, reverse=True)[:K])
        return keep


class ThresholdVault:
    """Keep-last-(K - v) plus a vault of v protected snapshots. When the daily statistic first
    exceeds ``threshold`` on a day, the newest held snapshot from before that day is moved into
    the vault (oldest vault entry evicted when full)."""

    name = "threshold_vault"

    def __init__(self, threshold: float, vault_size: int | None = None):
        self.threshold = threshold
        self.vault_size = vault_size
        self.vault: list[int] = []
        self._last_alarm = -1

    def decide(self, ctx: RetentionContext) -> set[int]:
        v = self.vault_size if self.vault_size is not None else max(1, ctx.budget // 4)
        v = min(v, ctx.budget - 1)
        self.vault = [sid for sid in self.vault if sid in ctx.snapshot_days]
        if ctx.daily_stat[-1] > self.threshold and ctx.day != self._last_alarm:
            self._last_alarm = ctx.day
            before = [(d, sid) for sid, d in ctx.snapshot_days.items() if d < ctx.day]
            if before:
                sid = max(before)[1]
                if sid not in self.vault:
                    self.vault.append(sid)
                    self.vault = self.vault[-v:] if v > 0 else []
        rolling = [sid for sid in sorted(ctx.snapshot_days, key=ctx.snapshot_days.get,
                                         reverse=True) if sid not in self.vault]  # fmt: skip
        return set(self.vault) | set(rolling[: ctx.budget - len(self.vault)])


class PosteriorDP:
    """The SlowBurn retention decision: exact per-decision DP on the start posterior conditioned
    on "not discovered yet". ``use_evidence=False`` is the prior-only (blind) policy."""

    def __init__(self, penalty: float | None, use_evidence: bool = True, name: str | None = None):
        self.penalty = penalty
        self.use_evidence = use_evidence
        self.name = name or ("slowburn" if use_evidence else "prior_only")

    def decide(self, ctx: RetentionContext) -> set[int]:
        pi = ctx.retention_pi if self.use_evidence else ctx.prior_retention_pi
        if pi is None:
            raise ValueError(f"{self.name} needs a retention posterior in the context")
        days = sorted(ctx.snapshot_days.values())
        keep_days = dp_select(days, pi, ctx.budget, self.penalty, keep_newest=True)
        return _ids_for_days(ctx, keep_days)


class Oracle:
    """Upper bound: knows the true start s; keeps the snapshot of day s - 1 forever once taken,
    plus the newest others."""

    name = "oracle"

    def decide(self, ctx: RetentionContext) -> set[int]:
        s = ctx.oracle_start
        newest_first = sorted(ctx.snapshot_days, key=ctx.snapshot_days.get, reverse=True)
        keep: list[int] = []
        if s is not None:
            pin = [sid for sid, d in ctx.snapshot_days.items() if d == s - 1]
            keep += pin
        for sid in newest_first:
            if len(keep) >= ctx.budget:
                break
            if sid not in keep:
                keep.append(sid)
        return set(keep)


def replay(policy: RetentionPolicy, n_days: int, budget: int, context_extra=None) -> list[set]:
    """Run a policy online over days 0..n_days-1 with snapshot id == day; returns the kept day
    set after each day. ``context_extra(day)`` may supply extra RetentionContext fields."""
    held: dict[int, int] = {}
    history = []
    for day in range(n_days):
        held[day] = day
        fields = context_extra(day) if context_extra else {}
        ctx = RetentionContext(day=day, snapshot_days=dict(held), budget=budget,
                               daily_stat=fields.pop("daily_stat", np.zeros(day + 1)),
                               start_posterior=fields.pop("start_posterior",
                                                          np.r_[np.zeros(day + 1), 1.0]),
                               **fields)  # fmt: skip
        keep = policy.decide(ctx)
        if len(keep) > budget or day not in keep or not keep <= set(held):
            raise AssertionError(f"{policy.name} violated the retention contract on day {day}")
        held = {sid: held[sid] for sid in keep}
        history.append(set(held.values()))
    return history
