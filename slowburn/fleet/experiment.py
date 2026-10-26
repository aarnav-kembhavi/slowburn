"""D73: fleet-aware retention experiment (OPEN_QUESTIONS D73). DEV only.

Stage 1 (one task per rep and machine): simulate the machine's benign trace once and fork it
at every attack start any (world, N, f, m) cell needs (``fleet.machine``); store each trace's
daily observations and file histories. Stage 2 (one task per rep, world and fleet size N):
retention for every method and K_avg, shared up to the fleet start S0 and branched per
(f, m) cell after it, then the restores at every discovery delay. Rows are fleet-level.

Methods: a = equal split, Bar-On recursive per machine; b = churn-proportional split, Bar-On
recursive per machine; c = FLEET (Bar-On floor at k_min + greedy reallocation under the
hierarchical posterior); d = SlowBurn per machine at K_avg (reported only); e = FLEET-indep
(the same reallocation under each machine's own posterior; reported only).
"""

from __future__ import annotations

import copy
import pickle
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
from scipy.special import logsumexp

from slowburn.bench.parallel import run_tasks
from slowburn.bench.registry import check_split_allowed, machine_key
from slowburn.bench.retention_experiment import _per_file_cols, attack_free_calibration
from slowburn.fleet.allocate import MachineLoss, greedy_allocate
from slowburn.fleet.machine import MachineSim
from slowburn.fleet.posterior import MachineLik, fleet_marginals
from slowburn.inference.changepoint import geometric_log_prior, hazard_from_window
from slowburn.retention.base import PosteriorDP, RetentionContext
from slowburn.retention.checkpointing import HORIZON_DAYS, OnlineCheckpointing, held_days
from slowburn.retention.dp import discovery_posterior, discovery_survival
from slowburn.sim.worlds import draw_start
from slowburn.store.restore import verified_restore
from slowburn.utils.seed import child_rng

METHODS = ("a_equal", "b_churn", "c_fleet", "d_slowburn", "e_fleet_indep")
RESTORES = "ABCDE"  # D72 per-file view: A verify_snap, B walk-back, C changepoint, D/E oracles
_W: dict = {}


# ---- design ------------------------------------------------------------------------------


def _salt(cfg: dict) -> tuple:
    """Split appended to the D73 streams on TEST only (DEV streams unchanged)."""
    split = cfg.get("split", "dev")
    return () if split == "dev" else (split,)


def fleet_design(cfg: dict, rep: int) -> dict:
    """Fleet starts per world, and per (world, N, f, m) the infected machines' start days."""
    seed, fl, salt = int(cfg["seed"]), cfg["fleet"], _salt(cfg)
    out = {}
    for world in cfg["worlds"]:
        s0 = draw_start(world, child_rng(seed, "d73_fleet_start", *salt, world["name"], rep))
        cells = {}
        for N in fl["sizes"]:
            perm = child_rng(seed, "d73_infect", *salt, rep, world["name"], N).permutation(N)
            u = child_rng(seed, "d73_lag", *salt, rep, world["name"], N).random(N)
            for f in fl["infected_fraction"]:
                inf = perm[: max(1, round(f * N))]
                for m in fl["lateral_mean"]:
                    lag = np.zeros(len(inf), int)
                    if m > 0:  # Geometric on {0, 1, ...} with mean m, common uniforms across m
                        p = 1.0 / (1.0 + m)
                        lag = np.floor(np.log(u[inf]) / np.log1p(-p)).astype(int)
                    lag[0] = 0  # patient zero
                    cells[(N, f, m)] = {int(i): int(s0 + L) for i, L in zip(inf, lag, strict=True)}
        out[world["name"]] = {"s0": int(s0), "cells": cells}
    return out


def machine_params(cfg: dict, rep: int, i: int) -> dict:
    fl, sc = cfg["fleet"], cfg["scenario"]
    z = child_rng(int(cfg["seed"]), "d73_fleet_churn", *_salt(cfg), rep, i).standard_normal()
    return {
        **sc,
        "attack_start": None,
        "benign_invalid_rate": float(fl["benign_invalid_rate"]),
        "edits_per_day": float(sc["edits_per_day"]) * float(np.exp(fl["churn_sigma"] * z)),
    }


def max_delay(cfg: dict) -> int:
    return max(int(d) for d in cfg["discovery_delay"])


# ---- stage 1: machine traces --------------------------------------------------------------


def _trace(sim: MachineSim) -> tuple:
    return sim.obs, sim.histories()


def machine_task(task: tuple) -> str:
    rep, i = task
    cfg, out = _W["cfg"], Path(_W["cfg"]["output_dir"]) / "machines"
    path = out / f"r{rep}_m{i:03d}.pkl"
    if path.exists():
        return str(path)
    design, D = fleet_design(cfg, rep), max_delay(cfg)
    ends: dict[int, int] = {}  # fork start -> last day needed + 1
    for w in design.values():
        end = w["s0"] + D + 1
        for starts in w["cells"].values():
            if i in starts and starts[i] < end:
                ends[starts[i]] = max(ends.get(starts[i], 0), end)
    n_days = max(w["s0"] for w in design.values()) + D + 1
    p = machine_params(cfg, rep, i)
    key = machine_key(int(cfg["seed"]), cfg.get("split", "dev"), "fleet",
                      {"fleet_machine": i, "data_source": p.get("data_source", "synthetic")},
                      rep)  # fmt: skip
    sim = MachineSim(cfg, p, key, n_days)
    forks = {}
    for s in sorted(ends):
        sim.run_to(s)
        forks[s] = _trace(sim.fork(s).run_to(ends[s]))
    sim.run_to(n_days)
    warm = int(cfg["warmup_days"])
    churn = float(np.mean([o.n for o in sim.obs[1:warm]]))
    rec = {"benign": _trace(sim), "forks": forks, "file_types": dict(sim.scen.file_types),
           "churn": churn, "edits_per_day": p["edits_per_day"]}  # fmt: skip
    out.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with tmp.open("wb") as fh:
        pickle.dump(rec, fh)
    tmp.replace(path)
    return str(path)


# ---- stage 2: retention and restores ------------------------------------------------------


class _Sched:
    """Bar-On recursive held sets (days) at budget K, from the precomputed schedule."""

    _cache: dict[int, tuple] = {}

    @classmethod
    def held(cls, K: int, day: int) -> set[int]:
        if K not in cls._cache:
            cls._cache[K] = held_days(OnlineCheckpointing("recursive").schedule(K), HORIZON_DAYS)
        return set(cls._cache[K][day]) | {day}


def churn_split(churn: np.ndarray, k_min: int, budget: int) -> np.ndarray:
    """k_min each plus the rest proportional to churn, largest remainder (ties: lower index)."""
    extra = budget - k_min * len(churn)
    share = (
        churn / churn.sum() * extra if churn.sum() > 0 else np.full(len(churn), extra / len(churn))
    )
    k = np.floor(share).astype(int)
    order = sorted(range(len(churn)), key=lambda j: (-(share[j] - k[j]), j))
    for j in order[: extra - int(k.sum())]:
        k[j] += 1
    return k_min + k


def k_min_of(K: int) -> int:
    return max(3, K // 2)


def _own_log_post(lp: np.ndarray, ratios: np.ndarray, days: np.ndarray, T: int) -> tuple:
    """Each machine's own start posterior on the window, unnormalised: (log w, log w_none)."""
    return lp[days][None, :] + ratios, lp[T]


def fleet_task(task: tuple) -> list[dict]:
    rep, world, N = task
    cfg, cal = _W["cfg"], _W["calib"]
    hp, fl = cfg["hp"], cfg["fleet"]
    warm, D = int(cfg["warmup_days"]), max_delay(cfg)
    penalty, gate = float(hp["penalty"]), float(hp["gate"])
    h = hazard_from_window(float(hp["p_attack_within_window"]), int(hp["prior_window_days"]))
    ad = hp["assumed_discovery"]
    S = discovery_survival(ad["kind"], int(ad["max_days"]))
    W = int(ad["max_days"]) + 1  # window of start days that can matter (survival 0 beyond)
    design = fleet_design(cfg, rep)[world]
    s0, end = design["s0"], design["s0"] + D
    mdir = Path(cfg["output_dir"]) / "machines"
    recs = []
    for i in range(N):
        with (mdir / f"r{rep}_m{i:03d}.pkl").open("rb") as fh:
            recs.append(pickle.load(fh))
    churn = np.array([r["churn"] for r in recs])
    lik_of = {}

    def lik(i, s):  # MachineLik of machine i attacked from s (None: benign)
        if (i, s) not in lik_of:
            obs = recs[i]["benign"][0] if s is None else recs[i]["forks"][s][0]
            lik_of[(i, s)] = MachineLik(obs, warm, cal["null_prior"], float(hp["blind_weight"]))
        return lik_of[(i, s)]

    Ks = [int(k) for k in fl["k_avg"]]
    pol_d = PosteriorDP(penalty, use_evidence=True, gate=gate, backbone=float(hp["backbone"]))
    delays = [int(d) for d in cfg["discovery_delay"]]

    def run(state, t0, t1, starts, keep_at):
        """Days t0..t1-1 for methods c, d, e at every K; ``starts``: machine -> start used."""
        for t in range(t0, t1):
            T = t + 1
            days = np.arange(max(0, t - W + 1), t + 1)
            ratios = np.stack([lik(i, starts.get(i)).ratio(T, days) for i in range(N)])
            lp = geometric_log_prior(T, h, warm)
            with np.errstate(divide="ignore"):
                log_s = np.log(S(t - days))
            lpost, lnone = _own_log_post(lp, ratios, days, T)
            own_z = np.logaddexp(logsumexp(lpost + log_s, axis=1), lnone)
            own = [np.zeros(t + 1) for _ in range(N)]
            for i in range(N):
                own[i][days] = np.exp(lpost[i] + log_s - own_z[i])
            logP, logZ = fleet_marginals(ratios, days, lp[days] + log_s, lp[T])
            hier = [np.zeros(t + 1) for _ in range(N)]
            for i in range(N):
                hier[i][days] = np.exp(logP[i] - logZ)
            for K in Ks:
                st = state[K]
                for i in range(N):  # d: SlowBurn per machine at K
                    hk = st["d_slowburn"][i]
                    hk[t] = t
                    ctx = RetentionContext(day=t, snapshot_days=hk, budget=K,
                                           daily_stat=np.zeros(1), start_posterior=np.zeros(1),
                                           retention_pi=own[i])  # fmt: skip
                    st["d_slowburn"][i] = {sid: hk[sid] for sid in pol_d.decide(ctx)}
                km = k_min_of(K)
                for nm, pis in (("c_fleet", hier), ("e_fleet_indep", own)):
                    held = st[nm]
                    ms = [MachineLoss(sorted({*held[i], t}), _Sched.held(km, t), pis[i], penalty,
                                      gate, float(churn[i])) for i in range(N)]  # fmt: skip
                    r = greedy_allocate(ms, N * K)
                    st[nm] = [{d: d for d in m.select(k)} for m, k in zip(ms, r, strict=True)]
            if t in keep_at:
                keep_at[t] = {K: {nm: [sorted(x) for x in state[K][nm]]
                                  for nm in ("c_fleet", "d_slowburn", "e_fleet_indep")}
                              for K in Ks}  # fmt: skip
                keep_at[t]["_restore"] = (days, ratios, lp)

    blank = {K: {nm: [{} for _ in range(N)] for nm in ("c_fleet", "d_slowburn", "e_fleet_indep")}
             for K in Ks}  # fmt: skip
    run(blank, 0, s0, {}, {})
    rows = []
    k_b = {K: churn_split(churn, k_min_of(K), N * K) for K in Ks}
    for (n_, f, m), starts_all in design["cells"].items():
        if n_ != N:
            continue
        starts = {i: s for i, s in starts_all.items() if s <= end}
        state = copy.deepcopy(blank)
        keep_at = {s0 + d: None for d in delays}
        run(state, s0, end + 1, starts, keep_at)
        for d in delays:
            td = s0 + d
            days, ratios, lp = keep_at[td]["_restore"]
            pmf = S(td - days - 1) - S(td - days)
            with np.errstate(divide="ignore"):
                lpmf = np.log(pmf)
            logP, _ = fleet_marginals(ratios, days, lp[days] + lpmf, -np.inf)
            own_lw = lp[days][None, :] + ratios
            infected = [i for i, s in starts.items() if s <= td]
            for K in Ks:
                kept = dict(keep_at[td][K])
                kept["a_equal"] = [sorted(_Sched.held(K, td)) for _ in range(N)]
                kept["b_churn"] = [sorted(_Sched.held(int(k_b[K][i]), td)) for i in range(N)]
                for nm in METHODS:
                    agg = {X: {"clean": [], "wl_file": 0.0, "resid": 0} for X in RESTORES}
                    whole, slots = 0.0, 0
                    for i in infected:
                        s = starts[i]
                        hist = recs[i]["forks"][s][1]
                        lw = logP[i] if nm == "c_fleet" else own_lw[i]
                        rpost = np.zeros(td + 2)
                        rpost[days] = np.exp(lw - logsumexp(lw))
                        if nm != "c_fleet":
                            rpost = discovery_posterior(rpost, td, S)
                        kp = kept[nm][i]
                        r = verified_restore(kp, rpost, td, hist, s, gate,
                                             float(hp["scan_eps"]), "verify_snap")  # fmt: skip
                        tr = SimpleNamespace(histories=hist, file_types=recs[i]["file_types"])
                        pf = _per_file_cols(kp, rpost, td, tr, s, r, "verify_snap",
                                            {"type_null_priors": cal["type_null_priors"]},
                                            float(fl["per_file_alpha"]))  # fmt: skip
                        for X in RESTORES:
                            agg[X]["clean"].append(pf[f"pf{X}_clean_recovery"])
                            agg[X]["wl_file"] += pf[f"pf{X}_work_lost_file_hours"]
                            agg[X]["resid"] += pf[f"pf{X}_residual_damaged_files"]
                        whole += r["work_lost_whole_system_hours"]
                        slots += len(kp)
                    row = {"rep": rep, "world": world, "N": N, "f": f, "m": m, "K_avg": K,
                           "method": nm, "discovery_delay": d, "s0": s0,
                           "n_infected": len(infected), "slots_infected": slots,
                           "slots_infected_share": slots / (N * K),
                           "work_lost_whole_hours_A": whole}  # fmt: skip
                    for X in RESTORES:
                        c = np.array(agg[X]["clean"], float)
                        row |= {f"fleet_clean_{X}": float(c.min()),
                                f"machine_clean_share_{X}": float(c.mean()),
                                f"work_lost_file_hours_{X}": agg[X]["wl_file"],
                                f"residual_files_{X}": agg[X]["resid"]}  # fmt: skip
                    rows.append(row)
    return rows


# ---- driver -------------------------------------------------------------------------------


def _init(cfg, calib=None):
    _W["cfg"], _W["calib"] = cfg, calib


def calibration(cfg: dict, log=print) -> dict:
    out = Path(cfg["output_dir"]) / "calibration.pkl"
    if out.exists():
        with out.open("rb") as fh:
            return pickle.load(fh)
    rate = float(cfg["fleet"]["benign_invalid_rate"])
    setting = {**cfg["scenario"], "benign_invalid_rate": rate}
    n_cal = int(cfg["vault_calib_machines"])
    _thr, prior, _mult, tprior = attack_free_calibration(cfg, setting, "dev", n_cal)
    types = {ft: tuple(map(float, ab)) for ft, ab in tprior.items()}
    cal = {"null_prior": tuple(map(float, prior)), "type_null_priors": types}
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("wb") as fh:
        pickle.dump(cal, fh)
    log(f"calibration: null prior {cal['null_prior']}")
    return cal


def run_fleet_experiment(cfg: dict, log=print, stages=("calib", "machines", "fleets")) -> None:
    # TEST: registry gate here, TEST content gate in the pool; calibration stays on DEV machines
    check_split_allowed(cfg.get("split", "dev"), dict(cfg.get("hp", {})),
                        cfg.get("frozen_path", "configs/frozen.yaml"))  # fmt: skip
    out = Path(cfg["output_dir"])
    out.mkdir(parents=True, exist_ok=True)
    fl, reps = cfg["fleet"], int(cfg["fleet"]["reps"])
    workers = int(cfg.get("workers", 5))
    cal = calibration(cfg, log) if "calib" in stages else None
    if "machines" in stages:
        tasks = [(r, i) for r in range(reps) for i in range(max(fl["sizes"]))]
        log(f"stage 1: {len(tasks)} machines")
        run_tasks(machine_task, tasks, workers=workers, init=_init, init_args=(cfg,), log=log)
    if "fleets" in stages:
        tasks = [(r, w["name"], int(N)) for r in range(reps) for w in cfg["worlds"]
                 for N in fl["sizes"]]  # fmt: skip
        log(f"stage 2: {len(tasks)} fleets")
        res = run_tasks(fleet_task, tasks, workers=workers, init=_init, init_args=(cfg, cal),
                        cache_dir=out / "fleets", log=log)  # fmt: skip
        df = pd.DataFrame([row for rows in res for row in rows])
        df["arm"] = cfg["fleet"]["arm"]
        df.to_csv(out / "fleet_rows.csv.gz", index=False)
        log(f"wrote {len(df)} rows")
