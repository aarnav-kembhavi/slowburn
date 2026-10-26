"""D78 recount (implementation notes): the D71 version recount on the D67 NapierOne grid at
injected benign rate 0 with one pool ("v2fix" or "v2check") and one candidate detector
(results/dev_d78/detectors/<name>.pkl). Each row: (world, rep, true_start, file, day, type,
version kind, flagged). Run from the repo root:

    uv run python paper/scripts/d78_recount.py <pool> <detector> [<detector> ...]
"""

import sys
from pathlib import Path

import pandas as pd

from slowburn.bench.parallel import run_tasks
from slowburn.bench.retention_experiment import simulate
from slowburn.utils.config import load_config

sys.path.insert(0, str(Path(__file__).parent))
from d71_false_flags import tasks_of  # noqa: E402

BASE = "configs/dev_d67_full_napierone_v2pool.yaml"
DET = Path("results/dev_d78/detectors")
OUT = Path("results/dev_d78")
_W: dict = {}


def _init(cfg):
    _W["cfg"] = cfg


def count(task):
    cfg = _W["cfg"]
    tr = simulate(cfg, task)
    types = cfg["scenario"]["file_types"]
    p = task.params
    base = {"world": p["world"], "rep": task.rep, "true_start": int(p["attack_start"])}
    rows = []
    for fid, h in tr.histories.items():
        ftype = types[int(fid[1:]) % len(types)]
        for v in h.change_days:
            damaged = h.damaged_day is not None and v == h.damaged_day
            rows.append({**base, "file_id": fid, "day": v, "file_type": ftype,
                         "version": "damaged" if damaged else ("day0" if v == 0 else "rewrite"),
                         "flagged": int(v in h.flagged_days)})  # fmt: skip
    return rows


def main(pool, names, workers=5):
    for name in names:
        cfg = load_config(BASE)
        cfg["scenario"] = {**cfg["scenario"], "napierone_pool": pool,
                           "detector_path": str(DET / f"{name}.pkl")}  # fmt: skip
        cfg["sweep"] = {"benign_invalid_rate": [0.0]}
        tasks = tasks_of(cfg)
        print(f"{pool} {name}: {len(tasks)} machines", flush=True)
        res = run_tasks(count, tasks, workers=workers, init=_init, init_args=(cfg,),
                        cache_dir=OUT / f"machines_{pool}_{name}",
                        task_key=lambda t: (t.params["world"], t.rep))  # fmt: skip
        df = pd.DataFrame([r for rows in res for r in rows])
        df.to_csv(OUT / f"recount_{pool}_{name}.csv.gz", index=False)
        print(name, len(df), "versions", flush=True)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2:])
