"""Mechanism check for the truncated-png effect (team request 2026-10-26; existing outputs only):
per world and pool (v2 scored, v2_notrunc unscored), whole-system work lost per policy, SlowBurn's
start estimate error (estimated_start - true_start) and restore-side measures. Count budgets,
w 0.75, verify_snap. Run from the repo root:

    uv run python paper/scripts/png_mechanism.py
"""

from pathlib import Path

import pandas as pd

RUNS = {"v2": "results/dev_d67_full_napierone_v2pool",
        "v2_notrunc": "results/dev_d67_full_napierone_v2notrunc"}  # fmt: skip
OUT = Path("results/dev_png_sensitivity")
pd.set_option("display.width", 250, "display.max_columns", 30)


def main():
    rows = []
    for pool, run in RUNS.items():
        d = pd.read_csv(Path(run) / "tuning_sweep.csv", low_memory=False)
        d = d[(d.variant == "method_v2_w075_vsnap") & (d.budget_kind == "count")]
        rows.append(d.assign(pool=pool))
    d = pd.concat(rows, ignore_index=True)
    d["est_err"] = d.estimated_start - d.true_start
    d["abs_err"] = d.est_err.abs()
    wl = d.pivot_table(index=["world", "pool"], columns="policy",
                       values="work_lost_whole_system_hours", aggfunc="mean")  # fmt: skip
    sb = d[d.policy == "slowburn"].groupby(["world", "pool"]).agg(
        start_err_mean=("est_err", "mean"), start_err_abs=("abs_err", "mean"),
        est_before_start=("est_err", lambda e: (e < 0).mean()),
        restore_depth_days=("restore_depth_days", "mean"),
        snapshots_scanned=("snapshots_scanned", "mean"),
        start_gap_days=("start_gap_days", "mean"), recovery=("clean_recovery", "mean"))
    gfs = d[d.policy == "gfs"].groupby(["world", "pool"]).agg(
        gfs_snapshots_scanned=("snapshots_scanned", "mean"),
        gfs_start_gap_days=("start_gap_days", "mean"))
    t = pd.concat([wl[["slowburn", "prior_only", "gfs", "tower_of_hanoi"]], sb, gfs], axis=1)
    t.to_csv(OUT / "mechanism_by_world.csv")
    print(t.round(2).to_string())


if __name__ == "__main__":
    main()
