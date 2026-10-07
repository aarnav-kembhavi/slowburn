"""M2 experiment: how well is the attack start day recovered from weak daily evidence?

Each simulated machine is one task, run in a pool of worker processes (``workers``, capped at
6). A worker simulates the machine to its last discovery day, scores every day once per
detector, and returns only a per-machine summary:

* one metrics row per (detector, discovery delay, statistic, start model, prior), and
* per-day trajectories of P(attack started), from which alarm thresholds and detection delays
  are derived afterwards.

Machines come from a named split (``dev`` or ``test``) with disjoint seed streams; alarm
thresholds for target false-alarm rates are only ever set on DEV attack-free machines.
"""

from __future__ import annotations

import hashlib
import os
import pickle
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from concurrent.futures.process import BrokenProcessPool
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from slowburn.bench.runner import SCENARIO_KEYS, expand_sweep, make_detector
from slowburn.inference.changepoint import hazard_from_window, make_start_model
from slowburn.inference.daily import make_aggregator
from slowburn.inference.pipeline import score_day, start_map
from slowburn.sim.damage import RandomDamageSource
from slowburn.sim.scenario import Scenario, ScenarioConfig
from slowburn.utils.config import resolve_path
from slowburn.utils.seed import child_rng
from slowburn.utils.sysinfo import peak_rss_mb

MAX_WORKERS = 6
NUMERIC = ["damage_fraction", "true_start", "map_start", "map_error_days", "missed",
           "map_signed_error_days", "expected_abs_error_days", "false_alarm_p05",
           "false_alarm_p09", "mass_within_0", "mass_within_1", "mass_within_3"]  # fmt: skip


def load_timing(path) -> dict:
    with resolve_path(path).open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def prior_grid(timing: dict) -> list[tuple[float, float]]:
    """[(p_attack_within_window, daily hazard)] from the timing config."""
    sp = timing["start_prior"]
    return [(float(p), hazard_from_window(float(p), int(sp["window_days"])))
            for p in sp["p_attack_within_window"]]  # fmt: skip


def start_metrics(post: np.ndarray, prior_p_started: float, true_start: int | None) -> dict:
    T = len(post) - 1
    m = start_map(post)
    row = {
        "p_started": float(1.0 - post[-1]),
        "prior_p_started": prior_p_started,
        "map_start": m,
        "false_alarm_p05": None,
        "false_alarm_p09": None,
    }
    if true_start is None:
        row["false_alarm_p05"] = int(row["p_started"] > 0.5)
        row["false_alarm_p09"] = int(row["p_started"] > 0.9)
        return row
    days = np.arange(T)
    started = post[:T]
    for w in (0, 1, 3):
        lo, hi = max(0, true_start - w), min(T, true_start + w + 1)
        row[f"mass_within_{w}"] = float(started[lo:hi].sum())
    row["map_error_days"] = None if m is None else abs(m - true_start)
    row["missed"] = int(m is None)
    mass = started.sum()
    row["expected_abs_error_days"] = (
        float((started * np.abs(days - true_start)).sum() / mass) if mass > 0 else None
    )
    row["map_signed_error_days"] = None if m is None else m - true_start
    return row


@dataclass(frozen=True)
class MachineTask:
    split: str
    params: dict
    attack: bool
    rep: int


def machine_key(seed: int, task: MachineTask) -> tuple:
    """Seed stream of one machine. The split name is part of the key, so dev and test machines
    never share randomness."""
    scen = {k: v for k, v in task.params.items() if k in SCENARIO_KEYS}
    return (seed, "machine", task.split, "attack" if task.attack else "clean", task.rep,
            *(str(v) for v in sorted(scen.items())))  # fmt: skip


def targets_label(params: dict) -> str:
    t = params.get("attack_target_types")
    if t is None or t == "all":
        return "all"
    return "high_entropy" if set(t) >= {"zip", "png"} and "txt" not in t else "+".join(t)


_WORKER: dict = {}


def _init_worker(cfg: dict) -> None:
    # One thread per worker: LightGBM/OpenMP otherwise starts a full-size thread pool in every
    # process, oversubscribing CPUs and multiplying memory (observed ~1.35 GB per worker).
    os.environ["OMP_NUM_THREADS"] = "1"
    _WORKER["cfg"] = cfg
    _WORKER["detectors"] = {
        name: make_detector({"kind": "trained", "path": path})
        for name, path in cfg["detectors"].items()
    }
    for det in _WORKER["detectors"].values():
        model = getattr(getattr(det, "classifier", None), "model", None)
        if model is not None and hasattr(model, "set_params"):
            model.set_params(n_jobs=1)
    _WORKER["priors"] = prior_grid(load_timing(cfg["timing_config"]))


def evaluate_machine(task: MachineTask) -> dict:
    """Simulate one machine, score it with every detector, return rows and trajectories."""
    cfg, detectors, priors = _WORKER["cfg"], _WORKER["detectors"], _WORKER["priors"]
    t0 = time.perf_counter()
    seed = int(cfg["seed"])
    warmup, alpha = int(cfg["warmup_days"]), float(cfg["alpha"])
    delays = [int(d) for d in cfg["discovery_delay"]]
    start = int(cfg["scenario"]["attack_start"])
    total_days = start + max(delays) + 1

    scen_params = {k: v for k, v in task.params.items() if k in SCENARIO_KEYS}
    if not task.attack:
        scen_params["attack_start"] = None
    key = machine_key(seed, task)
    scen = Scenario(ScenarioConfig.from_dict({**scen_params, "days": total_days}))
    source = RandomDamageSource(child_rng(*key, "damage"))
    scores = {name: [] for name in detectors}
    for day in scen.run(child_rng(*key), source):  # one simulation, every detector
        for name, det in detectors.items():
            scores[name].append(score_day(det, day))
    score_s = time.perf_counter() - t0

    true_start = start if task.attack else None
    disc_T = {d: start + d + 1 for d in delays}  # days 0..discovery day inclusive
    traj_T = list(range(warmup + 1, total_days + 1))
    all_T = sorted(set(traj_T) | set(disc_T.values()))
    rows, traj = [], {}
    for det_name, det_scores in scores.items():
        for stat, spec in cfg["statistics"].items():
            params = {"alpha": alpha} if spec["aggregator"] == "exceed" else {}
            agg = make_aggregator(spec["aggregator"], **params)
            obs = [agg(s) for s in det_scores]
            for kind in cfg["inference_models"]:
                for p_win, h in priors:
                    model = make_start_model(kind, stat, spec["model"], h, warmup)
                    path = model.posterior_path(obs, all_T)
                    traj[(det_name, stat, kind, p_win)] = np.array(
                        [1 - path[T][-1] for T in traj_T], dtype=np.float32
                    )
                    for d, T in disc_T.items():
                        lp = model.log_prior(T) if hasattr(model, "log_prior") else None
                        prior_p = float(1 - np.exp(lp[-1])) if lp is not None else float("nan")
                        row = {
                            "split": task.split, "rep": task.rep, "attack": int(task.attack),
                            "damage_fraction": task.params.get("damage_fraction"),
                            "attack_target_types": targets_label(task.params),
                            "discovery_delay": d, "true_start": true_start,
                            "detector": det_name, "statistic": stat, "model": kind,
                            "p_attack_within_window": p_win, "hazard": h,
                            "n_files_damaged_total": len(scen.damaged_on),
                            "benign_source": "synthetic",
                            "damage_source": source.name if task.attack else "none",
                        }  # fmt: skip
                        row.update(start_metrics(path[T], prior_p, true_start))
                        rows.append(row)
    return {"task": task, "rows": rows, "traj": traj, "traj_days": traj_T,
            "score_s": score_s, "seconds": time.perf_counter() - t0,
            "peak_rss_mb": peak_rss_mb()}  # fmt: skip


def make_tasks(cfg: dict, split: str) -> list[MachineTask]:
    tasks = [MachineTask(split, p, True, r)
             for p in expand_sweep(cfg["scenario"], cfg.get("sweep", {}))
             for r in range(int(cfg["reps"]))]  # fmt: skip
    tasks += [MachineTask(split, dict(cfg["scenario"]), False, r)
              for r in range(int(cfg.get("clean_reps", 0)))]  # fmt: skip
    return tasks


def task_id(seed: int, task: MachineTask) -> str:
    return hashlib.blake2b(repr(machine_key(seed, task)).encode(), digest_size=10).hexdigest()


def run_machines(cfg: dict, tasks: list[MachineTask], log=print, cache_dir=None,
                 max_pool_restarts: int = 3) -> list[dict]:  # fmt: skip
    """Run every task, persisting each machine's summary to ``cache_dir`` as it finishes.

    Finished machines are skipped on re-run (resume). If a worker dies (the pool breaks), a new
    pool is started for the remaining machines, up to ``max_pool_restarts`` times.
    """
    seed = int(cfg["seed"])
    workers = max(1, min(int(cfg.get("workers", 1)), MAX_WORKERS, os.cpu_count() or 1))
    cache = Path(cache_dir) if cache_dir is not None else None
    if cache is not None:
        cache.mkdir(parents=True, exist_ok=True)

    def path_of(t):
        return cache / f"{task_id(seed, t)}.pkl" if cache is not None else None

    done: dict[int, dict] = {}
    for i, t in enumerate(tasks):
        p = path_of(t)
        if p is not None and p.exists():
            with p.open("rb") as fh:
                done[i] = pickle.load(fh)
    if done:
        log(f"  resuming: {len(done)}/{len(tasks)} machines already done")

    def keep(i, res):
        done[i] = res
        p = path_of(tasks[i])
        if p is not None:
            tmp = p.with_suffix(".tmp")
            with tmp.open("wb") as fh:
                pickle.dump(res, fh)
            tmp.replace(p)
        if len(done) % 20 == 0 or len(done) == len(tasks):
            log(f"  machines {len(done)}/{len(tasks)} done")

    if workers == 1:
        _init_worker(cfg)
        for i, t in enumerate(tasks):
            if i not in done:
                keep(i, evaluate_machine(t))
    else:
        for attempt in range(max_pool_restarts + 1):
            pending = [i for i in range(len(tasks)) if i not in done]
            if not pending:
                break
            try:
                with ProcessPoolExecutor(workers, initializer=_init_worker,
                                         initargs=(cfg,)) as ex:  # fmt: skip
                    futures = {ex.submit(evaluate_machine, tasks[i]): i for i in pending}
                    for fut in as_completed(futures):
                        keep(futures[fut], fut.result())
            except BrokenProcessPool:
                log(f"  worker died (pool attempt {attempt + 1}); "
                    f"{len(tasks) - len(done)} machines left")  # fmt: skip
        missing = len(tasks) - len(done)
        if missing:
            raise RuntimeError(f"{missing} machines could not be evaluated after "
                               f"{max_pool_restarts} pool restarts")  # fmt: skip
    return [done[i] for i in range(len(tasks))]


def alarm_thresholds(results: list[dict], fa_targets: list[float]) -> pd.DataFrame:
    """Per (detector, statistic, model, prior): threshold on P(started) such that at most a
    fraction ``a`` of the given attack-free machines ever exceed it in the monitored window.
    Must only be called with DEV machines."""
    clean = [r for r in results if not r["task"].attack]
    if not clean:
        return pd.DataFrame()
    if any(r["task"].split != "dev" for r in clean):
        raise ValueError("alarm thresholds may only be set on dev machines")
    rows = []
    for combo in clean[0]["traj"]:
        peaks = np.array([float(r["traj"][combo].max()) for r in clean])
        for a in fa_targets:
            thr = float(np.quantile(peaks, 1 - a, method="higher"))
            rows.append({"detector": combo[0], "statistic": combo[1], "model": combo[2],
                         "p_attack_within_window": combo[3], "fa_target": a, "threshold": thr,
                         "empirical_fa": float(np.mean(peaks > thr)),
                         "n_clean_machines": len(peaks)})  # fmt: skip
    return pd.DataFrame(rows)


def detection_table(results: list[dict], thresholds: pd.DataFrame, start: int) -> pd.DataFrame:
    """Per attack machine and threshold: alarm before the start (false alarm), and days from
    the start to the first alarm (NaN if none within the horizon)."""
    rows = []
    for r in results:
        if not r["task"].attack:
            continue
        days = np.array(r["traj_days"]) - 1  # entry for the first T days ends on day T-1
        for th in thresholds.itertuples(index=False):
            p = r["traj"][(th.detector, th.statistic, th.model, th.p_attack_within_window)]
            alarm_days = days[(days >= start) & (p > th.threshold)]
            rows.append({"damage_fraction": r["task"].params.get("damage_fraction"),
                         "attack_target_types": targets_label(r["task"].params),
                         "rep": r["task"].rep, "detector": th.detector,
                         "statistic": th.statistic, "model": th.model,
                         "p_attack_within_window": th.p_attack_within_window,
                         "fa_target": th.fa_target,
                         "pre_start_alarm": int((p[days < start] > th.threshold).any()),
                         "detection_delay_days": (float(alarm_days.min() - start)
                                                  if len(alarm_days) else np.nan)})  # fmt: skip
    return pd.DataFrame(rows)


def example_traces(results: list[dict]) -> pd.DataFrame:
    rows = []
    for r in results:
        if not r["task"].attack or r["task"].rep != 0:
            continue
        for (det, stat, kind, p_win), traj in r["traj"].items():
            for T, p in zip(r["traj_days"], traj, strict=True):
                rows.append({"damage_fraction": r["task"].params.get("damage_fraction"),
                             "attack_target_types": targets_label(r["task"].params),
                             "detector": det, "statistic": stat, "model": kind,
                             "p_attack_within_window": p_win, "day": T - 1,
                             "p_started": float(p)})  # fmt: skip
    return pd.DataFrame(rows)


def run_inference_experiment(cfg: dict, log=print) -> dict:
    split = cfg.get("split", "dev")
    if split not in ("dev", "test"):
        raise ValueError("split must be 'dev' or 'test'")
    start = int(cfg["scenario"]["attack_start"])
    if start <= int(cfg["warmup_days"]):
        raise ValueError("attack_start must be after the warm-up window")
    headline = int(cfg.get("headline_delay", 14))
    if headline not in [int(d) for d in cfg["discovery_delay"]]:
        raise ValueError("headline_delay must be one of discovery_delay")
    out = resolve_path(cfg["output_dir"])
    out.mkdir(parents=True, exist_ok=True)

    t0 = time.perf_counter()
    results = run_machines(cfg, make_tasks(cfg, split), log, cache_dir=out / "machines")
    df = pd.DataFrame([row for r in results for row in r["rows"]])
    for col in NUMERIC:
        if col in df:
            df[col] = pd.to_numeric(df[col])  # None -> NaN; object columns break groupby aggs
    df.to_csv(out / "inference_results.csv", index=False)

    thresholds = (alarm_thresholds(results, list(cfg.get("fa_targets", [0.01, 0.05, 0.1])))
                  if split == "dev" else pd.DataFrame())  # fmt: skip
    thresholds.to_csv(out / "alarm_thresholds.csv", index=False)
    detect = detection_table(results, thresholds, start) if len(thresholds) else pd.DataFrame()
    detect.to_csv(out / "detection.csv", index=False)
    traces = example_traces(results)
    traces.to_csv(out / "example_traces.csv", index=False)
    info = {"split": split, "n_machines": len(results),
            "workers": min(int(cfg.get("workers", 1)), MAX_WORKERS),
            "wall_s": round(time.perf_counter() - t0, 1),
            "mean_machine_s": round(float(np.mean([r["seconds"] for r in results])), 2),
            "mean_score_s": round(float(np.mean([r["score_s"] for r in results])), 2),
            "max_worker_peak_rss_mb": round(float(np.nanmax([r["peak_rss_mb"]
                                                             for r in results])), 1)}  # fmt: skip
    log(f"  {info}")
    return {"results": df, "thresholds": thresholds, "detection": detect, "traces": traces,
            "headline_delay": headline, "info": info}  # fmt: skip


def summarise(df: pd.DataFrame, p_win: float, delay: int = 14,
              fraction: float = 0.1) -> dict[str, pd.DataFrame]:  # fmt: skip
    """Headline tables for one prior setting and the headline discovery delay."""
    a = df[(df.attack == 1) & np.isclose(df.p_attack_within_window, p_win)]
    c = df[(df.attack == 0) & np.isclose(df.p_attack_within_window, p_win)]
    idx = ["detector", "attack_target_types", "statistic", "model"]
    by_frac = a[a.discovery_delay == delay].pivot_table(
        index=idx, columns="damage_fraction", values="mass_within_3", aggfunc="mean"
    )
    by_frac = by_frac[sorted(by_frac.columns, reverse=True)]
    by_delay = a[np.isclose(a.damage_fraction, fraction)].pivot_table(
        index=idx, columns="discovery_delay", values="mass_within_3", aggfunc="mean"
    )
    err = (
        a[a.discovery_delay == delay]
        .groupby(idx)
        .agg(
            median_map_error=("map_error_days", "median"),
            median_signed_error=("map_signed_error_days", "median"),
            late_gt3_rate=("map_signed_error_days", lambda v: float((v > 3).mean())),
            early_gt3_rate=("map_signed_error_days", lambda v: float((v < -3).mean())),
            missed_rate=("missed", "mean"),
            mean_p_started=("p_started", "mean"),
            mean_expected_abs_error=("expected_abs_error_days", "mean"),
            n=("rep", "count"),
        )
    )
    clean = c.groupby(["detector", "statistic", "model", "discovery_delay"]).agg(
        prior_p_started=("prior_p_started", "mean"),
        mean_p_started=("p_started", "mean"),
        false_alarm_p05=("false_alarm_p05", "mean"),
        false_alarm_p09=("false_alarm_p09", "mean"),
        n=("rep", "count"),
    )  # fmt: skip
    return {"mass3_by_fraction": by_frac, "mass3_by_delay": by_delay, "errors": err,
            "clean": clean}  # fmt: skip
