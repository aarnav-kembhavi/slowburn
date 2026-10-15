"""Method v2 selection rules on DEV sweeps (D48, D49), applied mechanically to sweep CSVs.

DEV only: the functions refuse rows from any other split.
"""

from __future__ import annotations

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
