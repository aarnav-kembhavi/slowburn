"""D89 report (OPEN_QUESTIONS 2026-11-04; exploratory_dev_v3, DEV only).

verify_snap tolerance N(n) / T(t) against the untuned restore N1, on the D89 runs
(``d81_{arm}/d89_machines_rows.csv.gz``). In the committed order:
1. checks: N1 reproduces the existing D81 rows (count from d81, sbmax from d81max) and retention
   is identical across rules row for row; if either fails, write checks.json and stop;
2. fit half: per grid point, pooled work lost and each policy's recovery change (pooled over
   cells, rates and arms); selected = lowest pooled work lost with EVERY policy's recovery no
   more than 0.01 below N1 (ties: the earlier point in D89_TOLS, the smaller tolerance);
3. check half at the selected point: per policy recovery and work lost change against N1 with
   paired machine-cluster bootstrap CIs, pooled too; kill if any policy's recovery drops by more
   than 0.01; success if pooled work lost is lower and no kill; SlowBurn minus each baseline in
   relative work lost change (primary for N(n), secondary for T(t)); per-cell changes.

    uv run python -m slowburn.bench.d89_report
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from slowburn.bench import method_v2 as mv
from slowburn.bench.byte_matched import D89_POLICIES, D89_TOLS, LABEL
from slowburn.bench.byte_matched_report import REC, ROOT, WL
from slowburn.bench.d82_precheck import halves

OUT = ROOT / "d89_report"
ARMS = ("napierone", "synthetic")
CELLS = ("count_K8", "count_K12", "sbmax_K8", "sbmax_K12")
RULES = [f"{f}{v:g}" for f, v in D89_TOLS]
BASE = "N1"
KEY = ["arm_name", "policy", "d81_level", "world", "true_start", "rep", "benign_invalid_rate",
       "discovery_delay"]  # fmt: skip
RET = [*mv.RETENTION_COLS, "d81_kprime", "d81_infeasible"]
NOT_COMPARED = {"sim_s", "infer_ms_per_day", "dp_ms_per_decision", "label", "d89_rule"}


def load(arm: str) -> pd.DataFrame:
    d = pd.read_csv(ROOT / f"d81_{arm}" / "d89_machines_rows.csv.gz", low_memory=False)
    return d[d.policy.isin(D89_POLICIES) & d.d81_level.isin(CELLS)].assign(arm_name=arm)


def existing(arm: str) -> pd.DataFrame:
    sub = ROOT / f"d81_{arm}"
    c = pd.read_csv(sub / "d81_machines_rows.csv.gz", low_memory=False)
    b = pd.read_csv(sub / "d81max_machines_rows.csv.gz", low_memory=False)
    x = pd.concat([c[c.d81_arm == "count"], b[b.d81_arm == "bytes"]])
    return x[x.policy.isin(D89_POLICIES) & x.d81_level.isin(CELLS)].assign(arm_name=arm)


def _same(a: pd.Series, o: pd.Series) -> pd.Series:
    s = (a.astype(str) == o.astype(str)) | (a.isna() & o.isna())
    try:
        af, of = a.astype(float), o.astype(float)
        s |= (af - of).abs() <= 1e-9 * np.maximum(1.0, of.abs())
    except (TypeError, ValueError):
        pass
    return s


def checks(d: pd.DataFrame) -> dict:
    out = {}
    for arm in ARMS:
        n1, old = d[(d.arm_name == arm) & (d.d89_rule == BASE)], existing(arm)
        m = n1.merge(old, on=KEY, suffixes=("", "_old"), validate="one_to_one")
        cols = [c for c in n1.columns if c not in KEY and c not in NOT_COMPARED
                and not c.startswith("d81_feat_") and f"{c}_old" in m]  # fmt: skip
        bad = {c: int((~_same(m[c], m[f"{c}_old"])).sum()) for c in cols}
        out[arm] = {"n1_rows": len(n1), "existing_rows": len(old), "paired": len(m),
                    "columns_compared": len(cols),
                    "differing": {c: v for c, v in bad.items() if v}}  # fmt: skip
    g = d.groupby(KEY)[RET].nunique(dropna=False)
    rules_per_row = d.groupby(KEY).d89_rule.nunique()
    out["retention_identical_across_rules"] = bool((g == 1).all().all())
    out["every_row_has_every_rule"] = bool((rules_per_row == len(RULES)).all())
    out["passed"] = (out["retention_identical_across_rules"] and out["every_row_has_every_rule"]
                     and all(out[a]["paired"] == out[a]["n1_rows"] == out[a]["existing_rows"]
                             and not out[a]["differing"] for a in ARMS))  # fmt: skip
    return out


def _pairframe(x: pd.DataFrame, per_policy: bool) -> pd.DataFrame:
    """Rule as the "policy"; arm, cell (and the policy when pooling over policies) folded into
    the budget key; one bootstrap cluster per arm and machine."""
    y = x.copy()
    y["budget"] = y.arm_name + "|" + y.d81_level + ("" if per_policy else "|" + x.policy)
    y["budget_kind"] = y.d81_arm
    y["world"] = y.arm_name + "|" + y.world.astype(str)
    y["policy"] = y.d89_rule
    return y


def vs_base(x: pd.DataFrame, rule: str, per_policy: bool) -> pd.DataFrame:
    if per_policy:
        return pd.concat([mv.policy_vs_policy(_pairframe(g, True), rule, BASE).assign(pol=p)
                          for p, g in x.groupby("policy")], ignore_index=True)  # fmt: skip
    return mv.policy_vs_policy(_pairframe(x, False), rule, BASE).assign(pol="pooled")


def sb_minus_baselines(x: pd.DataFrame, rule: str, n_boot: int = 2000) -> pd.DataFrame:
    """SlowBurn's relative work lost change (rule vs N1) minus each baseline's, paired
    machine-cluster bootstrap over arm x machine (each policy on its own feasible rows)."""
    cl = x.arm_name + "|" + x.world.astype(str) + "|" + x.true_start.astype(str) + "|" + \
        x.rep.astype(str)
    s = (x.assign(cl=cl).pivot_table(index="cl", columns=["policy", "d89_rule"], values=WL,
                                     aggfunc="sum", fill_value=0.0))  # fmt: skip
    rng = np.random.default_rng(89)
    idx = rng.integers(0, len(s), (n_boot, len(s)))

    def rel(p, v):
        return v[:, s.columns.get_loc((p, rule))] / v[:, s.columns.get_loc((p, BASE))] - 1

    full, boot = s.to_numpy()[None].sum(1), s.to_numpy()[idx].sum(1)
    rows = []
    for p in D89_POLICIES[1:]:
        est = float(rel("slowburn", full)[0] - rel(p, full)[0])
        b = rel("slowburn", boot) - rel(p, boot)
        rows.append({"vs": p, "slowburn_rel": float(rel("slowburn", full)[0]),
                     "baseline_rel": float(rel(p, full)[0]), "sb_minus_baseline": est,
                     "lo": float(np.quantile(b, 0.025)), "hi": float(np.quantile(b, 0.975))})
    return pd.DataFrame(rows)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    d = pd.concat([load(a) for a in ARMS], ignore_index=True)
    chk = {"label": LABEL, **checks(d)}
    (OUT / "checks.json").write_text(json.dumps(chk, indent=1))
    print(json.dumps(chk, indent=1))
    if not chk["passed"]:
        raise SystemExit("D89 checks failed: stop and report (pre-registered)")
    h = halves(d)
    d["half"] = [h[k] for k in zip(d.world, d.true_start, d.rep, strict=True)]
    f = d[~d.d81_infeasible.astype(bool)]

    grid = []  # descriptive, both halves; recovery change per policy is a mean difference
    for half, x in f.groupby("half"):
        b = x[x.d89_rule == BASE]
        for rule in RULES:
            r = x[x.d89_rule == rule]
            row = {"half": half, "rule": rule, "work_lost_h": r[WL].mean(),
                   "work_lost_h_N1": b[WL].mean(), "recovery": r[REC].mean(),
                   "recovery_N1": b[REC].mean()}  # fmt: skip
            for p in D89_POLICIES:
                rp, bp = r[r.policy == p], b[b.policy == p]
                row[f"rec_change_{p}"] = rp[REC].mean() - bp[REC].mean()
                row[f"wl_change_{p}"] = rp[WL].mean() / bp[WL].mean() - 1
            grid.append(row)
    grid = pd.DataFrame(grid)
    grid.to_csv(OUT / "grid_by_half.csv", index=False)
    fit = grid[(grid.half == "fit") & (grid.rule != BASE)].copy()
    fit["qualifies"] = fit[[f"rec_change_{p}" for p in D89_POLICIES]].min(axis=1) >= -0.01
    q = fit[fit.qualifies]
    verdict = {"label": LABEL, "rule": "OPEN_QUESTIONS D89 (c81ee4c)",
               "fit_qualifying_points": q.rule.tolist()}
    if q.empty:
        verdict.update(selected=None, d89_killed=True, kill_reason="no grid point qualifies on "
                       "the fit half")  # fmt: skip
    else:
        best = q[q.work_lost_h == q.work_lost_h.min()]
        sel = best.rule.iloc[0]  # ties: earlier in D89_TOLS (smaller tolerance)
        chk_half = f[f.half == "check"]
        pp = vs_base(chk_half, sel, True)
        po = vs_base(chk_half, sel, False)
        pd.concat([pp, po]).to_csv(OUT / "check_selected_vs_N1.csv", index=False)
        sb = sb_minus_baselines(chk_half, sel)
        sb.to_csv(OUT / "check_slowburn_minus_baselines.csv", index=False)
        cells = []
        for half, x in f.groupby("half"):
            for (arm, rate, cell), g in x.groupby(["arm_name", "benign_invalid_rate", "d81_level"]):
                c = vs_base(g, sel, True)
                cells.append(c.assign(half=half, arm=arm, benign_invalid_rate=rate, d81_level=cell))
        pd.concat(cells).to_csv(OUT / "cells_selected_vs_N1.csv", index=False)
        drop = pp[pp.recovery_diff < -0.01]
        kill = len(drop) > 0
        verdict.update(
            selected=sel, family="N(n)" if sel.startswith("N") else "T(t)",
            sb_vs_baselines="primary" if sel.startswith("N") else "secondary",
            fit_work_lost_h={"selected": float(best.work_lost_h.iloc[0]),
                             "N1": float(best.work_lost_h_N1.iloc[0])},
            check_per_policy={r.pol: {"recovery_diff": r.recovery_diff,
                                      "recovery_ci": [r.recovery_diff_lo, r.recovery_diff_hi],
                                      "work_lost_rel": r.work_lost_rel,
                                      "work_lost_ci": [r.work_lost_rel_lo, r.work_lost_rel_hi]}
                              for r in pp.itertuples()},
            check_pooled={k: float(po[k].iloc[0]) for k in
                          ("recovery_diff", "recovery_diff_lo", "recovery_diff_hi",
                           "work_lost_rel", "work_lost_rel_lo", "work_lost_rel_hi")},
            d89_killed=kill,
            kill_reason=(f"recovery drops by more than 0.01: {drop.pol.tolist()}" if kill
                         else None),
            d89_success=(not kill) and float(po.work_lost_rel.iloc[0]) < 0,
            parameters=2)  # fmt: skip
    (OUT / "verdict.json").write_text(json.dumps(verdict, indent=1, default=float))
    print(fit.round(4).to_string(index=False))
    print(json.dumps(verdict, indent=1, default=float))


if __name__ == "__main__":
    main()
