"""D80 report (OPEN_QUESTIONS D80): C2 with the D78-accepted detector next to the scored v2 rows
(SlowBurn vs the six baselines, NapierOne v2 with the truncated pngs kept, paired machine-cluster
bootstrap, Holm across the six), plus the held-out alarm row at c = 3 with the new detector
(secondary). Run from the repo root:

    uv run python paper/scripts/d80_report.py
"""

import json
import sys
from pathlib import Path

import pandas as pd

from slowburn.bench import method_v2 as mv
from slowburn.bench.stats import holm

sys.path.insert(0, str(Path(__file__).parent))
from d72_c2r_holm import BASES, WL, boot_p  # noqa: E402

OUT = Path("results/dev_d80_report")
RUNS = {"scored v2 (unchanged detector)": "results/dev_d72_bytes_napierone_v2pool",
        "D78 detector": "results/dev_d80_c2_napierone"}  # fmt: skip


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    for label, run in RUNS.items():
        d = pd.read_csv(Path(run) / "tuning_sweep.csv", low_memory=False)
        d = d[(d.variant == "method_v2_w075_vsnap") & (d.budget_kind == "count")]
        key = [k for k in mv._row_key(d) if k != "policy"]
        part = []
        for base in BASES:
            r = mv.policy_vs_policy(d, "slowburn", base).assign(detector=label)
            xa, xb = (d[d.policy == p][[*key, WL]] for p in ("slowburn", base))
            r["p_boot"] = boot_p(xa.merge(xb, on=key, suffixes=("_a", "_b")))
            part.append(r)
        part = pd.concat(part, ignore_index=True)
        part["p_holm"] = holm(part.p_boot.to_numpy())
        rows.append(part)
    c = pd.concat(rows, ignore_index=True)
    c.to_csv(OUT / "c2_side_by_side.csv", index=False)
    cols = ["detector", "vs", "pairs", "work_lost_rel", "work_lost_rel_lo", "work_lost_rel_hi",
            "recovery_diff", "recovery_diff_lo", "recovery_diff_hi", "p_holm"]
    print(c[cols].round(4).to_string(index=False))
    h = Path("results/dev_d80_alarm_holdout/holdout.json")
    if h.exists():
        print("== held-out alarm at c = 3, D78 detector (secondary)")
        print(json.dumps(json.loads(h.read_text()), indent=1))


if __name__ == "__main__":
    main()
