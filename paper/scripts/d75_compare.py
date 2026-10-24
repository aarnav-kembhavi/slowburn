"""D75: NapierOne arms of D67 and D72 on the v1 (D67) pools vs the v2 (enlarged) pools, side by
side. Same seeds, machines, grid and detector; only the benign content pool differs. Run from
the repo root after both v2 runs:

    uv run python paper/scripts/d75_compare.py
"""

import sys
from pathlib import Path

import pandas as pd

from slowburn.bench import method_v2 as mv

sys.path.insert(0, str(Path(__file__).parent))
import d72_report as d72  # noqa: E402

OUT = Path("results/dev_d75_compare")
D67 = {"v1": "results/dev_d67_full_napierone", "v2": "results/dev_d67_full_napierone_v2pool"}
D72 = {"v1": "results/dev_d72_bytes_napierone", "v2": "results/dev_d72_bytes_napierone_v2pool"}
pd.set_option("display.width", 250, "display.max_columns", 40)


def d67(pool, run):
    d = pd.read_csv(Path(run) / "tuning_sweep.csv", low_memory=False)
    d = d[(d.variant == "method_v2_w075_vsnap") & (d.budget_kind == "count")]
    rows = []
    for base in ("gfs", "tower_of_hanoi"):
        r = mv.policy_vs_policy(d, "slowburn", base, ())
        rows.append(r.assign(claim="C2", vs=base))
    c3 = mv.evidence_reduction(d).assign(claim="C3'", vs="prior_only")
    c3["recovery_diff"] = c3.recovery_delta
    c1 = d.groupby("policy").clean_recovery.mean()
    out = pd.concat(rows + [c3], ignore_index=True).assign(pool=pool)
    return out, c1.rename(pool)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    claims, c1 = [], []
    for pool, run in D67.items():
        a, b = d67(pool, run)
        claims.append(a)
        c1.append(b)
    claims = pd.concat(claims, ignore_index=True)
    claims.to_csv(OUT / "d67_claims_v1_vs_v2.csv", index=False)
    c1 = pd.concat(c1, axis=1)
    c1.to_csv(OUT / "d67_c1_recovery_v1_vs_v2.csv")
    print("== D67 NapierOne arm: C1 recovery by policy")
    print(c1.round(4).to_string())
    print("== D67 NapierOne arm: C2 (vs default GFS / ToH) and C3' (vs prior-only)")
    cols = [c for c in claims.columns if c in ("pool", "claim", "vs", "pairs", "recovery_diff",
            "work_lost_rel", "work_lost_rel_lo", "work_lost_rel_hi", "rel_change", "rel_lo",
            "rel_hi", "rec_diff")]  # fmt: skip
    print(claims[cols].round(4).to_string(index=False))
    summ, crit = [], []
    for pool, run in D72.items():
        d = d72.load(run, None)
        d = d[d.policy.isin(d72.POL)]
        s = d.groupby("policy").apply(d72.summary, include_groups=False).reset_index()
        summ.append(s.assign(pool=pool))
        for pol in d72.REQUIRED:
            crit += [dict(r, pool=pool) for r in d72.criteria(d[d.policy == pol], "napierone", pol)]
    summ, crit = pd.concat(summ, ignore_index=True), pd.DataFrame(crit)
    summ.to_csv(OUT / "d72_summary_v1_vs_v2.csv", index=False)
    crit.to_csv(OUT / "d72_criteria_v1_vs_v2.csv", index=False)
    keep = ["pool", "policy"] + [f"{k}_{m}" for m in d72.M for k in ("rec", "res", "fwl")]
    print("== D72 NapierOne arm: restores A-E (recovery / residual files / per-file work lost h)")
    print(summ[summ.policy.isin(d72.REQUIRED)][keep].round(3).to_string(index=False))
    print(crit[["pool", "scope", "vs", "a_recovery", "b_residual", "c_work_lost", "all",
                "pooled_rec_diff", "pooled_fwl_rel"]].round(4).to_string(index=False))  # fmt: skip


if __name__ == "__main__":
    main()
