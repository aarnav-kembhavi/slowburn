"""D74 held-out alarm check (OPEN_QUESTIONS 2026-10-25): score the fixed c from
results/dev_d74_alarm_calib/threshold.json once on 100 new benign runs per arm (family
"d74_alarm_holdout"). c is never changed here. DEV only. Run from the repo root:

    uv run python paper/scripts/d74_alarm_holdout.py configs/dev_d74_attack_napierone.yaml ...
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from d74_alarm_calib import N_MACHINES, _init, counts  # same window and simulation
from scipy.stats import beta

from slowburn.bench.parallel import run_tasks
from slowburn.utils.config import load_config

OUT = Path("results/dev_d74_alarm_holdout")
FAMILY = "d74_alarm_holdout"


def exact_ci(x: int, n: int) -> tuple[float, float]:
    """Clopper-Pearson 95% interval."""
    lo = 0.0 if x == 0 else float(beta.ppf(0.025, x, n - x + 1))
    hi = 1.0 if x == n else float(beta.ppf(0.975, x + 1, n - x))
    return lo, hi


def score(k: np.ndarray, c: int) -> dict:
    runs, days = (k.max(axis=1) >= c), (k >= c)
    pr, pd_ = exact_ci(int(runs.sum()), runs.size), exact_ci(int(days.sum()), days.size)
    p_day = float(days.mean())
    return {"c": c, "runs": int(runs.size), "run_alarms": int(runs.sum()),
            "per_run_false_alarm": float(runs.mean()), "per_run_ci95": pr,
            "machine_days": int(days.size), "day_alarms": int(days.sum()), "p_day": p_day,
            "p_day_upper95": pd_[1],
            "fleet_false_alarms_per_week": {N: 7 * N * p_day for N in (20, 100)},
            "fleet_false_alarms_per_week_upper95": {N: 7 * N * pd_[1]
                                                    for N in (20, 100)}}  # fmt: skip


def main(paths):
    OUT.mkdir(parents=True, exist_ok=True)
    thr = json.loads(Path("results/dev_d74_alarm_calib/threshold.json").read_text())
    res = {}
    for path in paths:
        cfg = load_config(path)
        arm = cfg["attack"]["arm"]
        rows = run_tasks(counts, list(range(N_MACHINES)), workers=int(cfg.get("workers", 5)),
                         init=_init, init_args=(cfg, FAMILY),
                         cache_dir=OUT / f"machines_{arm}")  # fmt: skip
        k = np.array(rows)
        pd.DataFrame(k).to_csv(OUT / f"daily_counts_{arm}.csv.gz", index=False)
        res[arm] = score(k, int(thr[arm]["c"]))
        print(arm, json.dumps(res[arm]), flush=True)
    (OUT / "holdout.json").write_text(json.dumps(res, indent=1))


if __name__ == "__main__":
    main(sys.argv[1:])
