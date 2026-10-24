"""D71 item 3: benign (false) flag rate, synthetic bytes vs NapierOne bytes.

Re-simulates exactly the D67 eval machines of both arms (same tasks and seeds as build_tasks;
the calibration step is skipped because it does not change any machine) and counts, for every
clean file version written, whether the detector flagged it. Run from the repo root:

    uv run python paper/scripts/d71_false_flags.py [workers]
"""

import sys
from pathlib import Path

import pandas as pd

from slowburn.bench.parallel import run_tasks
from slowburn.bench.retention_experiment import RetentionTask, simulate, world_start
from slowburn.bench.runner import expand_sweep
from slowburn.utils.config import load_config

ARMS = {"synthetic": "configs/dev_d67_full_synthetic.yaml",
        "napierone": "configs/dev_d67_full_napierone.yaml",
        "napierone_v2pool": "configs/dev_d67_full_napierone_v2pool.yaml"}  # D75  # fmt: skip
OUT = Path("results/dev_d71_false_flags")
WARMUP = 14
_W: dict = {}


def tasks_of(cfg):
    seed, out = int(cfg["seed"]), []
    for setting in expand_sweep(cfg["scenario"], cfg.get("sweep", {})):
        for world in cfg["worlds"]:
            out += [RetentionTask("dev", "eval", {**setting, "world": world["name"],
                                                  "attack_start": world_start(seed, "dev",
                                                                              world, r)}, r)
                    for r in range(int(cfg["reps"]))]  # fmt: skip
    return out


def _init(cfg, arm):
    _W["cfg"], _W["arm"] = cfg, arm


def count(task):
    cfg, arm = _W["cfg"], _W["arm"]
    tr = simulate(cfg, task)
    types = cfg["scenario"]["file_types"]
    p, start = task.params, int(task.params["attack_start"])
    base = {"arm": arm, "world": p["world"], "rep": task.rep, "true_start": start,
            "benign_invalid_rate": float(p.get("benign_invalid_rate", 0.0))}  # fmt: skip
    rows, bad = [], {}
    for fid, h in tr.histories.items():
        ftype = types[int(fid[1:]) % len(types)]
        for v in h.change_days:
            damaged = h.damaged_day is not None and v == h.damaged_day
            rows.append({**base, "file_type": ftype, "version": "damaged" if damaged
                         else ("day0" if v == 0 else "rewrite"),  # fmt: skip
                         "flagged": int(v in h.flagged_days)})
            if not damaged and v in h.flagged_days:
                bad.setdefault(fid, []).append(v)
    # clean snapshots (warm-up .. start - 1) holding >= 1 flagged (benign) version
    held = []
    for j in range(WARMUP, start):
        n = 0
        for fid, vs in bad.items():
            cur = max(d for d in tr.histories[fid].change_days if d <= j)
            n += cur in vs
        held.append(n > 0)
    snap = {**base, "clean_snapshots": len(held), "clean_snapshots_flagged": sum(held)}
    return rows, snap


def main(workers=5):
    OUT.mkdir(parents=True, exist_ok=True)
    vers, snaps = [], []
    for arm, path in ARMS.items():
        cfg = load_config(path)
        tasks = tasks_of(cfg)
        print(f"{arm}: {len(tasks)} machines", flush=True)
        res = run_tasks(count, tasks, workers=workers, init=_init, init_args=(cfg, arm),
                        cache_dir=OUT / f"machines_{arm}", task_key=lambda t: (t.params["world"],
                        t.rep, t.params["benign_invalid_rate"], t.params["attack_start"]))  # fmt: skip
        for rows, snap in res:
            vers += rows
            snaps.append(snap)
    v, s = pd.DataFrame(vers), pd.DataFrame(snaps)
    v.to_csv(OUT / "versions.csv.gz", index=False)
    s.to_csv(OUT / "clean_snapshots.csv", index=False)
    print("done", len(v), len(s))


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 5)
