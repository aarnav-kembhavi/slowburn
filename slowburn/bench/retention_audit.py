"""D66 retention audit: product retention defaults (docs/baselines.md) on the attack grid.

DEV only, descriptive: nothing is selected or frozen. Machines are built exactly as in the
retention experiment (``build_tasks``, ``simulate``), with benign churn from FSL Homes when the
config sets ``scenario.benign_churn: fsl``. Every product is restored with the adopted restore
(D64a verify_snap): snapshot products through ``verified_restore``, per-file products through its
point-in-time analogue. Output per row: clean recovery, work lost, and whether a clean point was
held at all (retention alone).
"""

from __future__ import annotations

import time

import numpy as np
import pandas as pd

from slowburn.bench.parallel import run_tasks, stable_id
from slowburn.bench.retention_experiment import (
    adaptive_gate,
    build_tasks,
    simulate,
    start_posteriors,
    task_cache_key,
)
from slowburn.retention.dp import discovery_posterior, discovery_survival
from slowburn.retention.products import SNAPSHOT, is_per_file, retained_versions
from slowburn.store.restore import clean_point_held, point_in_time_restore, verified_restore
from slowburn.utils.config import resolve_path

_W: dict = {}
OUT_COLS = (
    "clean_recovery",
    "residual_damaged_files",
    "restore_point",
    "restore_point_clean",
    "work_lost_whole_system_hours",
    "work_lost_selective_file_hours",
    "verified",
)


def evaluate_products(cfg: dict, task, trace, hp: dict, products) -> list[dict]:
    p = task.params
    ad = hp["assumed_discovery"]
    S = discovery_survival(ad["kind"], int(ad["max_days"]), float(ad.get("tail", 0.0)),
                           float(ad.get("alpha", 1.0)))  # fmt: skip
    path, _ = start_posteriors(trace, hp, int(cfg["warmup_days"]), p.get("null_prior"), {})
    gate, scan_eps = float(hp.get("gate", 0.0)), float(hp.get("scan_eps", 0.001))
    start = trace.start
    rows = []
    for d in [int(x) for x in cfg["discovery_delay"]]:
        td = start + d
        rpost = discovery_posterior(path[td + 1], td, S)
        g = adaptive_gate(rpost, hp["adaptive_gate"], gate) if hp.get("adaptive_gate") else gate
        common = {"world": p.get("world"), "rep": task.rep, "split": task.split,
                  "detect_prob": p.get("detect_prob"),
                  "benign_invalid_rate": p.get("benign_invalid_rate"),
                  "benign_churn": p.get("benign_churn", "poisson"),
                  "discovery_delay": d, "true_start": start, "restore_gate": g,
                  "n_files_damaged": sum(h.damaged_day is not None and h.damaged_day <= td
                                         for h in trace.histories.values()),
                  "work_lost_ideal_hours": (td - (start - 1)) * 24}  # fmt: skip
        for name in products:
            if is_per_file(name):
                ret = retained_versions(name, trace.histories, td)
                r = point_in_time_restore(ret, rpost, td, trace.histories, start, g, scan_eps)
                held = clean_point_held(ret, trace.histories, start, td)
                extra = {"kind": "per_file", "versions_retained": sum(map(len, ret.values()))}
            else:
                kept = sorted(SNAPSHOT[name](td, trace.histories))
                r = verified_restore(kept, rpost, td, trace.histories, start, g, scan_eps,
                                     "verify_snap")  # fmt: skip
                held = int(any(j < start for j in kept))
                extra = {"kind": "snapshot", "snapshots_retained": len(kept)}
            rows.append(
                {
                    **common,
                    "product": name,
                    **extra,
                    "clean_point_held": held,
                    **{k: r[k] for k in OUT_COLS},
                }
            )
    return rows


def _init(cfg: dict, hp: dict, products: tuple) -> None:
    _W.update(cfg=cfg, hp=hp, products=products)


def _run(task) -> list[dict]:
    trace = simulate(_W["cfg"], task)
    return evaluate_products(_W["cfg"], task, trace, _W["hp"], _W["products"])


def first_below(curve: pd.DataFrame, col: str, thr: float):
    """First grid delay at which ``col`` is below ``thr`` (not interpolated); NaN if never."""
    below = curve[curve[col] < thr]
    return float(below.discovery_delay.min()) if len(below) else np.nan


def run_retention_audit(cfg: dict, log=print) -> pd.DataFrame:
    if cfg.get("split", "dev") != "dev":
        raise ValueError("the retention audit runs on the dev split only")
    from slowburn.bench.registry import load_frozen

    out = resolve_path(cfg["output_dir"])
    out.mkdir(parents=True, exist_ok=True)
    frozen = load_frozen(cfg.get("frozen_path", "configs/frozen.yaml")).get("params", {})
    hp = {**cfg["hp"], **{k: v for k, v in frozen.items() if k in cfg["hp"]}, **cfg["hp_override"]}
    products = tuple(cfg["products"])
    unknown = [n for n in products if not is_per_file(n) and n not in SNAPSHOT]
    if unknown:
        raise ValueError(f"unknown products {unknown}")
    t0 = time.perf_counter()
    tasks = build_tasks(cfg, "dev", log)
    seed = int(cfg["seed"])
    res = run_tasks(_run, tasks, workers=int(cfg.get("workers", 1)), init=_init,
                    init_args=(cfg, hp, products), cache_dir=out / "machines_audit",
                    task_key=lambda t: (stable_id(products), *task_cache_key(seed, t)),
                    log=log)  # fmt: skip
    df = pd.DataFrame([r for rows in res for r in rows])
    df.to_csv(out / "audit_rows.csv.gz", index=False)
    curve = (df.groupby(["product", "kind", "detect_prob", "discovery_delay"])
             .agg(recovery=("clean_recovery", "mean"), held=("clean_point_held", "mean"),
                  work_lost_h=("work_lost_whole_system_hours", "mean"),
                  rows=("clean_recovery", "size"))
             .reset_index())  # fmt: skip
    curve.to_csv(out / "audit_curves.csv", index=False)
    thr = []
    for (prod, kind, q), c in curve.groupby(["product", "kind", "detect_prob"]):
        c = c.sort_values("discovery_delay")
        thr.append({"product": prod, "kind": kind, "detect_prob": q,
                    "recovery_first_below_0.5": first_below(c, "recovery", 0.5),
                    "recovery_first_below_0.1": first_below(c, "recovery", 0.1),
                    "held_first_below_0.5": first_below(c, "held", 0.5),
                    "held_first_below_0.1": first_below(c, "held", 0.1)})  # fmt: skip
    pd.DataFrame(thr).to_csv(out / "audit_thresholds.csv", index=False)
    log(f"  {len(tasks)} machines, {len(df)} rows, {time.perf_counter() - t0:.1f}s")
    return curve
