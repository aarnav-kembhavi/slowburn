"""D78 power check (team request 2026-10-26, before any D78 fix code): can criteria 1 and 2 be
passed at the CHECK-half sample sizes? Uses the D71 v2-pool recount (same D67 NapierOne grid and
seeds as the D78 recount; version counts are set by the grid, not the pool), injected rate 0.
No detector is changed and nothing is simulated. Run from the repo root:

    uv run python paper/scripts/d78_power.py
"""

from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import beta

from slowburn.bench.stats import cluster_bootstrap_ratio

OUT = Path("results/dev_d78_power")
N_SIM, DISCORD, MARGIN = 200, (0.0, 0.05, 0.10, 0.20), -0.02


def cp_upper(k: int, n: int) -> float:
    return float(beta.ppf(0.95 if k == 0 else 0.975, k + 1, n - k)) if k < n else 1.0


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    v = pd.read_csv("results/dev_d71_false_flags/versions.csv.gz")
    v = v[(v.arm == "napierone_v2pool") & (v.benign_invalid_rate == 0)].copy()
    v["cl"] = v.world + "|" + v.rep.astype(str) + "|" + v.true_start.astype(str)
    sizes = v.groupby(["file_type", "version"]).flagged.agg(["size", "sum"]).unstack()
    sizes.to_csv(OUT / "sizes.csv")
    print(sizes.to_string())

    rw = v[v.version == "rewrite"]
    rows = [{"scope": "overall", "n": len(rw)}] + [
        {"scope": t, "n": int(n)} for t, n in rw.groupby("file_type").size().items()]
    b = pd.DataFrame(rows)
    for k in (0, 1, 2):
        b[f"cp_upper95_k{k}"] = [cp_upper(k, n) for n in b.n]
    b["max_flags_point_le_0.005"] = (0.005 * b.n).astype(int)
    b.to_csv(OUT / "criterion1_bounds.csv", index=False)
    print(b.to_string(index=False))

    # Criterion 2 null: a candidate with the same true detection rate as the unchanged detector
    # whose decision on each damaged version is redrawn (Bernoulli at the type rate) with
    # probability d; d = 0 is the unchanged detector against itself.
    rng = np.random.default_rng(78)
    dm, out = v[v.version == "damaged"], []
    for t, x in dm.groupby("file_type"):
        f, p = x.flagged.to_numpy(float), x.flagged.mean()
        for d in DISCORD:
            fails = 0
            for s in range(N_SIM):
                redraw = rng.random(len(f)) < d
                g = np.where(redraw, rng.random(len(f)) < p, f).astype(float)
                lo = cluster_bootstrap_ratio(g - f, np.ones(len(f)), x.cl, seed=s)[1]
                fails += lo < MARGIN
            out.append({"file_type": t, "n_damaged": len(f), "detection": p, "discordance": d,
                        "fail_rate_criterion2": fails / N_SIM})  # fmt: skip
    o = pd.DataFrame(out)
    o.to_csv(OUT / "criterion2_null.csv", index=False)
    print(o.pivot(index="file_type", columns="discordance", values="fail_rate_criterion2"))
    print("types failing (any sim) per d:", o.assign(f=o.fail_rate_criterion2 > 0)
          .groupby("discordance").f.sum().to_dict())  # fmt: skip
    print("expected types failing per d:", o.groupby("discordance").fail_rate_criterion2.sum()
          .round(2).to_dict())  # fmt: skip



def pooled_null(n_sim: int = N_SIM, n_boot: int = 2000):
    """Proposed amendment check: uniform type mean of the paired difference with one shared
    machine-cluster bootstrap (lower CI >= -0.02), and the per-type point guard (>= -0.05)."""
    v = pd.read_csv("results/dev_d71_false_flags/versions.csv.gz")
    v = v[(v.arm == "napierone_v2pool") & (v.benign_invalid_rate == 0) & (v.version == "damaged")]
    cl = (v.world + "|" + v.rep.astype(str) + "|" + v.true_start.astype(str)).to_numpy()
    codes = np.unique(cl, return_inverse=True)[1].ravel()
    n_cl, types = int(codes.max()) + 1, sorted(v.file_type.unique())
    rng = np.random.default_rng(79)
    out = []
    for d in DISCORD:
        lo_fail = guard_fail = 0
        for s in range(n_sim):
            w = np.random.default_rng(s).multinomial(n_cl, np.full(n_cl, 1 / n_cl), size=n_boot)
            means, points = [], []
            for t in types:
                m = (v.file_type == t).to_numpy()
                f, c = v.flagged.to_numpy(float)[m], codes[m]
                g = np.where(rng.random(len(f)) < d, rng.random(len(f)) < f.mean(), f)
                sn, sc = np.bincount(c, g - f, n_cl), np.bincount(c, None, n_cl)
                means.append((w @ sn) / (w @ sc))
                points.append((g - f).mean())
            lo_fail += np.quantile(np.mean(means, axis=0), 0.025) < MARGIN
            guard_fail += min(points) < -0.05
        out.append({"discordance": d, "pooled_fail_rate": lo_fail / n_sim,
                    "guard_fail_rate": guard_fail / n_sim})  # fmt: skip
    o = pd.DataFrame(out)
    o.to_csv(OUT / "criterion2_pooled_null.csv", index=False)
    print(o.to_string(index=False))


if __name__ == "__main__":
    main()
    pooled_null()
