"""D74 amendment: calibrate the daily flagged-file count alarm on attack-free machines that the
attack evaluation never uses (family "d74_alarm_calib"). DEV only. Run from the repo root:

    uv run python paper/scripts/d74_alarm_calib.py configs/dev_d74_attack_synthetic.yaml ...
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from slowburn.bench.parallel import run_tasks
from slowburn.bench.registry import machine_key
from slowburn.fleet.machine import MachineSim
from slowburn.utils.config import load_config

N_MACHINES, WARMUP, WINDOW, TARGET = 100, 14, 120, 0.05
OUT = Path("results/dev_d74_alarm_calib")
_W: dict = {}


def _init(cfg):
    _W["cfg"] = cfg


def counts(i: int) -> list[int]:
    cfg = _W["cfg"]
    p = {**cfg["scenario"], "attack_start": None,
         "benign_invalid_rate": float(cfg["attack"]["benign_invalid_rate"])}  # fmt: skip
    key = machine_key(int(cfg["seed"]), "dev", "d74_alarm_calib",
                      {"data_source": p.get("data_source", "synthetic")}, i)  # fmt: skip
    sim = MachineSim(cfg, p, key, WARMUP + WINDOW).run_to(WARMUP + WINDOW)
    return [o.k for o in sim.obs[WARMUP:]]


def calibrate(k: np.ndarray) -> dict:
    """Smallest c with P(run max >= c) <= TARGET; per-run and per-day rates at c."""
    mx = k.max(axis=1)
    c = next(c for c in range(1, int(mx.max()) + 2) if (mx >= c).mean() <= TARGET)
    p_day = float((k >= c).mean())
    return {"c": c, "per_run_false_alarm": float((mx >= c).mean()), "p_day": p_day,
            "fleet_false_alarms_per_week": {N: 7 * N * p_day for N in (20, 100)},
            "runs": int(len(mx)), "run_days": WINDOW,
            "max_count_quantiles": {q: float(np.quantile(mx, q)) for q in (0.5, 0.9, 0.95, 0.99)},
            "per_run_rate_by_c": {c_: float((mx >= c_).mean())
                                  for c_ in range(1, int(mx.max()) + 2)}}  # fmt: skip


def main(paths):
    OUT.mkdir(parents=True, exist_ok=True)
    res = {}
    for path in paths:
        cfg = load_config(path)
        arm = cfg["attack"]["arm"]
        cache = OUT / f"machines_{arm}"
        rows = run_tasks(counts, list(range(N_MACHINES)), workers=int(cfg.get("workers", 5)),
                         init=_init, init_args=(cfg,), cache_dir=cache)  # fmt: skip
        k = np.array(rows)
        pd.DataFrame(k).to_csv(OUT / f"daily_counts_{arm}.csv.gz", index=False)
        res[arm] = calibrate(k)
        print(arm, json.dumps(res[arm]), flush=True)
    (OUT / "threshold.json").write_text(json.dumps(res, indent=1))


if __name__ == "__main__":
    main(sys.argv[1:])
