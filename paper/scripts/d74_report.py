"""D74 report: adaptive attacker best response per defence (OPEN_QUESTIONS D74 and amendment).
Evaluation only. Run from the repo root after both arms:

    uv run python paper/scripts/d74_report.py

Primary: grid strategies that are stealth-feasible at delay d (the count alarm fires before
discovery on at most 5% of the selection-half machines); the attacker's best strategy is picked
on the selection half and scored on the evaluation half. Secondary: every grid strategy with
discovery at min(d, alarm). Bound: the threshold-aware attacker (c - 1 files per day). Also the
realistic D72 attacker under the D72 delays.
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from slowburn.bench.stats import cluster_bootstrap_ratio as cbr

ARMS = {"synthetic_bytes": "results/dev_d74_attack_synthetic",
        "napierone_bytes": "results/dev_d74_attack_napierone"}  # fmt: skip
OUT = Path("results/dev_d74_report")
STRAT = ["strategy_kind", "strategy_rate", "strategy_fraction", "strategy_targets"]
DEF = ["arm", "policy", "budget", "restore"]
MACH = ["world", "rep"]
REALISTIC = {"strategy_kind": "grid", "strategy_rate": 0.5, "strategy_fraction": 0.1,
             "strategy_targets": "all"}  # fmt: skip
REALISTIC_DELAYS = (7, 14, 30, 45, 60)
ARM_ORDER = ["napierone_bytes", "synthetic_bytes"]  # NapierOne first; synthetic = sanity arm
ARM_LABEL = {"napierone_bytes": "napierone_bytes", "synthetic_bytes": "synthetic_bytes (sanity)"}
CALIB = Path("results/dev_d74_alarm_calib")
pd.set_option("display.width", 250, "display.max_columns", 40, "display.max_rows", 400)


def ordered(t: pd.DataFrame) -> pd.DataFrame:
    """NapierOne first in every table; the synthetic arm labelled as the sanity arm."""
    if "arm" not in t:
        return t
    t = t.assign(arm=pd.Categorical(t.arm, ARM_ORDER, ordered=True))
    t = t.sort_values("arm", kind="stable")
    return t.assign(arm=t.arm.astype(str).map(ARM_LABEL))


def exact_upper(x: int, n: int) -> float:
    from scipy.stats import beta

    return 1.0 if x == n else float(beta.ppf(0.975, x + 1, n - x))


def false_alarms(c_of: dict) -> pd.DataFrame:
    """Per arm, from the calibration runs (IN SAMPLE: the same runs chose c; the held-out check
    is separate): per-run rate at c and c - 1, and fleet false alarms per week, point and exact
    95% upper bound, for N = 20 and 100, in one format for both arms."""
    rows = []
    for arm in ARM_ORDER:
        f = CALIB / f"daily_counts_{arm}.csv.gz"
        if not f.exists():
            continue
        k = pd.read_csv(f).to_numpy()
        c = int(c_of[arm])
        days, runs = k >= c, k.max(axis=1) >= c
        x, n = int(days.sum()), days.size
        up = exact_upper(x, n)
        rows.append({"arm": arm, "c": c, "sample": "in sample (calibration runs d74_alarm_calib); held out check pending",
                     "per_run_far": runs.mean(), "per_run_far_upper95": exact_upper(
                         int(runs.sum()), runs.size),
                     "per_run_far_at_c_minus_1": (k.max(axis=1) >= c - 1).mean(),
                     "p_day": x / n, "p_day_upper95": up,
                     **{f"fleet_fa_per_week_N{N}": 7 * N * x / n for N in (20, 100)},
                     **{f"fleet_fa_per_week_N{N}_upper95": 7 * N * up
                        for N in (20, 100)}})  # fmt: skip
    return pd.DataFrame(rows)


def threshold_aware_detection(under: pd.DataFrame) -> pd.DataFrame:
    """The c - 1 files/day attacker shares the daily counter with benign flags (one k_t per day,
    file_exceed): detection probability per run within d, and time to detection."""
    u = under.drop_duplicates(["arm", *STRAT, *MACH, "discovery_delay"])
    u = u.assign(detected=u.alarm_delay.notna() & (u.alarm_delay <= u.discovery_delay))
    g = u.groupby(["arm", "strategy_fraction", "strategy_targets", "discovery_delay"])
    out = g.agg(runs=("detected", "size"), p_detect=("detected", "mean")).reset_index()
    ttd = (u[u.alarm_delay.notna()].drop_duplicates(["arm", *STRAT, *MACH])
           .groupby(["arm", "strategy_fraction", "strategy_targets"]).alarm_delay
           .agg(ttd_median="median", ttd_mean="mean", detected_runs="size")
           .reset_index())  # fmt: skip
    return out.merge(ttd, on=["arm", "strategy_fraction", "strategy_targets"], how="left")


def load(arms=ARMS) -> pd.DataFrame:
    parts = []
    for arm, run in arms.items():
        p = Path(run) / "attack_rows.csv.gz"
        if p.exists():
            d = pd.read_csv(p, low_memory=False)
            parts.append(d[d.variant == "method_v2_w075_vsnap"].assign(arm=arm))
    d = pd.concat(parts, ignore_index=True)
    d["strategy_targets"] = d.strategy_targets.fillna("all")
    long = []
    for X, rec, wl in (("A", "clean_recovery", "pfA_work_lost_file_hours"),
                       ("B", "pfB_clean_recovery", "pfB_work_lost_file_hours")):  # fmt: skip
        long.append(d.assign(restore=X, rec=d[rec], wl=d[wl]))
    return pd.concat(long, ignore_index=True)


def feasibility(d: pd.DataFrame) -> pd.DataFrame:
    """Per (arm, strategy, d): share of selection machines where the alarm fires before d."""
    g = d[(d.grid_delay) & (d.selection_half)].drop_duplicates(["arm", *STRAT, *MACH,
                                                                 "discovery_delay"])  # fmt: skip
    fired = g.alarm_delay.notna() & (g.alarm_delay <= g.discovery_delay)
    f = g.assign(fired=fired).groupby(["arm", *STRAT, "discovery_delay"]).fired.mean()
    return f.rename("alarm_share").reset_index().assign(feasible=lambda x: x.alarm_share <= 0.05)


def caught(d: pd.DataFrame) -> pd.DataFrame:
    """Secondary: for each grid delay d, the row at min(d, alarm delay) per machine."""
    rows = []
    key = ["arm", *STRAT, *MACH, "policy", "budget", "restore"]
    by = {k: g for k, g in d.groupby(key, sort=False)}
    for k, g in by.items():
        idx = g.set_index("discovery_delay")
        ad = g.alarm_delay.iloc[0]
        for dd in sorted(g[g.grid_delay].discovery_delay.unique()):
            use = dd if pd.isna(ad) or ad >= dd else int(ad)
            r = idx.loc[use]
            r = r.iloc[0] if isinstance(r, pd.DataFrame) else r
            rows.append({**dict(zip(key, k, strict=True)), "discovery_delay": dd,
                         "rec": r.rec, "wl": r.wl, "caught": use < dd,
                         "selection_half": r.selection_half})  # fmt: skip
    return pd.DataFrame(rows)


def ci_mean(x: pd.Series, cl: pd.Series) -> tuple:
    return cbr(x.astype(float), np.ones(len(x)), cl)


def best_response(d: pd.DataFrame, objective: str, label: str) -> pd.DataFrame:
    """Per defence and d: pick the strategy on the selection half, score on the evaluation half.
    objective 'rec' = minimise recovery; 'wl' = maximise per-file work lost (ties: lower rec)."""
    out = []
    for k, g in d.groupby([*DEF, "discovery_delay"]):
        sel = g[g.selection_half].groupby(STRAT)[["rec", "wl"]].mean()
        if sel.empty:
            continue
        if objective == "rec":
            best = sel.sort_values(["rec", "wl"], ascending=[True, False]).index[0]
        else:
            best = sel.sort_values(["wl", "rec"], ascending=[False, True]).index[0]
        ev = g[~g.selection_half]
        ev = ev[(ev[STRAT] == pd.Series(best, index=STRAT)).all(axis=1)]
        cl = ev.world.astype(str) + "/" + ev.rep.astype(str)
        rec, wl = ci_mean(ev.rec, cl), ci_mean(ev.wl, cl)
        out.append({**dict(zip([*DEF, "discovery_delay"], k, strict=True)), "analysis": label,
                    "objective": objective, **dict(zip(STRAT, best, strict=True)),
                    "sel_rec": sel.loc[best, "rec"], "sel_wl": sel.loc[best, "wl"],
                    "eval_rec": rec[0], "eval_rec_lo": rec[1], "eval_rec_hi": rec[2],
                    "eval_wl": wl[0], "eval_wl_lo": wl[1], "eval_wl_hi": wl[2],
                    "eval_rows": len(ev)})  # fmt: skip
    return pd.DataFrame(out)


def main(arms=ARMS, out=OUT):
    out.mkdir(parents=True, exist_ok=True)
    d = load(arms)
    feas = feasibility(d)
    feas.to_csv(out / "feasibility.csv", index=False)
    grid = d[(d.strategy_kind == "grid") & d.grid_delay]
    fg = grid.merge(feas, on=["arm", *STRAT, "discovery_delay"], how="left")
    prim = fg[fg.feasible]
    res = [
        best_response(prim, "rec", "primary_feasible"),
        best_response(prim, "wl", "primary_feasible"),
    ]
    sec = caught(d[d.strategy_kind == "grid"])
    res += [
        best_response(sec, "rec", "secondary_alarm_caught"),
        best_response(sec, "wl", "secondary_alarm_caught"),
    ]
    under = d[(d.strategy_kind == "under_threshold") & d.grid_delay]
    if not under.empty:
        res += [
            best_response(under, "rec", "bound_threshold_aware"),
            best_response(under, "wl", "bound_threshold_aware"),
        ]
        det = threshold_aware_detection(under)
        ordered(det).to_csv(out / "threshold_aware_detection.csv", index=False)
        print("== threshold-aware attacker (c - 1 files/day; benign and attacker flags share one")
        print("   daily counter): detection probability per run within d, time to detection (days)")
        print(ordered(det).round(3).to_string(index=False))
        print("   boundary-straddling attacker: identical to these rows in the daily model "
              "(OPEN_QUESTIONS 2026-10-25)")  # fmt: skip
    br = pd.concat(res, ignore_index=True)
    br.to_csv(out / "best_response.csv", index=False)
    worst = (
        br.groupby([*DEF, "analysis", "objective"])
        .agg(worst_eval_rec=("eval_rec", "min"), worst_eval_wl=("eval_wl", "max"))
        .reset_index()
    )
    worst.to_csv(out / "worst_case_over_delays.csv", index=False)
    real = grid[(grid[STRAT] == pd.Series(REALISTIC)).all(axis=1)
                & grid.discovery_delay.isin(REALISTIC_DELAYS)]  # fmt: skip
    rs = real.groupby(DEF)[["rec", "wl"]].mean().reset_index()
    rs.to_csv(out / "realistic.csv", index=False)
    surf = d[d.grid_delay].groupby([*DEF, *STRAT, "discovery_delay"])[["rec", "wl"]].mean()
    surf.reset_index().to_csv(out / "surface.csv.gz", index=False)
    thr = json.loads((CALIB / "threshold.json").read_text())
    fa = false_alarms({a: v["c"] for a, v in thr.items()})
    ordered(fa).to_csv(out / "false_alarms.csv", index=False)
    print("== count alarm false alarms (in sample; held-out check registered separately)")
    print(ordered(fa).round(5).to_string(index=False))
    if len(fa) == 2:
        g = fa.set_index("arm").per_run_far_at_c_minus_1
        print(f"   finding: at c - 1 = 2 the benign per-run false-alarm rate is "
              f"{g['synthetic_bytes']:.0%} on synthetic bytes vs {g['napierone_bytes']:.0%} on "
              "NapierOne: synthetic data underestimates benign noise")  # fmt: skip
    for name in ("feasibility", "best_response", "worst_case_over_delays", "realistic"):
        f = out / f"{name}.csv"
        ordered(pd.read_csv(f)).to_csv(f, index=False)
    feas, worst, rs = ordered(feas), ordered(worst), ordered(rs)
    print("== feasible share of grid strategies by arm and delay")
    print(feas.groupby(["arm", "discovery_delay"]).feasible.mean().unstack().round(3).to_string())
    print("== worst case over delays (evaluation half), per defence")
    print(worst.round(3).to_string(index=False))
    print("== realistic attacker (D72 attacker, delays 7-60)")
    print(rs.round(3).to_string(index=False))


if __name__ == "__main__":
    main()
    sys.exit(0)
