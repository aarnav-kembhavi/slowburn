"""Retention experiment (Workstream C / headline): clean recovery and work lost per policy.

One task = one simulated machine (token content mode). Evidence comes from the abstract
file-level detector (detection probability ``detect_prob`` for damaged files; clean files are
flagged when they fail validation, rate ``benign_invalid_rate``). Both act only through
auxiliary random streams, so every (detect_prob, benign_invalid_rate) cell sees the SAME churn
and attack for a given seed: comparisons across cells and policies are paired.

Per machine: simulate to the latest discovery day; compute every day's start posterior (evidence)
and the prior-only posterior; replay every policy online; at each discovery delay run the shared
selective restore and record metrics.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np
import pandas as pd

from slowburn.bench.parallel import run_tasks
from slowburn.bench.registry import check_split_allowed, machine_key
from slowburn.inference.changepoint import (
    SingleChangepoint,
    geometric_log_prior,
    hazard_from_window,
)
from slowburn.inference.daily import make_aggregator
from slowburn.inference.obsmodels import BetaBinomialExceedance, fit_pooled_null_prior
from slowburn.inference.pipeline import AbstractFileDetector
from slowburn.retention.amoeba import AmoebaStyle, Write, fit_weights
from slowburn.retention.base import (
    GFS,
    KeepLastN,
    Oracle,
    PosteriorDP,
    RetentionContext,
    ThresholdVault,
    TowerOfHanoi,
)
from slowburn.retention.dp import discovery_survival, retention_posterior
from slowburn.sim.damage import RandomDamageSource
from slowburn.sim.scenario import Scenario, ScenarioConfig
from slowburn.store.restore import (
    HOURS_PER_DAY,
    FileHistory,
    selective_restore,
    snapshots_scanned,
    verified_restore,
)
from slowburn.utils.config import resolve_path
from slowburn.utils.seed import child_rng

SNAPSHOT_POLICIES = ("keep_last_n", "gfs", "tower_of_hanoi", "threshold_vault", "prior_only",
                     "slowburn", "oracle")  # fmt: skip
# act only through auxiliary streams -> excluded from the machine seed key (paired machines)
PAIRED_KEYS = frozenset({"detect_prob", "benign_invalid_rate"})
SCENARIO_FIELDS = set(ScenarioConfig.__dataclass_fields__)


@dataclass(frozen=True)
class RetentionTask:
    split: str
    family: str  # "eval", "amoeba_train", "vault_calib"
    params: dict
    rep: int


def task_seed_key(seed: int, task: RetentionTask) -> tuple:
    setting = {k: v for k, v in task.params.items()
               if k in SCENARIO_FIELDS and k not in PAIRED_KEYS}  # fmt: skip
    return machine_key(seed, task.split, task.family, setting, task.rep)


def task_cache_key(seed: int, task: RetentionTask) -> tuple:
    return (*task_seed_key(seed, task),
            *sorted((k, v) for k, v in task.params.items() if k in PAIRED_KEYS))  # fmt: skip


# ---- simulation -------------------------------------------------------------------------


@dataclass
class MachineTrace:
    start: int | None
    n_days: int
    snapshots: list[frozenset]  # chunk tokens per day
    obs: list  # DailyObs per day (file-level)
    histories: dict[str, FileHistory]
    writes: list[list[Write]]  # per day
    chunk_size: int


def trace_days(cfg: dict, start: int | None) -> int:
    """Days to simulate: through the latest discovery day. Attack-free machines run as long as
    the latest attack start in the config (base value or sweep) plus the longest delay."""
    delays = [int(d) for d in cfg["discovery_delay"]]
    if start is None:
        starts = [cfg["scenario"].get("attack_start")]
        starts += list(cfg.get("sweep", {}).get("attack_start", []))
        start = max(int(x) for x in starts if x is not None)
    return int(start) + max(delays) + 1


def simulate(cfg: dict, task: RetentionTask) -> MachineTrace:
    seed = int(cfg["seed"])
    key = task_seed_key(seed, task)
    p = task.params
    scen_params = {k: v for k, v in p.items() if k in SCENARIO_FIELDS}
    start = scen_params.get("attack_start")
    n_days = trace_days(cfg, start)
    scen = Scenario(ScenarioConfig.from_dict({**scen_params, "days": n_days,
                                              "content": "tokens"}))  # fmt: skip
    det = AbstractFileDetector(float(p.get("detect_prob", 0.0)), child_rng(*key, "detector"))
    agg = make_aggregator("file_exceed", alpha=0.5)  # p-values are 0/1: any alpha in (0,1)
    snapshots, obs, writes = [], [], []
    versions: dict[str, tuple] = {}
    change_days: dict[str, list[int]] = {}
    flagged_days: dict[str, set[int]] = {}
    recent_changes: list[int] = []
    for day in scen.run(child_rng(*key), RandomDamageSource(child_rng(*key, "damage")),
                        child_rng(*key, "benign_invalid")):  # fmt: skip
        snapshots.append(frozenset(c for chunks in day.files.values() for c in chunks))
        scores = det.score_day(day)
        obs.append(agg(scores))
        flagged = {f for f, pv in scores.file_pvals.items() if pv == 0}
        for f in flagged:
            flagged_days.setdefault(f, set()).add(day.day)
        files_today = day.changed_files
        mean_recent = np.mean(recent_changes[-7:]) if recent_changes else len(files_today)
        day_writes = []
        for fid, chunks in day.files.items():
            v = tuple(chunks)
            if versions.get(fid) != v:
                old = versions.get(fid)
                if old is not None:
                    same = len(set(old) & set(v)) / max(len(v), 1)
                    day_writes.append(Write(
                        fid, day.day, same, float(fid in flagged),
                        len(files_today) / max(mean_recent, 1.0), change_days[fid][-1],
                        len(old) * scen.cfg.chunk_size, files_today.get(fid, 0.0) > 0))  # fmt: skip
                versions[fid] = v
                change_days.setdefault(fid, []).append(day.day)
        if day.day > 0:
            recent_changes.append(len(files_today))
        writes.append(day_writes)
    histories = {f: FileHistory(tuple(d), scen.damaged_on.get(f),
                                frozenset(flagged_days.get(f, ())))
                 for f, d in change_days.items()}  # fmt: skip
    return MachineTrace(start, n_days, snapshots, obs, histories, writes, scen.cfg.chunk_size)


# ---- policies ---------------------------------------------------------------------------


def make_policies(hp: dict, vault_threshold: float) -> dict:
    """Fresh policy objects (some keep state). ``slowburn_*`` entries are ablations."""
    gate, bb, P = float(hp.get("gate", 0.0)), float(hp.get("backbone", 0.0)), hp["penalty"]
    return {
        "keep_last_n": KeepLastN(),
        "gfs": GFS(),
        "tower_of_hanoi": TowerOfHanoi(),
        "threshold_vault": ThresholdVault(vault_threshold),
        "prior_only": PosteriorDP(P, use_evidence=False, gate=gate, backbone=bb),
        "slowburn": PosteriorDP(P, use_evidence=True, gate=gate, backbone=bb),
        "oracle": Oracle(),
        # ablations (Tier 2 F): no backbone; DP loss ignoring the restore gate; symmetric loss
        "slowburn_no_backbone": PosteriorDP(P, gate=gate, name="slowburn_no_backbone"),
        "slowburn_ungated_loss": PosteriorDP(
            P, gate=0.0, backbone=bb, name="slowburn_ungated_loss"
        ),  # fmt: skip
        "slowburn_symmetric": PosteriorDP(None, gate=gate, backbone=bb, name="slowburn_symmetric"),
    }


def _unique_bytes(trace: MachineTrace, days) -> int:
    union = frozenset().union(*(trace.snapshots[d] for d in days)) if days else frozenset()
    return len(union) * trace.chunk_size


def evaluate_machine_retention(cfg: dict, task: RetentionTask) -> list[dict]:
    """Simulate one machine and evaluate every policy at every budget and discovery delay."""
    t0 = time.perf_counter()
    trace = simulate(cfg, task)
    sim_s = time.perf_counter() - t0
    names = cfg.get("policies", ALL_POLICIES)
    return evaluate_trace(cfg, task, trace, cfg["hp"], names, sim_s)


ALL_POLICIES = (*SNAPSHOT_POLICIES, "amoeba_style")


def budgets_of(cfg: dict, task: RetentionTask, hp: dict) -> list[int]:
    if "budget" in task.params:
        return [int(task.params["budget"])]
    return [int(k) for k in (cfg["budgets"] if "budgets" in cfg else [hp["budget"]])]


def start_posteriors(trace: MachineTrace, hp: dict, warmup: int, null_prior, cache: dict):
    """Evidence and prior-only start posteriors after every day (cached per hazard / null)."""
    h = hazard_from_window(float(hp["p_attack_within_window"]), int(hp["prior_window_days"]))
    pooled = hp.get("null_pool", "pooled") == "pooled" and null_prior is not None
    key = (h, pooled)
    if key not in cache:
        n = trace.n_days
        obs_model = BetaBinomialExceedance(null_prior=tuple(null_prior) if pooled else None)
        model = SingleChangepoint(obs_model, h, warmup)
        cache[key] = (
            model.posterior_path(trace.obs, list(range(1, n + 1))),  # T = t + 1 days
            {T: np.exp(geometric_log_prior(T, h, warmup)) for T in range(1, n + 1)},
        )
    return cache[key]


def evaluate_trace(
    cfg: dict,
    task: RetentionTask,
    trace: MachineTrace,
    hp: dict,
    policy_names,
    sim_s: float = 0.0,
    posterior_cache: dict | None = None,
) -> list[dict]:
    """Evaluate the given policies on a simulated machine under hyperparameters ``hp``."""
    p = task.params
    warmup = int(cfg["warmup_days"])
    S = discovery_survival(
        hp["assumed_discovery"]["kind"], int(hp["assumed_discovery"]["max_days"])
    )
    delays = [int(d) for d in cfg["discovery_delay"]]
    start = trace.start
    n = trace.n_days
    rule = hp.get("restore_rule", "verified")
    gate, scan_eps = float(hp.get("gate", 0.0)), float(hp.get("scan_eps", 0.001))

    t1 = time.perf_counter()
    cache = posterior_cache if posterior_cache is not None else {}
    path, prior = start_posteriors(trace, hp, warmup, p.get("null_prior"), cache)
    infer_s = time.perf_counter() - t1

    stat = np.array([o.value for o in trace.obs])
    Ks = budgets_of(cfg, task, hp)
    snap_names = [nm for nm in policy_names if nm != "amoeba_style"]
    pols = {K: {nm: pol for nm, pol in make_policies(hp, float(p.get("vault_threshold", 0.0)))
                .items() if nm in snap_names} for K in Ks}  # fmt: skip
    held = {(K, nm): {} for K in Ks for nm in pols[K]}
    kept_at = {(K, nm): {} for K in Ks for nm in pols[K]}
    dp_s, dp_calls = 0.0, 0
    disc_days = {d: start + d for d in delays}
    for t in range(n):
        T = t + 1
        rpi = retention_posterior(path[T], t, S)
        ppi = retention_posterior(prior[T], t, S)
        for K in Ks:
            for nm, pol in pols[K].items():
                hk = held[(K, nm)]
                hk[t] = t
                ctx = RetentionContext(day=t, snapshot_days=dict(hk), budget=K,
                                       daily_stat=stat[: t + 1], start_posterior=path[T],
                                       retention_pi=rpi, prior_retention_pi=ppi,
                                       oracle_start=start)  # fmt: skip
                t2 = time.perf_counter()
                keep = pol.decide(ctx)
                if nm == "slowburn":
                    dp_s += time.perf_counter() - t2
                    dp_calls += 1
                held[(K, nm)] = {sid: hk[sid] for sid in keep}
                if t in disc_days.values():
                    kept_at[(K, nm)][t] = sorted(held[(K, nm)].values())

    amoeba_rec = {}
    if "amoeba_style" in policy_names and "amoeba_weights" in p:
        for K in Ks:
            amoeba = AmoebaStyle(np.asarray(p["amoeba_weights"], float))
            for t in range(n):
                last_k = list(range(max(0, t - K + 1), t + 1))
                budget = _unique_bytes(trace, last_k) - len(trace.snapshots[t]) * trace.chunk_size
                amoeba.step(trace.writes[t], max(budget, 0))
                if t in disc_days.values():
                    amoeba_rec[(K, t)] = amoeba.recover(trace.histories, t)

    base = {k: v for k, v in p.items() if k not in ("amoeba_weights", "null_prior", "budget")}
    hp_cols = {"hp_p_attack_within_window": hp["p_attack_within_window"],
               "hp_penalty": hp["penalty"], "hp_gate": gate,
               "hp_backbone": float(hp.get("backbone", 0.0)),
               "hp_assumed_discovery_max": hp["assumed_discovery"]["max_days"],
               "hp_null_pool": hp.get("null_pool", "pooled"), "hp_restore_rule": rule,
               "hp_restore_quantile": hp.get("restore_quantile")}  # fmt: skip
    rows = []
    for K in Ks:
        for d, td in disc_days.items():
            post = path[td + 1]
            klast = list(range(max(0, td - K + 1), td + 1))
            klast_bytes = _unique_bytes(trace, klast)
            common = {**base, **hp_cols, "split": task.split, "rep": task.rep,
                      "discovery_delay": d, "true_start": start, "budget": K,
                      "start_offset_month": start % 28, "start_offset_week": start % 7,
                      "n_files_damaged": sum(h_.damaged_day is not None and h_.damaged_day <= td
                                             for h_ in trace.histories.values()),
                      # best achievable (oracle) work lost: restore from day s - 1
                      "work_lost_ideal_hours": (td - (start - 1)) * HOURS_PER_DAY,
                      "benign_source": "synthetic", "damage_source": "abstract_token",
                      "evidence": f"abstract_q{p.get('detect_prob')}",
                      "p_started_at_discovery": float(1 - post[-1]),
                      "sim_s": sim_s, "infer_ms_per_day": 1000 * infer_s / n,
                      "dp_ms_per_decision": 1000 * dp_s / max(dp_calls, 1)}  # fmt: skip
            for nm in pols[K]:
                kept = kept_at[(K, nm)][td]
                if rule == "verified":
                    r = verified_restore(kept, post, td, trace.histories, start, gate, scan_eps)
                else:
                    r = selective_restore(kept, post, td, trace.histories, start,
                                          float(hp["restore_quantile"]))  # fmt: skip
                    r["snapshots_scanned"] = snapshots_scanned(kept, start, r["restore_point"])
                ub = _unique_bytes(trace, kept)
                rows.append({**common, "policy": nm, **r,
                             "snapshots_retained": len(kept), "retained_unique_bytes": ub,
                             "storage_vs_keep_last_n": ub / klast_bytes if klast_bytes else np.nan,
                             "clean_snapshot_retained": int(any(j < start for j in kept)),
                             "oldest_retained_age": td - min(kept)})  # fmt: skip
            if (K, td) in amoeba_rec:
                rec = amoeba_rec[(K, td)]
                total = rec["backup_bytes"] + len(trace.snapshots[td]) * trace.chunk_size
                rows.append({**common, "policy": "amoeba_style", **rec,
                             "snapshots_retained": None, "retained_unique_bytes": total,
                             "storage_vs_keep_last_n": total / klast_bytes if klast_bytes
                             else np.nan, "clean_snapshot_retained": None,
                             "snapshots_scanned": None, "oldest_retained_age": None})  # fmt: skip
    return rows


# ---- calibration steps (DEV-style, inside each run; never use evaluation machines) -------


def fit_amoeba_weights(cfg: dict, setting: dict, split: str, n_machines: int) -> np.ndarray:
    writes = []
    for r in range(n_machines):
        trace = simulate(cfg, RetentionTask(split, "amoeba_train", setting, r))
        writes += [w for day in trace.writes for w in day]
    return fit_weights(writes)


def attack_free_calibration(cfg: dict, setting: dict, split: str, n_machines: int,
                            fa: float = 0.05) -> tuple[float, tuple[float, float]]:  # fmt: skip
    """From attack-free calibration machines (separate DEV family):
    * the threshold vault's fixed line: the (1 - fa) quantile of the largest daily flagged-file
      fraction after warm-up;
    * the fleet-level Beta prior on the benign flag rate (D31), from each machine's flagged and
      changed file totals after warm-up."""
    warmup = int(cfg["warmup_days"])
    peaks, ks, ns = [], [], []
    for r in range(n_machines):
        clean = {**setting, "attack_start": None}
        trace = simulate(cfg, RetentionTask(split, "vault_calib", clean, r))
        after = trace.obs[warmup:]
        peaks.append(max([o.value for o in after], default=0.0))
        ks.append(sum(o.k for o in after))
        ns.append(sum(o.n for o in after))
    thr = float(np.quantile(peaks, 1 - fa, method="higher"))
    return thr, fit_pooled_null_prior(np.array(ks), np.array(ns))


def vault_threshold(cfg: dict, setting: dict, split: str, n_machines: int,
                    fa: float = 0.05) -> float:  # fmt: skip
    return attack_free_calibration(cfg, setting, split, n_machines, fa)[0]


# ---- driver -----------------------------------------------------------------------------

_W: dict = {}


def _init(cfg: dict) -> None:
    _W["cfg"] = cfg


def _run_task(task: RetentionTask) -> list[dict]:
    return evaluate_machine_retention(_W["cfg"], task)


def build_tasks(cfg: dict, split: str, log=print) -> list[RetentionTask]:
    from slowburn.bench.runner import expand_sweep

    grid = expand_sweep(cfg["scenario"], cfg.get("sweep", {}))
    calib_split = "dev"  # calibration steps always use dev machines (separate families)
    calib = {}
    for setting in grid:
        ev_key = (setting.get("detect_prob"), setting.get("benign_invalid_rate"))
        if ev_key not in calib:
            w = fit_amoeba_weights(
                cfg, setting, calib_split, int(cfg.get("amoeba_train_machines", 8))
            )
            n_cal = int(cfg.get("vault_calib_machines", 40))
            thr, prior = attack_free_calibration(cfg, setting, calib_split, n_cal)
            calib[ev_key] = (w, thr, prior)
    log(f"  calibrated AMOEBA weights, vault thresholds and fleet null priors for {len(calib)} "
        "evidence settings")  # fmt: skip
    tasks = []
    for setting in grid:
        w, thr, prior = calib[(setting.get("detect_prob"), setting.get("benign_invalid_rate"))]
        params = {**setting, "amoeba_weights": tuple(map(float, w)), "vault_threshold": thr,
                  "null_prior": tuple(map(float, prior))}  # fmt: skip
        tasks += [RetentionTask(split, "eval", params, r) for r in range(int(cfg["reps"]))]
    return tasks


GRID_CELL = ["budget", "discovery_delay", "attack_start", "detect_prob", "benign_invalid_rate"]
REPORT_RULE = (
    "report every cell; per policy the average over cells and the worst cell of mean "
    "clean recovery and mean whole-system work lost, oracle-ideal work lost alongside"
)


def scenario_grid_of(cfg: dict) -> dict:
    """The scenario grid a run evaluates (compared with frozen.yaml's scenario_grid on test)."""
    sw = cfg.get("sweep", {})
    return {
        "budgets": [int(k) for k in cfg["budgets"]],
        "discovery_delay": [int(d) for d in cfg["discovery_delay"]],
        "attack_start": [int(x) for x in sw.get("attack_start", [cfg["scenario"]["attack_start"]])],
        "detect_prob": [float(x) for x in sw.get("detect_prob", [])],
        "benign_invalid_rate": [float(x) for x in sw.get("benign_invalid_rate", [])],
        "scenario": {k: v for k, v in cfg["scenario"].items() if k != "attack_start"},
        "warmup_days": int(cfg["warmup_days"]),
        "test_reps": int(cfg["reps"]),
        "report": REPORT_RULE,
    }


def preregister_grid(cfg: dict, path: str = "configs/frozen.yaml") -> dict:
    from slowburn.bench.registry import update_frozen

    grid = scenario_grid_of(cfg)
    update_frozen({"scenario_grid": grid}, path=path,
                  note=f"pre-registered scenario grid from {cfg.get('_config_path')}")  # fmt: skip
    return grid


def cell_table(df: pd.DataFrame) -> pd.DataFrame:
    """Mean clean recovery and work lost per grid cell and policy, oracle-ideal alongside."""
    g = df.groupby([*GRID_CELL, "policy"])
    return g.agg(clean_recovery=("clean_recovery", "mean"),
                 work_lost_whole_system_hours=("work_lost_whole_system_hours", "mean"),
                 work_lost_selective_file_hours=("work_lost_selective_file_hours", "mean"),
                 work_lost_ideal_hours=("work_lost_ideal_hours", "mean"),
                 snapshots_scanned=("snapshots_scanned", "mean"),
                 n=("clean_recovery", "size")).reset_index()  # fmt: skip


def grid_summary(cells: pd.DataFrame) -> pd.DataFrame:
    """Per policy: average over cells and worst cell (lowest recovery / highest work lost)."""
    out = cells.groupby("policy").agg(
        cells=("clean_recovery", "size"),
        recovery_avg=("clean_recovery", "mean"), recovery_worst=("clean_recovery", "min"),
        work_lost_avg=("work_lost_whole_system_hours", "mean"),
        work_lost_worst=("work_lost_whole_system_hours", "max"),
        ideal_work_lost_avg=("work_lost_ideal_hours", "mean"))  # fmt: skip
    return out.sort_values("recovery_avg", ascending=False)


def run_retention_experiment(cfg: dict, log=print) -> pd.DataFrame:
    split = cfg.get("split", "dev")
    run_params = dict(cfg["hp"])
    if "budgets" in cfg:
        run_params["scenario_grid"] = scenario_grid_of(cfg)
    frozen = check_split_allowed(split, run_params, cfg.get("frozen_path", "configs/frozen.yaml"))
    if split == "test":
        cfg = {**cfg, "hp": {**cfg["hp"], **{k: v for k, v in frozen.items() if k in cfg["hp"]}}}
    out = resolve_path(cfg["output_dir"])
    out.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()
    tasks = build_tasks(cfg, split, log)
    seed = int(cfg["seed"])
    results = run_tasks(_run_task, tasks, workers=int(cfg.get("workers", 1)), init=_init,
                        init_args=(cfg,), cache_dir=out / "machines",
                        task_key=lambda t: task_cache_key(seed, t), log=log)  # fmt: skip
    df = pd.DataFrame([row for rows in results for row in rows])
    for col in ("start_gap_days", "restore_point", "estimated_start", "snapshots_scanned",
                "snapshots_retained", "clean_snapshot_retained", "oldest_retained_age",
                "files_restored", "restore_point_clean"):  # fmt: skip
        if col in df:
            df[col] = pd.to_numeric(df[col])
    df.to_csv(out / "retention_results.csv", index=False)
    if "budgets" in cfg:
        cells = cell_table(df)
        cells.to_csv(out / "cells.csv", index=False)
        grid_summary(cells).to_csv(out / "grid_summary.csv")
    log(f"  {len(tasks)} machines, {len(df)} rows, {time.perf_counter() - t0:.1f}s")
    return df


# ---- DEV tuning (rule D27) ---------------------------------------------------------------


def _init_tune(cfg: dict, combos: list[dict], policies: tuple) -> None:
    _W["cfg"], _W["combos"], _W["policies"] = cfg, combos, policies


def _run_tune_task(task: RetentionTask) -> list[dict]:
    cfg, combos, policies = _W["cfg"], _W["combos"], _W["policies"]
    trace = simulate(cfg, task)
    cache: dict = {}
    rows = []
    for hp in combos:
        rows += evaluate_trace(cfg, task, trace, hp, policies, posterior_cache=cache)
    return rows


def _stage(cfg, tasks, combos, policies, out, name, log):
    seed = int(cfg["seed"])
    res = run_tasks(_run_tune_task, tasks, workers=int(cfg.get("workers", 1)), init=_init_tune,
                    init_args=(cfg, combos, policies), cache_dir=out / f"machines_{name}",
                    task_key=lambda t: task_cache_key(seed, t), log=log)  # fmt: skip
    df = pd.DataFrame([r for rows in res for r in rows])
    df.to_csv(out / f"tuning_{name}.csv", index=False)
    return df


def run_retention_tuning(cfg: dict, log=print) -> dict:
    """Pre-registered two-stage DEV tuning (D30); records the choices in configs/frozen.yaml."""
    from slowburn.bench.registry import update_frozen
    from slowburn.bench.tune import SHARED_STAGE_POLICIES, retention_stage1, retention_stage2

    if cfg.get("split", "dev") != "dev":
        raise ValueError("retention tuning must run on the dev split")
    out = resolve_path(cfg["output_dir"])
    out.mkdir(parents=True, exist_ok=True)
    tasks = build_tasks(cfg, "dev", log)
    base, grid = dict(cfg["hp"]), cfg["tuning"]
    combos1 = [{**base, "p_attack_within_window": p, "gate": g}
               for p in grid["stage1"]["p_attack_within_window"]
               for g in grid["stage1"]["gate"]]  # fmt: skip
    df1 = _stage(cfg, tasks, combos1, SHARED_STAGE_POLICIES, out, "stage1", log)
    board1, (p_best, g_best) = retention_stage1(df1)
    board1.to_csv(out / "stage1_scoreboard.csv")
    combos2 = [{**base, "p_attack_within_window": p_best, "gate": g_best, "penalty": P,
                "assumed_discovery": {**base["assumed_discovery"], "max_days": m},
                "backbone": bb}
               for P in grid["stage2"]["penalty"]
               for m in grid["stage2"]["assumed_discovery_max_days"]
               for bb in grid["stage2"]["backbone"]]  # fmt: skip
    df2 = _stage(cfg, tasks, combos2, ("slowburn",), out, "stage2", log)
    board2, (P_best, m_best, bb_best) = retention_stage2(df2)
    board2.to_csv(out / "stage2_scoreboard.csv")
    chosen = {
        "p_attack_within_window": float(p_best),
        "gate": float(g_best),
        "penalty": float(P_best),
        "assumed_discovery": {**base["assumed_discovery"], "max_days": int(m_best)},
        "backbone": float(bb_best),
        "prior_window_days": int(base["prior_window_days"]),
        "null_pool": base.get("null_pool", "pooled"),
        "restore_rule": base.get("restore_rule", "verified"),
        "scan_eps": float(base.get("scan_eps", 0.001)),
    }
    update_frozen(chosen, note=f"rule D30 on {cfg.get('_config_path')}",
                  path=cfg.get("frozen_path", "configs/frozen.yaml"),
                  remove=("budget",))  # fmt: skip
    return {"stage1": board1, "stage2": board2, "chosen": chosen}
