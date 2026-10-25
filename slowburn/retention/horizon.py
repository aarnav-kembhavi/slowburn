"""Equal-horizon fixed schedules (D68): Tower of Hanoi with base b and GFS with tier counts,
configured per budget K so that their guaranteed horizon reaches the assumed delay bound M.

Horizon H(policy, K): the largest D such that for every delay d <= D and every discovery day t
with attack start s = t - d >= max(1, 2d), the held set at t contains a day j < s (the G1 /
Theorem 2(a) check, maximised over D).
"""

from __future__ import annotations

import itertools
from dataclasses import replace
from functools import cache

import numpy as np

from slowburn.retention.base import (
    RetentionContext,
    TowerOfHanoi,
    _newest,
    backbone_size,
    replay,  # fmt: skip
)

N_DAYS, D_MAX = 800, 400
GFS_BLOCKS = (7, 28, 91)


def _v(n: int, b: int) -> int:
    k = 0
    while n % b == 0:
        n //= b
        k += 1
    return k


class TowerOfHanoiBase:
    """Tower of Hanoi rotation in base ``b``: day n = t + 1 goes to level min(v_b(n), K - 1);
    each level keeps its newest day, plus today. b = 2 is ``TowerOfHanoi``."""

    def __init__(self, base: int):
        self.base = int(base)
        self.name = f"toh_b{self.base}"

    def decide(self, ctx: RetentionContext) -> set[int]:
        K = ctx.budget
        latest: dict[int, tuple[int, int]] = {}
        for sid, d in ctx.snapshot_days.items():
            level = min(_v(d + 1, self.base), K - 1)
            if level not in latest or d > latest[level][1]:
                latest[level] = (sid, d)
        keep = {sid for sid, _ in latest.values()} | {_newest(ctx)}
        if len(keep) > K:
            keep = set(sorted(keep, key=ctx.snapshot_days.get, reverse=True)[:K])
        return keep


class GFSTiers:
    """GFS with explicit tier counts: the newest ``daily`` snapshots, then the newest snapshot of
    each of the most recent completed blocks of 7, 28 and 91 days (``GFS`` block semantics)."""

    def __init__(self, daily: int, weekly: int, monthly: int, quarterly: int):
        self.counts = (int(daily), int(weekly), int(monthly), int(quarterly))
        self.name = "gfs_{}d{}w{}m{}q".format(*self.counts)

    def decide(self, ctx: RetentionContext) -> set[int]:
        daily = self.counts[0]
        by_day = sorted(ctx.snapshot_days.items(), key=lambda kv: kv[1], reverse=True)
        keep: list[int] = [sid for sid, _ in by_day[:daily]]
        for size, count in zip(GFS_BLOCKS, self.counts[1:], strict=True):
            current, seen, added = ctx.day // size, set(), 0
            for sid, d in by_day:
                if added >= count:
                    break
                block = d // size
                if block >= current or block in seen:
                    continue
                seen.add(block)
                if sid not in keep:
                    keep.append(sid)
                    added += 1
        return set(keep[: ctx.budget])


def horizon(policy, K: int, n_days: int = N_DAYS, d_max: int = D_MAX) -> int:
    """H(policy, K) by replay (-1 if even d = 0 fails)."""
    kept = replay(policy, n_days, K)
    t = np.arange(n_days)
    gap = t - np.array([min(h) for h in kept])  # (t, d) is covered iff d < gap[t]
    for d in range(d_max + 1):
        lo = d + max(1, 2 * d)  # t = s + d with s >= max(1, 2d)
        if lo < n_days and (gap[lo:] <= d).any():
            return d - 1
    return d_max


def gfs_configs(K: int):
    """All (n1, n7, n28, n91) with n1 >= 1 summing to K, finest first (lexicographic max)."""
    out = [c for c in itertools.product(range(1, K + 1), range(K + 1), range(K + 1),
                                        range(K + 1)) if sum(c) == K]  # fmt: skip
    return sorted(out, reverse=True)


@cache
def choose(kind: str, K: int, M: int) -> tuple | None:
    """D68 rule: the configuration of ``kind`` ("toh" or "gfs") with H >= M at budget K, or None
    if none exists. toh: the smallest base b in 2..64; gfs: the finest tier counts."""
    if kind == "toh":
        for b in range(2, 65):
            if horizon(TowerOfHanoiBase(b), K) >= M:
                return (b,)
        return None
    if kind == "gfs":
        for c in gfs_configs(K):
            if horizon(GFSTiers(*c), K) >= M:
                return c
        return None
    raise ValueError(f"unknown kind {kind!r}")


class EqualHorizon:
    """``toh_eqh`` / ``gfs_eqh``: at budget K, the D68 configuration with horizon >= M."""

    def __init__(self, kind: str, M: int):
        self.kind, self.M = kind, int(M)
        self.name = f"{kind}_eqh"
        self._pol: dict[int, object] = {}

    def supports(self, K: int) -> bool:
        return choose(self.kind, K, self.M) is not None

    def decide(self, ctx: RetentionContext) -> set[int]:
        K = ctx.budget
        if K not in self._pol:
            cfg = choose(self.kind, K, self.M)
            if cfg is None:
                raise ValueError(f"{self.name}: no configuration with H >= {self.M} at K = {K}")
            self._pol[K] = TowerOfHanoiBase(*cfg) if self.kind == "toh" else GFSTiers(*cfg)
        return self._pol[K].decide(ctx)


@cache
def held_age(kind: str, K: int, M: int, n_days: int = 400, burn: int = 200) -> int | None:
    """D79: the largest snapshot age the D68 ``kind`` eqh configuration holds at budget K in a
    steady-state replay (days burn..n_days-1), or None if no configuration exists."""
    cfg = choose(kind, K, M)
    if cfg is None:
        return None
    pol = TowerOfHanoiBase(*cfg) if kind == "toh" else GFSTiers(*cfg)
    return max(t - min(h) for t, h in enumerate(replay(pol, n_days, K)) if t >= burn)


class AgeCapped:
    """D79 ``slowburn_age_gfs`` / ``slowburn_age_toh``: the SlowBurn DP (``inner``) with held
    snapshots older than the matching eqh baseline's held age deleted before each decision; the
    inner policy's Tower of Hanoi backbone set is exempt. Nothing else changes."""

    def __init__(self, inner, kind: str, M: int, name: str):
        self.inner, self.kind, self.M, self.name = inner, kind, int(M), name

    def supports(self, K: int) -> bool:
        return held_age(self.kind, K, self.M) is not None

    def decide(self, ctx: RetentionContext) -> set[int]:
        A = held_age(self.kind, ctx.budget, self.M)
        R = backbone_size(ctx.budget, self.inner.backbone)
        bb = TowerOfHanoi().decide(replace(ctx, budget=R)) if R >= 1 else set()
        days = {s: d for s, d in ctx.snapshot_days.items() if ctx.day - d <= A or s in bb}
        return self.inner.decide(replace(ctx, snapshot_days=days))
