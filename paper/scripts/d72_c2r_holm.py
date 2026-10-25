"""C2 wording (team request 2026-10-26): SlowBurn vs each of the six baselines, pooled, with the
same paired machine-cluster bootstrap as d72_c2r_report.py (2000 resamples, seed 0) plus a
two-sided bootstrap p-value for relative work lost and Holm across the six baselines per arm.
Reads the D72 byte-arm outputs; no new simulation. Run from the repo root:

    uv run python paper/scripts/d72_c2r_holm.py
"""

from pathlib import Path

import numpy as np
import pandas as pd

from slowburn.bench import method_v2 as mv
from slowburn.bench.figures import holm

OUT = Path("results/dev_d72_c2r")
ARMS = {"napierone_bytes": "results/dev_d72_bytes_napierone_v2pool",
        "synthetic_bytes": "results/dev_d72_bytes_synthetic",
        "napierone_bytes_v1pool": "results/dev_d72_bytes_napierone"}  # fmt: skip
BASES = ("gfs_eqh", "toh_eqh", "gfs", "tower_of_hanoi", "shamir_recursive", "shamir_rr")
WL, N_BOOT = "work_lost_whole_system_hours", 2000


def boot_p(x: pd.DataFrame) -> float:
    """Two-sided percentile p for sum(a - b) / sum(b) = 0, same resamples as the CI."""
    num, den = x[f"{WL}_a"] - x[f"{WL}_b"], x[f"{WL}_b"]
    codes = np.unique(mv._clusters(x), return_inverse=True)[1].ravel()
    n = int(codes.max()) + 1
    s_num, s_den = np.bincount(codes, num, n), np.bincount(codes, den, n)
    w = np.random.default_rng(0).multinomial(n, np.full(n, 1 / n), size=N_BOOT)
    b = (w @ s_num) / (w @ s_den)
    return float(min(1.0, 2 * min((b <= 0).mean(), (b >= 0).mean())))


def main():
    rows = []
    for arm, run in ARMS.items():
        d = pd.read_csv(Path(run) / "tuning_sweep.csv", low_memory=False)
        d = d[(d.variant == "method_v2_w075_vsnap") & (d.budget_kind == "count")]
        key = [k for k in mv._row_key(d) if k != "policy"]
        part = []
        for base in BASES:
            r = mv.policy_vs_policy(d, "slowburn", base).assign(arm=arm)
            xa, xb = (d[d.policy == p][[*key, WL]] for p in ("slowburn", base))
            r["p_boot"] = boot_p(xa.merge(xb, on=key, suffixes=("_a", "_b")))
            part.append(r)
        part = pd.concat(part, ignore_index=True)
        part["p_holm"] = holm(part.p_boot.to_numpy())
        part["significant_holm_05"] = part.p_holm < 0.05
        rows.append(part)
    c = pd.concat(rows, ignore_index=True)
    c.to_csv(OUT / "c2_holm.csv", index=False)
    cols = ["arm", "vs", "pairs", "work_lost_rel", "work_lost_rel_lo", "work_lost_rel_hi",
            "recovery_diff", "recovery_diff_lo", "recovery_diff_hi", "p_boot", "p_holm"]
    print(c[cols].round(4).to_string(index=False))


if __name__ == "__main__":
    main()
