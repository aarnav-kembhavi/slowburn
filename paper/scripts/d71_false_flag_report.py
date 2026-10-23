"""D71 item 3 report: benign flag rates from d71_false_flags.py output. DEV, descriptive.

    uv run python paper/scripts/d71_false_flag_report.py
"""

from pathlib import Path

import pandas as pd

R = Path("results/dev_d71_false_flags")
pd.set_option("display.width", 250, "display.max_columns", 40, "display.max_rows", 500)


def main():
    v = pd.read_csv(R / "versions.csv.gz")
    s = pd.read_csv(R / "clean_snapshots.csv")
    b = v[v.version != "damaged"]
    out = {}
    out["rate_by_arm_version"] = (v.groupby(["arm", "version"]).flagged
                                  .agg(["size", "mean"]).reset_index())  # fmt: skip
    out["rate_by_arm_rate_version"] = (v.groupby(["arm", "benign_invalid_rate", "version"]).flagged
                                       .agg(["size", "mean"]).reset_index())  # fmt: skip
    out["rate_by_arm_type"] = (b.groupby(["arm", "file_type", "version"]).flagged
                               .agg(["size", "mean"]).reset_index())  # fmt: skip
    m = b.groupby(["arm", "world", "rep", "true_start", "benign_invalid_rate"]).agg(
        versions=("flagged", "size"), flagged=("flagged", "sum"), rate=("flagged", "mean"))
    d0 = b[b.version == "day0"].groupby(["arm", "world", "rep", "true_start",
                                         "benign_invalid_rate"]).flagged.sum()  # fmt: skip
    m["day0_flagged"] = d0
    m = m.reset_index()
    out["per_machine"] = m
    out["per_machine_summary"] = m.groupby(["arm", "benign_invalid_rate"]).agg(
        machines=("rate", "size"), rate_median=("rate", "median"),
        rate_p90=("rate", lambda x: x.quantile(0.9)), flagged_median=("flagged", "median"),
        any_flag=("flagged", lambda x: (x > 0).mean()),
        any_day0_flag=("day0_flagged", lambda x: (x > 0).mean())).reset_index()
    s["share"] = s.clean_snapshots_flagged / s.clean_snapshots
    out["clean_snapshots_flagged"] = s.groupby(["arm", "benign_invalid_rate"]).agg(
        machines=("share", "size"), snapshots=("clean_snapshots", "sum"),
        flagged=("clean_snapshots_flagged", "sum"), share_mean=("share", "mean"),
        all_flagged=("share", lambda x: (x == 1).mean())).reset_index()
    for k, t in out.items():
        t.to_csv(R / f"{k}.csv", index=False)
        if k != "per_machine":
            print(f"== {k}")
            print(t.round(4).to_string(index=False))


if __name__ == "__main__":
    main()
