"""Exact per-decision retention optimiser (dynamic programming over the 1-D timeline).

Model (see docs/theory.md):
    * snapshot of day j is clean iff j < s, where s is the attack start day;
    * ``pi[s]`` for s = 0..t is P(attack started on day s), already conditioned on the evidence
      and on "not discovered yet"; the remaining mass is "not started" and costs nothing;
    * keeping the set J (sorted j_1 < ... < j_k), the loss of start s is
          s - 1 - max{j in J : j < s}     clean work lost, if some kept snapshot is clean
          penalty                         if no kept snapshot is clean (s <= j_1)
      ``penalty=None`` gives the symmetric variant: loss s (as if a clean copy of day -1 existed).

Expected loss = penalty * P(s <= j_1) + sum_i C(j_i, j_{i+1}) + C(j_k, inf), with
C(a, b) = sum_{a < s <= b} pi[s] (s - 1 - a); the DP over (last kept index, count) is exact and
O(m^2 K) for m candidates. It is optimal for THIS decision given the held snapshots (myopic):
it does not plan for future deletions.
"""

from __future__ import annotations

import itertools
from collections.abc import Sequence

import numpy as np


class _Sums:
    """O(1) interval sums of pi over start days via prefix sums."""

    def __init__(self, pi: np.ndarray):
        pi = np.asarray(pi, float)
        self.n = len(pi)
        self.s0 = np.r_[0.0, np.cumsum(pi)]
        self.s1 = np.r_[0.0, np.cumsum(pi * np.arange(self.n))]

    def _idx(self, x: float) -> int:
        """Number of start days <= x (x may be fractional, negative or beyond the end)."""
        return int(np.clip(np.floor(x) + 1, 0, self.n))

    def mass_le(self, a: float) -> float:
        return float(self.s0[self._idx(a)])

    def gap_cost(self, a: int, b: float) -> float:
        """C(a, b) = sum_{a < s <= b} pi[s] (s - 1 - a)."""
        lo, hi = self._idx(a), self._idx(b)
        if hi <= lo:
            return 0.0
        m0 = self.s0[hi] - self.s0[lo]
        m1 = self.s1[hi] - self.s1[lo]
        return float(m1 - (a + 1) * m0)

    def no_clean_cost(self, oldest: int, penalty: float | None) -> float:
        if penalty is not None:
            return penalty * self.mass_le(oldest)
        lo, hi = 0, self._idx(oldest)  # symmetric: loss s for s <= oldest
        return float(self.s1[hi] - self.s1[lo])


def expected_loss(keep: Sequence[int], pi: np.ndarray, penalty: float | None) -> float:
    """Expected loss of keeping the snapshot days ``keep`` under start posterior ``pi``."""
    if not len(keep):
        raise ValueError("keep must not be empty")
    j = sorted(keep)
    S = _Sums(pi)
    cost = S.no_clean_cost(j[0], penalty)
    for a, b in itertools.pairwise(j):
        cost += S.gap_cost(a, b)
    return cost + S.gap_cost(j[-1], np.inf)


def dp_select(candidates: Sequence[int], pi: np.ndarray, budget: int, penalty: float | None,
              keep_newest: bool = True) -> list[int]:  # fmt: skip
    """Exact minimiser of ``expected_loss`` over subsets of ``candidates`` with at most
    ``budget`` elements (always containing the newest candidate if ``keep_newest``)."""
    c = sorted(set(candidates))
    if budget < 1 or not c:
        raise ValueError("need budget >= 1 and at least one candidate")
    m, K = len(c), min(budget, len(c))
    S = _Sums(pi)
    # f[i, n]: min cost of an n-element set whose newest element is c[i], counting the no-clean
    # term and the gaps up to c[i]
    f = np.full((m, K + 1), np.inf)
    back = np.full((m, K + 1), -1, dtype=int)
    for i in range(m):
        f[i, 1] = S.no_clean_cost(c[i], penalty)
        for n in range(2, min(K, i + 1) + 1):
            vals = [f[h, n - 1] + S.gap_cost(c[h], c[i]) for h in range(i)]
            h = int(np.argmin(vals))  # first minimiser: deterministic ties
            f[i, n], back[i, n] = vals[h], h
    ends = [m - 1] if keep_newest else range(m)
    best, end = np.inf, None
    for i in ends:
        for n in range(1, K + 1):
            v = f[i, n] + S.gap_cost(c[i], np.inf)
            if v < best - 1e-15:
                best, end = v, (i, n)
    i, n = end
    out = []
    while n >= 1:
        out.append(c[i])
        i, n = back[i, n], n - 1
    return sorted(out)


def brute_force_select(
    candidates: Sequence[int],
    pi: np.ndarray,
    budget: int,
    penalty: float | None,
    keep_newest: bool = True,
) -> tuple[float, list]:
    """Exhaustive minimum (for tests): returns (best expected loss, one optimal set)."""
    c = sorted(set(candidates))
    best, arg = np.inf, None
    for k in range(1, min(budget, len(c)) + 1):
        for J in itertools.combinations(c, k):
            if keep_newest and c[-1] not in J:
                continue
            v = expected_loss(J, pi, penalty)
            if v < best - 1e-15:
                best, arg = v, list(J)
    return best, arg


def discovery_survival(kind: str, max_days: int) -> callable:
    """S(k) = P(discovery delay > k) for an assumed delay distribution on {1..max_days}.

    ``uniform``: uniform on {1..max_days}. ``geometric``: mean max_days/2, truncated at max_days.
    """
    if kind == "uniform":

        def S(k):
            k = np.asarray(k, float)
            return np.clip((max_days - k) / max_days, 0.0, 1.0)

        return S
    if kind == "geometric":
        p = 2.0 / max_days

        def S(k):
            k = np.asarray(k, float)
            return np.where(k < max_days, (1 - p) ** np.maximum(k, 0), 0.0)

        return S
    raise ValueError(f"unknown discovery distribution {kind!r}")


def retention_posterior(post: np.ndarray, t: int, survival) -> np.ndarray:
    """Condition a start posterior (length t+2: days 0..t then 'not started') on "the attack has
    not been discovered by day t". Returns pi over days 0..t (not-started mass dropped, so pi
    sums to P(started | evidence, not discovered))."""
    post = np.asarray(post, float)
    if len(post) != t + 2:
        raise ValueError("posterior must cover days 0..t plus 'not started'")
    started = post[: t + 1] * survival(t - np.arange(t + 1))
    total = started.sum() + post[-1]
    return started / total if total > 0 else started
