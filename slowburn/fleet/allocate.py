"""D73: daily reallocation of a shared snapshot budget across machines.

Each machine has candidates (held snapshots plus today's) and a forced floor (its Bar-On
recursive set at k_min, which includes today). ``MachineLoss.loss(r)`` is the minimum SlowBurn DP
expected loss (retention.dp, penalty and gate as frozen) after removing r non-forced candidates,
under the machine's start posterior pi. The greedy runs from the top (OPEN_QUESTIONS D73): start
from keep-all and repeatedly remove the slot whose removal raises c_i * loss_i least, until the
fleet total fits the budget. ``brute_force_allocate`` is the exact optimum, for the check.
"""

from __future__ import annotations

import itertools
from collections.abc import Sequence

import numpy as np

from slowburn.retention.dp import _LossEval, dp_select


class MachineLoss:
    def __init__(self, cands: Sequence[int], forced: Sequence[int], pi: np.ndarray,
                 penalty: float | None, gate: float, weight: float = 1.0):  # fmt: skip
        self.cands = sorted(cands)
        self.forced = set(forced) | {self.cands[-1]}  # today's snapshot is always kept
        if not self.forced <= set(self.cands):
            raise ValueError("the floor must be among the candidates")
        self.free = [x for x in self.cands if x not in self.forced]
        self.pi, self.penalty, self.gate, self.weight = pi, penalty, gate, weight
        self._eval = _LossEval(pi, penalty, gate)
        self._cache: dict[int, float] = {}

    @property
    def n(self) -> int:
        return len(self.cands)

    @property
    def max_removals(self) -> int:
        return len(self.free)

    def loss(self, r: int) -> float:
        """Minimum expected loss with r free candidates removed."""
        if r not in self._cache:
            if r == 0:
                v = self._eval(self.cands)
            elif r <= 2:  # the online cases: exact enumeration
                v = min(self._eval([x for x in self.cands if x not in drop])
                        for drop in itertools.combinations(self.free, r))  # fmt: skip
            else:
                v = self._eval(self.select(r))
            self._cache[r] = v
        return self._cache[r]

    def select(self, r: int) -> list[int]:
        """The kept days after r removals (the D37 DP selection, its tie-break included)."""
        if r == 0:
            return list(self.cands)
        # dp_select counts today's snapshot (passed as non-forced, kept by keep_newest) in budget
        return dp_select(self.cands, self.pi, len(self.free) + 1 - r, self.penalty,
                         keep_newest=True, forced=sorted(self.forced - {self.cands[-1]}),
                         gate=self.gate)  # fmt: skip

    def step_cost(self, r: int) -> float:
        """Weighted loss increase of the (r + 1)-th removal."""
        return self.weight * (self.loss(r + 1) - self.loss(r))


def greedy_allocate(machines: Sequence[MachineLoss], budget: int) -> list[int]:
    """Removals per machine so that the fleet keeps at most ``budget`` snapshots."""
    r = [0] * len(machines)
    excess = sum(m.n for m in machines) - budget
    cost = [m.step_cost(0) if m.max_removals else np.inf for m in machines]
    while excess > 0:
        # cheapest removal; ties: the machine holding more, then the lower index
        i = min(range(len(machines)), key=lambda j: (cost[j], -(machines[j].n - r[j]), j))
        if not np.isfinite(cost[i]):
            raise ValueError("budget below the fleet's floors")
        r[i] += 1
        excess -= 1
        m = machines[i]
        cost[i] = m.step_cost(r[i]) if r[i] < m.max_removals else np.inf
    return r


def total_loss(machines: Sequence[MachineLoss], r: Sequence[int]) -> float:
    return float(sum(m.weight * m.loss(k) for m, k in zip(machines, r, strict=True)))


def brute_force_allocate(machines: Sequence[MachineLoss], budget: int) -> tuple[float, list]:
    """Exact minimum of the weighted total loss over all removal vectors that fit the budget
    with no slot left idle (D37: delete only what the budget forces)."""
    excess = max(0, sum(m.n for m in machines) - budget)
    best, arg = np.inf, None
    for r in itertools.product(*(range(m.max_removals + 1) for m in machines)):
        if sum(r) != excess:
            continue
        v = total_loss(machines, r)
        if v < best - 1e-12:
            best, arg = v, list(r)
    if arg is None:
        raise ValueError("budget below the fleet's floors")
    return best, arg
