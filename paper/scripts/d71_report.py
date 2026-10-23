"""D71 items 1 and 2: oracle gap (verify_snap vs oracle snapshot restore), restore-choice
diagnosis, and the per-file oracle ceiling. DEV, descriptive. Run from the repo root:

    uv run python paper/scripts/d71_report.py
"""

from pathlib import Path

import numpy as np
import pandas as pd

from slowburn.bench.method_v2 import _clusters
from slowburn.bench.stats import cluster_bootstrap_ratio as cbr

R = Path("results/dev_d71_oracle_gap")
QS = (0.0, 0.2, 0.5, 1.0)
POL = ("slowburn", "prior_only", "shamir_exact", "shamir_rr", "shamir_recursive", "gfs",
       "tower_of_hanoi", "toh_eqh", "gfs_eqh")  # fmt: skip
CAUSES = ("missed_damage", "false_flag", "gated_out", "residual_outside_scope", "other")
pd.set_option("display.width", 250, "display.max_columns", 40, "display.max_rows", 2000)


def load():
    d = pd.read_csv(R / "tuning_sweep.csv", low_memory=False)
    d = d[d.budget_kind == "count"].copy()
    d["q"] = d.detect_prob.astype(float)
    d = d[d.q.isin(QS)]
    d["cl"] = _clusters(d)
    return d


def gap(x):
    """(a) verify_snap vs (b) oracle snapshot vs (c) per-file oracle on the same rows."""
    ra, rb, rc = x.clean_recovery, x.oracle_clean_recovery, x.filoracle_clean_recovery
    wa, wb = x.work_lost_whole_system_hours, x.oracle_work_lost_whole_system_hours
    fa, fb, fc = (x.work_lost_selective_file_hours, x.oracle_work_lost_selective_file_hours,
                  x.filoracle_work_lost_selective_file_hours)  # fmt: skip
    one = np.ones(len(x))
    rec = cbr(ra - rb, one, x.cl)
    wl = cbr(wa - wb, wb, x.cl)
    rec_c = cbr(ra - rc, one, x.cl)
    return pd.Series({
        "rows": len(x), "rec_a": ra.mean(), "rec_b": rb.mean(), "rec_c": rc.mean(),
        "rec_gap_ab": rec[0], "rec_gap_ab_lo": rec[1], "rec_gap_ab_hi": rec[2],
        "wl_a_h": wa.mean(), "wl_b_h": wb.mean(),
        "wl_rel_ab": wl[0], "wl_rel_ab_lo": wl[1], "wl_rel_ab_hi": wl[2],
        "rec_gap_ac": rec_c[0], "rec_gap_ac_lo": rec_c[1], "rec_gap_ac_hi": rec_c[2],
        "filewl_a_h": fa.mean(), "filewl_b_h": fb.mean(), "filewl_c_h": fc.mean()})  # fmt: skip


def diagnosis(x):
    held = x.diag_clean_held == 1
    miss = held & (x.restore_point != x.newest_clean_kept)
    fail = held & (x.clean_recovery == 0)
    one = np.ones(len(x))
    out = {"rows": len(x), "clean_held": held.mean()}
    for name, ind in (("not_picked", miss), ("failed_despite_held", fail)):
        e = cbr(ind.astype(float), one, x.cl)
        out |= {name: e[0], f"{name}_lo": e[1], f"{name}_hi": e[2]}
    for c in CAUSES:
        ind = (x.diag_cause == c) & held
        e = cbr(ind.astype(float), one, x.cl)
        out |= {f"cause_{c}": e[0], f"cause_{c}_lo": e[1], f"cause_{c}_hi": e[2],
                f"fail_{c}": (ind & (x.clean_recovery == 0)).mean()}  # fmt: skip
    out["false_flag_day0"] = ((x.diag_cause == "false_flag") & (x.diag_false_flag_day0 == 1)).mean()
    return pd.Series(out)


def table(d, by, f):
    return d.groupby(by, sort=False).apply(f, include_groups=False).reset_index()


def main():
    d = load()
    out = {}
    out["gap_full_by_q"] = table(d, ["policy", "q"], gap)
    out["gap_full_by_q_K"] = table(d, ["policy", "q", "budget"], gap)
    out["gap_worlds_by_q"] = table(d, ["policy", "q", "world"], gap)
    out["gap_worlds_by_q_K"] = table(d, ["policy", "q", "world", "budget"], gap)
    out["diag_full_by_q"] = table(d, ["policy", "q"], diagnosis)
    out["diag_full_by_q_K"] = table(d, ["policy", "q", "budget"], diagnosis)
    out["diag_worlds_by_q"] = table(d, ["policy", "q", "world"], diagnosis)
    for k, t in out.items():
        t.to_csv(R / f"{k}.csv", index=False)
    g = out["gap_full_by_q"]
    g["policy"] = pd.Categorical(g.policy, POL, ordered=True)
    print("== oracle gap, full grid, pooled K (a = verify_snap, b = oracle snapshot, c = oracle per file)")
    print(g.sort_values(["policy", "q"]).round(4).to_string(index=False))
    t = out["diag_full_by_q"]
    t["policy"] = pd.Categorical(t.policy, POL, ordered=True)
    print("== restore-choice diagnosis, full grid, pooled K (shares of all rows)")
    print(t.sort_values(["policy", "q"]).round(4).to_string(index=False))


if __name__ == "__main__":
    main()
