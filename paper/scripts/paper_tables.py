"""LaTeX table bodies for the paper, generated from committed outputs only (no hand-typed
numbers): results/analysis_test and results/analysis_dev (confirmatory, TEST and DEV v2),
results/exploratory (E1 to E4, exploratory), results/test_inventory.json and
results/exploratory/dev_inventory.json (data card), results/dev_d66_retention_audit (DEV audit).
Writes paper/ieee_access/sections/generated/*.tex. Run from the repo root:

    uv run python paper/scripts/paper_tables.py
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd

OUT = Path("paper/ieee_access/sections/generated")
AT, AD, EX = Path("results/analysis_test"), Path("results/analysis_dev"), Path("results/exploratory")
VS = {"gfs": "GFS", "tower_of_hanoi": "ToH", "shamir_recursive": "Bar-On rec.",
      "shamir_rr": "Bar-On RR", "gfs_eqh": "GFS-eqh", "toh_eqh": "ToH-eqh"}  # fmt: skip
POL = {"slowburn": "SlowBurn", "prior_only": "Prior-only", "shamir_recursive": "Bar-On rec.",
       "gfs": "GFS", "tower_of_hanoi": "ToH"}  # fmt: skip
ARM = {"napierone_bytes": "NapierOne", "synthetic_bytes": "Synthetic"}


def m(x: float, d: int = 1, sign: bool = True) -> str:
    """A number in math mode (real minus sign); signed unless ``sign`` is False."""
    if pd.isna(x):
        return "--"
    return f"${x:+.{d}f}$" if sign else f"${x:.{d}f}$"


def pct(x, lo, hi) -> str:
    return f"{m(100 * x)} [{m(100 * lo, 1, False)}, {m(100 * hi, 1, False)}]"


def dif(x, lo, hi, d=3) -> str:
    return f"{m(x, d)} [{m(lo, d, False)}, {m(hi, d, False)}]"


def write(name: str, body: str) -> None:
    (OUT / f"{name}.tex").write_text(body, encoding="utf-8")


def ptxt(p: float) -> str:
    return "$<0.001$" if p < 0.001 else f"{p:.3f}"


# ---- confirmatory, appendix --------------------------------------------------------------


def full_c2() -> None:
    rows = []
    for arm in ARM:
        for vs in VS:
            r = {}
            for sp, root in (("t", AT), ("d", AD)):
                c = pd.read_csv(root / "d72_c2r_holm/c2_holm.csv")
                r[sp] = c[(c.arm == arm) & (c.vs == vs)].iloc[0]
            t, d = r["t"], r["d"]
            rows.append(f"{ARM[arm]} & {VS[vs]} & "
                        f"{pct(t.work_lost_rel, t.work_lost_rel_lo, t.work_lost_rel_hi)} & "
                        f"{dif(t.recovery_diff, t.recovery_diff_lo, t.recovery_diff_hi)} & "
                        f"{ptxt(t.p_holm)} & "
                        f"{pct(d.work_lost_rel, d.work_lost_rel_lo, d.work_lost_rel_hi)} & "
                        f"{ptxt(d.p_holm)}\\\\")  # fmt: skip
    write("tab_full_c2", "\n".join(rows) + "\n")


def full_d79() -> None:
    rows = []
    for arm in ARM:
        for root, sp in ((AT, "TEST"), (AD, "DEV")):
            p = pd.read_csv(root / "d79_report/primary.csv")
            for x in p[p.arm == arm].itertuples():
                rows.append(f"{ARM[arm]} & {sp} & {VS[x.vs]} & "
                            f"{pct(x.work_lost_rel, x.work_lost_rel_lo, x.work_lost_rel_hi)} & "
                            f"{dif(x.recovery_diff, x.recovery_diff_lo, x.recovery_diff_hi)} & "
                            f"{ptxt(x.p_holm)} & {'yes' if x.success else 'no'}\\\\")  # fmt: skip
    write("tab_full_d79", "\n".join(rows) + "\n")


def full_d72() -> None:
    rows = []
    for unit, arm in (("bytes_napierone_v2pool", "NapierOne"), ("bytes_synthetic", "Synthetic")):
        for root, sp in ((AT, "TEST"), (AD, "DEV")):
            s = pd.read_csv(root / "d72_report/summary.csv")
            x = s[(s.unit == unit) & (s.policy == "slowburn")].iloc[0]
            cells = [f"{x[f'rec_{k}']:.3f} / {x[f'fwl_{k}']:,.0f}" for k in "ABCDE"]
            rows.append(f"{arm} & {sp} & " + " & ".join(cells) + "\\\\")
    write("tab_full_d72", "\n".join(rows) + "\n")


def full_d71() -> None:
    rows = []
    for pol in ("slowburn", "shamir_recursive", "toh_eqh", "gfs", "tower_of_hanoi"):
        for q in (1.0, 0.5, 0.2, 0.0):
            cell = []
            for root in (AT, AD):
                g = pd.read_csv(root / "d71_report/gap_full_by_q.csv")
                x = g[(g.policy == pol) & (g.q == q)].iloc[0]
                cell.append(f"{x.rec_a:.3f} & {dif(x.rec_gap_ab, x.rec_gap_ab_lo, x.rec_gap_ab_hi)}")
            rows.append(f"{VS.get(pol, POL.get(pol, pol))} & {q:g} & " + " & ".join(cell) + "\\\\")
    write("tab_full_d71", "\n".join(rows) + "\n")


def full_d73() -> None:
    rows = []
    for arm in ARM:
        for vs, lab in (("a_equal", "equal split"), ("b_churn", "churn split")):
            cell = []
            for root in (AT, AD):
                c = pd.read_csv(root / "d73_report/criteria.csv")
                x = c[c.primary & (c.arm == arm) & (c.vs == vs)].iloc[0]
                cell.append(f"{pct(x.pooled_file_wl_rel, x.wl_lo, x.wl_hi)} & "
                            f"{dif(x.pooled_recovery_diff, x.rec_lo, x.rec_hi)} & "
                            f"{x.worst_cell_recovery_diff:.2f} & {'yes' if x['all'] else 'no'}")  # fmt: skip
            rows.append(f"{ARM[arm]} & {lab} & " + " & ".join(cell) + "\\\\")
    write("tab_full_d73", "\n".join(rows) + "\n")


def full_d74() -> None:
    rows = []
    for arm in ARM:
        for root, sp in ((AT, "TEST"), (AD, "DEV")):
            b = pd.read_csv(root / "d74_report/best_response.csv")
            b = b[(b.analysis == "primary_feasible") & (b.objective == "rec") & (b.restore == "A")
                  & b.arm.str.startswith(arm)]  # fmt: skip
            if b.empty:
                rows.append(f"{ARM[arm]} & {sp} & \\multicolumn{{9}}{{l}}{{no scored "
                            "best-response rows}\\\\")  # fmt: skip
                continue
            for K in (4, 8):
                for pol in POL:
                    g = b[(b.policy == pol) & (b.budget == K)].sort_values("discovery_delay")
                    rows.append(f"{ARM[arm]} & {sp} & {K} & {POL[pol]} & "
                                + " & ".join(f"{v:.2f}" for v in g.eval_rec) + "\\\\")  # fmt: skip
    write("tab_full_d74", "\n".join(rows) + "\n")


def full_alarm() -> None:
    rows = []
    for arm in ARM:
        for root, sp in ((AT, "TEST"), (AD, "DEV")):
            h = json.loads((root / "d74_alarm_holdout/holdout.json").read_text())[arm]
            lo, hi = h["per_run_ci95"]
            rows.append(f"{ARM[arm]} & {sp} & {h['run_alarms']}/{h['runs']} & [{lo:.4f}, {hi:.4f}] "
                        f"& {h['day_alarms']}/{h['machine_days']:,} & {h['p_day_upper95']:.2e} & "
                        f"{h['fleet_false_alarms_per_week']['20']:.3f} "
                        f"({h['fleet_false_alarms_per_week_upper95']['20']:.3f}) & "
                        f"{h['fleet_false_alarms_per_week']['100']:.3f} "
                        f"({h['fleet_false_alarms_per_week_upper95']['100']:.3f})\\\\")  # fmt: skip
    write("tab_full_alarm", "\n".join(rows).replace("e-0", "e$-$0") + "\n")


def full_threshold() -> None:
    from scipy.stats import beta

    def cp(x, n):
        return (0.0 if x == 0 else beta.ppf(0.025, x, n - x + 1),
                1.0 if x == n else beta.ppf(0.975, x + 1, n - x))  # fmt: skip

    rows = []
    for arm in ARM:
        t = {sp: pd.read_csv(root / "d74_report/threshold_aware_detection.csv")
             for root, sp in ((AT, "t"), (AD, "d"))}  # fmt: skip
        for frac in (0.01, 0.05, 0.1, 0.5, 1.0):
            for tg in ("all", "weak4", "csv"):
                cell = []
                for sp in ("t", "d"):
                    x = t[sp][t[sp].arm.str.startswith(arm) & (t[sp].discovery_delay == 120)
                              & (t[sp].strategy_fraction == frac)
                              & (t[sp].strategy_targets == tg)].iloc[0]  # fmt: skip
                    k = int(round(x.p_detect * x.runs))
                    lo, hi = cp(k, int(x.runs))
                    med = "--" if pd.isna(x.ttd_median) else f"{x.ttd_median:g}"
                    cell.append(f"{k}/{int(x.runs)} [{lo:.2f}, {hi:.2f}] & {med}")
                rows.append(f"{ARM[arm]} & {tg} & {frac:g} & " + " & ".join(cell) + "\\\\")
    write("tab_full_threshold", "\n".join(rows) + "\n")


# ---- exploratory ----------------------------------------------------------------------------


def breakdown_c2() -> None:
    c = pd.read_csv(EX / "posthoc/c2_breakdowns.csv")
    c = c[(c.split == "test") & (c.arm == "napierone_bytes")]
    lab = {"world": "world", "budget": "$K$", "benign_invalid_rate": "benign rate"}
    rows = []
    for by in ("world", "budget", "benign_invalid_rate"):
        for lev in sorted(c[c.by == by].level.unique(), key=lambda v: (str(type(v)), v)):
            cells = []
            for vs in ("gfs", "tower_of_hanoi", "shamir_recursive", "gfs_eqh", "toh_eqh"):
                x = c[(c.by == by) & (c.level == lev) & (c.vs == vs)]
                cells.append("--" if x.empty else
                             pct(x.iloc[0].work_lost_rel, x.iloc[0].work_lost_rel_lo,
                                 x.iloc[0].work_lost_rel_hi))  # fmt: skip
            lv = lev if by == "world" else f"{float(lev):g}"
            rows.append(f"{lab[by]} & {lv} & " + " & ".join(cells) + "\\\\")
    write("tab_ex_c2", "\n".join(rows) + "\n")


def breakdown_d79() -> None:
    c = pd.read_csv(EX / "posthoc/d79_breakdowns.csv")
    c = c[c.split == "test"]
    lab = {"world": "world", "budget": "$K$", "benign_invalid_rate": "benign rate"}
    rows = []
    for by in ("world", "budget", "benign_invalid_rate"):
        for lev in sorted(c[c.by == by].level.unique(), key=lambda v: (str(type(v)), v)):
            cells = []
            for arm in ARM:
                for vs in ("gfs_eqh", "toh_eqh"):
                    x = c[(c.by == by) & (c.level == lev) & (c.vs == vs) & (c.arm == arm)]
                    cells.append("--" if x.empty else
                                 pct(x.iloc[0].work_lost_rel, x.iloc[0].work_lost_rel_lo,
                                     x.iloc[0].work_lost_rel_hi))  # fmt: skip
            lv = lev if by == "world" else f"{float(lev):g}"
            rows.append(f"{lab[by]} & {lv} & " + " & ".join(cells) + "\\\\")
    write("tab_ex_d79", "\n".join(rows) + "\n")


def breakdown_d74() -> None:
    d = pd.read_csv(EX / "posthoc/d74_by_world.csv")
    d = d[(d.split == "test") & (d.arm == "napierone_bytes")]
    rows = []
    for att, lab in (("realistic", "realistic"), ("best_response_eval_d7_60", "best response")):
        for K in (4, 8):
            for pol in ("slowburn", "shamir_recursive", "gfs", "tower_of_hanoi"):
                cells = []
                for w in ("uniform", "early", "late", "bursty"):
                    x = d[(d.attacker == att) & (d.budget == K) & (d.policy == pol)
                          & (d.world == w)].iloc[0]  # fmt: skip
                    cells.append(f"{x.rec:.2f} [{x.lo:.2f}, {x.hi:.2f}]")
                rows.append(f"{lab} & {K} & {POL[pol]} & " + " & ".join(cells) + "\\\\")
    write("tab_ex_d74", "\n".join(rows) + "\n")


def overhead() -> None:
    o = pd.read_csv(EX / "overhead/overhead.csv")
    rows = []
    for K in sorted(o.K.unique()):
        sb = [o[(o.policy == "slowburn") & (o.K == K) & (o.M == M)].iloc[0] for M in (30, 60, 120, 365)]
        g = o[(o.policy == "gfs") & (o.K == K)].iloc[0]
        h = o[(o.policy == "tower_of_hanoi") & (o.K == K)].iloc[0]
        rows.append(f"{K} & " + " & ".join(f"{x.ms_median:.2f} ({x.ms_p95:.2f})" for x in sb)
                    + f" & {max(x.peak_traced_mib for x in sb) * 1024:.0f} & "
                    f"{g.ms_median * 1000:.1f} & {h.ms_median * 1000:.1f}\\\\")  # fmt: skip
    write("tab_ex_overhead", "\n".join(rows) + "\n")
    t = pd.read_csv(EX / "overhead/recorded_timing.csv")
    t = t[t.policy == "slowburn"]
    rows = [f"{ARM[x.arm]} & {x.split.upper()} & {x.infer_ms_per_day_mean:.2f} & "
            f"{x.dp_ms_per_decision_mean:.3f}\\\\" for x in t.itertuples()]  # fmt: skip
    write("tab_ex_recorded_timing", "\n".join(rows) + "\n")


def storage() -> None:
    s = pd.read_csv(EX / "storage/storage_by_policy_K.csv")
    s = s[(s.split == "test") & (s.arm == "napierone_bytes")]
    rows = []
    for pol in ("slowburn", "prior_only", "shamir_recursive", "shamir_rr", "gfs",
                "tower_of_hanoi", "gfs_eqh", "toh_eqh"):  # fmt: skip
        cells = []
        for K in (4, 6, 8, 12):
            x = s[(s.policy == pol) & (s.budget == K)]
            cells.append("--" if x.empty else
                         f"{x.iloc[0].snapshots_retained:.1f} / "
                         f"{x.iloc[0].retained_unique_bytes / 2**20:.1f} / "
                         f"{x.iloc[0].storage_vs_keep_last_n:.2f}")  # fmt: skip
        rows.append(f"{VS.get(pol, POL.get(pol, 'Bar-On RR'))} & " + " & ".join(cells) + "\\\\")
    write("tab_ex_storage", "\n".join(rows) + "\n")


def restic() -> None:
    p = EX / "d76_restic/summary.csv"
    if not p.exists():
        write("tab_ex_restic", "\\multicolumn{6}{l}{not run}\\\\\n")
        return
    s = pd.read_csv(p)
    lab = {"slowburn_plan": "SlowBurn plan (forget by id)",
           "restic_kd7_kw5": "restic --keep-daily 7 --keep-weekly 5",
           "restic_kd4_kw4": "restic --keep-daily 4 --keep-weekly 4"}  # fmt: skip
    rows = [f"{lab[x.repo]} & {x.final_snapshots} & {x.forget_s_median:.2f} ({x.forget_s_p95:.2f}) & "
            f"{x.prune_s_median:.2f} ({x.prune_s_max:.2f}) & {x.final_repo_mib:.1f} & "
            f"{x.max_repo_mib:.1f}\\\\".replace("--", "-{}-") for x in s.itertuples()]  # fmt: skip
    write("tab_ex_restic", "\n".join(rows) + "\n")


# ---- benchmark --------------------------------------------------------------------------------


def data_card() -> None:
    t = json.loads(Path("results/test_inventory.json").read_text())["types"]
    d = json.loads((EX / "dev_inventory.json").read_text())["types"]
    rows = []
    for ty in ("txt", "csv", "bin", "docx", "zip", "png", "jpg", "mp3", "zlib"):
        a, b = d[ty], t[ty]
        na = " (n/a)" if a["validity_not_applicable"] else ""
        rows.append(f"{ty} & {a['files']} ({a['from_v1_sim_dev']} + {a['from_benign_v2_dev']}) & "
                    f"{a['validity_failures']}{na} & {b['files']} ({b['from_v1_sim_test']} + "
                    f"{b['from_benign_v2_test']}) & {b['validity_failures']}{na}\\\\")  # fmt: skip
    write("tab_data_card", "\n".join(rows) + "\n")


def audit() -> None:
    a = pd.read_csv("results/dev_d66_retention_audit/audit_thresholds.csv")
    prods = [("dropbox_30d", "Dropbox, 30-day plans"), ("dropbox_180d", "Dropbox, 180-day plans"),
             ("dropbox_365d", "Dropbox, 365-day plans"),
             ("gdrive_30d_100v", "Google Drive (window from replacement)"),
             ("gdrive_30d_100v_created", "Google Drive (window from creation)"),
             ("onedrive_business_500v", "OneDrive work/school, 500 versions"),
             ("restic_docs_dwmy", "restic example (daily/weekly/monthly/yearly)"),
             ("restic_docs_within", "restic example (keep-within)")]  # fmt: skip

    def v(x):
        return ">400" if pd.isna(x) else f"{x:g}"

    rows = []
    for key, lab in prods:
        b, p = (a[(a["product"] == key) & (a.detect_prob == q)].iloc[0] for q in (0.0, 1.0))
        rows.append(f"{lab} & {v(b['recovery_first_below_0.5'])} & {v(b['recovery_first_below_0.1'])}"
                    f" & {v(b['held_first_below_0.5'])} & {v(p['recovery_first_below_0.5'])}\\\\")  # fmt: skip
    write("tab_audit", "\n".join(rows) + "\n")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for f in (full_c2, full_d79, full_d72, full_d71, full_d73, full_d74, full_alarm,
              full_threshold, breakdown_c2, breakdown_d79, breakdown_d74, overhead, storage,
              restic, data_card, audit):  # fmt: skip
        f()
        print("ok", f.__name__)


if __name__ == "__main__":
    np.seterr(all="ignore")
    main()
