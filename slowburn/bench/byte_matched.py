"""D81 byte-budget arm (OPEN_QUESTIONS 2026-11-02, protocol v3; exploratory_dev_v3, DEV only).

Every policy is held to the same repository bytes by the team rule: for each machine, policy and
budget level, K' is the largest snapshot count in 2..24 whose retained unique bytes stay within
the budget on every day of the run (each count simulated with the policy's own count rule). K' is
fixed per machine; the machine's work lost and recovery at that level are its rows at count K',
produced by the unchanged ``evaluate_trace``. No policy is byte-aware.

Levels (multipliers of the machine's day-0 snapshot size, D46 convention), per arm and benign
invalid rate, from the 40 attack-free DEV calibration machines:
* ``sbdaymed_K{K}``, K in {4, 6, 8, 12} (written ``sb_K{K}`` in levels.json, the first run): the
  median over all pooled calibration machine-days after warm-up (not a median over machines) of
  SlowBurn's daily retained unique bytes at count K / that machine's day-0 size;
* ``sbmax_K{K}`` (D81 addendum, levels_sbmax.json): the median over calibration machines of each
  machine's MAX daily retained unique bytes at count K over every day of the run / day-0 size;
* secondary ``keep30``: the D46 keep-last 30-day footprint (``attack_free_calibration``).

Run from the repo root (one heavy job at a time):

    uv run python -u -m slowburn.bench.byte_matched calibrate CONFIG     # levels -> levels.json
    uv run python -u -m slowburn.bench.byte_matched calibrate-max CONFIG # -> levels_sbmax.json
    uv run python -u -m slowburn.bench.byte_matched run CONFIG [--pilot N]
    uv run python -u -m slowburn.bench.byte_matched run-max CONFIG [--pilot N]
    uv run python -u -m slowburn.bench.byte_matched run-tol CONFIG [--pilot N]  # D89
"""

from __future__ import annotations

import json
import pickle
import sys
import time
from dataclasses import replace

import numpy as np
import pandas as pd

from slowburn.bench.parallel import run_tasks
from slowburn.bench.registry import load_frozen
from slowburn.bench.retention_experiment import (
    RetentionTask,
    attack_free_calibration,
    build_tasks,
    evaluate_trace,
    make_policies,
    simulate,
    start_posteriors,
    task_cache_key,
)
from slowburn.retention.base import RetentionContext
from slowburn.retention.bytes import ByteIndex
from slowburn.retention.dp import discovery_survival, retention_posterior
from slowburn.utils.config import load_config, resolve_path

COUNTS = tuple(range(2, 25))  # the supported range of K' (team rule)
LEVEL_KS = (4, 6, 8, 12)
AT_CAP = 0.95  # a day is "at the cap" when retained bytes >= 0.95 x budget
LABEL = "exploratory_dev_v3"
# D89 (OPEN_QUESTIONS 2026-11-04): verify_snap tolerances; ("N", 1) is the untuned restore
D89_TOLS = [("N", 1), ("N", 2), ("N", 3), ("N", 5), ("N", 10),
            ("T", 0.001), ("T", 0.002), ("T", 0.005), ("T", 0.01), ("T", 0.02)]  # fmt: skip
D89_POLICIES = ["slowburn", "gfs", "tower_of_hanoi", "gfs_eqh", "toh_eqh", "shamir_recursive"]
D89_COUNTS = (8, 12)


def base_hp(cfg: dict) -> dict:
    """The frozen operating point with the config's single variant applied (as run_dev_sweep)."""
    frozen = load_frozen(cfg.get("frozen_path", "configs/frozen.yaml")).get("params", {})
    hp = {**cfg["hp"], **{k: v for k, v in frozen.items() if k in cfg["hp"]}}
    (v,) = cfg["variants"]
    return {**hp, **v["hp"], "_variant": v["name"]}


def supported(pol, c: int) -> bool:
    """The policy's own feasibility test, plus Bar-On schedules that cannot be built at count c
    (round robin has no schedule for one checkpoint, c = 2); reported per policy by ``run``."""
    if not getattr(pol, "supports", lambda K: True)(c):
        return False
    if hasattr(pol, "schedule"):
        try:
            pol.schedule(c)
        except (IndexError, ValueError, TypeError, ZeroDivisionError):
            return False
    return True


def daily_bytes(cfg: dict, task: RetentionTask, trace, hp: dict, names, counts,
                cache: dict) -> dict:  # fmt: skip
    """{(policy, count): per-day retained unique bytes} for every supported count, simulated with
    the same count rule and contexts as ``evaluate_trace``."""
    p = task.params
    warmup = int(cfg["warmup_days"])
    ad = hp["assumed_discovery"]
    S = discovery_survival(ad["kind"], int(ad["max_days"]), float(ad.get("tail", 0.0)),
                           float(ad.get("alpha", 1.0)))  # fmt: skip
    path, prior = start_posteriors(trace, hp, warmup, p.get("null_prior"), cache)
    stat = np.array([o.value for o in trace.obs])
    pols = {nm: pol for nm, pol in make_policies(hp, float(p.get("vault_threshold", 0.0))).items()
            if nm in names}  # fmt: skip
    index = ByteIndex(trace.snapshots, trace.chunk_size)
    keys = [(nm, c) for nm in pols for c in counts if supported(pols[nm], c)]
    held = {k: {} for k in keys}
    out = {k: np.zeros(trace.n_days, dtype=np.int64) for k in keys}
    for t in range(trace.n_days):
        T = t + 1
        rpi = retention_posterior(path[T], t, S)
        ppi = retention_posterior(prior[T], t, S)
        for nm, c in keys:
            hk = held[(nm, c)]
            hk[t] = t
            ctx = RetentionContext(day=t, snapshot_days=dict(hk), budget=c,
                                   daily_stat=stat[: t + 1], start_posterior=path[T],
                                   retention_pi=rpi, prior_retention_pi=ppi,
                                   oracle_start=trace.start)  # fmt: skip
            keep = pols[nm].decide(ctx)
            held[(nm, c)] = {sid: hk[sid] for sid in keep}
            out[(nm, c)][t] = index.unique_bytes(held[(nm, c)].values())
    return out, index.size(0)


# ---- calibration of the budget levels (attack-free DEV calibration machines) -----------------


def _calib_task(args) -> dict:
    """SlowBurn's retained bytes / day-0 size at each level count on one attack-free calibration
    machine (the machine ``attack_free_calibration`` simulates): the days after warm-up, and the
    max over every day of the run (``sbmax``)."""
    task, clean = args
    cfg, hp = _W["cfg"], _W["hp"]
    trace = simulate(cfg, replace(task, params=clean))
    b, size0 = daily_bytes(cfg, task, trace, hp, ["slowburn"], LEVEL_KS, {})
    w = int(cfg["warmup_days"])
    days = {K: b[("slowburn", K)][w:] / size0 for K in LEVEL_KS}
    return days | {("max", K): b[("slowburn", K)].max() / size0 for K in LEVEL_KS}


def calibrate(cfg: dict, log=print, kind: str = "daymed") -> dict:
    from slowburn.bench.runner import expand_sweep

    hp = base_hp(cfg)
    n_cal = int(cfg.get("vault_calib_machines", 40))
    levels = {}
    for setting in expand_sweep(cfg["scenario"], cfg.get("sweep", {})):
        thr, prior, mult, _ = attack_free_calibration(cfg, setting, "dev", n_cal, byte_ks=[30])
        clean = {**setting, "attack_start": None}
        params = {**clean, "vault_threshold": thr, "null_prior": tuple(map(float, prior))}
        args = [(RetentionTask("dev", "vault_calib", params, r), clean) for r in range(n_cal)]
        res = run_tasks(_calib_task, args, workers=int(cfg.get("workers", 1)), init=_init,
                        init_args=(cfg, hp, {}), log=log)  # fmt: skip
        key = f"benign_invalid_rate={setting.get('benign_invalid_rate')}"
        if kind == "max":  # median over machines of each machine's max daily bytes
            levels[key] = {f"sbmax_K{K}": float(np.median([x[("max", K)] for x in res]))
                           for K in LEVEL_KS}  # fmt: skip
            # check: the pooled machine-day medians reproduce levels.json (sb_K)
            levels[key]["_check_sb_K"] = {f"sb_K{K}": float(np.median(np.concatenate(
                [x[K] for x in res]))) for K in LEVEL_KS}  # fmt: skip
        else:  # median over pooled machine-days after warm-up
            ratios = {K: np.concatenate([x[K] for x in res]) for K in LEVEL_KS}
            levels[key] = {**{f"sb_K{K}": float(np.median(ratios[K])) for K in LEVEL_KS},
                           "keep30": float(mult[30])}  # fmt: skip
        log(f"  {key}: {levels[key]}")
    return levels


# ---- evaluation ------------------------------------------------------------------------------

_W: dict = {}


def _init(cfg: dict, hp: dict, levels: dict, count_ks=LEVEL_KS) -> None:
    _W.update(cfg=cfg, hp=hp, levels=levels, count_ks=tuple(count_ks))


TYPES = ("txt", "csv", "bin", "docx", "zip", "png", "jpg", "mp3", "zlib")


def machine_features(trace, size0: int) -> dict:
    """Per machine covariates for the feasibility selection check (review item 5), pre-attack
    days only: churn = mean new unique bytes per day / day-0 size; benign flag rate = flagged
    (file, day) pairs per file-day; the file type mix; the attack start."""
    s = trace.start
    churn = [len(trace.snapshots[t] - trace.snapshots[t - 1]) * trace.chunk_size / size0
             for t in range(1, s)]  # fmt: skip
    n = max(len(trace.histories), 1)
    flags = sum(sum(1 for d in h.flagged_days if d < s) for h in trace.histories.values())
    types = list(trace.file_types.values())
    return {
        "d81_feat_churn": float(np.mean(churn)),
        "d81_feat_benign_flag_rate": flags / (n * s),
        "d81_feat_attack_start": s,
        **{f"d81_feat_type_{ft}": types.count(ft) / max(len(types), 1) for ft in TYPES},
    }


def evaluate_machine(task: RetentionTask) -> list[dict]:
    cfg, hp, levels, cks = _W["cfg"], _W["hp"], _W["levels"], _W["count_ks"]
    names = list(cfg["policies"])
    t0 = time.perf_counter()
    trace = simulate(cfg, task)
    sim_s = time.perf_counter() - t0
    cache: dict = {}
    b, size0 = daily_bytes(cfg, task, trace, hp, names, COUNTS, cache)
    feat = machine_features(trace, size0)
    lev = levels[f"benign_invalid_rate={task.params.get('benign_invalid_rate')}"]
    sel = []  # (level, policy, budget bytes, K' or None, max bytes at K', days at cap)
    for name, mult in lev.items():
        budget = mult * size0
        for nm in names:
            fit = [c for c in COUNTS if (nm, c) in b and b[(nm, c)].max() <= budget]
            k = max(fit) if fit else None
            at_cap = int((b[(nm, k)] >= AT_CAP * budget).sum()) if k else np.nan
            sel.append((name, nm, budget, k, b[(nm, k)].max() if k else np.nan, at_cap))
    rows = []
    for nm in names:  # each policy at the registered counts and its own selected K' only
        need = sorted(set(cks) | {s[3] for s in sel if s[1] == nm and s[3] is not None})
        rows += evaluate_trace({**cfg, "budgets": need}, task, trace, hp, [nm], sim_s,
                               posterior_cache=cache)  # fmt: skip
    by = {(r["policy"], r["budget"], r["discovery_delay"], r.get("d89_rule")): r for r in rows}
    rules = sorted({r.get("d89_rule") for r in rows}, key=str)
    out = []
    for r in rows:  # matched count: the registered count budgets, unchanged rows
        if r["budget"] in cks:
            out.append({**r, "d81_arm": "count", "d81_level": f"count_K{r['budget']}",
                        "d81_kprime": r["budget"], "d81_infeasible": False})  # fmt: skip
    delays = [int(d) for d in cfg["discovery_delay"]]
    for (name, nm, budget, k, mx, at_cap), rule in [(s, u) for s in sel for u in rules]:
        for d in delays:
            meta = {"d81_arm": "bytes", "d81_level": name, "d81_budget_bytes": budget,
                    "d81_day0_bytes": size0, "d81_kprime": k, "d81_max_bytes": mx,
                    "d81_days_at_cap": at_cap, "d81_infeasible": k is None,
                    "d81_censored": k == COUNTS[-1]}  # fmt: skip
            if k is None:
                out.append({"policy": nm, "discovery_delay": d, "split": task.split,
                            "rep": task.rep, "true_start": trace.start,
                            **{c: task.params.get(c) for c in
                            ("world", "benign_invalid_rate")}, **meta,
                            **({"d89_rule": rule} if rule else {})})  # fmt: skip
                continue
            r = by[(nm, k, d, rule)]
            td = trace.start + d
            if r["retained_unique_bytes"] != b[(nm, k)][td]:  # same simulation as evaluate_trace
                raise AssertionError(f"{nm} K'={k} day {td}: byte replay differs from the rows")
            if r["retained_unique_bytes"] > budget:  # invariant (kill rule)
                raise AssertionError(f"{nm} at K'={k} exceeds its byte budget")
            out.append({**r, **meta})
    return [{**r, **feat} for r in out]


def run(cfg: dict, pilot: int | None = None, log=print, tag: str = "d81",
        M: int | None = None) -> pd.DataFrame:  # fmt: skip
    """tag "d81": the levels.json levels; "d81max": the sbmax addendum levels only. With ``M``
    (D82 stage 1 precheck): SlowBurn only, its assumed discovery bound set to M days (restore A
    uses the same bound), at the fixed sbmax_K8 and sbmax_K12 levels; tag d82pre_M{M}. tag "d89":
    the D89 policies at count K8 / K12 and sbmax K8 / K12, one row per verify_snap tolerance."""
    out = resolve_path(cfg["output_dir"])
    lfile = "levels.json" if tag == "d81" else "levels_sbmax.json"
    levels = json.loads((out / lfile).read_text())["levels"]
    keep = ("sbmax_K8", "sbmax_K12") if M or tag == "d89" else None
    levels = {s: {k: v for k, v in lv.items() if not k.startswith("_") and (not keep or k in keep)}
              for s, lv in levels.items()}  # fmt: skip
    hp = base_hp(cfg)
    if M:
        hp["assumed_discovery"] = {**hp["assumed_discovery"], "max_days": int(M)}
        cfg = {**cfg, "policies": ["slowburn"]}
    cks = LEVEL_KS
    if tag == "d89":
        hp["d89_tolerances"] = [list(t) for t in D89_TOLS]
        cfg, cks = {**cfg, "policies": D89_POLICIES}, D89_COUNTS
    tasks = build_tasks(cfg, "dev", log)
    name = "machines"
    if pilot:
        tasks, name = tasks[:pilot], "pilot"
    seed = int(cfg["seed"])
    with (out / f"{tag}_{name}_tasks.pkl").open("wb") as fh:  # for the review item 4 replay
        pickle.dump(tasks, fh)
    res = run_tasks(evaluate_machine, tasks, workers=int(cfg.get("workers", 1)), init=_init,
                    init_args=(cfg, hp, levels, cks), cache_dir=out / f"{name}_{tag}",
                    task_key=lambda t: task_cache_key(seed, t), log=log)  # fmt: skip
    df = pd.DataFrame([r for rows in res for r in rows])
    df["label"] = LABEL
    df.to_csv(out / f"{tag}_{name}_rows.csv.gz", index=False)
    return df


def main(argv: list[str]) -> None:
    cmd, path = argv[0], argv[1]
    cfg = load_config(path)
    out = resolve_path(cfg["output_dir"])
    out.mkdir(parents=True, exist_ok=True)
    if cmd == "calibrate":
        lv = calibrate(cfg)
        (out / "levels.json").write_text(json.dumps({"label": LABEL, "config": path,
                                                     "levels": lv}, indent=1))  # fmt: skip
    elif cmd == "calibrate-max":
        lv = calibrate(cfg, kind="max")
        (out / "levels_sbmax.json").write_text(json.dumps({"label": LABEL, "config": path,
                                                           "levels": lv}, indent=1))  # fmt: skip
    elif cmd in ("run", "run-max"):
        pilot = int(argv[3]) if len(argv) > 3 and argv[2] == "--pilot" else None
        run(cfg, pilot, tag="d81" if cmd == "run" else "d81max")
    elif cmd == "run-tol":  # D89
        pilot = int(argv[3]) if len(argv) > 3 and argv[2] == "--pilot" else None
        run(cfg, pilot, tag="d89")
    elif cmd == "run-m":  # D82 stage 1 precheck: run-m CONFIG M
        M = int(argv[2])
        run(cfg, tag=f"d82pre_M{M}", M=M)
    else:
        raise SystemExit(f"unknown command {cmd!r}")


if __name__ == "__main__":
    main(sys.argv[1:])
