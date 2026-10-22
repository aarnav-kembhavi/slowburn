"""Byte budgets (simulator v2, D46): retained storage measured in unique bytes, not snapshots.

In token mode every chunk is a fresh token that, once replaced, never returns, so each chunk
lives on one contiguous interval of days [first, last]. The unique bytes of a set of snapshot
days D = d_1 < ... < d_m are then

    chunk_size * (sum_i |S(d_i)| - sum_i |S(d_{i-1}) ∩ S(d_i)|),

and |S(a) ∩ S(b)| (a <= b) is the number of chunks with first <= a and last >= b, read from a
precomputed table in O(1).

In byte mode (real or synthetic file contents) a chunk can disappear and reappear (identical
headers, padding, a file redrawn from a small pool), so the interval formula would over-count.
Those traces fall back to the exact union: one bitset per day over all distinct chunks.

A byte budget is enforced with each policy's OWN deletion rule: after today's snapshot is added,
while the retained bytes exceed the budget, the policy is asked for its choice with a count
budget of one less than it holds (one deletion at a time). No policy is byte-aware.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

import numpy as np

_POPCOUNT = np.array([bin(i).count("1") for i in range(256)], dtype=np.int64)


class ByteIndex:
    def __init__(self, snapshots: Sequence[frozenset], chunk_size: int):
        n = len(snapshots)
        first: dict[bytes, int] = {}
        spans: list[tuple[int, int]] = []
        prev: frozenset = frozenset()
        dead: set[bytes] = set()
        self.chunk_size = int(chunk_size)
        self.bits: np.ndarray | None = None
        for d, cur in enumerate(snapshots):
            for c in prev - cur:
                spans.append((first.pop(c), d - 1))
                dead.add(c)
            for c in cur - prev:
                if c in dead:
                    self._exact(snapshots)
                    return
                first[c] = d
            prev = cur
        spans += [(f, n - 1) for f in first.values()]
        H = np.zeros((n, n), dtype=np.int64)
        if spans:
            f, last = np.array(spans).T
            np.add.at(H, (f, last), 1)
        # N[a, b] = #chunks with first <= a and last >= b
        self.N = np.cumsum(H, axis=0)[:, ::-1].cumsum(axis=1)[:, ::-1]

    def _exact(self, snapshots: Sequence[frozenset]) -> None:
        ids: dict[bytes, int] = {}
        for cur in snapshots:
            for c in cur:
                ids.setdefault(c, len(ids))
        rows = np.zeros((len(snapshots), len(ids)), dtype=bool)
        for d, cur in enumerate(snapshots):
            rows[d, [ids[c] for c in cur]] = True
        self.bits = np.packbits(rows, axis=1)
        self.N = None

    def size(self, d: int) -> int:
        return self.unique_bytes([d])

    def unique_bytes(self, days) -> int:
        j = sorted(days)
        if not j:
            return 0
        if self.bits is not None:
            union = np.bitwise_or.reduce(self.bits[j], axis=0)
            return int(_POPCOUNT[union].sum()) * self.chunk_size
        a, b = np.array(j[:-1], int), np.array(j[1:], int)
        total = self.N[j, j].sum() - self.N[a, b].sum()
        return int(total) * self.chunk_size


Decide = Callable[[dict[int, int], int], set[int]]


def enforce_byte_budget(held: dict[int, int], budget_bytes: float, index: ByteIndex,
                        decide: Decide) -> dict[int, int]:  # fmt: skip
    """Delete, one snapshot at a time by the policy's own rule, until the held snapshots fit.
    ``decide(held, k)`` returns the ids the policy keeps with a count budget of ``k``. Today's
    snapshot alone may exceed the budget; it is always kept."""
    while len(held) > 1 and index.unique_bytes(held.values()) > budget_bytes:
        today = max(held, key=held.get)
        keep = decide(dict(held), len(held) - 1)
        if len(keep) >= len(held) or today not in keep or not keep <= set(held):
            raise AssertionError("policy violated the retention contract under a byte budget")
        held = {sid: held[sid] for sid in keep}
    return held
