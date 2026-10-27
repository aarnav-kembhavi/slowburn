"""D74: adaptive attacker, best response per defence (OPEN_QUESTIONS D74). DEV only; evaluation
only: no defence parameter is changed by anything here.

One task per (world, rep): the machine's benign trace is simulated once up to its attack start
s, then forked once per damage strategy (rate, damage fraction, target types) and run to
s + max delay; every defence is evaluated on each fork by ``evaluate_trace`` at the grid delays
plus the alarm delay (the first day the threshold-vault alarm fires, plus one), so both the
primary (stealth-feasible strategies) and the secondary (discovery at the alarm) analyses read
the same rows. The attacker exists only as these simulation parameters.
"""

from __future__ import annotations

import itertools
import json
import pickle
from pathlib import Path

import pandas as pd

from slowburn.bench.parallel import run_tasks
from slowburn.bench.registry import check_split_allowed, load_frozen, machine_key
from slowburn.bench.retention_experiment import (
    RetentionTask,
    attack_free_calibration,
    evaluate_trace,
)
from slowburn.fleet.machine import MachineSim
from slowburn.sim.worlds import draw_start
from slowburn.utils.seed import child_rng

_W: dict = {}


def strategies(cfg: dict, c: int) -> list[dict]:
    """The pre-registered grid, plus (D74 amendment) the threshold-aware attacker that damages
    exactly c - 1 files every day, crossed with the fractions and target sets."""
    a = cfg["attack"]
    grid = [{"kind": "grid", "rate": float(r), "fixed": None, "fraction": float(f), "targets": t}
            for r, f, t in itertools.product(a["rates"], a["fractions"], a["targets"])]  # fmt: skip
    if c - 1 < 1:
        return grid  # c = 1: no damage possible without risking an alarm (reported)
    under = [{"kind": "under_threshold", "rate": float(c - 1), "fixed": c - 1,
              "fraction": float(f), "targets": t}
             for f, t in itertools.product(a["fractions"], a["targets"])]  # fmt: skip
    return grid + under


def first_alarm_delay(obs, start: int, c: int, horizon: int) -> int | None:
    """Days from the start to discovery by the count alarm: first day t >= start with at least
    c flagged files, discovery the next day (t + 1 - start); None if none within horizon."""
    for t in range(start, min(start + horizon, len(obs))):
        if obs[t].k >= c:
            return t + 1 - start
    return None


def attack_task(task: tuple) -> list[dict]:
    world_name, rep = task
    cfg, cal = _W["cfg"], _W["calib"]
    a, sc = cfg["attack"], cfg["scenario"]
    world = next(w for w in cfg["worlds"] if w["name"] == world_name)
    seed = int(cfg["seed"])
    split = cfg.get("split", "dev")
    salt = () if split == "dev" else (split,)  # TEST starts differ; DEV streams unchanged
    s = draw_start(world, child_rng(seed, "d74_start", *salt, world_name, rep))
    D = max(int(d) for d in a["delays"])
    n_days = s + D + 1
    p = {**sc, "attack_start": None, "benign_invalid_rate": float(a["benign_invalid_rate"])}
    key = machine_key(seed, split, "d74_attack",
                      {"world": world_name, "data_source": p.get("data_source", "synthetic")},
                      rep)  # fmt: skip
    benign = MachineSim(cfg, p, key, n_days, keep_snapshots=True).run_to(s)
    params = {**p, "world": world_name, "attack_start": s, "vault_threshold": cal["thr"],
              "null_prior": cal["null_prior"],
              "type_null_priors": cal["type_null_priors"]}  # fmt: skip
    rows = []
    c = int(cal["alarm_c"])
    for st in strategies(cfg, c):
        tgt = a["targets"][st["targets"]]
        sim = benign.fork(s, attack_files_per_day=st["rate"], damage_fraction=st["fraction"],
                          attack_target_types=None if tgt is None else tuple(tgt),
                          attack_fixed_per_day=st["fixed"])  # fmt: skip
        tr = sim.run_to(n_days).trace()
        ad = first_alarm_delay(tr.obs, s, c, D)
        delays = sorted({int(d) for d in a["delays"]} | ({ad} if ad is not None else set()))
        ecfg = {**cfg, "discovery_delay": delays, "budgets": a["budgets"]}
        t = RetentionTask(
            split,
            "d74_attack",
            {**params, **{"attack_files_per_day": st["rate"], "damage_fraction": st["fraction"]}},
            rep,
        )
        for hp in _W["combos"]:
            for r in evaluate_trace(ecfg, t, tr, hp, cfg["policies"]):
                r.update(strategy_kind=st["kind"], alarm_c=c,
                         strategy_rate=st["rate"], strategy_fraction=st["fraction"],
                         strategy_targets=st["targets"], alarm_delay=ad,
                         grid_delay=int(r["discovery_delay"]) in {int(d) for d in a["delays"]},
                         is_alarm_delay=ad is not None and int(r["discovery_delay"]) == ad,
                         selection_half=rep in set(a["selection_reps"]))  # fmt: skip
                rows.append(r)
    return rows


def _init(cfg, calib, combos):
    _W["cfg"], _W["calib"], _W["combos"] = cfg, calib, combos


def calibration(cfg: dict, log=print) -> dict:
    out = Path(cfg["output_dir"]) / "calibration.pkl"
    if out.exists():
        with out.open("rb") as fh:
            return pickle.load(fh)
    rate = float(cfg["attack"]["benign_invalid_rate"])
    setting = {**cfg["scenario"], "benign_invalid_rate": rate}
    thr, prior, _m, tprior = attack_free_calibration(cfg, setting, "dev",
                                                     int(cfg["vault_calib_machines"]))  # fmt: skip
    # D74 amendment: the count alarm threshold from the disjoint calibration set
    alarm = json.loads(Path(cfg["attack"]["alarm_path"]).read_text())[cfg["attack"]["arm"]]
    cal = {"thr": float(thr), "alarm_c": int(alarm["c"]), "null_prior": tuple(map(float, prior)),
           "type_null_priors": {k: tuple(map(float, v)) for k, v in tprior.items()}}  # fmt: skip
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("wb") as fh:
        pickle.dump(cal, fh)
    log(f"calibration: count alarm c = {cal['alarm_c']}, null prior {cal['null_prior']}")
    return cal


def attack_gate(cfg: dict) -> None:
    """D74 entrypoint gate (also called by the TEST dry run): registry gate here, TEST content
    gate in the pool; calibration stays on DEV machines."""
    check_split_allowed(cfg.get("split", "dev"), dict(cfg["hp"]),
                        cfg.get("frozen_path", "configs/frozen.yaml"))  # fmt: skip


def run_attacker_experiment(cfg: dict, log=print) -> pd.DataFrame:
    attack_gate(cfg)
    out = Path(cfg["output_dir"])
    out.mkdir(parents=True, exist_ok=True)
    frozen = load_frozen(cfg.get("frozen_path", "configs/frozen.yaml")).get("params", {})
    base = {**cfg["hp"], **{k: v for k, v in frozen.items() if k in cfg["hp"]}}
    combos = [{**base, **v["hp"], "_variant": v["name"]} for v in cfg["variants"]]
    cal = calibration(cfg, log)
    tasks = [(w["name"], r) for w in cfg["worlds"] for r in range(int(cfg["attack"]["reps"]))]
    log(f"D74: {len(tasks)} machines x {len(strategies(cfg, cal['alarm_c']))} damage strategies")
    res = run_tasks(attack_task, tasks, workers=int(cfg.get("workers", 5)), init=_init,
                    init_args=(cfg, cal, combos), cache_dir=out / "machines", log=log)  # fmt: skip
    df = pd.DataFrame([r for rows in res for r in rows])
    df["arm"] = cfg["attack"]["arm"]
    df.to_csv(out / "attack_rows.csv.gz", index=False)
    log(f"wrote {len(df)} rows")
    return df
