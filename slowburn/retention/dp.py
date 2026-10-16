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

Deletion only when forced (decision D37, after the K = 12 diagnosis). The retained set always
holds exactly min(K, number of candidates) non-forced snapshots: a snapshot is deleted only when
the budget is exceeded, and then the DP removes the one whose removal increases expected loss
least. Among equal-loss options the tie-break, fixed before the rerun, is: the smallest largest
gap between consecutive kept snapshots, then the smallest sum of kept days (with one deletion:
delete the newest eligible snapshot). The earlier code allowed fewer than K snapshots and broke
ties towards the smaller set, which deleted zero-marginal-value snapshots while slots were free.
"""

from __future__ import annotations

import itertools
import math
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
        if x >= self.n:
            return self.n  # also +inf
        if x < 0:
            return 0  # also -inf
        return min(math.floor(x) + 1, self.n)

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


class _LossEval:
    """``expected_loss`` for many sets under one posterior and gate (prefix sums built once)."""

    def __init__(self, pi: np.ndarray, penalty: float | None, gate: float):
        self.penalty = penalty
        self.g = gate_day(pi, gate)
        self.S = _Sums(pi)
        self.Sg = _Sums(gated_pi(pi, self.g))
        # gated_pi charges starts s > g + 1 as if s = g + 1; add back their constant (s - 1 - g)
        self.shift = self.S.gap_cost(int(self.g), np.inf) if np.isfinite(self.g) else 0.0

    def __call__(self, j: list[int]) -> float:
        """Loss of the sorted, non-empty set ``j``."""
        if j[0] > self.g:  # no kept snapshot passes the gate: fallback to the oldest kept one
            return self.S.no_clean_cost(j[0], self.penalty) + self.S.gap_cost(j[0], np.inf)
        return _ungated_loss(j, self.Sg, self.penalty) + self.shift


def expected_loss(keep: Sequence[int], pi: np.ndarray, penalty: float | None,
                  gate: float = 0.0) -> float:  # fmt: skip
    """Expected loss of keeping the snapshot days ``keep`` under start posterior ``pi``, for the
    restore rule with posterior gate ``gate`` and reliable verification (module docstring)."""
    if not len(keep):
        raise ValueError("keep must not be empty")
    return _LossEval(pi, penalty, gate)(sorted(keep))


def _tol(a: float, b: float) -> float:
    return 1e-9 * (1.0 + max(abs(a), abs(b)))


def _better(a: tuple, b: tuple) -> bool:
    """Lexicographic order on (expected loss, largest gap, sum of kept days), with equal losses
    judged up to a relative tolerance of 1e-9 (D37 tie-break, fixed before the rerun)."""
    if not np.isfinite(b[0]):
        return np.isfinite(a[0])
    if abs(a[0] - b[0]) > _tol(a[0], b[0]):
        return a[0] < b[0]
    return (a[1], a[2]) < (b[1], b[2])


def max_gap(keep: Sequence[int]) -> int:
    """Largest gap between consecutive kept days (0 for a single day)."""
    j = sorted(keep)
    return max((b - a for a, b in itertools.pairwise(j)), default=0)


def selection_key(keep: Sequence[int], pi: np.ndarray, penalty: float | None,
                  gate: float = 0.0) -> tuple:  # fmt: skip
    """The order the selection minimises: expected loss first; among equal losses the set with
    the smallest largest gap between consecutive kept snapshots; then the smallest sum of kept
    days (with one deletion: delete the newest eligible snapshot)."""
    return (expected_loss(keep, pi, penalty, gate), max_gap(keep), int(sum(keep)))


def _chain_dp(c, is_f, cost1, n_exact, first_f, ends, init, trans, tail, max_step=np.inf):
    """Best chain over the sorted candidates ``c`` that contains every forced element and exactly
    ``n_exact`` non-forced ones, ends at an index in ``ends`` and has no gap between consecutive
    elements larger than ``max_step``. "Best" is lexicographic on (loss, sum of days), both
    additive along the chain, so the recursion is exact. ``init(i)``: loss of a chain whose
    oldest element is c[i] (inf if not allowed); ``trans(hs, i)``: loss added by the step
    c[h] -> c[i] for an array of h; ``tail(i)``: loss after the newest element c[i].
    Returns ((loss, sum), days) or (None, None)."""
    m, K = len(c), n_exact
    L = np.full((m, K + 1), np.inf)
    T = np.zeros((m, K + 1))
    back = np.full((m, K + 1), -1, dtype=int)
    ca = np.asarray(c, float)
    for i in range(m):
        if i <= first_f and cost1[i] <= K:
            v = init(i)
            if np.isfinite(v):
                L[i, cost1[i]], T[i, cost1[i]] = v, c[i]
        if i == 0:
            continue
        prev_f = np.flatnonzero(is_f[:i])
        lo = int(prev_f[-1]) if len(prev_f) else 0  # may not skip a forced element
        hs = np.arange(lo, i)
        hs = hs[ca[i] - ca[hs] <= max_step]
        if not len(hs):
            continue
        step = trans(hs, i)
        for n in range(cost1[i], K + 1):
            p = n - cost1[i]
            vals = L[hs, p] + step
            if not np.isfinite(vals).any():
                continue
            vmin = vals.min()
            ok = np.flatnonzero(vals <= vmin + _tol(vmin, vmin))
            sums = T[hs, p] + c[i]
            k = ok[np.argmin(sums[ok])]
            cand = (vals[k], 0, sums[k])
            if _better(cand, (L[i, n], 0, T[i, n])):
                L[i, n], T[i, n], back[i, n] = vals[k], sums[k], hs[k]
    best, end = (np.inf, 0, 0.0), None
    for i in ends:
        if not np.isfinite(L[i, K]):
            continue
        cand = (L[i, K] + tail(i), 0, T[i, K])
        if _better(cand, best):
            best, end = cand, i
    if end is None:
        return None, None
    i, n, out = end, K, []
    while i >= 0:
        out.append(c[i])
        i, n = back[i, n], n - cost1[i]
    return (best[0], best[2]), sorted(out)


def _single_deletion(c, fset, pi, penalty, gate, keep_newest):
    """Fast path when exactly one snapshot must go (the online case: K held + today): evaluate
    ``selection_key`` for every eligible removal. Same minimiser as the DP (tested)."""
    loss = _LossEval(pi, penalty, gate)
    best, arg = (np.inf, 0, 0), None
    for x in c:
        if x in fset or (keep_newest and x == c[-1]):
            continue
        J = [y for y in c if y != x]
        key = (loss(J), max_gap(J), int(sum(J)))  # = selection_key(J, pi, penalty, gate)
        if _better(key, best):
            best, arg = key, J
    return arg


def dp_select(candidates: Sequence[int], pi: np.ndarray, budget: int, penalty: float | None,
              keep_newest: bool = True, forced: Sequence[int] = (),
              gate: float = 0.0) -> list[int]:  # fmt: skip
    """Exact minimiser of ``selection_key`` over subsets of ``candidates`` that contain every
    ``forced`` day, the newest candidate if ``keep_newest``, and exactly
    min(``budget``, number of non-forced candidates) other days: snapshots are deleted only
    when the budget is exceeded (D37).

    Loss and the day sum are additive along the chain, the largest gap is not, so the largest
    gap is handled exactly by a threshold search: the DP minimises (loss, day sum) with every
    gap capped at G, and G is the smallest cap whose optimum still attains the minimum loss
    (that optimum is non-increasing in G, so a binary search over the candidate gaps suffices).
    """
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
    if keep_newest and not is_f[-1] and K < 1:
        raise ValueError("no feasible retention set (budget too small for the constraints)")
    if K == int(cost1.sum()):
        return c  # within budget: delete nothing
    if keep_newest and K == int(cost1.sum()) - 1 and (is_f[-1] or K >= 1):
        return _single_deletion(c, fset, pi, penalty, gate, keep_newest)
    g = gate_day(pi, gate)
    S_orig = _Sums(pi)
    S = _Sums(gated_pi(pi, g))
    ca = np.asarray(c, float)
    ends = [m - 1] if keep_newest else list(range(last_f, m))
    shift = S_orig.gap_cost(int(g), np.inf) if np.isfinite(g) else 0.0  # see expected_loss

    def solve(cap):
        """Best (loss, day sum) set with every gap <= cap, over both restore branches."""
        # option B: oldest kept day <= g; loss under the gated posterior (see expected_loss)
        kb, ob = _chain_dp(
            c, is_f, cost1, K, first_f, ends,
            init=lambda i: S.no_clean_cost(c[i], penalty) if c[i] <= g else np.inf,
            trans=lambda hs, i: S.gap_cost_many(ca[hs], c[i]),
            tail=lambda i: S.gap_cost(c[i], np.inf) + shift, max_step=cap,
        )  # fmt: skip
        if not np.isfinite(g):
            return kb, ob
        # option A: every kept day > g, so the restore falls back to the oldest kept day j1 and
        # the loss depends on j1 only
        ka, oa = _chain_dp(
            c, is_f, cost1, K, first_f, ends,
            init=lambda i: (S_orig.no_clean_cost(c[i], penalty) + S_orig.gap_cost(c[i], np.inf)
                            if c[i] > g else np.inf),
            trans=lambda hs, i: np.zeros(len(hs)), tail=lambda i: 0.0, max_step=cap,
        )  # fmt: skip
        if ob is None or (oa is not None and _better((ka[0], 0, ka[1]), (kb[0], 0, kb[1]))):
            return ka, oa
        return kb, ob

    k_inf, out = solve(np.inf)
    if out is None:
        raise ValueError("no feasible retention set (budget too small for the constraints)")
    caps = np.unique([0.0, *(b - a for a, b in itertools.combinations(c, 2))])
    lo, hi = 0, len(caps) - 1  # caps[hi] = largest possible gap: the uncapped optimum
    while lo < hi:
        mid = (lo + hi) // 2
        k, o = solve(caps[mid])
        if o is not None and k[0] <= k_inf[0] + _tol(k[0], k_inf[0]):
            hi = mid
        else:
            lo = mid + 1
    return solve(caps[lo])[1]


def brute_force_select(
    candidates: Sequence[int],
    pi: np.ndarray,
    budget: int,
    penalty: float | None,
    keep_newest: bool = True,
    forced: Sequence[int] = (),
    gate: float = 0.0,
) -> tuple[float, list]:
    """Exhaustive minimum of ``selection_key`` under the same constraints as ``dp_select``
    (for tests): returns (best expected loss, the selected set)."""
    fset = set(forced)
    free = sorted(set(candidates) - fset)
    allc = sorted(set(candidates) | fset)
    k = min(budget, len(free))
    best, arg = (np.inf, 0, 0), None
    for extra in itertools.combinations(free, k):
        J = sorted(fset | set(extra))
        if not J or (keep_newest and allc[-1] not in J):
            continue
        key = selection_key(J, pi, penalty, gate)
        if _better(key, best):
            best, arg = key, J
    return best[0], arg


def discovery_survival(kind: str, max_days: int, tail: float = 0.0, alpha: float = 1.0) -> callable:
    """S(k) = P(discovery delay > k) for an assumed delay distribution on {1..max_days}.

    ``soft`` (method v3, D56): no hard bound. With weight 1 - ``tail`` uniform on {1..max_days},
    with weight ``tail`` a Lomax (Pareto II) tail S_tail(k) = (1 + k / max_days)^-alpha, which
    never reaches zero: any delay keeps positive probability.

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
    if kind == "soft":
        if not 0.0 < tail < 1.0 or alpha <= 0:
            raise ValueError("soft delay needs 0 < tail < 1 and alpha > 0")

        def S(k):
            k = np.asarray(k, float)
            core = np.clip((max_days - k) / max_days, 0.0, 1.0)
            heavy = (1.0 + np.maximum(k, 0.0) / max_days) ** -alpha
            return np.where(k < 0, 1.0, (1 - tail) * core + tail * heavy)

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
