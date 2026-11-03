"""D82 stage 1 precheck report (OPEN_QUESTIONS 2026-11-04; exploratory_dev_v3, DEV only).

SlowBurn at assumed discovery bound M in {60, 75, 90}; benign rates 0, 0.01, 0.05; both arms;
cells count_K8, count_K12, sbmax_K8, sbmax_K12. M = 60 rows are the existing D81 rows; M = 75 and
90 are the run-m runs. Fit and check halves by machine (ed3f273). Tables only:
* per half, arm, rate, cell and M: mean work lost and recovery, rows, infeasible machines, K';
* M = 75 and M = 90 against M = 60 with method_v2.policy_vs_policy (paired machine-cluster
  bootstrap, 2000 resamples);
* the kill rule on the fit half: per rate, mean work lost pooled over both arms and the four cells
  (all feasible rows, as pre-registered; the rows feasible at all three M shown alongside).

    uv run python -m slowburn.bench.d82_precheck
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from slowburn.bench import method_v2 as mv
from slowburn.bench.byte_matched import LABEL
from slowburn.bench.byte_matched_report import REC, ROOT, WL

OUT = ROOT / "d82_precheck"
ARMS = ("napierone", "synthetic")
MS = (60, 75, 90)
CELLS = ("count_K8", "count_K12", "sbmax_K8", "sbmax_K12")
MACH = ["world", "true_start", "rep"]
SPLIT_SEED = 82082  # ed3f273


def halves(d: pd.DataFrame) -> dict:
    """{(world, true_start, rep): "fit" | "check"}: machines sorted by (world, rep), permuted with
    default_rng(82082), first half fit (ed3f273)."""
    m = d[MACH].drop_duplicates().sort_values(["world", "rep"]).reset_index(drop=True)
    perm = np.random.default_rng(SPLIT_SEED).permutation(len(m))
    fit = set(perm[: len(m) // 2])
    return {
        tuple(r): ("fit" if i in fit else "check") for i, r in enumerate(m.itertuples(index=False))
    }


def load(arm: str) -> pd.DataFrame:
    sub = ROOT / f"d81_{arm}"
    parts = []
    c = pd.read_csv(sub / "d81_machines_rows.csv.gz", low_memory=False)
    b = pd.read_csv(sub / "d81max_machines_rows.csv.gz", low_memory=False)
    parts.append(pd.concat([c[c.d81_arm == "count"], b[b.d81_arm == "bytes"]]).assign(M=60))
    for M in MS[1:]:
        x = pd.read_csv(sub / f"d82pre_M{M}_machines_rows.csv.gz", low_memory=False)
        if set(x.hp_assumed_discovery_max.dropna().unique()) != {M}:
            raise AssertionError(f"{arm} M={M}: rows carry another assumed discovery bound")
        parts.append(x.assign(M=M))
    d = pd.concat(parts, ignore_index=True)
    d = d[(d.policy == "slowburn") & d.d81_level.isin(CELLS)].copy()
    d["arm_name"] = arm
    return d


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    d = pd.concat([load(a) for a in ARMS], ignore_index=True)
    h = halves(d)
    d["half"] = [h[k] for k in zip(d.world, d.true_start, d.rep, strict=True)]
    d["feasible"] = ~d.d81_infeasible.astype(bool)
    keys = ["half", "arm_name", "benign_invalid_rate", "d81_level", "M"]
    mach = d.drop_duplicates([*keys, "world", "true_start", "rep"])
    f = d[d.feasible]
    t1 = f.groupby(keys).agg(rows=(WL, "size"), work_lost_h=(WL, "mean"), recovery=(REC, "mean"))
    inf = mach.groupby(keys).agg(machines=("feasible", "size"),
                                 infeasible=("feasible", lambda s: int((~s).sum())),
                                 kprime_mean=("d81_kprime", "mean"),
                                 kprime_mode=("d81_kprime", lambda s: s.mode().iloc[0]
                                              if s.notna().any() else np.nan))  # fmt: skip
    t1 = t1.join(inf).reset_index()
    t1.to_csv(OUT / "precheck_cells.csv", index=False)
    kd = (mach[mach.feasible & mach.d81_level.str.startswith("sbmax")]
          .groupby(keys).d81_kprime.value_counts().rename("machines").reset_index())  # fmt: skip
    kd.to_csv(OUT / "precheck_kprime_distribution.csv", index=False)

    x = f.copy()  # pairing frame: M as the "policy", the cell as the budget
    x["policy"] = "M" + x.M.astype(str)
    x["budget"], x["budget_kind"] = x.d81_level, x.d81_arm
    cmp = []
    for (half, arm, rate, cell), g in x.groupby(["half", "arm_name", "benign_invalid_rate",
                                                 "d81_level"]):  # fmt: skip
        for M in MS[1:]:
            r = mv.policy_vs_policy(g, f"M{M}", "M60")
            cmp.append(r.assign(half=half, arm=arm, benign_invalid_rate=rate, d81_level=cell))
    cmp = pd.concat(cmp, ignore_index=True)
    cmp.to_csv(OUT / "precheck_vs_M60.csv", index=False)

    fit = f[f.half == "fit"]
    pooled = fit.groupby(["benign_invalid_rate", "M"])[WL].mean().unstack("M")
    rk = ["arm_name", "benign_invalid_rate", "d81_level", "world", "true_start", "rep",
          "discovery_delay"]  # fmt: skip
    common = fit.groupby(rk).M.transform("nunique") == len(MS)
    pooled_c = fit[common].groupby(["benign_invalid_rate", "M"])[WL].mean().unstack("M")
    lowest = {float(r): int(pooled.loc[r].idxmin()) for r in pooled.index}
    killed = all(m == 60 for m in lowest.values())
    kill = {"label": LABEL, "rule": "fit half; per benign rate, mean SlowBurn work lost pooled "
            "over both arms and the four cells (all feasible rows); killed if M = 60 lowest at "
            "every rate", "pooled_work_lost_h": {str(r): {str(m): float(v) for m, v in row.items()}
                                                 for r, row in pooled.iterrows()},
            "pooled_work_lost_h_common_rows": {str(r): {str(m): float(v) for m, v in row.items()}
                                               for r, row in pooled_c.iterrows()},
            "lowest_M_per_rate": {str(k): v for k, v in lowest.items()},
            "d82_killed_by_precheck": killed}  # fmt: skip
    (OUT / "precheck_kill.json").write_text(json.dumps(kill, indent=1))
    print(json.dumps(kill, indent=1))


if __name__ == "__main__":
    main()
