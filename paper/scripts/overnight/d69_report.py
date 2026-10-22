"""D69: Bar-On et al. schedules vs SlowBurn, prior-only, ToH, GFS; verify_snap and oracle restore."""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, "C:/PROJECTS/ISM")
from slowburn.bench import method_v2 as mv  # noqa: E402

pd.set_option("display.width", 240, "display.max_columns", 30)
SH = ("shamir_exact", "shamir_rr", "shamir_recursive")
REFS = ("slowburn", "prior_only", "tower_of_hanoi", "gfs")
REST = {"verify_snap": ("clean_recovery", "work_lost_whole_system_hours"),
        "oracle": ("oracle_clean_recovery", "oracle_work_lost_whole_system_hours")}


def load(run):
    d = pd.read_csv(f"results/{run}/tuning_sweep.csv", low_memory=False)
    d = d[d.budget_kind == "count"].copy()
    d["q"] = d.detect_prob.astype(float)
    return d


def means(d, by):
    rows = []
    for rest, (rc, wc) in REST.items():
        g = d.groupby([*by, "policy"]).agg(recovery=(rc, "mean"), work_lost_h=(wc, "mean"), rows=(rc, "size")).reset_index()
        rows.append(g.assign(restore=rest))
    return pd.concat(rows, ignore_index=True)


def compare(d, by, label):
    out = []
    for rest, (rc, wc) in REST.items():
        for a in SH:
            for b in REFS:
                if a in set(d.policy):
                    out.append(mv.policy_vs_policy(d, a, b, by, rec=rc, wl=wc).assign(restore=rest, grid=label))
    return pd.concat(out, ignore_index=True)


grids = {"full": ("dev_d69_full", lambda d: d), "worlds_q0": ("dev_d69_full", lambda d: d[d.q == 0.0]),
         "worlds_q1": ("dev_d69_full", lambda d: d[d.q == 1.0]), "worst": ("dev_d69_worst", lambda d: d),
         "delay_q0": ("dev_d69_delay_grid", lambda d: d[d.q == 0.0]),
         "delay_q1": ("dev_d69_delay_grid", lambda d: d[d.q == 1.0])}
cache = {}
allm, allc = [], []
for label, (run, f) in grids.items():
    if not Path(f"results/{run}/tuning_sweep.csv").exists():
        print(f"!! {run} missing; {label} skipped"); continue
    d = f(cache.setdefault(run, load(run)))
    by_extra = ("variant",) if run == "dev_d69_delay_grid" else ()
    allm.append(means(d, ("budget", *by_extra)).assign(grid=label))
    allc.append(compare(d, (), label)); allc.append(compare(d, ("budget",), label))
    if by_extra:
        allc.append(compare(d, by_extra, label))
        und = d[d.discovery_delay > d.hp_assumed_discovery_max]
        if len(und):
            allc.append(compare(und, (), label + "_underestimated"))
            allm.append(means(und, ("budget",)).assign(grid=label + "_underestimated"))
M = pd.concat(allm, ignore_index=True); C = pd.concat(allc, ignore_index=True)
Path("results/dev_d69_compare").mkdir(exist_ok=True)
M.to_csv("results/dev_d69_compare/means.csv", index=False); C.to_csv("results/dev_d69_compare/paired.csv", index=False)
for label in M.grid.unique():
    m = M[M.grid == label]
    idx = [c for c in ("variant", "budget") if c in m and m[c].notna().any()] + ["policy"]
    print(f"== means {label}")
    print(m.pivot_table(index=idx, columns="restore", values=["recovery", "work_lost_h"]).round(4).to_string())
cols = ["grid", "restore", "budget", "policy", "vs", "pairs", "recovery_diff", "recovery_diff_lo", "recovery_diff_hi", "work_lost_rel", "work_lost_rel_lo", "work_lost_rel_hi"]
pooled = C.budget.isna() & (C["variant"].isna() if "variant" in C else True)
print("== paired, pooled over K"); print(C[pooled][cols].round(4).to_string(index=False))
