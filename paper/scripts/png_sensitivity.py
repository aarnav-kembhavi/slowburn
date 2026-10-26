"""Truncated-png sensitivity row (OPEN_QUESTIONS, team decision 2026-10-25; UNSCORED): the D67
NapierOne arm on pool v2_notrunc (v2 minus the 9 truncated pngs) next to v2. Same seeds,
machines, grid and detector. Run from the repo root:

    uv run python paper/scripts/png_sensitivity.py
"""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import d75_compare as d75  # noqa: E402

OUT = Path("results/dev_png_sensitivity")
RUNS = {"v2": "results/dev_d67_full_napierone_v2pool",
        "v2_notrunc (unscored)": "results/dev_d67_full_napierone_v2notrunc"}  # fmt: skip


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    claims, c1 = [], []
    for pool, run in RUNS.items():
        a, b = d75.d67(pool, run)
        claims.append(a)
        c1.append(b)
    claims = pd.concat(claims, ignore_index=True)
    claims.to_csv(OUT / "claims_v2_vs_notrunc.csv", index=False)
    pd.concat(c1, axis=1).to_csv(OUT / "c1_recovery_v2_vs_notrunc.csv")
    print(pd.concat(c1, axis=1).round(4).to_string())
    cols = [c for c in ("pool", "claim", "vs", "pairs", "recovery_diff", "work_lost_rel",
                        "work_lost_rel_lo", "work_lost_rel_hi", "rel_change", "rel_lo", "rel_hi")
            if c in claims.columns]  # fmt: skip
    print(claims[cols].round(4).to_string(index=False))


if __name__ == "__main__":
    main()
