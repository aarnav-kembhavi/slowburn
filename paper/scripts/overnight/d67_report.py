"""D67: C1 / C2 / C3' side by side: abstract q (current claims), synthetic bytes + synthetic
detector, NapierOne bytes + NapierOne detector. Count budgets, then byte budgets (D71 item 4:
replaces the ad hoc byte-budget comparison of the overnight report), w 0.75, verify_snap."""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, "C:/PROJECTS/ISM")
from slowburn.bench import method_v2 as mv  # noqa: E402

OUT = Path("results/dev_d67_compare"); OUT.mkdir(exist_ok=True)
pd.set_option("display.width", 220, "display.max_columns", 30)
ARMS = {"abstract_q": "dev_d64a_full", "synthetic_bytes": "dev_d67_full_synthetic",
        "napierone_bytes": "dev_d67_full_napierone"}
data, bdata = {}, {}
for arm, run in ARMS.items():
    d = pd.read_csv(f"results/{run}/tuning_sweep.csv", low_memory=False)
    d = d[d.variant == "method_v2_w075_vsnap"]
    b = d[d.budget_kind == "bytes"].copy()
    for c in ("detect_prob", "benign_invalid_rate"):  # pairing keys: NaN never matches NaN
        if c in b:
            b[c] = b[c].fillna(-1)
    d = d[d.budget_kind == "count"]
    assert len(d) and len(b), arm
    data[arm], bdata[arm] = d, b
c1 = pd.concat([d.groupby(["world", "policy"]).agg(recovery=("clean_recovery", "mean"),
                work_lost_h=("work_lost_whole_system_hours", "mean"), rows=("clean_recovery", "size"))
                .reset_index().assign(arm=a) for a, d in data.items()])
c1.to_csv(OUT / "c1_by_world.csv", index=False)
print("== C1: recovery by world (count budgets)")
print(c1.pivot_table(index=["world", "policy"], columns="arm", values="recovery").round(4).to_string())
pooled = pd.concat([d.groupby("policy").agg(recovery=("clean_recovery", "mean"),
                    work_lost_h=("work_lost_whole_system_hours", "mean")).reset_index().assign(arm=a)
                    for a, d in data.items()])
pooled.to_csv(OUT / "c1_pooled.csv", index=False)
print("== pooled"); print(pooled.pivot_table(index="policy", columns="arm", values=["recovery", "work_lost_h"]).round(4).to_string())
rows = []
for a, d in data.items():
    for base in ("gfs", "tower_of_hanoi"):
        for by in ((), ("world",)):
            rows.append(mv.policy_vs_policy(d, "slowburn", base, by).assign(arm=a))
c2 = pd.concat(rows, ignore_index=True); c2.to_csv(OUT / "c2_slowburn_vs_fixed.csv", index=False)
print("== C2: SlowBurn vs fixed schedules (work lost rel, recovery diff)")
print(c2[["arm", "vs", "world", "pairs", "recovery_diff", "recovery_diff_lo", "recovery_diff_hi", "work_lost_rel", "work_lost_rel_lo", "work_lost_rel_hi"]].round(4).to_string(index=False))
c3 = pd.concat([pd.concat([mv.evidence_reduction(d).assign(world="all"), mv.evidence_reduction(d, ("world",))]).assign(arm=a) for a, d in data.items()], ignore_index=True)
c3.to_csv(OUT / "c3_evidence_reduction.csv", index=False)
print("== C3': SlowBurn vs prior-only"); print(c3.round(4).to_string(index=False))

# byte budgets (14/30/90-day keep-last multipliers): C1 pooled, C2, C3'
b1 = pd.concat([d.groupby("policy").agg(recovery=("clean_recovery", "mean"),
                work_lost_h=("work_lost_whole_system_hours", "mean")).reset_index().assign(arm=a)
                for a, d in bdata.items()])
b1.to_csv(OUT / "bytes_c1_pooled.csv", index=False)
print("== byte budgets: pooled")
print(b1.pivot_table(index="policy", columns="arm", values=["recovery", "work_lost_h"]).round(4).to_string())
rows = []
for a, d in bdata.items():
    for base in ("prior_only", "gfs", "tower_of_hanoi"):
        for by in ((), ("world",), ("budget",)):
            rows.append(mv.policy_vs_policy(d, "slowburn", base, by).assign(arm=a))
b2 = pd.concat(rows, ignore_index=True); b2.to_csv(OUT / "bytes_slowburn_vs.csv", index=False)
print("== byte budgets: SlowBurn vs prior-only / GFS / ToH")
print(b2[["arm", "vs", "world", "budget", "pairs", "recovery_diff", "recovery_diff_lo", "recovery_diff_hi",
          "work_lost_rel", "work_lost_rel_lo", "work_lost_rel_hi"]].round(4).to_string(index=False))
