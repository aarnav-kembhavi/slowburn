"""M2 experiment: how well is the attack start day recovered from weak daily evidence?

For every scenario (damage fraction x attacker target types x rep) one machine is simulated to
the latest discovery day; the trained detector scores each day's changed chunks once. Every
(daily statistic, start model, hazard, discovery delay) combination is then evaluated on the
prefix of days up to discovery. Attack-free machines measure false alarms.
"""

from __future__ import annotations

import time

import numpy as np
import pandas as pd
import yaml

from slowburn.bench.runner import SCENARIO_KEYS, expand_sweep, make_detector
from slowburn.inference.changepoint import geometric_log_prior, make_start_model
from slowburn.inference.daily import make_aggregator
from slowburn.inference.pipeline import score_day, start_map
from slowburn.sim.damage import RandomDamageSource
from slowburn.sim.scenario import Scenario, ScenarioConfig
from slowburn.utils.config import resolve_path
from slowburn.utils.seed import child_rng


def load_timing(path) -> dict:
    with resolve_path(path).open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


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
    # how much earlier/later than truth, signed (negative = estimate too early)
    row["map_signed_error_days"] = None if m is None else m - true_start
    return row


def _simulate_scores(params: dict, attack: bool, rep: int, seed: int, detector, days: int):
    scen_params = {k: v for k, v in params.items() if k in SCENARIO_KEYS}
    if not attack:
        scen_params["attack_start"] = None
    scfg = ScenarioConfig.from_dict({**scen_params, "days": days})
    key = (seed, "inference", "attack" if attack else "clean", rep,
           *(str(v) for v in sorted(scen_params.items())))  # fmt: skip
    scen = Scenario(scfg)
    source = RandomDamageSource(child_rng(*key, "damage"))
    scores, t_score = [], 0.0
    for day in scen.run(child_rng(*key), source):
        t = time.perf_counter()
        scores.append(score_day(detector, day))
        t_score += time.perf_counter() - t
    n_damaged = len(scen.damaged_on)
    return scores, t_score / max(1, len(scores)), n_damaged, source.name


def run_inference_experiment(cfg: dict) -> dict:
    seed = int(cfg["seed"])
    detector = make_detector({"kind": "trained", "path": cfg["detector_path"]})
    timing = load_timing(cfg["timing_config"])
    hazards = [float(timing["start_prior"]["hazard"])] + [
        float(h) for h in cfg.get("extra_hazards", [])
    ]
    warmup, alpha = int(cfg["warmup_days"]), float(cfg["alpha"])
    delays = [int(d) for d in cfg["discovery_delay"]]
    headline = int(cfg.get("headline_delay", 14))
    if headline not in delays:
        raise ValueError(f"headline_delay {headline} must be one of discovery_delay {delays}")
    start = int(cfg["scenario"]["attack_start"])
    total_days = start + max(delays) + 1
    if start < warmup:
        raise ValueError("attack_start must be after the warm-up window")

    aggs = {}
    for stat, spec in cfg["statistics"].items():
        params = {"alpha": alpha} if spec["aggregator"] == "exceed" else {}
        aggs[stat] = (make_aggregator(spec["aggregator"], **params), spec["model"])

    runs = [(p, True, r) for p in expand_sweep(cfg["scenario"], cfg.get("sweep", {}))
            for r in range(int(cfg["reps"]))]  # fmt: skip
    clean_params = dict(cfg["scenario"])
    runs += [(clean_params, False, r) for r in range(int(cfg.get("clean_reps", 0)))]

    out = resolve_path(cfg["output_dir"])
    out.mkdir(parents=True, exist_ok=True)
    partial = out / "inference_results.partial.csv"
    rows, traces = [], []
    for i, (params, attack, rep) in enumerate(runs):
        t0 = time.perf_counter()
        scores, score_s, n_damaged, dsource = _simulate_scores(
            params, attack, rep, seed, detector, total_days
        )
        obs = {stat: [agg(s) for s in scores] for stat, (agg, _) in aggs.items()}
        for delay in delays:
            T = start + delay + 1  # days 0..discovery day inclusive
            for stat, (_, obs_model) in aggs.items():
                for kind in cfg["inference_models"]:
                    for h in hazards:
                        model = make_start_model(kind, stat, obs_model, h, warmup)
                        t = time.perf_counter()
                        post = model.posterior(obs[stat][:T])
                        infer_ms = 1000 * (time.perf_counter() - t)
                        prior_p = _prior_p_started(model, T, h, warmup)
                        row = {
                            "damage_fraction": params.get("damage_fraction"),
                            "attack_target_types": _targets_label(params),
                            "attack": int(attack), "rep": rep, "discovery_delay": delay,
                            "true_start": start if attack else None,
                            "statistic": stat, "model": kind, "hazard": h,
                            "n_files_damaged_total": n_damaged,
                            "benign_source": "synthetic",
                            "damage_source": dsource if attack else "none",
                            "detector": detector.name,
                            "inference_ms": infer_ms, "score_ms_per_day": 1000 * score_s,
                        }  # fmt: skip
                        row.update(start_metrics(post, prior_p, start if attack else None))
                        rows.append(row)
                        if attack and rep == 0 and h == hazards[0] and delay == headline:
                            traces.append(_trace(params, stat, kind, obs[stat][:T], post))
        print(f"  run {i + 1}/{len(runs)} ({'attack' if attack else 'clean'}, "
              f"f={params.get('damage_fraction')}, targets={_targets_label(params)}, rep={rep})"
              f" {time.perf_counter() - t0:.1f}s", flush=True)  # fmt: skip
        # keep progress if the run is interrupted (e.g. the OS reclaims memory)
        pd.DataFrame(rows).to_csv(partial, index=False)

    df = pd.DataFrame(rows)
    numeric = ["damage_fraction", "true_start", "map_start", "map_error_days", "missed",
               "map_signed_error_days", "expected_abs_error_days", "false_alarm_p05",
               "false_alarm_p09", "mass_within_0", "mass_within_1", "mass_within_3"]  # fmt: skip
    for col in numeric:
        if col in df:
            df[col] = pd.to_numeric(df[col])  # None -> NaN; object columns break groupby aggs
    df.to_csv(out / "inference_results.csv", index=False)
    partial.unlink(missing_ok=True)
    trace = pd.concat(traces, ignore_index=True) if traces else pd.DataFrame()
    trace.to_csv(out / "example_traces.csv", index=False)
    return {"results": df, "traces": trace, "hazards": hazards, "headline_delay": headline}


def _prior_p_started(model, T: int, hazard: float, warmup: int) -> float:
    """Prior P(attack started by day T) under this model's own start prior.

    BOCPD's implied prior on the most recent changepoint is the same constant-hazard geometric.
    """
    lp = (
        model.log_prior(T)
        if hasattr(model, "log_prior")
        else geometric_log_prior(T, hazard, warmup)
    )
    return float(1.0 - np.exp(lp[-1]))


def _targets_label(params: dict) -> str:
    t = params.get("attack_target_types")
    if t is None or t == "all":
        return "all"
    return "high_entropy" if set(t) >= {"zip", "png"} and "txt" not in t else "+".join(t)


def _trace(params, stat, kind, obs, post) -> pd.DataFrame:
    T = len(obs)
    return pd.DataFrame({
        "damage_fraction": params.get("damage_fraction"),
        "attack_target_types": _targets_label(params),
        "statistic": stat, "model": kind, "day": np.arange(T),
        "value": [o.value for o in obs], "k": [o.k for o in obs], "n": [o.n for o in obs],
        "posterior": post[:T], "p_not_started": post[T],
    })  # fmt: skip


def summarise(df: pd.DataFrame, hazard: float, delay: int = 14,
              fraction: float = 0.1) -> dict[str, pd.DataFrame]:  # fmt: skip
    """Headline tables at the primary hazard and headline discovery delay."""
    a = df[(df.attack == 1) & (df.hazard == hazard)]
    c = df[(df.attack == 0) & (df.hazard == hazard)]
    by_frac = a[a.discovery_delay == delay].pivot_table(
        index=["attack_target_types", "statistic", "model"], columns="damage_fraction",
        values="mass_within_3", aggfunc="mean",
    )  # fmt: skip
    by_frac = by_frac[sorted(by_frac.columns, reverse=True)]
    by_delay = a[np.isclose(a.damage_fraction, fraction)].pivot_table(
        index=["attack_target_types", "statistic", "model"], columns="discovery_delay",
        values="mass_within_3", aggfunc="mean",
    )  # fmt: skip
    err = (
        a[a.discovery_delay == delay]
        .groupby(["attack_target_types", "statistic", "model"])
        .agg(
            median_map_error=("map_error_days", "median"),
            median_signed_error=("map_signed_error_days", "median"),
            late_gt3_rate=("map_signed_error_days", lambda v: float((v > 3).mean())),
            early_gt3_rate=("map_signed_error_days", lambda v: float((v < -3).mean())),
            missed_rate=("missed", "mean"),
            mean_p_started=("p_started", "mean"),
            mean_expected_abs_error=("expected_abs_error_days", "mean"),
        )
    )
    clean = c.groupby(["statistic", "model", "discovery_delay"]).agg(
        prior_p_started=("prior_p_started", "mean"),
        mean_p_started=("p_started", "mean"),
        false_alarm_p05=("false_alarm_p05", "mean"),
        false_alarm_p09=("false_alarm_p09", "mean"),
        n=("rep", "count"),
    )
    return {"mass3_by_fraction": by_frac, "mass3_by_delay": by_delay,
            "errors": err, "clean": clean}  # fmt: skip
