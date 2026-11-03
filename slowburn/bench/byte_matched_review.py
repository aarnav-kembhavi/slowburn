"""D81 review (exploratory_dev_v3, DEV only): items 4 and 5, numbers and tables only.

Item 4: prior_only against SlowBurn at the sbdaymed byte levels, per K; the 5 (level, machine)
cells with the largest summed recovery difference, with both policies' retained snapshot days at
each discovery day (replayed at their K' with the run's own tasks) and the attack window.
Item 5: feasible against infeasible machines on the run-max per machine covariates.

    uv run python -m slowburn.bench.byte_matched_review item4|item5
"""

from __future__ import annotations

import pickle
import sys

import pandas as pd

from slowburn.bench import method_v2 as mv
from slowburn.bench.byte_matched import LEVEL_KS, base_hp
from slowburn.bench.byte_matched_report import REC, ROOT, WL, load
from slowburn.utils.config import load_config

OUT = ROOT / "d81_report"
MACH = ["world", "benign_invalid_rate", "rep"]
ARMS = tuple(sys.argv[2:]) or ("napierone", "synthetic")


def item4_rows() -> tuple[pd.DataFrame, pd.DataFrame]:
    per_k, top = [], []
    for arm in ARMS:
        d = load(f"d81_{arm}")
        x = d[~d.d81_infeasible.astype(bool)].copy()
        x["budget"], x["budget_kind"] = x.d81_level, x.d81_arm
        for lev in [f"sbdaymed_K{K}" for K in LEVEL_KS] + [f"count_K{K}" for K in LEVEL_KS]:
            r = mv.policy_vs_policy(x[x.d81_level == lev], "slowburn", "prior_only")
            per_k.append(r.assign(arm=arm, d81_level=lev))
        b = x[x.d81_level.str.startswith("sbdaymed")]
        cols = [*MACH, "true_start", "d81_level", "discovery_delay"]
        m = b[b.policy == "slowburn"].merge(b[b.policy == "prior_only"], on=cols,
                                            suffixes=("_sb", "_po"))  # fmt: skip
        m["rec_diff"] = m[f"{REC}_sb"] - m[f"{REC}_po"]
        g = (m.groupby([*MACH, "true_start", "d81_level"])
             .agg(rec_diff_sum=("rec_diff", "sum"), kprime_sb=("d81_kprime_sb", "first"),
                  kprime_po=("d81_kprime_po", "first"),
                  budget_mib=("d81_budget_bytes_sb", lambda s: s.iloc[0] / 2**20))
             .reset_index().sort_values("rec_diff_sum", ascending=False).head(5))  # fmt: skip
        top.append(g.assign(arm=arm))
    return pd.concat(per_k, ignore_index=True), pd.concat(top, ignore_index=True)


def held_days(cfg, task, trace, hp, name: str, k: int, days: list[int]) -> dict:
    """The snapshot days ``name`` holds at count k on each of ``days`` (same replay as
    ``byte_matched.daily_bytes``)."""
    import numpy as np

    from slowburn.bench.retention_experiment import make_policies, start_posteriors
    from slowburn.retention.base import RetentionContext
    from slowburn.retention.dp import discovery_survival, retention_posterior

    ad = hp["assumed_discovery"]
    S = discovery_survival(ad["kind"], int(ad["max_days"]), float(ad.get("tail", 0.0)),
                           float(ad.get("alpha", 1.0)))  # fmt: skip
    path, prior = start_posteriors(trace, hp, int(cfg["warmup_days"]),
                                   task.params.get("null_prior"), {})  # fmt: skip
    stat = np.array([o.value for o in trace.obs])
    pol = make_policies(hp, float(task.params.get("vault_threshold", 0.0)))[name]
    held, out = {}, {}
    for t in range(max(days) + 1):
        T = t + 1
        held[t] = t
        ctx = RetentionContext(day=t, snapshot_days=dict(held), budget=k,
                               daily_stat=stat[: t + 1], start_posterior=path[T],
                               retention_pi=retention_posterior(path[T], t, S),
                               prior_retention_pi=retention_posterior(prior[T], t, S),
                               oracle_start=trace.start)  # fmt: skip
        held = {sid: held[sid] for sid in pol.decide(ctx)}
        if t in days:
            out[t] = sorted(held.values())
    return out


def item4() -> None:
    from slowburn.bench.retention_experiment import simulate

    per_k, top = item4_rows()
    per_k.to_csv(OUT / "review_item4_prior_only_per_k.csv", index=False)
    lines = []
    for arm in ARMS:
        cfg = load_config(f"configs/dev_v3_d81_{arm}.yaml")
        hp = base_hp(cfg)
        tasks = pickle.loads((ROOT / f"d81_{arm}" / "d81max_machines_tasks.pkl").read_bytes())
        delays = [int(d) for d in cfg["discovery_delay"]]
        d = load(f"d81_{arm}")
        for r in top[top.arm == arm].itertuples():
            (task,) = [t for t in tasks if t.rep == r.rep and t.params["world"] == r.world
                       and t.params["benign_invalid_rate"] == r.benign_invalid_rate]  # fmt: skip
            trace = simulate(cfg, task)
            disc = [trace.start + dl for dl in delays]
            rows = d[(d.d81_level == r.d81_level) & (d.rep == r.rep) & (d.world == r.world)
                     & (d.benign_invalid_rate == r.benign_invalid_rate)
                     & d.policy.isin(["slowburn", "prior_only"])]  # fmt: skip
            lines.append(f"\n{arm} {r.world} rate={r.benign_invalid_rate} rep={r.rep} "
                         f"{r.d81_level} budget {r.budget_mib:.2f} MiB: attack window "
                         f"[{trace.start}, disc]; K' slowburn={r.kprime_sb} "
                         f"prior_only={r.kprime_po}; rec diff {r.rec_diff_sum:+.0f}")  # fmt: skip
            for nm, k in (("slowburn", r.kprime_sb), ("prior_only", r.kprime_po)):
                h = held_days(cfg, task, trace, hp, nm, int(k), disc)
                for dl, t in zip(delays, disc, strict=True):
                    row = rows[(rows.policy == nm) & (rows.discovery_delay == dl)].iloc[0]
                    lines.append(f"  {nm:10s} delay {dl:2d} discovery day {t}: held {h[t]} "
                                 f"restore {row.restore_point} clean {row[REC]:.0f} "
                                 f"WL {row[WL]:.0f} h")  # fmt: skip
    text = "\n".join(lines)
    (OUT / "review_item4_top5.txt").write_text("label exploratory_dev_v3\n" + text + "\n")
    print(per_k[["arm", "d81_level", "pairs", "recovery_diff", "recovery_diff_lo",
                 "recovery_diff_hi", "work_lost_rel", "work_lost_rel_lo",
                 "work_lost_rel_hi"]].round(3).to_string(index=False))  # fmt: skip
    print(text)


def item5() -> None:
    feats = None
    out = []
    groups = {"bar_on": ["shamir_recursive", "shamir_rr"], "eqh": ["gfs_eqh", "toh_eqh"]}
    for arm in ARMS:
        d = load(f"d81_{arm}")
        m = pd.read_csv(ROOT / f"d81_{arm}" / "d81max_machines_rows.csv.gz", low_memory=False)
        feats = [c for c in m.columns if c.startswith("d81_feat_")]
        f = m[m.d81_arm == "bytes"].drop_duplicates(MACH)[[*MACH, *feats, "d81_day0_bytes"]]
        b = d[d.d81_arm == "bytes"].drop_duplicates([*MACH, "d81_level", "policy"])
        for pol_group in groups.values():
            for nm in pol_group:
                for lev, g in b[b.policy == nm].groupby("d81_level"):
                    g = g[MACH + ["d81_infeasible"]].merge(f, on=MACH)
                    for inf, h in g.groupby(g.d81_infeasible.astype(bool)):
                        out.append({"arm": arm, "policy": nm, "d81_level": lev,
                                    "machines": "infeasible" if inf else "feasible", "n": len(h),
                                    **h[[*feats, "d81_day0_bytes"]].mean().to_dict()})  # fmt: skip
    t = pd.DataFrame(out)
    t["d81_day0_mib"] = t.pop("d81_day0_bytes") / 2**20
    t.to_csv(OUT / "review_item5_selection.csv", index=False)
    print(t.round(4).to_string(index=False))


LEVELS = [f"{p}{K}" for p in ("count_K", "sbdaymed_K", "sbmax_K") for K in LEVEL_KS]
PRIMARY = {"sbmax_K8", "sbmax_K12"}  # Bar-On claims: primary byte levels (review 2)


def _ci(r, col: str) -> str:
    return f"{r[col]:+.3f} [{r[col + '_lo']:+.3f}, {r[col + '_hi']:+.3f}]"


def review2() -> None:
    """Review 2 tables 1-3 on existing outputs: SlowBurn minus GFS / ToH by level family and K;
    Bar-On and eqh comparisons by churn tercile (feasible pairs only); Bar-On primary rows."""
    c = pd.read_csv(OUT / "slowburn_vs_policy.csv")
    c["arm"] = c.arm.str.replace("_bytes", "")
    c = c[c.d81_level.isin(LEVELS)]
    c["family"] = c.d81_level.str.rsplit("_", n=1).str[0]
    c["K"] = c.d81_level.str.rsplit("K", n=1).str[1].astype(int)
    c["recovery_diff_ci"] = c.apply(_ci, axis=1, col="recovery_diff")
    c["work_lost_rel_ci"] = c.apply(_ci, axis=1, col="work_lost_rel")
    cols = ["arm", "vs", "family", "K", "pairs", "recovery_diff_ci", "work_lost_rel_ci"]
    t1 = c[c.vs.isin(["gfs", "tower_of_hanoi"])].sort_values(["arm", "vs", "family", "K"])[cols]
    t1.to_csv(OUT / "review2_t1_gfs_toh_by_level.csv", index=False)
    print("T1 SlowBurn minus GFS / ToH\n" + t1.to_string(index=False))

    t2 = []
    for arm in ARMS:
        f = ROOT / f"d81_{arm}" / "d81max_machines_rows.csv.gz"
        if not f.exists():
            print(f"\nT2 {arm}: no per machine churn yet (sbmax run pending)")
            continue
        m = pd.read_csv(f, low_memory=False, usecols=[*MACH, "d81_arm", "d81_feat_churn"])
        ch = m[m.d81_arm == "bytes"].drop_duplicates(MACH)[[*MACH, "d81_feat_churn"]]
        ch["churn_tercile"] = pd.qcut(ch.d81_feat_churn, 3, labels=["low", "mid", "high"])
        d = load(f"d81_{arm}")
        x = d[~d.d81_infeasible.astype(bool) & d.d81_level.isin(LEVELS)]
        x = x.drop(columns=[k for k in x.columns if k.startswith("d81_feat_")]).merge(ch, on=MACH)
        x["budget"], x["budget_kind"] = x.d81_level, x.d81_arm
        for (lev, terc), g in x.groupby(["d81_level", "churn_tercile"], observed=True):
            for base in ("shamir_recursive", "shamir_rr", "gfs_eqh", "toh_eqh"):
                if not {"slowburn", base} <= set(g.policy):
                    continue
                r = mv.policy_vs_policy(g, "slowburn", base).iloc[0]
                t2.append({"arm": arm, "vs": base, "d81_level": lev, "churn_tercile": terc,
                           "churn_range": f"{g.d81_feat_churn.min():.4f}-"
                                          f"{g.d81_feat_churn.max():.4f}",
                           "pairs": int(r.pairs), "recovery_diff_ci": _ci(r, "recovery_diff"),
                           "work_lost_rel_ci": _ci(r, "work_lost_rel")})  # fmt: skip
    t2 = pd.DataFrame(t2)
    if not t2.empty:
        t2["_o"] = t2.d81_level.map(LEVELS.index)
        t2 = t2.sort_values(["arm", "vs", "_o", "churn_tercile"]).drop(columns="_o")
        t2.to_csv(OUT / "review2_t2_baron_eqh_by_churn.csv", index=False)
        print("\nT2 SlowBurn minus Bar-On / eqh by churn tercile (feasible pairs)\n"
              + t2.to_string(index=False))  # fmt: skip

    fe = pd.read_csv(OUT / "feasibility.csv")
    fe["arm"] = fe.arm.str.replace("_bytes", "")
    t3 = c[c.vs.isin(["shamir_recursive", "shamir_rr"]) & (c.family != "count")]
    t3 = t3.merge(fe.rename(columns={"policy": "vs"})[["arm", "vs", "d81_level", "infeasible"]],
                  on=["arm", "vs", "d81_level"], how="left")  # fmt: skip
    t3["status"] = t3.d81_level.map(lambda v: "primary" if v in PRIMARY else
                                    ("selected subset" if v.endswith(("K4", "K6")) else
                                     "secondary"))  # fmt: skip
    t3 = t3.sort_values(["arm", "vs", "status", "family", "K"])
    t3 = t3[["arm", "vs", "d81_level", "status", "infeasible", "pairs", "recovery_diff_ci",
             "work_lost_rel_ci"]]  # fmt: skip
    t3.to_csv(OUT / "review2_t3_baron_primary.csv", index=False)
    print("\nT3 SlowBurn minus Bar-On at byte levels\n" + t3.to_string(index=False))


HORIZON = 60


def review3() -> None:
    """Review 3 tables on existing outputs. T1: per policy and sbmax K, the share of the 480
    machines whose retained set at discovery reaches back HORIZON days at every delay
    (oldest_retained_age >= 60; infeasible machines count as not reaching), with mean recovery and
    work lost over those machines. T2: per policy, the smallest byte level (ordered by mean budget
    / day-0) whose mean recovery (feasible rows) is >= SlowBurn's mean recovery at each sbmax K."""
    t1, t2 = [], []
    for arm in ARMS:
        d = load(f"d81_{arm}")
        b = d[d.d81_arm == "bytes"].copy()
        if not b.d81_level.str.startswith("sbmax").any():
            print(f"{arm}: sbmax rows pending")
            continue
        b["feas"] = ~b.d81_infeasible.astype(bool)
        b["reach"] = b.feas & (b.oldest_retained_age >= HORIZON)
        for (lev, nm), g in b[b.d81_level.str.startswith("sbmax")].groupby(["d81_level", "policy"]):
            mach = g.groupby(MACH).reach.all()
            ok = g.set_index(MACH).loc[mach[mach].index]
            t1.append({"arm": arm, "d81_level": lev, "policy": nm, "machines": len(mach),
                       "share_60d": mach.mean(), "n_60d": int(mach.sum()),
                       "recovery_60d": ok[REC].mean(),
                       "work_lost_h_60d": ok[WL].mean()})  # fmt: skip
        f = b[b.feas]
        mult = (f.d81_budget_bytes / f.d81_day0_bytes).groupby(f.d81_level).mean().sort_values()
        rec = f.groupby(["d81_level", "policy"])[REC].mean()
        nfe = (
            f.drop_duplicates([*MACH, "d81_level", "policy"])
            .groupby(["d81_level", "policy"])
            .size()
        )
        for K in LEVEL_KS:
            ref = rec[(f"sbmax_K{K}", "slowburn")]
            for nm in sorted(f.policy.unique()):
                hit = [lv for lv in mult.index if (lv, nm) in rec.index and rec[(lv, nm)] >= ref]
                lv = hit[0] if hit else None
                t2.append({"arm": arm, "reference": f"slowburn sbmax_K{K}", "ref_recovery": ref,
                           "policy": nm, "smallest_level": lv or "not reached",
                           "level_mult": mult[lv] if lv else float("nan"),
                           "policy_recovery": rec[(lv, nm)] if lv else float("nan"),
                           "feasible_machines": int(nfe[(lv, nm)]) if lv else None})  # fmt: skip
        print(f"{arm} level ladder (mean budget / day-0): "
              + ", ".join(f"{k} {v:.2f}" for k, v in mult.items()))  # fmt: skip
    t1, t2 = pd.DataFrame(t1), pd.DataFrame(t2)
    t1["_o"] = t1.d81_level.map(LEVELS.index)
    t1 = t1.sort_values(["arm", "policy", "_o"]).drop(columns="_o")
    t1.to_csv(OUT / "review3_t1_horizon60_sbmax.csv", index=False)
    t2.to_csv(OUT / "review3_t2_smallest_level_matching_slowburn.csv", index=False)
    print("T1 60-day horizon at sbmax\n" + t1.round(3).to_string(index=False))
    print(
        "\nT2 smallest level matching SlowBurn mean recovery\n" + t2.round(3).to_string(index=False)
    )


if __name__ == "__main__":
    {"item4": item4, "item5": item5, "review2": review2, "review3": review3}[sys.argv[1]]()
