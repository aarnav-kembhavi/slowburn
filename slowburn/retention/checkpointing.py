"""Worst-case-optimal online checkpointing (D69): Bar-On, Dinur, Dunkelman, Hod, Keller, Ronen,
Shamir, "Tight Bounds on Online Checkpointing Algorithms" (arXiv 1704.02659v2).

Model: k checkpoints in [0, T], with 0 and the present T as free virtual checkpoints. An
algorithm is an initial snapshot plus update actions (t_i, p_i): at time t_i the p_i-th oldest
checkpoint moves to t_i. Efficiency q: every subinterval of every snapshot stays <= q T / (k + 1)
(Section 1). Cyclic algorithms are given as one period of updates and a period scale gamma
(t_{i+n} = gamma t_i).

Our budget K counts today's snapshot, which plays the role of the present T, so k = K - 1. In
daily time (unit ``scale`` days) the policy holds today plus floor(scale * T_j) for the
checkpoints after every update before the end of the day.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache

import numpy as np

from slowburn.retention.base import RetentionContext

HORIZON_DAYS = 2048  # schedules are precomputed this far (longest trace: 681 days)


@dataclass(frozen=True)
class Cyclic:
    """Initial snapshot ``init`` (k sorted times), one period of updates ``period`` = ((t, p),
    ...), each next period = the previous one times ``gamma``."""

    name: str
    init: tuple[float, ...]
    period: tuple[tuple[float, int], ...]
    gamma: float

    @property
    def k(self) -> int:
        return len(self.init)

    def events(self, t_max: float):
        """Yield (t, p) for every update with t <= t_max (p = None: initial placements)."""
        for t in self.init:
            yield t, None
        c = 0
        while True:
            for t, p in self.period:
                tt = t * self.gamma**c
                if tt > t_max:
                    return
                yield tt, p
            c += 1


def _smallest_root(f, lo: float, hi: float, n: int = 20000) -> float:
    xs = np.linspace(lo, hi, n)
    v = np.array([f(x) for x in xs])
    i = int(np.flatnonzero(np.sign(v[:-1]) != np.sign(v[1:]))[0])
    a, b = xs[i], xs[i + 1]
    for _ in range(200):
        m = (a + b) / 2
        if np.sign(f(m)) == np.sign(f(a)):
            a = m
        else:
            b = m
    return (a + b) / 2


def round_robin(k: int, G: float | None = None) -> Cyclic:
    """Prop. 3.1: p_i = 1 always, t_i = G^i; the paper's G = 1/(1 - r), r the smallest root of
    x = (1 - x)^(k - 1)."""
    if G is None:
        r = _smallest_root(lambda x: x - (1 - x) ** (k - 1), 1e-9, 1 - 1e-9)
        G = 1 / (1 - r)
    return Cyclic(f"round_robin_k{k}", tuple(G**j for j in range(k)), ((G**k, 1),), G)


def exact(k: int) -> Cyclic:
    """The optimal schedules given in closed form: k = 3 (Prop. 3.2), 4 (Prop. 3.4), 5 (3.3)."""
    if k == 3:
        return _exact3()
    if k == 4:
        g = max(np.roots([1, -1, -2, 1]).real)
        return Cyclic("exact_k4", (1, g, g**3 - g**2, g**2), ((g**4 - g**3, 3), (g**3, 1)), g)
    if k == 5:
        r5 = _smallest_root(lambda x: x**3 - 4 * x**2 + 5 * x - 1, 0.0, 1.0)
        G = 1 / (1 - r5)
        return Cyclic("exact_k5", (1, G**2, G**3, G**4, G**5), ((G**6, 3), (G**7, 1)), G**2)
    raise ValueError(f"the paper gives no closed-form optimal schedule for k = {k}")


def _exact3() -> Cyclic:
    G = (1 + math.sqrt(5)) / 2
    return Cyclic("exact_k3", (1, G, G**2), ((G**3, 1),), G)


def recursive_K(k: int) -> tuple[int, ...]:
    """K* = (k_0 = k, k_1, ..., k_m, 0) with k_j = floor(2^-j k), m = floor(log2 k) - 1."""
    m = int(math.floor(math.log2(k))) - 1
    return (*(k >> j for j in range(m + 1)), 0)


def recursive_r(G: float, K: tuple[int, ...]) -> float:
    """r(G, K) of Section 4.2: max of (1a), (1b) over l = 0..m-1, and (1c)."""
    m = len(K) - 2

    def e(ell):
        return sum(2**j * (K[j] - K[j + 1]) for j in range(ell + 1))

    terms = [1 - 1 / G]
    terms += [G ** (-e(ell)) * (G ** (2**ell) - G ** (-(2**ell))) for ell in range(m)]
    terms.append(G ** (2**m - e(m)))
    return max(terms)


def recursive(k: int, G: float | None = None) -> Cyclic:
    """Recursive(G, K*), (2^m, G)-geometric with pattern p_{k+i} = 1 + k_{mu(i)+1}, mu(i) the
    largest mu <= m with 2^mu | i; G = G* minimising r(G, K*) unless given. The initial snapshot
    is not specified by the paper (rebasing, Remark 1): G^1..G^k."""
    K = recursive_K(k)
    m = len(K) - 2
    if G is None:
        xs = np.linspace(1.0005, 4.0, 40000)
        rs = np.array([recursive_r(x, K) for x in xs])
        i = int(np.argmin(rs))
        a, b = xs[max(i - 1, 0)], xs[min(i + 1, len(xs) - 1)]
        for _ in range(200):  # ternary search on the bracketing interval
            c1, c2 = a + (b - a) / 3, b - (b - a) / 3
            if recursive_r(c1, K) <= recursive_r(c2, K):
                b = c2
            else:
                a = c1
        G = (a + b) / 2
    n = 2**m

    def mu(i):
        return max(u for u in range(m + 1) if i % 2**u == 0)

    period = tuple((G ** (k + i), 1 + K[mu(i) + 1]) for i in range(1, n + 1))
    return Cyclic(f"recursive_k{k}", tuple(G**j for j in range(1, k + 1)), period, G**n)


def snapshots(alg: Cyclic, t_max: float):
    """Yield (t_i, sorted snapshot) after each event."""
    snap: list[float] = []
    for t, p in alg.events(t_max):
        if p is not None:
            snap.pop(p - 1)
        snap.append(t)
        snap.sort()
        yield t, tuple(snap)


def efficiency(alg: Cyclic, periods: int = 40, warm: int = 8) -> float:
    """Continuous efficiency, measured at update times after ``warm`` periods (rebasing): the
    largest (k + 1) * gap / T over the gaps of each snapshot at its own time, and the last gap
    just before the next update, (k + 1)(t_{i+1} - t_i) / t_{i+1}."""
    k = alg.k
    t_max = alg.period[-1][0] * alg.gamma ** (periods - 1)
    t_warm = alg.period[-1][0] * alg.gamma**warm
    ev = list(snapshots(alg, t_max))
    q = 0.0
    for (t, s), (t_next, _) in zip(ev[:-1], ev[1:], strict=True):
        if t < t_warm:
            continue
        gaps = np.diff((0.0, *s))
        q = max(q, (k + 1) * gaps.max() / t, (k + 1) * (t_next - t) / t_next)
    return q


def day_scale(alg: Cyclic) -> float:
    """Smallest integer time unit (days) putting the initial checkpoints on distinct days."""
    s = 1
    while len({math.floor(s * t) for t in alg.init}) < alg.k:
        s += 1
    return float(s)


@lru_cache(maxsize=64)
def held_days(alg: Cyclic, n_days: int) -> tuple[frozenset, ...]:
    """Days held (besides today) at the end of each day 0..n_days-1."""
    s = day_scale(alg)
    out, snap = [], ()
    ev = iter(snapshots(alg, (n_days + 1) / s))
    nxt = next(ev, None)
    for d in range(n_days):
        while nxt is not None and s * nxt[0] < d + 1:
            snap = nxt[1]
            nxt = next(ev, None)
        out.append(frozenset(math.floor(s * t) for t in snap))
    return tuple(out)


def discrete_efficiency(alg: Cyclic, d_from: int = 2000, d_to: int = 200000) -> float:
    """Daily-discretised efficiency: the largest (k + 1) * gap / d over days d_from..d_to, with
    gaps between 0, the held days and today."""
    k = alg.k
    days = held_days(alg, d_to + 1)
    q = 0.0
    for d in range(d_from, d_to + 1):
        pts = sorted(days[d] | {0, d})
        q = max(q, (k + 1) * max(np.diff(pts)) / d)
    return q


class OnlineCheckpointing:
    """Retention policy (D69): at budget K the schedule ``family`` with k = K - 1 checkpoints
    ("exact": closed-form optimal, k in {3, 4, 5}; "rr": Round-Robin with the paper's G;
    "recursive": Recursive(G*, K*))."""

    def __init__(self, family: str):
        self.family = family
        self.name = f"shamir_{family}"
        self._alg: dict[int, Cyclic] = {}

    def supports(self, K: int) -> bool:
        return self.family != "exact" or K - 1 in (3, 4, 5)

    def schedule(self, K: int) -> Cyclic:
        if K not in self._alg:
            k = K - 1
            self._alg[K] = {"exact": exact, "rr": round_robin, "recursive": recursive}[
                self.family](k)  # fmt: skip
        return self._alg[K]

    def decide(self, ctx: RetentionContext) -> set[int]:
        alg = self.schedule(ctx.budget)
        if ctx.day >= HORIZON_DAYS:
            raise ValueError(f"{self.name}: precomputed for {HORIZON_DAYS} days")
        want = held_days(alg, HORIZON_DAYS)[ctx.day] | {ctx.day}
        keep = {sid for sid, d in ctx.snapshot_days.items() if d in want}
        if len(keep) != len(want):
            raise AssertionError(f"{self.name}: schedule needs a dropped snapshot on {ctx.day}")
        return keep
