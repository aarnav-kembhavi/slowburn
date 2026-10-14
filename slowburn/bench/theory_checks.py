"""Numerical checks for docs/theory.md (Theorem 2), with tightness reports."""

from __future__ import annotations

import itertools

import numpy as np
import pandas as pd

from slowburn.retention.base import PosteriorDP, TowerOfHanoi, replay


def toh_guarantee_table(K: int, n_days: int = 600) -> pd.DataFrame:
    """Replay ToH with K media; for every discovery day t and delay d covered by Theorem 2(a),
    record whether a clean snapshot is held and the whole-system work lost W."""
    kept = replay(TowerOfHanoi(), n_days, K)
    rows = []
    for t in range(n_days):
        held = kept[t]
        for d in range(0, 2 ** (K - 2)):
            s = t - d
            if s < 1 or (d >= 1 and s < 2 * d):
                continue  # outside the theorem's conditions
            clean = [j for j in held if j < s]
            W = (t - max(clean)) if clean else None
            bound = 1 if d == 0 else 3 * d
            rows.append({"K": K, "t": t, "d": d, "s": s, "clean": bool(clean), "W": W,
                         "bound": bound, "within_bound": bool(clean) and W <= bound})  # fmt: skip
    return pd.DataFrame(rows)


def hybrid_guarantee_table(K: int, R: int, n_days: int = 300, seed: int = 0,
                           gate: float = 0.5) -> pd.DataFrame:  # fmt: skip
    """Theorem 2(c) check: replay the hybrid (R-media Tower of Hanoi backbone + DP on K - R
    slots) under random daily posteriors; record whether its held set contains the R-media ToH
    set and, for every (t, d) within Theorem 2(a)'s conditions for R, whether a clean snapshot
    with W <= 3d is held."""
    rng = np.random.default_rng(seed)
    toh = replay(TowerOfHanoi(), n_days, R)

    def extra(day):
        w = rng.dirichlet(np.full(day + 1, rng.uniform(0.1, 2.0))) * rng.uniform(0.05, 1.0)
        return {"retention_pi": w, "prior_retention_pi": w}

    hyb = replay(PosteriorDP(30.0, gate=gate, backbone=R / K), n_days, K, extra)
    rows = []
    for t in range(n_days):
        superset = toh[t] <= hyb[t]
        for d in range(0, 2 ** (R - 2)):
            s = t - d
            if s < 1 or (d >= 1 and s < 2 * d):
                continue
            clean = [j for j in hyb[t] if j < s]
            W = (t - max(clean)) if clean else None
            bound = 1 if d == 0 else 3 * d
            rows.append({"K": K, "R": R, "t": t, "d": d, "superset": superset,
                         "within_bound": bool(clean) and W <= bound})  # fmt: skip
    return pd.DataFrame(rows)


def min_ages_brute(D: int, c: float) -> int:
    """Smallest number of ages a covering every d in 0..D with d < a <= c(d+1) (exhaustive)."""
    top = int(np.floor(c * (D + 1)))
    candidates = range(1, top + 1)
    for m in range(1, top + 1):
        for ages in itertools.combinations(candidates, m):
            if all(any(d < a <= c * (d + 1) for a in ages) for d in range(D + 1)):
                return m
    raise RuntimeError("unreachable")


def lower_bound_K(D: int, c: float) -> float:
    """Theorem 2(b): K >= log_c((c - 1)(D + 1) + c) (K counts today's snapshot)."""
    return float(np.log((c - 1) * (D + 1) + c) / np.log(c))


def theory_report(out_dir) -> dict[str, pd.DataFrame]:
    from pathlib import Path

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    tightness = []
    for K in (4, 5, 6, 8):
        tab = toh_guarantee_table(K)
        pos = tab[tab.d >= 1]
        tightness.append({"K": K, "cases": len(tab), "violations": int((~tab.within_bound).sum()),
                          "horizon_D": 2 ** (K - 2) - 1,
                          "max_W_over_3d": float((pos.W / (3 * pos.d)).max()),
                          "mean_W_over_3d": float((pos.W / (3 * pos.d)).mean())})  # fmt: skip
    lb = []
    for c in (2.0, 3.0, 4.0):
        for D in range(0, 13):
            m = min_ages_brute(D, c)
            lb.append({"c": c, "D": D, "min_useful_ages": m, "K_min_exhaustive": m + 1,
                       "K_lower_bound": lower_bound_K(D, c)})  # fmt: skip
    hyb = []
    for K, R in ((6, 3), (8, 4), (12, 6), (12, 4)):
        tab = hybrid_guarantee_table(K, R)
        hyb.append({"K": K, "R": R, "cases": len(tab), "horizon_D": 2 ** (R - 2) - 1,
                    "days_superset_violated": int((~tab.groupby("t").superset.first()).sum()),
                    "bound_violations": int((~tab.within_bound).sum())})  # fmt: skip
    res = {"toh_tightness": pd.DataFrame(tightness), "horizon_lower_bound": pd.DataFrame(lb),
           "hybrid_guarantee": pd.DataFrame(hyb)}  # fmt: skip
    for name, df in res.items():
        df.to_csv(out / f"{name}.csv", index=False)
    return res
