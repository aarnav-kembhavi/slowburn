"""E1 overhead (OPEN_QUESTIONS 2026-11-01, exploratory; no data): SlowBurn's retention decision
(PosteriorDP with the frozen penalty 90, gate 0.8, backbone 0.25) replayed online for 400 days
on a uniform start prior conditioned on "not discovered yet", for K in {4, 6, 8, 12, 16, 24} and
assumed discovery bound M in {30, 60, 120, 365}; GFS and Tower of Hanoi at the same K for
reference. Per replay: median and 95th percentile wall time per daily decision over days 30 to
399, and peak traced Python memory (tracemalloc, a separate replay so tracing does not inflate the
timings). Run from the repo root:

    uv run python paper/scripts/overhead.py
"""

import json
import os
import platform
import time
import tracemalloc
from pathlib import Path

import numpy as np
import pandas as pd

from slowburn.retention.base import GFS, PosteriorDP, RetentionContext, TowerOfHanoi
from slowburn.retention.dp import discovery_survival, retention_posterior

OUT = Path("results/exploratory/overhead")
KS, MS, DAYS, FROM = (4, 6, 8, 12, 16, 24), (30, 60, 120, 365), 400, 30
P_STARTED = 0.5  # prior mass on "the attack started within the history"


def context(day: int, held: dict[int, int], K: int, S) -> RetentionContext:
    post = np.r_[np.full(day + 1, P_STARTED / (day + 1)), 1 - P_STARTED]
    pi = retention_posterior(post, day, S)
    return RetentionContext(day=day, snapshot_days=dict(held), budget=K,
                            daily_stat=np.zeros(day + 1), start_posterior=post,
                            retention_pi=pi, prior_retention_pi=pi)  # fmt: skip


def replay(policy, K: int, M: int, trace: bool = False) -> tuple[list[float], float]:
    S = discovery_survival("uniform", M)
    held, times = {}, []
    if trace:
        tracemalloc.start()
    for day in range(DAYS):
        held[day] = day
        ctx = context(day, held, K, S)
        t0 = time.perf_counter()
        keep = policy.decide(ctx)
        times.append(time.perf_counter() - t0)
        held = {sid: held[sid] for sid in keep}
    peak = tracemalloc.get_traced_memory()[1] / 2**20 if trace else float("nan")
    if trace:
        tracemalloc.stop()
    return times, peak


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    policies = {"slowburn": lambda: PosteriorDP(90.0, gate=0.8, backbone=0.25),
                "gfs": GFS, "tower_of_hanoi": TowerOfHanoi}  # fmt: skip
    for name, make in policies.items():
        for K in KS:
            for M in MS if name == "slowburn" else (60,):  # fixed schedules ignore M
                times, _ = replay(make(), K, M)
                _, peak = replay(make(), K, M, trace=True)
                t = 1e3 * np.array(times[FROM:])
                rows.append({"policy": name, "K": K, "M": M, "days": DAYS,
                             "ms_median": float(np.median(t)),
                             "ms_p95": float(np.percentile(t, 95)), "ms_max": float(t.max()),
                             "peak_traced_mib": peak})  # fmt: skip
                print(rows[-1], flush=True)
    pd.DataFrame(rows).to_csv(OUT / "overhead.csv", index=False)
    (OUT / "machine.json").write_text(json.dumps({
        "platform": platform.platform(), "processor": platform.processor(),
        "python": platform.python_version(), "cpu_count": os.cpu_count()}, indent=1))  # fmt: skip


if __name__ == "__main__":
    main()
