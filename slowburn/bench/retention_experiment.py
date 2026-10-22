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
from functools import lru_cache

import numpy as np
import pandas as pd

from slowburn.bench.parallel import run_tasks
from slowburn.bench.registry import check_split_allowed, machine_key
from slowburn.inference.changepoint import (
    SingleChangepoint,
    hazard_from_window,
    timing_log_prior,
)
from slowburn.inference.daily import make_aggregator
from slowburn.inference.obsmodels import BetaBinomialExceedance, fit_pooled_null_prior
from slowburn.inference.pipeline import AbstractFileDetector, score_day
from slowburn.retention.amoeba import AmoebaStyle, Write, fit_weights
from slowburn.retention.base import (
    GFS,
    KeepFirst,
    KeepLastN,
    Oracle,
    PosteriorDP,
    RetentionContext,
    ThresholdVault,
    TowerOfHanoi,
)
from slowburn.retention.bytes import ByteIndex, enforce_byte_budget
from slowburn.retention.dp import (
    discovery_posterior,
    discovery_survival,
    retention_posterior,
)
from slowburn.sim.damage import RandomDamageSource
from slowburn.sim.scenario import Scenario, ScenarioConfig
from slowburn.sim.worlds import world_start
from slowburn.store.restore import (
    HOURS_PER_DAY,
    FileHistory,
    selective_restore,
    snapshots_scanned,
    verified_restore,
    walkback_restore,
)
from slowburn.utils.config import resolve_path
from slowburn.utils.seed import child_rng

SNAPSHOT_POLICIES = ("keep_last_n", "keep_first", "gfs", "tower_of_hanoi", "threshold_vault",
                     "prior_only", "slowburn", "oracle")  # fmt: skip
# keep_first cannot meet a byte budget below |first U today| (D46): count budgets only
COUNT_ONLY = frozenset({"keep_first"})
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
    # the world name labels the rows: two worlds can draw the same start for one rep (identical
    # machine), but their cached rows must stay apart
    world = (("world", task.params["world"]),) if "world" in task.params else ()
    return (
        *task_seed_key(seed, task),
        *sorted((k, v) for k, v in task.params.items() if k in PAIRED_KEYS),
        *world,
    )


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
    evidence = p.get("evidence", "abstract")
    if evidence not in ("abstract", "detector"):
        raise ValueError(f"unknown evidence {evidence!r}")
    content = "bytes" if evidence == "detector" else "tokens"  # D67: a real detector reads bytes
    scen = Scenario(ScenarioConfig.from_dict({**scen_params, "days": n_days,
                                              "content": content}))  # fmt: skip
    damage_source = RandomDamageSource(child_rng(*key, "damage"))
    if p.get("data_source", "synthetic") == "napierone":  # D67: real benign and encrypted bytes
        if evidence != "detector":
            raise ValueError("data_source napierone needs evidence: detector (byte mode)")
        scen.content_pool, damage_source = _napierone(p["napierone_dir"])
    elif p.get("data_source", "synthetic") != "synthetic":
        raise ValueError(f"unknown data_source {p['data_source']!r}")
    if p.get("benign_churn") == "fsl":  # D66: real per-file rewrite days from FSL Homes
        from slowburn.datasets.fsl_churn import load_churn, machine_schedule

        _, scen.edit_schedule = machine_schedule(load_churn(), child_rng(*key, "fsl_churn"),
                                                 scen.cfg.n_files, n_days)  # fmt: skip
    elif p.get("benign_churn", "poisson") != "poisson":
        raise ValueError(f"unknown benign_churn {p['benign_churn']!r}")
    if evidence == "detector":  # D67: trained detector, flag = file p-value <= frozen alpha
        det, flag_alpha = _load_detector(p["detector_path"]), float(p["flag_alpha"])
        agg = make_aggregator("file_exceed", alpha=flag_alpha)
    else:
        det = AbstractFileDetector(float(p.get("detect_prob", 0.0)), child_rng(*key, "detector"))
        agg = make_aggregator("file_exceed", alpha=0.5)  # p-values are 0/1: any alpha in (0,1)
        flag_alpha = 0.0
    snapshots, obs, writes = [], [], []
    versions: dict[str, tuple] = {}
    change_days: dict[str, list[int]] = {}
    flagged_days: dict[str, set[int]] = {}
    recent_changes: list[int] = []
    for day in scen.run(child_rng(*key), damage_source,
                        child_rng(*key, "benign_invalid")):  # fmt: skip
        snapshots.append(frozenset(c for chunks in day.files.values() for c in chunks))
        scores = score_day(det, day) if evidence == "detector" else det.score_day(day)
        obs.append(agg(scores))
        flagged = {f for f, pv in (scores.file_pvals or {}).items() if pv <= flag_alpha}
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


@lru_cache(maxsize=4)
def _load_detector(path: str):
    import pickle

    with resolve_path(path).open("rb") as fh:
        return pickle.load(fh)


@lru_cache(maxsize=2)
def _napierone(root: str):
    """DEV content pool and DEV-family damage source (D67); TEST pools are never read here."""
    from slowburn.detector.datasets import NapierOneDamageSource
    from slowburn.detector.napierone import ContentPool, encrypted_samples, family_splits

    r = resolve_path(root)
    fams = family_splits(r)["sim_dev"]
    return ContentPool(r, "sim_dev"), NapierOneDamageSource(r, samples=encrypted_samples(r, fams))


def _data_labels(p: dict) -> dict:
    """What produced a row's files, damage and evidence (synthetic and real data never mix)."""
    if p.get("evidence", "abstract") == "abstract":
        return {"benign_source": "synthetic", "damage_source": "abstract_token",
                "evidence": f"abstract_q{p.get('detect_prob')}"}  # fmt: skip
    src = p.get("data_source", "synthetic")
    return {"benign_source": src,
            "damage_source": "napierone" if src == "napierone" else "synthetic_random",
            "evidence": f"detector:{p['detector_path']}@{p['flag_alpha']}"}  # fmt: skip


# ---- policies ---------------------------------------------------------------------------


def make_policies(hp: dict, vault_threshold: float) -> dict:
    """Fresh policy objects (some keep state). ``slowburn_*`` entries are ablations."""
    gate, bb, P = float(hp.get("gate", 0.0)), float(hp.get("backbone", 0.0)), hp["penalty"]
    return {
        "keep_last_n": KeepLastN(),
        "keep_first": KeepFirst(),
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
    cache: dict = {}
    rows = evaluate_trace(cfg, task, trace, cfg["hp"], names, sim_s, posterior_cache=cache)
    return rows + tradeoff_rows(cfg, task, trace, cache)


def tradeoff_combos(cfg: dict) -> list[dict]:
    """SlowBurn settings for the recovery / work-lost trade-off curve (reporting only: the
    operating point is fixed on DEV before test; the curve shows what other settings would do)."""
    t = cfg.get("tradeoff")
    if not t:
        return []
    base = cfg["hp"]
    return [{**base, "penalty": P, "backbone": bb,
             "assumed_discovery": {**base["assumed_discovery"], "max_days": m}}
            for P in t["penalty"] for m in t["assumed_discovery_max_days"]
            for bb in t["backbone"]]  # fmt: skip


def tradeoff_rows(cfg: dict, task: RetentionTask, trace: MachineTrace, cache: dict) -> list[dict]:
    rows = []
    for hp in tradeoff_combos(cfg):
        for r in evaluate_trace(cfg, task, trace, hp, ("slowburn",), posterior_cache=cache):
            rows.append({**r, "policy": "slowburn_curve"})
    return rows


ALL_POLICIES = (*SNAPSHOT_POLICIES, "amoeba_style")


def budgets_of(cfg: dict, task: RetentionTask, hp: dict) -> list[int]:
    if "budget" in task.params:
        return [int(task.params["budget"])]
    return [int(k) for k in (cfg["budgets"] if "budgets" in cfg else [hp["budget"]])]


def start_posteriors(trace: MachineTrace, hp: dict, warmup: int, null_prior, cache: dict):
    """Evidence and prior-only start posteriors after every day (cached per hazard / null)."""
    h = hazard_from_window(float(hp["p_attack_within_window"]), int(hp["prior_window_days"]))
    pooled = hp.get("null_pool", "pooled") == "pooled" and null_prior is not None
    tp = hp.get("timing_prior")  # misspecification sweep only; None = the frozen geometric prior
    spec = dict(tp) if tp else {"kind": "geometric", "hazard": h}
    spec.pop("name", None)
    blind = float(hp.get("blind_weight", 0.0))  # method v2 (D48); 0 = v1
    key = (h, pooled, repr(sorted(spec.items())), blind)
    if key not in cache:
        n = trace.n_days
        obs_model = BetaBinomialExceedance(null_prior=tuple(null_prior) if pooled else None,
                                           blind_weight=blind)  # fmt: skip
        model = SingleChangepoint(obs_model, h, warmup, prior=spec)
        cache[key] = (
            model.posterior_path(trace.obs, list(range(1, n + 1))),  # T = t + 1 days
            {T: np.exp(timing_log_prior(T, spec, warmup)) for T in range(1, n + 1)},
        )
    return cache[key]


def adaptive_gate(post: np.ndarray, spec: dict, gate: float) -> float:
    """Method v2 restore gate (D49): ``gate`` when the start posterior is diffuse, down to
    ``spec['min']`` when it is concentrated. Concentration c = the largest posterior mass of the
    started days inside any window of ``spec['window']`` consecutive days; the gate is
    min + (gate - min) * (1 - c). Applied only to restores that use detector evidence, so the
    no-detector (prior-only) restore keeps the fixed gate."""
    started = np.asarray(post[:-1], float)
    total = started.sum()
    if total <= 0:
        return gate
    w = int(spec.get("window", 7))
    cs = np.r_[0.0, np.cumsum(started / total)]
    c = float(np.max(cs[w:] - cs[:-w])) if len(started) >= w else 1.0
    lo = float(spec["min"])
    return lo + (gate - lo) * (1.0 - c)


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
    ad = hp["assumed_discovery"]
    S = discovery_survival(ad["kind"], int(ad["max_days"]), float(ad.get("tail", 0.0)),
                           float(ad.get("alpha", 1.0)))  # fmt: skip
    # method v4 (D60): the restore may assume a different (hard) delay than retention plans with
    rd = hp.get("restore_discovery") or ad
    S_r = S if rd is ad else discovery_survival(rd["kind"], int(rd["max_days"]),
                                                float(rd.get("tail", 0.0)),
                                                float(rd.get("alpha", 1.0)))  # fmt: skip
    walk = hp.get("walkback")
    old_flags = hp.get("old_flags", "skip")  # D62 diagnostics, D64a verify_snap
    if walk and p.get("null_prior") is None:
        raise ValueError("the v4 walk-back needs the fleet-pooled benign prior")
    sa = hp.get("snap_accept")  # method v2.1 (D65): significance-based snapshot accept rule
    if sa and p.get("null_prior") is None:
        raise ValueError("the D65 accept test needs the fleet-pooled benign prior")
    accept = (tuple(p["null_prior"]), float(sa["alpha"])) if sa else None
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
    # budget keys: ("count", K) caps the number of snapshots; ("bytes", K) caps unique bytes at
    # the calibrated keep-last-K footprint times this machine's day-0 size (D46)
    Ks = [("count", K) for K in budgets_of(cfg, task, hp)]
    bmult = {int(k): float(v) for k, v in (p.get("byte_budget_mult") or {}).items()}
    index = ByteIndex(trace.snapshots, trace.chunk_size) if bmult else None
    Ks += [("bytes", K) for K in sorted(bmult)]
    budget_bytes = {K: bmult[K] * index.size(0) for K in bmult} if bmult else {}
    snap_names = [nm for nm in policy_names if nm != "amoeba_style"]
    pols = {bk: {nm: pol for nm, pol in make_policies(hp, float(p.get("vault_threshold", 0.0)))
                 .items() if nm in snap_names and (bk[0] == "count" or nm not in COUNT_ONLY)}
            for bk in Ks}  # fmt: skip
    held = {(bk, nm): {} for bk in Ks for nm in pols[bk]}
    kept_at = {(bk, nm): {} for bk in Ks for nm in pols[bk]}
    dp_s, dp_calls = 0.0, 0
    disc_days = {d: start + d for d in delays}
    for t in range(n):
        T = t + 1
        rpi = retention_posterior(path[T], t, S)
        ppi = retention_posterior(prior[T], t, S)
        for bk in Ks:
            kind, K = bk
            for nm, pol in pols[bk].items():
                hk = held[(bk, nm)]
                hk[t] = t

                def decide(h, k, pol=pol, t=t, T=T, rpi=rpi, ppi=ppi):
                    ctx = RetentionContext(day=t, snapshot_days=h, budget=k,
                                           daily_stat=stat[: t + 1], start_posterior=path[T],
                                           retention_pi=rpi, prior_retention_pi=ppi,
                                           oracle_start=start)  # fmt: skip
                    return pol.decide(ctx)

                t2 = time.perf_counter()
                if kind == "count":
                    keep = decide(dict(hk), K)
                    new = {sid: hk[sid] for sid in keep}
                else:
                    new = enforce_byte_budget(hk, budget_bytes[K], index, decide)
                if nm == "slowburn" and kind == "count":
                    dp_s += time.perf_counter() - t2
                    dp_calls += 1
                held[(bk, nm)] = new
                if t in disc_days.values():
                    kept_at[(bk, nm)][t] = sorted(new.values())

    amoeba_rec = {}
    if "amoeba_style" in policy_names and "amoeba_weights" in p:
        for K in [K for kind, K in Ks if kind == "count"]:
            amoeba = AmoebaStyle(np.asarray(p["amoeba_weights"], float))
            for t in range(n):
                last_k = list(range(max(0, t - K + 1), t + 1))
                budget = _unique_bytes(trace, last_k) - len(trace.snapshots[t]) * trace.chunk_size
                amoeba.step(trace.writes[t], max(budget, 0))
                if t in disc_days.values():
                    amoeba_rec[(K, t)] = amoeba.recover(trace.histories, t)

    base = {
        k: v
        for k, v in p.items()
        if k not in ("amoeba_weights", "null_prior", "budget", "byte_budget_mult")
    }
    hp_cols = {"hp_p_attack_within_window": hp["p_attack_within_window"],
               "hp_penalty": hp["penalty"], "hp_gate": gate,
               "hp_backbone": float(hp.get("backbone", 0.0)),
               "hp_timing_prior": (hp.get("timing_prior") or {}).get("name", "frozen_geometric"),
               "variant": hp.get("_variant", ""),
               "hp_blind_weight": float(hp.get("blind_weight", 0.0)),
               "hp_adaptive_gate": repr(hp.get("adaptive_gate") or ""),
               "hp_assumed_discovery_max": hp["assumed_discovery"]["max_days"],
               "hp_assumed_discovery_kind": hp["assumed_discovery"]["kind"],
               "hp_assumed_discovery_tail": float(hp["assumed_discovery"].get("tail", 0.0)),
               "hp_null_pool": hp.get("null_pool", "pooled"), "hp_restore_rule": rule,
               "hp_restore_quantile": hp.get("restore_quantile"),
               "hp_restore_posterior": hp.get("restore_posterior", "discovery"),
               "hp_restore_discovery_kind": rd["kind"],
               "hp_restore_discovery_max": rd["max_days"],
               "hp_walkback_alpha": float(walk["alpha"]) if walk else np.nan,
               "hp_old_flags": old_flags,
               "hp_snap_accept_alpha": float(sa["alpha"]) if sa else np.nan}  # fmt: skip
    rows = []
    for bk in Ks:
        kind, K = bk
        for d, td in disc_days.items():
            post = path[td + 1]
            klast = list(range(max(0, td - K + 1), td + 1))
            klast_bytes = _unique_bytes(trace, klast)
            common = {**base, **hp_cols, "split": task.split, "rep": task.rep,
                      "discovery_delay": d, "true_start": start, "budget": K,
                      "budget_kind": kind, "budget_bytes": budget_bytes.get(K, np.nan)
                      if kind == "bytes" else np.nan,
                      "start_offset_month": start % 28, "start_offset_week": start % 7,
                      "n_files_damaged": sum(h_.damaged_day is not None and h_.damaged_day <= td
                                             for h_ in trace.histories.values()),
                      # best achievable (oracle) work lost: restore from day s - 1
                      "work_lost_ideal_hours": (td - (start - 1)) * HOURS_PER_DAY,
                      **_data_labels(p),
                      "p_started_at_discovery": float(1 - post[-1]),
                      "sim_s": sim_s, "infer_ms_per_day": 1000 * infer_s / n,
                      "dp_ms_per_decision": 1000 * dp_s / max(dp_calls, 1)}  # fmt: skip
            for nm, pol in pols[bk].items():
                kept = kept_at[(bk, nm)][td]
                # a posterior-DP policy restores with the posterior it plans with (D33): the
                # blind policy's DP loss assumes a prior-gated restore, so its gate uses the prior
                rpost = post if getattr(pol, "use_evidence", True) else prior[td + 1]
                if hp.get("restore_posterior", "discovery") == "discovery":  # D34
                    rpost = discovery_posterior(rpost, td, S_r)
                g_r = gate
                if hp.get("adaptive_gate") and getattr(pol, "use_evidence", True):
                    g_r = adaptive_gate(rpost, hp["adaptive_gate"], gate)  # method v2 (D49)
                if rule == "verified" and walk:
                    r = walkback_restore(kept, rpost, td, trace.histories, start, g_r,
                                         tuple(p["null_prior"]), float(walk["alpha"]),
                                         scan_eps, old_flags, accept)  # fmt: skip
                elif rule == "verified":
                    r = verified_restore(kept, rpost, td, trace.histories, start, g_r, scan_eps,
                                         old_flags, accept)  # fmt: skip
                else:
                    r = selective_restore(kept, rpost, td, trace.histories, start,
                                          float(hp["restore_quantile"]))  # fmt: skip
                    r["snapshots_scanned"] = snapshots_scanned(kept, start, r["restore_point"])
                ub = _unique_bytes(trace, kept)
                rows.append({**common, "policy": nm, **r,
                             "snapshots_retained": len(kept), "retained_unique_bytes": ub,
                             "storage_vs_keep_last_n": ub / klast_bytes if klast_bytes else np.nan,
                             "clean_snapshot_retained": int(any(j < start for j in kept)),
                             # best restore the kept set allows (diagnostic, D49)
                             "newest_clean_kept": max((j for j in kept if j < start),
                                                      default=np.nan),
                             "restore_gate": g_r,
                             "oldest_retained_age": td - min(kept),
                             # how far back the restore went (D60)
                             "walkback_steps": r.get("walkback_steps", 0),
                             "walkback_from": r.get("walkback_from", r["restore_point"]),
                             "restore_depth_days": td - r["restore_point"],
                             "restore_beyond_bound": int(td - r["restore_point"]
                                                         > int(rd["max_days"]))})  # fmt: skip
            if kind == "count" and (K, td) in amoeba_rec:
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
                            fa: float = 0.05, byte_ks=()) -> tuple:  # fmt: skip
    """From attack-free calibration machines (separate DEV family):
    * the threshold vault's fixed line: the (1 - fa) quantile of the largest daily flagged-file
      fraction after warm-up;
    * the fleet-level Beta prior on the benign flag rate (D31), from each machine's flagged and
      changed file totals after warm-up;
    * for each K in ``byte_ks``, the byte-budget multiplier (D46): the median, over machines and
      days after warm-up, of the unique bytes of the newest K snapshots divided by the machine's
      day-0 snapshot size (the keep-last-K footprint)."""
    warmup = int(cfg["warmup_days"])
    peaks, ks, ns = [], [], []
    foot: dict[int, list[float]] = {int(K): [] for K in byte_ks}
    for r in range(n_machines):
        clean = {**setting, "attack_start": None}
        trace = simulate(cfg, RetentionTask(split, "vault_calib", clean, r))
        after = trace.obs[warmup:]
        peaks.append(max([o.value for o in after], default=0.0))
        ks.append(sum(o.k for o in after))
        ns.append(sum(o.n for o in after))
        if foot:
            idx = ByteIndex(trace.snapshots, trace.chunk_size)
            for K in foot:
                foot[K] += [idx.unique_bytes(range(t - K + 1, t + 1)) / idx.size(0)
                            for t in range(warmup + K - 1, trace.n_days)]  # fmt: skip
    thr = float(np.quantile(peaks, 1 - fa, method="higher"))
    mult = {K: float(np.median(v)) for K, v in foot.items()}
    return thr, fit_pooled_null_prior(np.array(ks), np.array(ns)), mult


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
    """One task per (evidence/scenario setting, rep), or with ``worlds`` (simulator v2, D45) one
    per (world, setting, rep) with the attack start drawn from the world for that rep."""
    from slowburn.bench.runner import expand_sweep

    grid = expand_sweep(cfg["scenario"], cfg.get("sweep", {}))
    calib_split = "dev"  # calibration steps always use dev machines (separate families)
    need_amoeba = "amoeba_style" in cfg.get("policies", ALL_POLICIES)
    byte_ks = [int(k) for k in cfg.get("byte_budgets", [])]
    calib = {}
    for setting in grid:
        ev_key = (setting.get("detect_prob"), setting.get("benign_invalid_rate"))
        if ev_key not in calib:
            w = (fit_amoeba_weights(cfg, setting, calib_split,
                                    int(cfg.get("amoeba_train_machines", 8)))
                 if need_amoeba else None)  # fmt: skip
            n_cal = int(cfg.get("vault_calib_machines", 40))
            calib[ev_key] = (w, *attack_free_calibration(cfg, setting, calib_split, n_cal,
                                                         byte_ks=byte_ks))  # fmt: skip
    log(f"  calibrated vault thresholds, fleet null priors{' and AMOEBA weights' * need_amoeba}"
        f" for {len(calib)} evidence settings")  # fmt: skip
    if byte_ks:
        mult = next(iter(calib.values()))[3]  # churn does not depend on the evidence setting
        log(f"  byte-budget multipliers (keep-last-K footprint / day-0 size): {mult}")
    worlds = cfg.get("worlds")
    seed = int(cfg["seed"])
    tasks = []
    for setting in grid:
        w, thr, prior, mult = calib[(setting.get("detect_prob"),
                                     setting.get("benign_invalid_rate"))]  # fmt: skip
        params = {**setting, "vault_threshold": thr, "null_prior": tuple(map(float, prior))}
        if w is not None:
            params["amoeba_weights"] = tuple(map(float, w))
        if mult:
            params["byte_budget_mult"] = dict(mult)
        if not worlds:
            tasks += [RetentionTask(split, "eval", params, r) for r in range(int(cfg["reps"]))]
            continue
        for world in worlds:
            tasks += [RetentionTask(split, "eval", {**params, "world": world["name"],
                                                    "attack_start": world_start(seed, split,
                                                                                world, r)}, r)
                      for r in range(int(cfg["reps"]))]  # fmt: skip
    return tasks


GRID_CELL = ["world", "budget_kind", "budget", "discovery_delay", "attack_start", "detect_prob",
             "benign_invalid_rate"]  # fmt: skip
CELL_DEFAULTS = {"world": "fixed_starts", "budget_kind": "count"}  # v1 result files
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
    """Mean clean recovery and work lost per grid cell and policy, oracle-ideal alongside
    (the SlowBurn trade-off-curve rows are excluded: they are not a policy)."""
    df = df.assign(**{c: df.get(c, v) for c, v in CELL_DEFAULTS.items()})
    g = df[df.policy != "slowburn_curve"].groupby([*GRID_CELL, "policy"], dropna=False)
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


def world_summary(df: pd.DataFrame, by=()) -> pd.DataFrame:
    """Simulator v2: per world, budget kind and policy (and ``by``), mean clean recovery, mean
    whole-system work lost, oracle-ideal work lost and share with a clean snapshot retained,
    pooled over every machine, evidence cell, budget and delay."""
    df = df.assign(**{c: df.get(c, v) for c, v in CELL_DEFAULTS.items()})
    keys = ["world", "budget_kind", "policy", *by]
    return (df[df.policy != "slowburn_curve"].groupby(keys)
            .agg(recovery=("clean_recovery", "mean"),
                 work_lost_h=("work_lost_whole_system_hours", "mean"),
                 ideal_work_lost_h=("work_lost_ideal_hours", "mean"),
                 clean_retained=("clean_snapshot_retained", "mean"),
                 rows=("clean_recovery", "size"))
            .reset_index())  # fmt: skip


def worst_case_timing(df: pd.DataFrame) -> pd.DataFrame:
    """Worst-case timing over a grid of attack starts and discovery delays (simulation
    parameters only, D47): per policy, budget and detection probability, the mean over timing
    cells and the worst timing cell (lowest mean recovery; highest mean work lost), with the
    start and delay of the worst recovery cell."""
    df = df.assign(**{c: df.get(c, v) for c, v in CELL_DEFAULTS.items()})
    key = ["budget_kind", "budget", "detect_prob", "policy"]
    cells = (df.groupby([*key, "attack_start", "discovery_delay"])
             .agg(recovery=("clean_recovery", "mean"),
                  work_lost_h=("work_lost_whole_system_hours", "mean"))
             .reset_index())  # fmt: skip
    worst = cells.loc[cells.groupby(key).recovery.idxmin()].set_index(key)
    out = cells.groupby(key).agg(recovery_avg=("recovery", "mean"),
                                 recovery_worst=("recovery", "min"),
                                 work_lost_avg=("work_lost_h", "mean"),
                                 work_lost_worst=("work_lost_h", "max"),
                                 timing_cells=("recovery", "size"))  # fmt: skip
    out["worst_start"] = worst.attack_start
    out["worst_delay"] = worst.discovery_delay
    return out.reset_index()


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
    if cfg.get("worlds"):
        world_summary(df).to_csv(out / "world_summary.csv", index=False)
        for by in ("budget", "detect_prob", "discovery_delay"):
            world_summary(df, (by,)).to_csv(out / f"world_by_{by}.csv", index=False)
    if cfg.get("worst_case_timing"):
        worst_case_timing(df).to_csv(out / "worst_case_timing.csv", index=False)
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
        "restore_posterior": base.get("restore_posterior", "discovery"),
        "scan_eps": float(base.get("scan_eps", 0.001)),
    }
    update_frozen(chosen, note=f"rule D30 on {cfg.get('_config_path')}",
                  path=cfg.get("frozen_path", "configs/frozen.yaml"),
                  remove=("budget",))  # fmt: skip
    return {"stage1": board1, "stage2": board2, "chosen": chosen}


def apply_constrained_stage2(cfg: dict, stage1_choice: tuple, freeze: bool = True) -> dict:
    """Rule D36 on the stored D30 DEV tuning CSVs (no re-run): records the choice in
    configs/frozen.yaml and, with ``freeze``, freezes it."""
    from slowburn.bench.registry import update_frozen
    from slowburn.bench.tune import retention_stage2_constrained

    out = resolve_path(cfg["output_dir"])
    df1 = pd.read_csv(out / "tuning_stage1.csv")
    df2 = pd.read_csv(out / "tuning_stage2.csv")
    board, (P, m, bb), cap = retention_stage2_constrained(df2, df1, stage1_choice)
    board.to_csv(out / "stage2_scoreboard_constrained.csv")
    base = cfg["hp"]
    chosen = {"penalty": float(P), "backbone": float(bb),
              "assumed_discovery": {**base["assumed_discovery"], "max_days": int(m)}}  # fmt: skip
    update_frozen(chosen, freeze=freeze, path=cfg.get("frozen_path", "configs/frozen.yaml"),
                  note=f"rule D36 (deviation from D30 stage 2, see OPEN_QUESTIONS) on "
                  f"{out}: work-lost cap {cap:.3f} h (best fixed schedule on DEV)")  # fmt: skip
    return {"board": board, "chosen": chosen, "cap": cap}


# ---- DEV sweeps (Tier 2 F: reporting, never tuning) --------------------------------------


def sweep_summary(df: pd.DataFrame, by=()) -> pd.DataFrame:
    """Mean clean recovery and whole-system work lost per sweep variant and policy (and ``by``),
    averaged over every grid cell, with GFS and Tower of Hanoi alongside for reference."""
    keys = ["variant", *(["world"] if "world" in df else []), "policy", *by]
    return (df.groupby(keys)
            .agg(recovery=("clean_recovery", "mean"),
                 work_lost_h=("work_lost_whole_system_hours", "mean"),
                 clean_retained=("clean_snapshot_retained", "mean"),
                 rows=("clean_recovery", "size"))
            .reset_index())  # fmt: skip


def run_dev_sweep(cfg: dict, log=print) -> pd.DataFrame:
    """Evaluate the frozen hyperparameters with each variant in ``cfg['variants']`` (a name plus
    hp overrides) on the same DEV machines. Reporting only: nothing is chosen or frozen."""
    if cfg.get("split", "dev") != "dev":
        raise ValueError("sweeps run on the dev split only")
    from slowburn.bench.registry import load_frozen

    out = resolve_path(cfg["output_dir"])
    out.mkdir(parents=True, exist_ok=True)
    frozen = load_frozen(cfg.get("frozen_path", "configs/frozen.yaml")).get("params", {})
    base = {**cfg["hp"], **{k: v for k, v in frozen.items() if k in cfg["hp"]}}
    tasks = build_tasks(cfg, "dev", log)
    combos = [{**base, **v["hp"], "_variant": v["name"]} for v in cfg["variants"]]
    policies = tuple(cfg.get("policies", ("slowburn", "prior_only", "gfs", "tower_of_hanoi")))
    df = _stage(cfg, tasks, combos, policies, out, "sweep", log)
    summ = sweep_summary(df)
    summ.to_csv(out / "sweep_summary.csv", index=False)
    sweep_summary(df, ("budget",)).to_csv(out / "sweep_by_budget.csv", index=False)
    if "detect_prob" in df:  # absent with a trained detector (D67): no abstract q axis
        sweep_summary(df, ("detect_prob",)).to_csv(out / "sweep_by_q.csv", index=False)
    sweep_summary(df, ("discovery_delay",)).to_csv(out / "sweep_by_delay.csv", index=False)
    return summ
