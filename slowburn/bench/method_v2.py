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
                rows.append({"variant": v, "grid": grid, "unit": u, "pairs": len(x),
                             "fail_slowburn": fs, "fail_prior_only": fp, "excess": fs - fp,
                             "p_one_sided": _one_sided_mcnemar(x.vfail_sb, x.vfail_po)})  # fmt: skip
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
