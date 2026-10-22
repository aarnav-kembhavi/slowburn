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


# ---- D64b: old vs adopted restore on the same machines --------------------------------------

RETENTION_COLS = ["snapshots_retained", "retained_unique_bytes", "clean_snapshot_retained",
                  "newest_clean_kept", "oldest_retained_age"]  # fmt: skip
METRICS = {"recovery": "clean_recovery", "work_lost_h": "work_lost_whole_system_hours"}


def _row_key(df: pd.DataFrame) -> list[str]:
    return [k for k in [*PAIR_KEY, "true_start", "detect_prob", "budget_kind", "policy"] if k in df]


def _clusters(df: pd.DataFrame) -> pd.Series:
    """One cluster per simulated machine (world, true start, rep): shared across q and b."""
    cols = [c for c in ("world", "true_start", "rep") if c in df]
    return df[cols].astype(str).agg("|".join, axis=1)


def pair_old_new(old: pd.DataFrame, new: pd.DataFrame) -> pd.DataFrame:
    """Row-for-row pairing of two runs on the same machines; raises unless every row pairs and
    retention (the kept set) is identical, so only the restore differs."""
    key = _row_key(new)
    cols = key + list(METRICS.values()) + RETENTION_COLS
    m = old[cols].merge(new[cols], on=key, suffixes=("_old", "_new"), validate="one_to_one")
    if len(m) != len(old) or len(m) != len(new):
        raise ValueError(f"pairing incomplete: old {len(old)}, new {len(new)}, paired {len(m)}")
    for c in RETENTION_COLS:
        a, b = m[f"{c}_old"], m[f"{c}_new"]
        if not ((a == b) | (a.isna() & b.isna())).all():
            raise ValueError(f"retention differs in {c}")
    return m


def paired_deltas(m: pd.DataFrame, by=("policy",), n_boot: int = 2000) -> pd.DataFrame:
    """Per group of a paired frame: old and new means, new - old with a machine-cluster bootstrap
    95% CI, and for work lost the relative change with its CI."""
    from slowburn.bench.stats import cluster_bootstrap_ratio

    rows = []
    for g, x in m.groupby(list(by)):
        r = dict(zip(by, g if isinstance(g, tuple) else (g,), strict=True), pairs=len(x))
        cl = _clusters(x)
        for name, col in METRICS.items():
            o, n_ = x[f"{col}_old"].to_numpy(float), x[f"{col}_new"].to_numpy(float)
            r[f"{name}_old"], r[f"{name}_new"] = o.mean(), n_.mean()
            d, lo, hi = cluster_bootstrap_ratio(n_ - o, np.ones(len(o)), cl, n_boot)
            r.update({f"{name}_delta": d, f"{name}_delta_lo": lo, f"{name}_delta_hi": hi})
        rel = cluster_bootstrap_ratio(x.work_lost_whole_system_hours_new
                                      - x.work_lost_whole_system_hours_old,
                                      x.work_lost_whole_system_hours_old, cl, n_boot)  # fmt: skip
        r.update(dict(zip(("work_lost_rel", "work_lost_rel_lo", "work_lost_rel_hi"), rel,
                          strict=True)))  # fmt: skip
        rows.append(r)
    return pd.DataFrame(rows)


def evidence_reduction(df: pd.DataFrame, by=(), n_boot: int = 2000) -> pd.DataFrame:
    """C3': SlowBurn vs prior-only relative work-lost change on paired machines (count budgets),
    with SlowBurn minus prior-only recovery; machine-cluster bootstrap CIs."""
    from slowburn.bench.stats import cluster_bootstrap_ratio

    d = df[df.budget_kind == "count"] if "budget_kind" in df else df
    key = [k for k in _row_key(d) if k != "policy"]
    cols = key + list(METRICS.values())
    sb, po = d[d.policy == "slowburn"][cols], d[d.policy == "prior_only"][cols]
    m = sb.merge(po, on=key, suffixes=("_sb", "_po"), validate="one_to_one")
    if len(m) != len(sb) or len(m) != len(po):
        raise ValueError("SlowBurn / prior-only pairing incomplete")
    groups = m.groupby(list(by)) if by else [((), m)]
    rows = []
    for g, x in groups:
        cl = _clusters(x)
        wl = "work_lost_whole_system_hours"
        rel = cluster_bootstrap_ratio(x[f"{wl}_sb"] - x[f"{wl}_po"], x[f"{wl}_po"], cl, n_boot)
        rec = cluster_bootstrap_ratio(x.clean_recovery_sb - x.clean_recovery_po,
                                      np.ones(len(x)), cl, n_boot)  # fmt: skip
        rows.append({**dict(zip(by, g if isinstance(g, tuple) else (g,), strict=True)),
                     "pairs": len(x),
                     "recovery_slowburn": x.clean_recovery_sb.mean(),
                     "recovery_prior_only": x.clean_recovery_po.mean(),
                     "work_lost_slowburn": x[f"{wl}_sb"].mean(),
                     "work_lost_prior_only": x[f"{wl}_po"].mean(),
                     "work_lost_rel": rel[0], "work_lost_rel_lo": rel[1],
                     "work_lost_rel_hi": rel[2],
                     "recovery_delta": rec[0], "recovery_delta_lo": rec[1],
                     "recovery_delta_hi": rec[2]})  # fmt: skip
    return pd.DataFrame(rows)
