"""E4 / D76 restic prototype (OPEN_QUESTIONS 2026-11-01; exploratory, DEV synthetic only).

One simulated DEV synthetic-bytes machine (config dev_d72_bytes_synthetic: frozen hyperparameters
and variant method_v2_w075_vsnap; world uniform, rep 0, benign invalid rate 0.01, K = 8; machine
family "d76_restic") is materialised as a file tree in the gitignored restic/ folder. Each
simulated day the tree is set to that day's file versions (the simulator's benign edits and its
synthetic damaged bytes; nothing is encrypted), `restic backup` takes the day's snapshot, and
SlowBurn's held set for that day (replayed on the same machine with the sweep's own code) is
applied with `restic forget <ids>` for the snapshots the plan drops. Every day the repository's
snapshot set is compared with the plan. The same backups go to two more repositories that use
restic's own policies (--keep-daily 7 --keep-weekly 5, and the count-matched --keep-daily 4
--keep-weekly 4). Measured per repository: forget and prune wall time (prune every 7 days and at
the end) and repository size after each prune. Pinned restic: tools/restic.exe (0.17.3, SHA-256
checked). Run from the repo root (one heavy job at a time; RAM >= 16 GB, C: >= 45 GB free):

    uv run python -u paper/scripts/d76_restic.py
"""

import ctypes
import json
import os
import shutil
import subprocess
import time
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from slowburn.bench.registry import load_frozen
from slowburn.bench.retention_experiment import (
    SCENARIO_FIELDS,
    build_tasks,
    make_policies,
    simulate,
    start_posteriors,
    task_seed_key,
    trace_days,
)
from slowburn.retention.base import RetentionContext
from slowburn.retention.dp import discovery_survival, retention_posterior
from slowburn.sim.damage import RandomDamageSource
from slowburn.sim.scenario import Scenario, ScenarioConfig
from slowburn.utils.config import load_config
from slowburn.utils.seed import child_rng

ROOT = Path("restic")
OUT = Path("results/exploratory/d76_restic")
RESTIC = str(Path("tools/restic.exe").resolve())
K, BENIGN, WORLD, REP, PRUNE_EVERY = 8, 0.01, "uniform", 0, 7
T0 = datetime(2026, 1, 1, 12, 0, 0)
REPOS = {"slowburn_plan": None, "restic_kd7_kw5": ["--keep-daily", "7", "--keep-weekly", "5"],
         "restic_kd4_kw4": ["--keep-daily", "4", "--keep-weekly", "4"]}  # fmt: skip


def free_gb() -> tuple[float, float]:
    class MS(ctypes.Structure):
        _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                    *[(n, ctypes.c_ulonglong) for n in ("tp", "ap", "tpf", "apf", "tv", "av",
                                                        "aev")]]  # fmt: skip

    m = MS()
    m.dwLength = ctypes.sizeof(m)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
    return m.ap / 2**30, shutil.disk_usage("C:/").free / 1e9


def restic(repo: Path, *args: str) -> tuple[subprocess.CompletedProcess, float]:
    env = {**os.environ, "RESTIC_PASSWORD": "d76-local-only", "RESTIC_REPOSITORY": str(repo)}
    t = time.perf_counter()
    r = subprocess.run([RESTIC, *args], env=env, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"restic {args[0]} failed: {r.stderr[-2000:]}")
    return r, time.perf_counter() - t


def dir_bytes(p: Path) -> int:
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file())


def machine():
    """The task, its trace, the per-day file contents and SlowBurn's held days per day."""
    cfg = load_config("configs/dev_d72_bytes_synthetic.yaml")
    cfg.update(experiment="dev_d76_restic", output_dir=str(OUT), reps=REP + 1,
               worlds=[w for w in cfg["worlds"] if w["name"] == WORLD],
               sweep={"benign_invalid_rate": [BENIGN]}, budgets=[K], policies=["slowburn"])  # fmt: skip
    task = next(t for t in build_tasks(cfg, "dev") if t.rep == REP)
    task = replace(task, family="d76_restic")
    trace = simulate(cfg, task)
    frozen = load_frozen("configs/frozen.yaml").get("params", {})
    hp = {**cfg["hp"], **{k: v for k, v in frozen.items() if k in cfg["hp"]},
          **cfg["variants"][0]["hp"], "_variant": cfg["variants"][0]["name"]}  # fmt: skip
    # the same file versions as simulate(): same scenario, same random streams
    key = task_seed_key(int(cfg["seed"]), task)
    scen_params = {k: v for k, v in task.params.items() if k in SCENARIO_FIELDS}
    n = trace_days(cfg, scen_params.get("attack_start"))
    scen = Scenario(ScenarioConfig.from_dict({**scen_params, "days": n, "content": "bytes"}))
    days = []
    for t, d in enumerate(scen.run(child_rng(*key), RandomDamageSource(child_rng(*key, "damage")),
                                   child_rng(*key, "benign_invalid"))):  # fmt: skip
        # check: the same chunks as the trace's snapshot (compared as chunks, not re-chunked
        # bytes: a benign edit can place a short final chunk mid-file)
        if frozenset(c for cs in d.files.values() for c in cs) != trace.snapshots[t]:
            raise AssertionError(f"day {t}: reconstructed tree differs from the trace")
        days.append({f: b"".join(c) for f, c in d.files.items()})
    path, prior = start_posteriors(trace, hp, int(cfg["warmup_days"]), task.params["null_prior"], {})
    ad = hp["assumed_discovery"]
    S = discovery_survival(ad["kind"], int(ad["max_days"]))
    pol = make_policies(hp, float(task.params["vault_threshold"]))["slowburn"]
    held, plan = {}, []
    for t in range(n):
        held[t] = t
        ctx = RetentionContext(day=t, snapshot_days=dict(held), budget=K,
                               daily_stat=np.array([o.value for o in trace.obs[: t + 1]]),
                               start_posterior=path[t + 1],
                               retention_pi=retention_posterior(path[t + 1], t, S),
                               prior_retention_pi=retention_posterior(prior[t + 1], t, S))  # fmt: skip
        held = {sid: held[sid] for sid in pol.decide(ctx)}
        plan.append(sorted(held.values()))
    return task, trace, days, plan


def main() -> None:
    while True:  # gate: wait and poll every 5 minutes, as the analysis queue does
        ram, disk = free_gb()
        if ram >= 16 and disk >= 45:
            break
        print(f"gate: free RAM {ram:.1f} GB, disk {disk:.0f} GB (need 16 / 45); waiting", flush=True)
        time.sleep(300)
    OUT.mkdir(parents=True, exist_ok=True)
    if ROOT.exists():
        shutil.rmtree(ROOT)
    tree = ROOT / "tree"
    tree.mkdir(parents=True)
    task, trace, days, plan = machine()
    print(f"machine: attack start {trace.start}, {len(days)} days, {len(days[0])} files", flush=True)
    repos = {name: ROOT / f"repo_{name}" for name in REPOS}
    for repo in repos.values():
        restic(repo, "init")
    ids = {name: {} for name in REPOS}  # day -> restic snapshot id
    rows, mism = [], []
    for t, files in enumerate(days):
        for f, data in files.items():
            (tree / f).write_bytes(data)
        stamp = (T0 + timedelta(days=t)).strftime("%Y-%m-%d %H:%M:%S")
        for name, repo in repos.items():
            r, tb = restic(repo, "backup", str(tree), "--json", "--time", stamp, "--host", "d76")
            summ = [json.loads(x) for x in r.stdout.splitlines() if '"summary"' in x][-1]
            ids[name][t] = summ["snapshot_id"]
            if REPOS[name] is None:
                drop = [ids[name][d] for d in sorted(ids[name]) if d not in set(plan[t])]
                tf = restic(repo, "forget", *drop)[1] if drop else 0.0
                for d in [d for d in ids[name] if d not in set(plan[t])]:
                    del ids[name][d]
            else:
                tf = restic(repo, "forget", "--host", "d76", *REPOS[name])[1]
            tp, size = np.nan, np.nan
            if t % PRUNE_EVERY == PRUNE_EVERY - 1 or t == len(days) - 1:
                tp = restic(repo, "prune")[1]
                size = dir_bytes(repo)
            snaps = json.loads(restic(repo, "snapshots", "--json")[0].stdout)
            held_ids = {s["short_id"] if len(s["id"]) != 64 else s["id"] for s in snaps}
            if REPOS[name] is None:
                want = {ids[name][d] for d in plan[t]}
                ok = held_ids == want
                if not ok:
                    mism.append({"day": t, "plan": plan[t], "repo": sorted(held_ids),
                                 "want": sorted(want)})  # fmt: skip
            else:
                ok = None
            rows.append({"repo": name, "day": t, "backup_s": tb, "forget_s": tf, "prune_s": tp,
                         "repo_bytes": size, "snapshots": len(snaps), "plan_match": ok})  # fmt: skip
        if t % 25 == 0:
            print(t, {n: rows[-3 + i]["snapshots"] for i, n in enumerate(REPOS)}, flush=True)
    df = pd.DataFrame(rows)
    df.to_csv(OUT / "per_day.csv", index=False)
    summary = (df.groupby("repo").agg(days=("day", "size"), forget_s_median=("forget_s", "median"),
                                      forget_s_p95=("forget_s", lambda x: x.quantile(0.95)),
                                      prune_s_median=("prune_s", "median"),
                                      prune_s_max=("prune_s", "max"),
                                      final_repo_mib=("repo_bytes", lambda x: x.dropna().iloc[-1] / 2**20),
                                      max_repo_mib=("repo_bytes", lambda x: x.max() / 2**20),
                                      final_snapshots=("snapshots", "last"))
               .reset_index())  # fmt: skip
    summary.to_csv(OUT / "summary.csv", index=False)
    (OUT / "mismatches.json").write_text(json.dumps(mism, indent=1))
    (OUT / "run.json").write_text(json.dumps({
        "restic": restic(repos["slowburn_plan"], "version")[0].stdout.strip(),
        "attack_start": trace.start, "days": len(days), "K": K, "benign_invalid_rate": BENIGN,
        "world": WORLD, "rep": REP, "family": task.family,
        "tree_bytes_day0": sum(len(b) for b in days[0].values()),
        "plan_mismatch_days": len(mism)}, indent=1))  # fmt: skip
    print(summary.to_string(index=False))
    print(f"plan mismatches: {len(mism)} days")


if __name__ == "__main__":
    main()
