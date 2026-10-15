"""Simulator v2: generating distributions for the attack start day ("worlds", D45).

The policy's timing assumption stays fixed (the flat, constant-hazard prior); what varies is the
world that generates attack starts. Each machine draws its own start from its world, on a stream
keyed by (seed, split, world, rep) only, so every evidence cell (detection probability, benign
flag rate) of a world sees the same start for the same rep: comparisons stay paired.

Kinds (all on the integer window [lo, hi]):
* ``uniform``: every day equally likely.
* ``beta``: lo + floor((hi - lo + 1) * Beta(a, b)); a < b concentrates early, a > b late.
* ``clusters``: bursty campaigns; pick one of ``centres`` uniformly, add Normal(0, ``sd``)
  jitter, round, clip to the window.
"""

from __future__ import annotations

import numpy as np

from slowburn.utils.seed import child_rng

KINDS = ("uniform", "beta", "clusters")


def draw_start(world: dict, rng: np.random.Generator) -> int:
    lo, hi = int(world["window"][0]), int(world["window"][1])
    if hi < lo:
        raise ValueError("world window must have lo <= hi")
    kind = world["kind"]
    if kind == "uniform":
        return int(rng.integers(lo, hi + 1))
    if kind == "beta":
        x = rng.beta(float(world["a"]), float(world["b"]))
        return int(min(hi, lo + np.floor((hi - lo + 1) * x)))
    if kind == "clusters":
        centre = float(rng.choice(np.asarray(world["centres"], float)))
        return int(np.clip(round(centre + rng.normal(0.0, float(world["sd"]))), lo, hi))
    raise ValueError(f"unknown world kind {kind!r} (expected one of {KINDS})")


def world_start(seed: int, split: str, world: dict, rep: int) -> int:
    """The attack start of machine ``rep`` in ``world`` (independent of evidence parameters)."""
    return draw_start(world, child_rng(int(seed), "attack_start", split, world["name"], int(rep)))


def world_pmf(world: dict, n: int = 200_000, seed: int = 0) -> dict[int, float]:
    """Empirical start-day distribution of a world (for reports and the data card)."""
    rng = child_rng(seed, "world_pmf", world["name"])
    days = np.array([draw_start(world, rng) for _ in range(n)])
    vals, counts = np.unique(days, return_counts=True)
    return {int(v): float(c) / n for v, c in zip(vals, counts, strict=True)}
