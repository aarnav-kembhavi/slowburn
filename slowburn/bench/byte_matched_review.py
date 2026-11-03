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


if __name__ == "__main__":
    {"item4": item4, "item5": item5}[sys.argv[1]]()
