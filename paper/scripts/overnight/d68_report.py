"""D68 equal-horizon diagnostic: toh_eqh / gfs_eqh vs SlowBurn and prior-only, paired, CIs."""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, "C:/PROJECTS/ISM")
from slowburn.bench import method_v2 as mv  # noqa: E402

R = Path("results/dev_d68_equal_horizon")
pd.set_option("display.width", 240, "display.max_columns", 30)
d = pd.read_csv(R / "tuning_sweep.csv", low_memory=False)
d = d[d.budget_kind == "count"]
d["q"] = d.detect_prob.astype(float)
print("rows per policy x K:"); print(d.groupby(["policy", "budget"]).size().unstack().fillna(0).astype(int).to_string())
COLS = ["policy", "vs", "pairs", "clean_recovery_a", "clean_recovery_b", "recovery_diff", "recovery_diff_lo",
        "recovery_diff_hi", "work_lost_rel", "work_lost_rel_lo", "work_lost_rel_hi"]
out = []
for grid, x in (("full", d), ("worlds_q0", d[d.q == 0.0]), ("worlds_q1", d[d.q == 1.0])):
    for a in ("toh_eqh", "gfs_eqh"):
        for b in ("slowburn", "prior_only"):
            for by in ((), ("budget",), ("world",)):
                t = mv.policy_vs_policy(x, a, b, by)
                out.append(t.assign(grid=grid))
t = pd.concat(out, ignore_index=True)
t.to_csv(R / "eqh_vs_slowburn_prior.csv", index=False)
for grid in ("full", "worlds_q0", "worlds_q1"):
    print(f"== {grid}")
    print(t[t.grid == grid][["budget", "world", *COLS]].round(4).to_string(index=False))
