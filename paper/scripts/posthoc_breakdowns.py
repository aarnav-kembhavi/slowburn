"""E2 / E3 (OPEN_QUESTIONS 2026-11-01): exploratory, post hoc breakdowns of the frozen TEST run
and the DEV v2 run, read only, no rerun, no Holm.

E2: C2 (SlowBurn vs each of the six baselines) and D79 (age-capped SlowBurn vs the equal-horizon
schedules) per world, per budget K and per benign invalid rate, with the confirmatory scripts'
paired machine-cluster bootstrap (method_v2.policy_vs_policy, 2000 resamples, seed 0); D74 per
world: the realistic attacker's mean recovery per policy and K, and the best-response strategy
chosen in analysis_<split>/d74_report/best_response.csv scored on the evaluation half per world
(delays 7 to 60 pooled). E3: mean retained snapshot count and retained unique bytes per policy
and K (recorded columns). Also the recorded per-row timing columns (infer_ms_per_day,
dp_ms_per_decision). Run from the repo root:

    uv run python paper/scripts/posthoc_breakdowns.py
"""

from pathlib import Path

import numpy as np
import pandas as pd

from slowburn.bench import method_v2 as mv
from slowburn.bench.stats import cluster_bootstrap_ratio as cbr

OUT = Path("results/exploratory")
ARMS = {"napierone_bytes": "napierone", "synthetic_bytes": "synthetic"}
C2_RUN = {"napierone_bytes": "d72_bytes_napierone_v2pool", "synthetic_bytes": "d72_bytes_synthetic"}
BASES = ("gfs_eqh", "toh_eqh", "gfs", "tower_of_hanoi", "shamir_recursive", "shamir_rr")
D79 = (("slowburn_age_gfs", "gfs_eqh"), ("slowburn_age_toh", "toh_eqh"))
SPLITS = ("world", "budget", "benign_invalid_rate")
STRAT = ["strategy_kind", "strategy_rate", "strategy_fraction", "strategy_targets"]
SWEEP_COLS = ["world", "rep", "true_start", "benign_invalid_rate", "discovery_delay", "budget",
              "budget_kind", "variant", "policy", "clean_recovery",
              "work_lost_whole_system_hours", "snapshots_retained", "retained_unique_bytes",
              "storage_vs_keep_last_n", "infer_ms_per_day", "dp_ms_per_decision"]  # fmt: skip
ATTACK_COLS = ["world", "rep", "policy", "budget", "discovery_delay", "grid_delay",
               "selection_half", "variant", "clean_recovery", *STRAT]  # fmt: skip
REALISTIC = {"strategy_kind": "grid", "strategy_rate": 0.5, "strategy_fraction": 0.1,
             "strategy_targets": "all"}  # fmt: skip


def sweep(path: str) -> pd.DataFrame:
    cols = pd.read_csv(path, nrows=0).columns
    d = pd.read_csv(path, usecols=[c for c in SWEEP_COLS if c in cols], low_memory=False)
    return d[(d.variant == "method_v2_w075_vsnap") & (d.budget_kind == "count")]


def compare(d: pd.DataFrame, pairs, split: str, arm: str) -> pd.DataFrame:
    out = []
    for a, b in pairs:
        for g in SPLITS:
            r = mv.policy_vs_policy(d, a, b, (g,))
            out.append(r.rename(columns={g: "level"}).assign(split=split, arm=arm, by=g))
    return pd.concat(out, ignore_index=True)


def d74_world(split: str, arm: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    d = pd.read_csv(f"results/{split}_d74_attack_{ARMS[arm]}/attack_rows.csv.gz",
                    usecols=ATTACK_COLS, low_memory=False)  # fmt: skip
    d = d[d.variant == "method_v2_w075_vsnap"]
    d["strategy_targets"] = d.strategy_targets.fillna("all")
    d = d[d.grid_delay & (d.discovery_delay <= 60)]
    cl = lambda x: x.world.astype(str) + "/" + x.rep.astype(str)  # noqa: E731
    rows = []
    real = d[(d[STRAT] == pd.Series(REALISTIC)).all(axis=1)]
    for (pol, K, w), x in real.groupby(["policy", "budget", "world"]):
        m, lo, hi = cbr(x.clean_recovery.astype(float), np.ones(len(x)), cl(x))
        rows.append({"split": split, "arm": arm, "attacker": "realistic", "policy": pol,
                     "budget": K, "world": w, "rows": len(x), "rec": m, "lo": lo, "hi": hi})  # fmt: skip
    br = pd.read_csv(f"results/analysis_{split}/d74_report/best_response.csv")
    br = br[(br.analysis == "primary_feasible") & (br.objective == "rec") & (br.restore == "A")
            & br.arm.str.startswith(arm) & (br.discovery_delay <= 60)]  # fmt: skip
    br["strategy_targets"] = br.strategy_targets.fillna("all")
    ev = d[~d.selection_half].merge(br[["policy", "budget", "discovery_delay", *STRAT]],
                                    on=["policy", "budget", "discovery_delay", *STRAT])  # fmt: skip
    for (pol, K, w), x in ev.groupby(["policy", "budget", "world"]):
        m, lo, hi = cbr(x.clean_recovery.astype(float), np.ones(len(x)), cl(x))
        rows.append({"split": split, "arm": arm, "attacker": "best_response_eval_d7_60",
                     "policy": pol, "budget": K, "world": w, "rows": len(x), "rec": m,
                     "lo": lo, "hi": hi})  # fmt: skip
    return pd.DataFrame(rows), br


def main() -> None:
    (OUT / "posthoc").mkdir(parents=True, exist_ok=True)
    (OUT / "storage").mkdir(parents=True, exist_ok=True)
    c2, d79, d74, store, timing = [], [], [], [], []
    for split in ("test", "dev"):
        for arm in ARMS:
            d = sweep(f"results/{split}_{C2_RUN[arm]}/tuning_sweep.csv")
            c2.append(compare(d, [("slowburn", b) for b in BASES], split, arm))
            g = d.groupby(["policy", "budget"])
            store.append(g[["snapshots_retained", "retained_unique_bytes",
                            "storage_vs_keep_last_n"]].mean().reset_index()
                         .assign(split=split, arm=arm))  # fmt: skip
            timing.append(d.groupby("policy")[["infer_ms_per_day", "dp_ms_per_decision"]]
                          .agg(["mean", "median"]).reset_index().assign(split=split, arm=arm))  # fmt: skip
            e = sweep(f"results/{split}_d79_eqh_{ARMS[arm]}/tuning_sweep.csv")
            d79.append(compare(e, D79, split, arm))
            d74.append(d74_world(split, arm)[0])
            print(split, arm, "done", flush=True)
    pd.concat(c2).to_csv(OUT / "posthoc/c2_breakdowns.csv", index=False)
    pd.concat(d79).to_csv(OUT / "posthoc/d79_breakdowns.csv", index=False)
    pd.concat(d74).to_csv(OUT / "posthoc/d74_by_world.csv", index=False)
    pd.concat(store).to_csv(OUT / "storage/storage_by_policy_K.csv", index=False)
    t = pd.concat(timing)
    t.columns = ["_".join(c).strip("_") if isinstance(c, tuple) else c for c in t.columns]
    t.to_csv(OUT / "overhead/recorded_timing.csv", index=False)


if __name__ == "__main__":
    main()
