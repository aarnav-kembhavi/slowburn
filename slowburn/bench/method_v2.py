"""Method v2 selection rules on DEV sweeps (D48, D49), applied mechanically to sweep CSVs.

DEV only: the functions refuse rows from any other split.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

Q0_MARGIN = 0.01  # D48: SlowBurn q = 0 restore-time failure at most prior-only's + 1 point


def _dev_only(df: pd.DataFrame) -> pd.DataFrame:
    if "split" in df and set(df.split.unique()) - {"dev"}:
        raise ValueError("method v2 selection uses DEV rows only")
    return df.assign(vfail=(df.clean_snapshot_retained == 1) & (df.clean_recovery == 0))


def q0_excess(df: pd.DataFrame) -> pd.DataFrame:
    """Per variant and world: SlowBurn minus prior-only pooled q = 0 restore-time failure."""
    d = _dev_only(df)
    d = d[d.detect_prob == 0.0]
    r = d.groupby(["variant", "world", "policy"]).vfail.mean().unstack("policy")
    return (r["slowburn"] - r["prior_only"]).rename("q0_excess").reset_index()


def variant_scores(df: pd.DataFrame) -> pd.DataFrame:
    """Per variant: SlowBurn mean recovery and work lost over everything, worst-world q = 0
    excess, and whether every world meets the q = 0 criterion."""
    d = _dev_only(df)
    sb = (
        d[d.policy == "slowburn"]
        .groupby("variant")
        .agg(
            recovery=("clean_recovery", "mean"),
            work_lost_h=("work_lost_whole_system_hours", "mean"),
        )
    )
    ex = q0_excess(df).groupby("variant").q0_excess.max().rename("q0_excess_worst_world")
    out = sb.join(ex)
    out["eligible"] = out.q0_excess_worst_world <= Q0_MARGIN + 1e-12
    return out


def select_stage_a(df: pd.DataFrame) -> tuple[str, bool, pd.DataFrame]:
    """D48: (variant, criterion_met, scoreboard)."""
    s = variant_scores(df)
    ok = s[s.eligible]
    if ok.empty:
        return str(s.q0_excess_worst_world.idxmin()), False, s
    best = ok.recovery.max()
    tied = ok[ok.recovery >= best - 0.001]
    return str(tied.work_lost_h.idxmin()), True, s


def select_stage_b(df: pd.DataFrame, control: str, recovery_slack: float = 0.005):
    """D49: adopt an adaptive-gate variant only if the q = 0 criterion holds in every world,
    SlowBurn recovery is at most ``recovery_slack`` below the control and work lost is below the
    control; the lowest work lost among those. Returns (variant, scoreboard)."""
    s = variant_scores(df)
    c = s.loc[control]
    ok = s[s.eligible & (s.recovery >= c.recovery - recovery_slack)
           & (s.work_lost_h < c.work_lost_h) & (s.index != control)]  # fmt: skip
    return (str(ok.work_lost_h.idxmin()) if len(ok) else control), s


# ---- D57 / D56: q = 0 non-inferiority as a hard constraint --------------------------------

PAIR_KEY = ["attack_start", "world", "benign_invalid_rate", "rep", "discovery_delay", "budget"]


def _one_sided_mcnemar(fail_method, fail_base) -> float:
    """P(method fails more than the baseline by chance): exact binomial on discordant pairs."""
    from scipy import stats

    a, b = np.asarray(fail_method, bool), np.asarray(fail_base, bool)
    n10, n01 = int(np.sum(a & ~b)), int(np.sum(~a & b))
    n = n10 + n01
    return 1.0 if n == 0 else float(stats.binomtest(n10, n, 0.5, alternative="greater").pvalue)


def q0_units(world_df: pd.DataFrame, worst_df: pd.DataFrame, margin: float = Q0_MARGIN):
    """Per variant: the 8 q = 0 units (4 worlds pooled over budgets; 4 budgets on the
    worst-case grid) with SlowBurn minus prior-only restore-time failure, one-sided McNemar p,
    Holm-adjusted p over the 8 units, and whether each unit passes."""
    from slowburn.bench.stats import holm

    rows = []
    for grid, df, unit in (("worlds", world_df, "world"), ("worst", worst_df, "budget")):
        d = _dev_only(df)
        d = d[d.detect_prob.astype(float) == 0.0].copy()
        if "world" not in d:
            d["world"] = "worst_case_grid"
        key = [k for k in PAIR_KEY if k in d]
        for v, g in d.groupby("variant"):
            m = g[g.policy == "slowburn"][key + ["vfail"]].merge(
                g[g.policy == "prior_only"][key + ["vfail"]], on=key, suffixes=("_sb", "_po")
            )
            for u, x in m.groupby(unit):
                fs, fp = x.vfail_sb.mean(), x.vfail_po.mean()
                p = _one_sided_mcnemar(x.vfail_sb, x.vfail_po)
                rows.append({"variant": v, "grid": grid, "unit": u, "pairs": len(x),
                             "fail_slowburn": fs, "fail_prior_only": fp, "excess": fs - fp,
                             "p_one_sided": p})  # fmt: skip
    out = pd.DataFrame(rows)
    out["p_holm"] = out.groupby("variant").p_one_sided.transform(lambda p: holm(p.values))
    out["passes"] = (out.excess <= margin + 1e-12) & (out.p_holm >= 0.05)
    return out


def select_blind_safe(world_df: pd.DataFrame, worst_df: pd.DataFrame):
    """D57: eligible = all 8 units pass; then highest mean SlowBurn recovery on the worlds grid,
    ties within 0.001 by lower work lost. Returns (variant or None, scoreboard, units)."""
    units = q0_units(world_df, worst_df)
    d = _dev_only(world_df)
    board = (
        d[d.policy == "slowburn"]
        .groupby("variant")
        .agg(
            recovery=("clean_recovery", "mean"),
            work_lost_h=("work_lost_whole_system_hours", "mean"),
        )
    )
    board["units_passing"] = units.groupby("variant").passes.sum()
    board["units"] = units.groupby("variant").passes.size()
    board["eligible"] = (board.units_passing == board.units) & (board.units == 8)
    ok = board[board.eligible]
    if ok.empty:
        return None, board, units
    tied = ok[ok.recovery >= ok.recovery.max() - 0.001]
    return str(tied.work_lost_h.idxmin()), board, units


# ---- D60: method v4 (soft tail in retention, walk-back restore) ---------------------------

V2_W075_G2_WORK_LOST = 1644.030625  # D57: method v2 (w 0.75) SlowBurn on the normal grid
C2_FACTOR = 1.10
RESCUE_MIN = 0.10
RESCUE_Q = (0.2, 0.5, 1.0)


def _fail(df: pd.DataFrame) -> pd.DataFrame:
    return _dev_only(df).assign(fail=lambda d: d.clean_recovery == 0)


def d60_c1_units(normal_df, worst_df, variant: str, hard: str, margin: float = Q0_MARGIN):
    """C1: at q = 0, ``variant`` SlowBurn vs HARD prior-only (variant ``hard``) on paired
    clean-recovery failure; 4 worlds on G2, 4 budgets on G3, Holm over the 8 units."""
    from slowburn.bench.stats import holm

    rows = []
    for grid, df, unit in (("normal", normal_df, "world"), ("worst", worst_df, "budget")):
        d = _fail(df)
        d = d[d.detect_prob.astype(float) == 0.0].copy()
        if "world" not in d:
            d["world"] = "worst_case_grid"
        key = [k for k in PAIR_KEY if k in d]
        a = d[(d.variant == variant) & (d.policy == "slowburn")][key + ["fail"]]
        b = d[(d.variant == hard) & (d.policy == "prior_only")][key + ["fail"]]
        m = a.merge(b, on=key, suffixes=("_v4", "_hard"), validate="one_to_one")
        if len(m) != len(a) or len(m) != len(b):
            raise ValueError(f"C1 pairing incomplete on {grid}")
        for u, x in m.groupby(unit):
            fv, fh = x.fail_v4.mean(), x.fail_hard.mean()
            rows.append({"variant": variant, "grid": grid, "unit": u, "pairs": len(x),
                         "fail_v4_slowburn": fv, "fail_prior_only_hard": fh, "excess": fv - fh,
                         "p_one_sided": _one_sided_mcnemar(x.fail_v4, x.fail_hard)})  # fmt: skip
    out = pd.DataFrame(rows)
    out["p_holm"] = holm(out.p_one_sided.values)
    out["passes"] = (out.excess <= margin + 1e-12) & (out.p_holm >= 0.05)
    return out


def d60_rescue(under_df: pd.DataFrame, variant_of_m: dict) -> pd.DataFrame:
    """C3 for one tail: on G1 rows with true delay > M, SlowBurn recovery at q minus at q = 0
    (same machines) for q in RESCUE_Q and each M; one-sided exact McNemar (q recovers more),
    Holm over the 6 tests. ``variant_of_m``: {M: variant name}."""
    from slowburn.bench.stats import holm

    d = _fail(under_df)
    key = [k for k in PAIR_KEY if k in d]
    rows = []
    for M, v in sorted(variant_of_m.items()):
        g = d[(d.variant == v) & (d.policy == "slowburn") & (d.discovery_delay > M)]
        base = g[g.detect_prob.astype(float) == 0.0][key + ["fail"]]
        for q in RESCUE_Q:
            x = g[g.detect_prob.astype(float) == q][key + ["fail"]].merge(
                base, on=key, suffixes=("_q", "_q0"), validate="one_to_one")  # fmt: skip
            if len(x) != len(base):
                raise ValueError(f"C3 pairing incomplete: {v} q {q}")
            rq, r0 = 1 - x.fail_q.mean(), 1 - x.fail_q0.mean()
            rows.append({"variant": v, "M": M, "q": q, "pairs": len(x), "recovery_q": rq,
                         "recovery_q0": r0, "gain": rq - r0,
                         "p_one_sided": _one_sided_mcnemar(x.fail_q0, x.fail_q)})  # fmt: skip
    out = pd.DataFrame(rows)
    out["p_holm"] = holm(out.p_one_sided.values)
    out["rescue"] = (out.gain >= RESCUE_MIN - 1e-12) & (out.p_holm < 0.05)
    return out


def restore_depth_table(df: pd.DataFrame, bound: dict | None = None) -> pd.DataFrame:
    """Recovery, work lost and how far back restores went, per variant, policy and q.
    ``bound``: {variant: M} for rows that predate the depth columns (v3 runs)."""
    d = _dev_only(df).copy()
    if "restore_depth_days" not in d:
        d["restore_depth_days"] = d.true_start + d.discovery_delay - d.restore_point
        d["restore_beyond_bound"] = (d.restore_depth_days > d.variant.map(bound)).astype(int)
        d["walkback_steps"] = 0
    return (d.groupby(["variant", "policy", "detect_prob"])
            .agg(recovery=("clean_recovery", "mean"),
                 work_lost_h=("work_lost_whole_system_hours", "mean"),
                 depth_mean=("restore_depth_days", "mean"),
                 depth_median=("restore_depth_days", "median"),
                 depth_p90=("restore_depth_days", lambda s: s.quantile(0.9)),
                 beyond_bound=("restore_beyond_bound", "mean"),
                 walked=("walkback_steps", lambda s: (s > 0).mean()),
                 walk_steps=("walkback_steps", "mean"),
                 rows=("clean_recovery", "size"))
            .reset_index())  # fmt: skip


def d60_select(normal_df, worst_df, under_df, tails, hard_normal: str) -> dict:
    """Apply D60: reproduction check, C1, C2, selection, C3. ``tails``: {tail: {M: variant}}
    with M = 60 for the normal-grid variant. Returns the scoreboard and per-test tables."""
    d = _dev_only(normal_df)
    hard_wl = d[(d.variant == hard_normal) & (d.policy == "slowburn")] \
        .work_lost_whole_system_hours.mean()  # fmt: skip
    if abs(hard_wl - V2_W075_G2_WORK_LOST) > 1e-6:
        raise ValueError(f"hard variant does not reproduce v2 w 0.75 on G2: {hard_wl}")
    limit = C2_FACTOR * V2_W075_G2_WORK_LOST
    board, units, rescue = [], [], []
    for tail, vm in tails.items():
        v60 = vm[60]
        u = d60_c1_units(normal_df, worst_df, v60, hard_normal)
        units.append(u)
        sb = d[(d.variant == v60) & (d.policy == "slowburn")]
        under_m = {M: v for M, v in vm.items() if M != 60}
        g1 = _dev_only(under_df)
        g1 = g1[g1.variant.isin(under_m.values()) & (g1.policy == "slowburn")]
        g1 = g1[g1.discovery_delay > g1.variant.map({v: M for M, v in under_m.items()})]
        r = d60_rescue(under_df, under_m).assign(tail=tail)
        rescue.append(r)
        board.append({"tail": tail, "c1_units_passing": int(u.passes.sum()),
                      "c1": bool(u.passes.all() and len(u) == 8),
                      "g2_recovery": sb.clean_recovery.mean(),
                      "g2_work_lost_h": sb.work_lost_whole_system_hours.mean(),
                      "c2_limit_h": limit,
                      "c2": bool(sb.work_lost_whole_system_hours.mean() <= limit + 1e-9),
                      "g1_beyond_recovery": g1.clean_recovery.mean(),
                      "rescue_q": ",".join(str(q) for q, x in r.groupby("q")
                                           if x.rescue.all())})  # fmt: skip
    board = pd.DataFrame(board)
    board["eligible"] = board.c1 & board.c2
    ok = board[board.eligible]
    chosen = None
    if len(ok):
        tied = ok[ok.g1_beyond_recovery >= ok.g1_beyond_recovery.max() - 0.001]
        chosen = float(tied.sort_values("g2_work_lost_h")["tail"].iloc[0])
    rescue = pd.concat(rescue, ignore_index=True)
    adopt = False
    if chosen is not None:
        held = set(board.loc[board["tail"] == chosen, "rescue_q"].iloc[0].split(",")) - {""}
        adopt = bool(held & {"0.2", "0.5"})
    return {"board": board, "units": pd.concat(units, ignore_index=True), "rescue": rescue,
            "chosen_tail": chosen, "adopt": adopt, "hard_g2_work_lost": hard_wl}  # fmt: skip
