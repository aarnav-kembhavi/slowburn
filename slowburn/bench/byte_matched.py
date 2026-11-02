"""D81 byte-budget arm (OPEN_QUESTIONS 2026-11-02, protocol v3; exploratory_dev_v3, DEV only).

Every policy is held to the same repository bytes by the team rule: for each machine, policy and
budget level, K' is the largest snapshot count in 2..24 whose retained unique bytes stay within
the budget on every day of the run (each count simulated with the policy's own count rule). K' is
fixed per machine; the machine's work lost and recovery at that level are its rows at count K',
produced by the unchanged ``evaluate_trace``. No policy is byte-aware.

Levels (multipliers of the machine's day-0 snapshot size, D46 convention):
* primary ``sb_K{K}``, K in {4, 6, 8, 12}: the median, over the attack-free DEV calibration
  machines and days after warm-up, of SlowBurn's retained unique bytes at count K / day-0 size;
  per arm and benign invalid rate;
* secondary ``keep30``: the D46 keep-last 30-day footprint (``attack_free_calibration``).

Run from the repo root (one heavy job at a time):

    uv run python -u -m slowburn.bench.byte_matched calibrate CONFIG     # levels -> levels.json
    uv run python -u -m slowburn.bench.byte_matched run CONFIG [--pilot N]
"""

from __future__ import annotations

import json
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
    """SlowBurn's retained bytes / day-0 size at each level count, days after warm-up, on one
    attack-free calibration machine (the machine ``attack_free_calibration`` simulates)."""
    task, clean = args
    cfg, hp = _W["cfg"], _W["hp"]
    trace = simulate(cfg, replace(task, params=clean))
    b, size0 = daily_bytes(cfg, task, trace, hp, ["slowburn"], LEVEL_KS, {})
    w = int(cfg["warmup_days"])
    return {K: b[("slowburn", K)][w:] / size0 for K in LEVEL_KS}


def calibrate(cfg: dict, log=print) -> dict:
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
        ratios = {K: np.concatenate([x[K] for x in res]) for K in LEVEL_KS}
        key = f"benign_invalid_rate={setting.get('benign_invalid_rate')}"
        levels[key] = {**{f"sb_K{K}": float(np.median(ratios[K])) for K in LEVEL_KS},
                       "keep30": float(mult[30])}  # fmt: skip
        log(f"  {key}: {levels[key]}")
    return levels


# ---- evaluation ------------------------------------------------------------------------------

_W: dict = {}


def _init(cfg: dict, hp: dict, levels: dict) -> None:
    _W.update(cfg=cfg, hp=hp, levels=levels)


def evaluate_machine(task: RetentionTask) -> list[dict]:
    cfg, hp, levels = _W["cfg"], _W["hp"], _W["levels"]
    names = list(cfg["policies"])
    t0 = time.perf_counter()
    trace = simulate(cfg, task)
    sim_s = time.perf_counter() - t0
    cache: dict = {}
    b, size0 = daily_bytes(cfg, task, trace, hp, names, COUNTS, cache)
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
        need = sorted(set(LEVEL_KS) | {s[3] for s in sel if s[1] == nm and s[3] is not None})
        rows += evaluate_trace({**cfg, "budgets": need}, task, trace, hp, [nm], sim_s,
                               posterior_cache=cache)  # fmt: skip
    by = {(r["policy"], r["budget"], r["discovery_delay"]): r for r in rows}
    out = []
    for r in rows:  # matched count: the registered count budgets, unchanged rows
        if r["budget"] in LEVEL_KS:
            out.append({**r, "d81_arm": "count", "d81_level": f"count_K{r['budget']}",
                        "d81_kprime": r["budget"], "d81_infeasible": False})  # fmt: skip
    delays = [int(d) for d in cfg["discovery_delay"]]
    for name, nm, budget, k, mx, at_cap in sel:
        for d in delays:
            meta = {"d81_arm": "bytes", "d81_level": name, "d81_budget_bytes": budget,
                    "d81_day0_bytes": size0, "d81_kprime": k, "d81_max_bytes": mx,
                    "d81_days_at_cap": at_cap, "d81_infeasible": k is None,
                    "d81_censored": k == COUNTS[-1]}  # fmt: skip
            if k is None:
                out.append({"policy": nm, "discovery_delay": d, "split": task.split,
                            "rep": task.rep, "true_start": trace.start,
                            **{c: task.params.get(c) for c in
                            ("world", "benign_invalid_rate")}, **meta})  # fmt: skip
                continue
            r = by[(nm, k, d)]
            td = trace.start + d
            if r["retained_unique_bytes"] != b[(nm, k)][td]:  # same simulation as evaluate_trace
                raise AssertionError(f"{nm} K'={k} day {td}: byte replay differs from the rows")
            if r["retained_unique_bytes"] > budget:  # invariant (kill rule)
                raise AssertionError(f"{nm} at K'={k} exceeds its byte budget")
            out.append({**r, **meta})
    return out


def run(cfg: dict, pilot: int | None = None, log=print) -> pd.DataFrame:
    out = resolve_path(cfg["output_dir"])
    levels = json.loads((out / "levels.json").read_text())["levels"]
    hp = base_hp(cfg)
    tasks = build_tasks(cfg, "dev", log)
    name = "machines"
    if pilot:
        tasks, name = tasks[:pilot], "pilot"
    seed = int(cfg["seed"])
    res = run_tasks(evaluate_machine, tasks, workers=int(cfg.get("workers", 1)), init=_init,
                    init_args=(cfg, hp, levels), cache_dir=out / f"{name}_d81",
                    task_key=lambda t: task_cache_key(seed, t), log=log)  # fmt: skip
    df = pd.DataFrame([r for rows in res for r in rows])
    df["label"] = LABEL
    df.to_csv(out / f"d81_{name}_rows.csv.gz", index=False)
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
    elif cmd == "run":
        pilot = int(argv[3]) if len(argv) > 3 and argv[2] == "--pilot" else None
        run(cfg, pilot)
    else:
        raise SystemExit(f"unknown command {cmd!r}")


if __name__ == "__main__":
    main(sys.argv[1:])
