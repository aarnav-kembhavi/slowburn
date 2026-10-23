"""D72 report: per-file restore methods A (verify_snap), B (per-file walk-back), C (monotone
changepoint), D (per-file oracle), E (oracle snapshot) on the same rows. DEV. Criteria as
pre-registered (OPEN_QUESTIONS D72 + amendment). Run from the repo root:

    uv run python paper/scripts/d72_report.py
"""

from pathlib import Path

import numpy as np
import pandas as pd

from slowburn.bench.method_v2 import _clusters
from slowburn.bench.stats import cluster_bootstrap_ratio as cbr

OUT = Path("results/dev_d72_report")
UNITS = {  # unit -> (run dir, scored q values or None for a trained-detector arm)
    "full": ("results/dev_d72_full", (0.2, 0.5, 1.0)),
    "worst": ("results/dev_d72_worst", (0.2, 0.5, 1.0)),
    "bytes_synthetic": ("results/dev_d72_bytes_synthetic", None),
    "bytes_napierone": ("results/dev_d72_bytes_napierone", None),
}
POL = ("slowburn", "prior_only", "shamir_recursive", "shamir_rr", "gfs", "tower_of_hanoi")
REQUIRED = ("slowburn", "shamir_recursive")  # D72 amendment 2, option (iii); others reported only
M = "ABCDE"
pd.set_option("display.width", 250, "display.max_columns", 60, "display.max_rows", 2000)


def load(run, qs):
    d = pd.read_csv(Path(run) / "tuning_sweep.csv", low_memory=False)
    d = d[d.budget_kind == "count"].copy()
    if qs is None:
        d["q"] = "detector"
    else:
        d["q"] = d.detect_prob.astype(float)
        d = d[d.q.isin((0.0, *qs))]
    if "world" not in d:
        d["world"] = "fixed_starts"
    d["cl"] = _clusters(d)
    return d


def summary(x):
    out = {"rows": len(x)}
    for m in M:
        out |= {f"rec_{m}": x[f"pf{m}_clean_recovery"].mean(),
                f"res_{m}": x[f"pf{m}_residual_damaged_files"].mean(),
                f"fwl_{m}": x[f"pf{m}_work_lost_file_hours"].mean(),
                f"wwl_{m}": x[f"pf{m}_work_lost_whole_hours"].mean()}  # fmt: skip
    out["wwl_A_snapshot"] = x.work_lost_whole_system_hours.mean()  # A's own whole-system metric
    for m in "BC":  # share of the oracle gap A - D closed
        for g, col in (("all", "work_lost_file_hours"), ("zip", "work_lost_file_hours_zip"),
                       ("nonzip", "work_lost_file_hours_nonzip")):  # fmt: skip
            a, d, z = (x[f"pf{k}_{col}"].mean() for k in ("A", m, "D"))
            gap = a - x[f"pfD_{col}"].mean()
            out[f"gapshare_fwl_{g}_{m}"] = (a - d) / gap if gap else np.nan
        for g, col in (("all", "residual_damaged_files"), ("zip", "residual_zip"),
                       ("nonzip", "residual_nonzip")):  # fmt: skip
            a, d = x[f"pfA_{col}"].mean(), x[f"pf{m}_{col}"].mean()
            gap = a - x[f"pfD_{col}"].mean()
            out[f"gapshare_res_{g}_{m}"] = (a - d) / gap if gap else np.nan
    return pd.Series(out)


def paired(x, ref):
    one = np.ones(len(x))
    c = x.pfC_clean_recovery - x[f"pf{ref}_clean_recovery"]
    r = x.pfC_residual_damaged_files - x[f"pf{ref}_residual_damaged_files"]
    wa, wb = x.pfC_work_lost_file_hours, x[f"pf{ref}_work_lost_file_hours"]
    e_rec, e_res = cbr(c, one, x.cl), cbr(r, one, x.cl)
    e_wl = cbr(wa - wb, wb, x.cl) if wb.sum() > 0 else (np.nan,) * 3
    return pd.Series({"rows": len(x), "rec_diff": e_rec[0], "rec_lo": e_rec[1], "rec_hi": e_rec[2],
                      "res_diff": e_res[0], "res_lo": e_res[1], "res_hi": e_res[2],
                      "fwl_rel": e_wl[0], "fwl_lo": e_wl[1], "fwl_hi": e_wl[2],
                      "fwl_diff_h": float((wa - wb).mean())})  # fmt: skip


def criteria(d, unit, scope):
    """Adoption criteria a-c for C vs A and vs B, per scored q, on the rows of ``scope``."""
    rows = []
    for q in sorted(d.q.unique(), key=str):
        if q == 0.0:
            continue  # reported, not scored
        x = d[d.q == q]
        for ref in "AB":
            pooled = paired(x, ref)
            worlds = x.groupby("world").apply(paired, ref, include_groups=False)
            a = bool((worlds.rec_lo >= -0.01).all())
            b = bool(pooled.res_hi <= 0)
            c = bool(pooled.fwl_diff_h < 0) and int((worlds.fwl_diff_h < 0).sum()) >= min(
                3, len(worlds)
            )
            rows.append({"unit": unit, "scope": scope, "q": q, "vs": ref, "a_recovery": a,
                         "b_residual": b, "c_work_lost": c, "all": a and b and c,
                         "worlds_lower_wl": int((worlds.fwl_diff_h < 0).sum()),
                         "n_worlds": len(worlds), "min_world_rec_lo": worlds.rec_lo.min(),
                         **pooled.add_prefix("pooled_").to_dict()})  # fmt: skip
    return rows


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    summ, crit = [], []
    for unit, (run, qs) in UNITS.items():
        if not (Path(run) / "tuning_sweep.csv").exists():
            print(f"missing {run}")
            continue
        d = load(run, qs)
        d = d[d.policy.isin(POL)]  # eqh policies (byte arms) are for D72-C2R only
        s = d.groupby(["policy", "q"]).apply(summary, include_groups=False).reset_index()
        s.insert(0, "unit", unit)
        summ.append(s)
        for pol in POL:
            crit += criteria(d[d.policy == pol], unit, pol)
        crit += criteria(d, unit, "all_policies")
    s, c = pd.concat(summ), pd.DataFrame(crit)
    s.to_csv(OUT / "summary.csv", index=False)
    c["required"] = c.scope.isin(REQUIRED)
    c.to_csv(OUT / "criteria.csv", index=False)
    v = c[c.required].groupby(["unit", "q", "vs"])["all"].agg(["all", "size"]).reset_index()
    v = v.rename(columns={"all": "adopt_passes", "size": "required_policies"})
    v.to_csv(OUT / "verdict.csv", index=False)
    print(s.round(3).to_string(index=False))
    print(c[["unit", "scope", "q", "vs", "a_recovery", "b_residual", "c_work_lost", "all",
             "pooled_rec_diff", "pooled_res_diff", "pooled_fwl_rel", "worlds_lower_wl"]]
          .round(4).to_string(index=False))  # fmt: skip
    print("== verdict (criteria a-c must pass under SlowBurn AND Bar-On recursive)")
    print(v.to_string(index=False))


if __name__ == "__main__":
    main()
