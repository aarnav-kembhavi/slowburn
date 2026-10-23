"""D73 report: the greedy-vs-exact allocation check and the pre-registered adoption criteria
(OPEN_QUESTIONS D73), FLEET (c) vs equal split (a) and churn split (b), each arm. DEV only.

    uv run python paper/scripts/d73_report.py [primary restore letter, default A]

Primary restore: A (verify_snap) unless D72 adopted method C (then pass C). Every restore is
reported; criteria are computed for every restore and the primary one is marked.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

from slowburn.bench.stats import cluster_bootstrap_ratio as cbr
from slowburn.fleet.allocate import (
    MachineLoss,
    brute_force_allocate,
    greedy_allocate,
    total_loss,
)

OUT = Path("results/dev_d73_report")
ARMS = {"synthetic_bytes": "results/dev_d73_fleet_synthetic",
        "napierone_bytes": "results/dev_d73_fleet_napierone"}  # fmt: skip
PAIR = ["arm", "rep", "world", "N", "f", "m", "K_avg", "discovery_delay"]
RESTORES = "ABCDE"
pd.set_option("display.width", 250, "display.max_columns", 40, "display.max_rows", 500)


def greedy_check(n_cases: int = 500, seed: int = 0) -> pd.DataFrame:
    """Random small cases: N in {2, 3, 4} machines, up to 6 removals beyond keep-all."""
    rng = np.random.default_rng(seed)
    rows = []
    while len(rows) < n_cases:
        ms = []
        for _ in range(int(rng.integers(2, 5))):
            t = int(rng.integers(30, 90))
            pi = np.zeros(t + 1)
            lo = int(rng.integers(0, t - 5))
            pi[lo:] = rng.random(t + 1 - lo)
            pi *= rng.uniform(0.01, 0.9) / pi.sum()
            cands = sorted({*rng.choice(t, int(rng.integers(3, 9)), replace=False).tolist(), t})
            forced = [cands[0]] if rng.random() < 0.5 else []
            ms.append(MachineLoss(cands, forced, pi, 90.0, 0.8, float(rng.uniform(0.5, 4.0))))
        room = sum(m.max_removals for m in ms)
        if room == 0:
            continue
        excess = int(rng.integers(1, 1 + min(6, room)))
        budget = sum(m.n for m in ms) - excess
        g = total_loss(ms, greedy_allocate(ms, budget))
        best, _ = brute_force_allocate(ms, budget)
        rows.append({"machines": len(ms), "removals": excess, "greedy": g, "exact": best,
                     "optimal": g <= best + 1e-9 * (1 + best),
                     "rel_excess": (g - best) / best if best > 0 else 0.0})  # fmt: skip
    return pd.DataFrame(rows)


def load() -> pd.DataFrame:
    parts = [pd.read_csv(Path(r) / "fleet_rows.csv.gz") for r in ARMS.values()
             if (Path(r) / "fleet_rows.csv.gz").exists()]  # fmt: skip
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()


def paired(d: pd.DataFrame, base: str, X: str) -> pd.DataFrame:
    cols = [f"fleet_clean_{X}", f"work_lost_file_hours_{X}", f"residual_files_{X}"]
    a = d[d.method == "c_fleet"].set_index(PAIR)[cols]
    b = d[d.method == base].set_index(PAIR)[cols]
    m = a.join(b, lsuffix="_c", rsuffix="_b", how="inner").reset_index()
    m["cl"] = m.rep.astype(str) + "/" + m.world  # fleets of one rep and world share machines
    return m


def criteria(d: pd.DataFrame, primary: str) -> pd.DataFrame:
    out = []
    for arm in sorted(d.arm.unique()):
        for base in ("a_equal", "b_churn"):
            for X in RESTORES:
                m = paired(d[d.arm == arm], base, X)
                rc, rb = f"fleet_clean_{X}_c", f"fleet_clean_{X}_b"
                wc, wb = f"work_lost_file_hours_{X}_c", f"work_lost_file_hours_{X}_b"
                cell = m.groupby(["N", "K_avg", "f", "m"])[[rc, rb]].mean()
                rec_drop = (cell[rc] - cell[rb]).min()
                wl = cbr(m[wc] - m[wb], m[wb], m.cl)
                fm = m.groupby(["f", "m"])[[wc, wb]].sum()
                lower = int((fm[wc] < fm[wb]).sum())
                one = np.ones(len(m))
                rec = cbr(m[rc] - m[rb], one, m.cl)
                out.append({"arm": arm, "vs": base, "restore": X, "primary": X == primary,
                            "pairs": len(m), "worst_cell_recovery_diff": rec_drop,
                            "c1_recovery": rec_drop >= -0.01,
                            "pooled_recovery_diff": rec[0], "rec_lo": rec[1], "rec_hi": rec[2],
                            "pooled_file_wl_rel": wl[0], "wl_lo": wl[1], "wl_hi": wl[2],
                            "c2_pooled_wl": wl[2] < 0, "fm_cells_lower": lower,
                            "c3_cells": lower >= 6})  # fmt: skip
    c = pd.DataFrame(out)
    c["all"] = c.c1_recovery & c.c2_pooled_wl & c.c3_cells
    return c


def main(primary: str = "A"):
    OUT.mkdir(parents=True, exist_ok=True)
    g = greedy_check()
    g.to_csv(OUT / "greedy_check.csv", index=False)
    print(f"== greedy vs exact: {len(g)} cases, optimal {g.optimal.mean():.3f}, "
          f"largest relative excess {g.rel_excess.max():.4f}")  # fmt: skip
    d = load()
    if d.empty:
        print("no fleet rows yet")
        return
    keys = ["arm", "N", "K_avg", "f", "m", "method"]
    summ = d.groupby(keys)[
        [c for c in d if c.startswith(("fleet_clean_", "work_lost_", "residual_", "slots_"))]
    ].mean()
    summ.reset_index().to_csv(OUT / "summary.csv", index=False)
    c = criteria(d, primary)
    c.to_csv(OUT / "criteria.csv", index=False)
    print(c.round(4).to_string(index=False))
    p = c[c.primary]
    adopt = bool(len(p) == 4 and p["all"].all())
    print(f"== FLEET adopted (primary restore {primary}, vs a and b, both arms): {adopt}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "A")
