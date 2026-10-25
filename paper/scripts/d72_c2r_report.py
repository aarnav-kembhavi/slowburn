"""D72-C2R: C2 restated against Bar-On recursive / round robin and the equal-horizon GFS / Tower
of Hanoi configurations, on synthetic and NapierOne bytes (OPEN_QUESTIONS D72-C2R). Reads the D72
byte-arm outputs; no new simulation. Paired, machine-cluster bootstrap CIs. Run from the repo root:

    uv run python paper/scripts/d72_c2r_report.py
"""

from pathlib import Path

import pandas as pd

from slowburn.bench import method_v2 as mv

OUT = Path("results/dev_d72_c2r")
ARMS = {"synthetic_bytes": "results/dev_d72_bytes_synthetic",
        "napierone_bytes": "results/dev_d72_bytes_napierone_v2pool",  # D75: v2 is the source
        "napierone_bytes_v1pool": "results/dev_d72_bytes_napierone"}  # sensitivity row  # fmt: skip
D67 = Path("results/dev_d67_compare/c2_slowburn_vs_fixed.csv")
BASES = ("gfs", "tower_of_hanoi", "shamir_recursive", "shamir_rr", "gfs_eqh", "toh_eqh")
COLS = ["arm", "vs", "world", "budget", "pairs", "recovery_diff", "recovery_diff_lo",
        "recovery_diff_hi", "work_lost_rel", "work_lost_rel_lo", "work_lost_rel_hi"]  # fmt: skip
pd.set_option("display.width", 250, "display.max_columns", 30, "display.max_rows", 500)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    for arm, run in ARMS.items():
        d = pd.read_csv(Path(run) / "tuning_sweep.csv", low_memory=False)
        d = d[(d.variant == "method_v2_w075_vsnap") & (d.budget_kind == "count")]
        for base in BASES:
            for by in ((), ("world",), ("budget",)):
                rows.append(mv.policy_vs_policy(d, "slowburn", base, by).assign(arm=arm))
    c = pd.concat(rows, ignore_index=True)
    for col in ("world", "budget"):
        c[col] = c[col].fillna("all") if col in c else "all"
    pooled = (c.world == "all") & (c.budget == "all")
    c["holds"] = pooled & (c.work_lost_rel_hi < 0) & (c.recovery_diff_hi >= 0)
    c.to_csv(OUT / "c2_restated.csv", index=False)
    print("== C2 restated: SlowBurn vs each baseline, pooled (work lost rel, recovery diff)")
    print(c[pooled][COLS + ["holds"]].round(4).to_string(index=False))
    print("== by world")
    print(c[(c.world != "all")][COLS].round(4).to_string(index=False))
    print("== by budget")
    print(c[(c.budget != "all")][COLS].round(4).to_string(index=False))
    if D67.exists():  # sanity: same seed and machines as D67, so GFS / ToH must reproduce
        old = pd.read_csv(D67)
        old["arm"] = old.arm.replace({"napierone_bytes": "napierone_bytes_v1pool"})  # D67 = v1
        old = old[old.arm.isin(ARMS) & old.world.isna()][["arm", "vs", "work_lost_rel"]]
        m = old.merge(c[pooled][["arm", "vs", "work_lost_rel"]], on=["arm", "vs"],
                      suffixes=("_d67", "_d72"))  # fmt: skip
        m["match"] = (m.work_lost_rel_d67 - m.work_lost_rel_d72).abs() < 1e-9
        m.to_csv(OUT / "d67_reproduction.csv", index=False)
        print("== D67 reproduction check")
        print(m.to_string(index=False))


if __name__ == "__main__":
    main()
