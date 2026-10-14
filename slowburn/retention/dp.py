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

Restore rule matched exactly (decision D29). At discovery the shared restore walks the kept
snapshots newest first, skipping those whose posterior probability of being clean is below the
gate tau, verifies each candidate with the detector, and restores from the first that verifies;
if none does, it falls back to the oldest kept snapshot. With reliable verification its loss
for start s is therefore that of the newest kept snapshot j < min(s, g + 1), where g is the
newest day with P(start > g) >= tau, plus the fallback case where every kept snapshot is newer
than g. ``gate`` reproduces exactly this loss (``gated_pi`` + the fallback branch in
``dp_select``); gate = 0 is the ungated loss above. ``forced`` snapshots (the hybrid's backbone)
are always kept and do not count against the budget.
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

    def gap_cost_many(self, a: np.ndarray, b: float) -> np.ndarray:
        """``gap_cost`` for an array of left ends ``a`` and one right end ``b``."""
        a = np.asarray(a)
        lo = np.clip(np.floor(a) + 1, 0, self.n).astype(int)
        hi = self._idx(b)
        m0 = self.s0[hi] - self.s0[lo]
        m1 = self.s1[hi] - self.s1[lo]
        return np.where(hi > lo, m1 - (a + 1) * m0, 0.0)

    def no_clean_cost(self, oldest: int, penalty: float | None) -> float:
        if penalty is not None:
            return penalty * self.mass_le(oldest)
        lo, hi = 0, self._idx(oldest)  # symmetric: loss s for s <= oldest
        return float(self.s1[hi] - self.s1[lo])


def gate_day(pi: np.ndarray, gate: float) -> float:
    """Newest day g with P(start > g | started) >= gate under ``pi`` (days 0..len-1).
    ``gate <= 0`` disables the gate (returns +inf); -1 when no day qualifies."""
    if gate <= 0:
        return np.inf
    pi = np.asarray(pi, float)
    total = pi.sum()
    if total <= 0:
        return np.inf  # no attack mass at all: nothing to gate
    p_clean = (total - np.cumsum(pi)) / total
    ok = np.flatnonzero(p_clean >= gate - 1e-12)
    return float(ok[-1]) if len(ok) else -1.0


def gated_pi(pi: np.ndarray, g: float) -> np.ndarray:
    """Move the mass of starts s > g + 1 onto s = g + 1: snapshots newer than g are never
    restored from, so for those starts the restore lands on the newest kept j <= g."""
    pi = np.asarray(pi, float)
    if not np.isfinite(g) or g + 1 >= len(pi) - 1:
        return pi
    gi = int(g)
    out = np.zeros(gi + 2)
    out[: gi + 1] = pi[: gi + 1]
    out[gi + 1] = pi[gi + 1 :].sum()
    return out


def _ungated_loss(j: list[int], S: _Sums, penalty: float | None) -> float:
    cost = S.no_clean_cost(j[0], penalty)
    for a, b in itertools.pairwise(j):
        cost += S.gap_cost(a, b)
    return cost + S.gap_cost(j[-1], np.inf)


def expected_loss(keep: Sequence[int], pi: np.ndarray, penalty: float | None,
                  gate: float = 0.0) -> float:  # fmt: skip
    """Expected loss of keeping the snapshot days ``keep`` under start posterior ``pi``, for the
    restore rule with posterior gate ``gate`` and reliable verification (module docstring)."""
    if not len(keep):
        raise ValueError("keep must not be empty")
    j = sorted(keep)
    g = gate_day(pi, gate)
    if j[0] > g:  # no kept snapshot passes the gate: fallback to the oldest kept snapshot
        S = _Sums(pi)
        return S.no_clean_cost(j[0], penalty) + S.gap_cost(j[0], np.inf)
    # gated_pi charges starts s > g + 1 as if s = g + 1; add back their constant (s - 1 - g)
    shift = _Sums(pi).gap_cost(int(g), np.inf) if np.isfinite(g) else 0.0
    return _ungated_loss(j, _Sums(gated_pi(pi, g)), penalty) + shift


def dp_select(candidates: Sequence[int], pi: np.ndarray, budget: int, penalty: float | None,
              keep_newest: bool = True, forced: Sequence[int] = (),
              gate: float = 0.0) -> list[int]:  # fmt: skip
    """Exact minimiser of ``expected_loss`` over subsets of ``candidates`` that contain every
    ``forced`` day and at most ``budget`` other days (and the newest candidate if
    ``keep_newest``)."""
    fset = set(forced)
    c = sorted(set(candidates) | fset)
    if not c or (budget < 1 and not fset):
        raise ValueError("need budget >= 1 (or forced days) and at least one candidate")
    m = len(c)
    is_f = np.array([x in fset for x in c])
    cost1 = (~is_f).astype(int)
    first_f = int(np.argmax(is_f)) if is_f.any() else m - 1  # the oldest element is <= this
    last_f = int(m - 1 - np.argmax(is_f[::-1])) if is_f.any() else 0
    K = min(budget, int(cost1.sum()))
    g = gate_day(pi, gate)
    S_orig = _Sums(pi)
    S = _Sums(gated_pi(pi, g))
    ends = [m - 1] if keep_newest else list(range(last_f, m))

    # option B: oldest kept day <= g (gated loss). f[i, n] = min cost of a set whose newest element
    # is c[i] using n non-forced elements and skipping no forced element older than c[i]
    f = np.full((m, K + 1), np.inf)
    back = np.full((m, K + 1), -1, dtype=int)
    for i in range(m):
        if c[i] <= g and i <= first_f and cost1[i] <= K:
            f[i, cost1[i]] = S.no_clean_cost(c[i], penalty)
        if i == 0:
            continue
        prev_f = np.flatnonzero(is_f[:i])
        lo = int(prev_f[-1]) if len(prev_f) else 0  # the newest forced element below i
        hs = np.arange(lo, i)
        gaps = S.gap_cost_many(np.array([c[h] for h in hs], float), c[i])
        for n in range(cost1[i], K + 1):
            vals = f[hs, n - cost1[i]] + gaps
            k = int(np.argmin(vals))  # first minimiser: deterministic ties
            if vals[k] < f[i, n]:
                f[i, n], back[i, n] = vals[k], hs[k]
    best, end = np.inf, None
    shift = S_orig.gap_cost(int(g), np.inf) if np.isfinite(g) else 0.0  # see expected_loss
    for i in ends:
        tail = S.gap_cost(c[i], np.inf) + shift
        for n in range(K + 1):
            v = f[i, n] + tail
            if v < best - 1e-15:
                best, end = v, (i, n)
    out_b = None
    if end is not None:
        i, n = end
        out_b = []
        while i >= 0:
            out_b.append(c[i])
            i, n = back[i, n], n - cost1[i]
        out_b = sorted(out_b)

    # option A: every kept day > g, so the restore falls back to the oldest kept day j1 and the
    # loss depends on j1 only; the cheapest such set is {j1} + forced (+ newest)
    out_a, best_a = None, np.inf
    if np.isfinite(g):
        newest = [c[-1]] if keep_newest else []
        for i in range(m):
            if c[i] <= g or i > first_f:
                continue
            J = sorted({c[i], *fset, *newest})
            if sum(1 for x in J if x not in fset) > budget:
                continue
            v = S_orig.no_clean_cost(c[i], penalty) + S_orig.gap_cost(c[i], np.inf)
            if v < best_a - 1e-15:
                best_a, out_a = v, J
    if out_b is None and out_a is None:
        raise ValueError("no feasible retention set (budget too small for the constraints)")
    if out_b is None or best_a < best - 1e-12:
        return out_a
    return out_b


def brute_force_select(
    candidates: Sequence[int],
    pi: np.ndarray,
    budget: int,
    penalty: float | None,
    keep_newest: bool = True,
    forced: Sequence[int] = (),
    gate: float = 0.0,
) -> tuple[float, list]:
    """Exhaustive minimum (for tests): returns (best expected loss, one optimal set)."""
    fset = set(forced)
    free = sorted(set(candidates) - fset)
    allc = sorted(set(candidates) | fset)
    best, arg = np.inf, None
    for k in range(0, min(budget, len(free)) + 1):
        for extra in itertools.combinations(free, k):
            J = sorted(fset | set(extra))
            if not J or (keep_newest and allc[-1] not in J):
                continue
            v = expected_loss(J, pi, penalty, gate)
            if v < best - 1e-15:
                best, arg = v, J
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


def discovery_posterior(post: np.ndarray, t: int, survival) -> np.ndarray:
    """Condition a start posterior (length t+2: days 0..t then 'not started') on "the attack was
    discovered on day t", under the assumed delay distribution with survival S (D34):
    P(s | evidence, discovered at t) ∝ P(s | evidence) * P(delay = t - s). Returns the same
    layout with zero 'not started' mass (falls back to the input if the product vanishes)."""
    post = np.asarray(post, float)
    if len(post) != t + 2:
        raise ValueError("posterior must cover days 0..t plus 'not started'")
    k = t - np.arange(t + 1)
    pmf = survival(k - 1) - survival(k)
    w = post[: t + 1] * pmf
    total = w.sum()
    if total <= 0:
        return post
    return np.r_[w / total, 0.0]
