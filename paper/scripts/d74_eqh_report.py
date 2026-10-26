"""D74 eqh arm report (OPEN_QUESTIONS 2026-10-26, descriptive): the D74 NapierOne rows plus the
equal-horizon rows from the same machines and seeds, through the unchanged D74 report code.
Run from the repo root after both runs:

    uv run python paper/scripts/d74_eqh_report.py
"""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import d74_report  # noqa: E402

RUNS = ["results/dev_d74_attack_napierone", "results/dev_d74_attack_napierone_eqh"]
MERGED = Path("results/dev_d74_eqh_combined")
OUT = Path("results/dev_d74_eqh_report")


def main():
    MERGED.mkdir(parents=True, exist_ok=True)
    d = pd.concat([pd.read_csv(Path(r) / "attack_rows.csv.gz", low_memory=False) for r in RUNS],
                  ignore_index=True)  # fmt: skip
    d.to_csv(MERGED / "attack_rows.csv.gz", index=False)
    d74_report.main(arms={"napierone_bytes": str(MERGED)}, out=OUT)
    br = pd.read_csv(OUT / "best_response.csv")
    br = br[(br.restore == "A") & (br.analysis == "primary_feasible") & (br.objective == "rec")]
    print("== recovery vs delay, best response (recovery-minimising), restore A")
    print(br.pivot_table(index=["policy", "budget"], columns="discovery_delay",
                         values="eval_rec").round(2).to_string())  # fmt: skip


if __name__ == "__main__":
    main()
