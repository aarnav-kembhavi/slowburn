"""D89 review tables (exploratory_dev_v3, DEV only; existing D89 rows, check half, no new run).

1. absolute work lost and recovery per policy at N3 (and N1 for reference), by budget (pooled
   over rates and arms), by benign rate (pooled over budgets and arms), and per arm x budget x
   rate; machine-cluster bootstrap CIs (cluster = arm x machine);
2. SlowBurn minus each policy, relative work lost sum(SB) / sum(policy) - 1, paired CI
   (method_v2.policy_vs_policy), same groupings, at N3 and N1;
3. count K4 / K6: not in the D89 rows (run at count K8 / K12 and sbmax K8 / K12 only).

    uv run python -m slowburn.bench.d89_review
"""

from __future__ import annotations

import pandas as pd

from slowburn.bench import method_v2 as mv
from slowburn.bench.byte_matched import D89_POLICIES
from slowburn.bench.byte_matched_report import REC, WL
from slowburn.bench.d82_precheck import halves
from slowburn.bench.d89_report import ARMS, OUT, load
from slowburn.bench.stats import cluster_bootstrap_ratio

REV = OUT / "review"
RULES = ("N3", "N1")
GROUPS = {"by_budget": ["d81_level"], "by_rate": ["benign_invalid_rate"],
          "by_arm_budget_rate": ["arm_name", "d81_level", "benign_invalid_rate"]}  # fmt: skip


def main() -> None:
    REV.mkdir(parents=True, exist_ok=True)
    d = pd.concat([load(a) for a in ARMS], ignore_index=True)
    h = halves(d)
    d["half"] = [h[k] for k in zip(d.world, d.true_start, d.rep, strict=True)]
    x = d[(d.half == "check") & ~d.d81_infeasible.astype(bool) & d.d89_rule.isin(RULES)].copy()
    x["cl"] = x.arm_name + "|" + x.world.astype(str) + "|" + x.true_start.astype(str) + "|" + \
        x.rep.astype(str)
    present = sorted(d.d81_level.unique())
    for name, by in GROUPS.items():
        rows = []
        for (rule, pol, *g), y in x.groupby(["d89_rule", "policy", *by]):
            wl = cluster_bootstrap_ratio(y[WL], [1] * len(y), y.cl)
            rc = cluster_bootstrap_ratio(y[REC], [1] * len(y), y.cl)
            rows.append({"rule": rule, "policy": pol, **dict(zip(by, g, strict=True)),
                         "rows": len(y), "work_lost_h": wl[0], "wl_lo": wl[1], "wl_hi": wl[2],
                         "recovery": rc[0], "rec_lo": rc[1], "rec_hi": rc[2]})  # fmt: skip
        pd.DataFrame(rows).to_csv(REV / f"t1_absolute_{name}.csv", index=False)
        y = x.copy()  # pairing frame: cell folded into the budget key, cluster per arm x machine
        y["budget"] = y.arm_name + "|" + y.d81_level
        y["budget_kind"] = y.d81_arm
        y["world"] = y.arm_name + "|" + y.world.astype(str)
        cmp = []
        for (rule, *g), z in y.groupby(["d89_rule", *by]):
            for p in D89_POLICIES[1:]:
                if z[z.policy == p].empty:  # policy infeasible on every machine of the cell
                    cmp.append(pd.DataFrame([{"policy": "slowburn", "vs": p, "pairs": 0,
                                              "rule": rule, **dict(zip(by, g, strict=True))}]))
                    continue
                r = mv.policy_vs_policy(z, "slowburn", p)
                cmp.append(r.assign(rule=rule, **dict(zip(by, g, strict=True))))
        pd.concat(cmp, ignore_index=True).to_csv(REV / f"t2_slowburn_minus_{name}.csv",
                                                 index=False)  # fmt: skip
    (REV / "t3_k4_k6.txt").write_text(
        "count K4 and K6 rows: not in the D89 outputs. The D89 runs used count K8 / K12 and "
        f"sbmax K8 / K12 only (levels present: {present}); N3 at K4 / K6 needs a new run.\n")
    print("written", sorted(p.name for p in REV.iterdir()))


if __name__ == "__main__":
    main()
