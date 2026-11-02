"""D81 report (exploratory_dev_v3, DEV only): numbers, no interpretation.

Per arm and level: per policy mean work lost (whole-system hours), clean recovery and retained
unique bytes; SlowBurn against every other policy with the paired machine-cluster bootstrap of
``method_v2.policy_vs_policy`` (2000 resamples, seed 0), at matched count (count_K{K}) and at
matched bytes; the distribution of K'; infeasible, censored and unsupported cells; days at the cap.

Byte levels (multipliers of each machine's day-0 snapshot size; see LEVEL_DEFS):
* sbdaymed_K{K} (levels.json key sb_K{K}): median over all pooled calibration machine-days after
  warm-up (40 attack-free DEV machines x days; NOT a median over machines) of SlowBurn's daily
  retained unique bytes at count K / that machine's day-0 size;
* sbmax_K{K} (D81 addendum): median over the 40 calibration machines of each machine's max daily
  retained unique bytes at count K over every day of the run / day-0 size;
* keep30: the D46 keep-last 30-day footprint.

Checks the kill invariants: count-K rows reproduce the DEV v2 rows of the same machines, and no
selected run exceeds its budget (also asserted during the run).

    uv run python -m slowburn.bench.byte_matched_report
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from slowburn.bench import method_v2 as mv
from slowburn.bench.byte_matched import COUNTS, LABEL, LEVEL_KS, supported
from slowburn.bench.retention_experiment import make_policies

ROOT = Path("results/exploratory_dev_v3")
OUT = ROOT / "d81_report"
ARMS = {"napierone_bytes": ("d81_napierone", "results/dev_d72_bytes_napierone_v2pool"),
        "synthetic_bytes": ("d81_synthetic", "results/dev_d72_bytes_synthetic")}  # fmt: skip
WL, REC, UB = "work_lost_whole_system_hours", "clean_recovery", "retained_unique_bytes"
KEY = ["world", "benign_invalid_rate", "rep", "discovery_delay", "true_start", "policy"]
RENAME = {f"sb_K{K}": f"sbdaymed_K{K}" for K in LEVEL_KS}
LEVEL_DEFS = {
    "count_K{K}": "every policy at snapshot count K (the DEV v2 rows)",
    "sbdaymed_K{K}": "median over pooled calibration machine-days after warm-up of SlowBurn's "
    "daily retained unique bytes at count K / day-0 size (levels.json key sb_K{K})",
    "sbmax_K{K}": "median over calibration machines of SlowBurn's per machine max daily retained "
    "unique bytes at count K over every day / day-0 size (levels_sbmax.json)",
    "keep30": "D46 keep-last 30-day footprint / day-0 size",
}


def load(sub: str) -> pd.DataFrame:
    """The D81 rows with renamed levels, plus the sbmax addendum byte rows when present."""
    d = pd.read_csv(ROOT / sub / "d81_machines_rows.csv.gz", low_memory=False)
    d["d81_level"] = d.d81_level.replace(RENAME)
    f = ROOT / sub / "d81max_machines_rows.csv.gz"
    if f.exists():
        m = pd.read_csv(f, low_memory=False)
        d = pd.concat([d, m[m.d81_arm == "bytes"]], ignore_index=True)
    return d


def reproduce(d: pd.DataFrame, v2: str) -> dict:
    """Count-K rows against the DEV v2 rows of the same machines (kill invariant)."""
    old = pd.read_csv(Path(v2) / "tuning_sweep.csv", low_memory=False,
                      usecols=[*KEY, "budget", "budget_kind", "variant", WL, REC, UB])  # fmt: skip
    old = old[(old.budget_kind == "count") & (old.variant == "method_v2_w075_vsnap")]
    new = d[d.d81_arm == "count"]
    m = new[[*KEY, "budget", WL, REC, UB]].merge(old[[*KEY, "budget", WL, REC, UB]],
                                                  on=[*KEY, "budget"], how="left",
                                                  suffixes=("", "_v2"), indicator=True)  # fmt: skip
    same = {c: bool(np.allclose(m[c], m[f"{c}_v2"], equal_nan=True)) for c in (WL, REC, UB)}
    return {"rows": len(new), "matched": int((m._merge == "both").sum()), **same}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    cmp, pol, kp, inf, checks = [], [], [], [], {}
    for arm, (sub, v2) in ARMS.items():
        d = load(sub)
        checks[arm] = {"reproduces_dev_v2_count_rows": reproduce(d, v2)}
        b = d[d.d81_arm == "bytes"]
        over = b[~b.d81_infeasible & (b[UB] > b.d81_budget_bytes)]
        checks[arm]["selected_rows_over_budget"] = len(over)
        # one row per machine for K' / feasibility (K' does not depend on the delay)
        mach = b.drop_duplicates(["d81_level", *[k for k in KEY if k != "discovery_delay"]])
        g = mach.groupby(["d81_level", "policy"])
        feas = {"machines": ("d81_infeasible", "size"), "infeasible": ("d81_infeasible", "sum"),
                "censored_at_24": ("d81_censored", "sum"),
                "machines_with_days_at_cap": ("d81_days_at_cap", lambda s: int((s > 0).sum())),
                "days_at_cap_mean": ("d81_days_at_cap", "mean")}  # fmt: skip
        inf.append(g.agg(**feas).reset_index().assign(arm=arm))
        kp.append(mach[~mach.d81_infeasible].groupby(["d81_level", "policy"]).d81_kprime
                  .value_counts().rename("machines").reset_index().assign(arm=arm))  # fmt: skip
        # pairing frame: budget := level, so policies pair across their own K'
        x = d[~d.d81_infeasible.astype(bool)].copy()
        x["budget"] = x.d81_level
        x["budget_kind"] = x.d81_arm
        per = {"rows": (WL, "size"), "work_lost_h": (WL, "mean"), "recovery": (REC, "mean"),
               "retained_mib": (UB, lambda s: s.mean() / 2**20),
               "kprime_mean": ("d81_kprime", "mean")}  # fmt: skip
        pol.append(x.groupby(["d81_level", "policy"]).agg(**per).reset_index().assign(arm=arm))
        for lev in sorted(x.d81_level.unique()):
            xl = x[x.d81_level == lev]
            for base in sorted(set(xl.policy) - {"slowburn"}):
                r = mv.policy_vs_policy(xl, "slowburn", base)
                cmp.append(r.assign(arm=arm, d81_level=lev))
        sbk = mach[(mach.policy == "slowburn") & mach.d81_level.str.startswith("sb")]
        checks[arm]["slowburn_kprime_vs_K"] = {
            lev: {"machines": len(g), "infeasible": int(g.d81_infeasible.sum()),
                  "kprime_eq_K": int((g.d81_kprime == int(lev.split("K")[1])).sum()),
                  "kprime_ge_K": int((g.d81_kprime >= int(lev.split("K")[1])).sum())}
            for lev, g in sbk.groupby("d81_level")}  # fmt: skip
        for pref in ("count_K", "sbdaymed_K", "sbmax_K"):  # pooled over the four levels
            xp = x[x.d81_level.isin([f"{pref}{K}" for K in LEVEL_KS])]
            if xp.empty:
                continue
            for base in sorted(set(xp.policy) - {"slowburn"}):
                r = mv.policy_vs_policy(xp, "slowburn", base)
                cmp.append(r.assign(arm=arm, d81_level=f"{pref}pooled"))
    P = make_policies(_hp(), 0.0)
    unsup = {nm: [c for c in COUNTS if not supported(P[nm], c)] for nm in P if nm in _policies()}
    pd.concat(cmp, ignore_index=True).to_csv(OUT / "slowburn_vs_policy.csv", index=False)
    pd.concat(pol, ignore_index=True).to_csv(OUT / "per_policy.csv", index=False)
    pd.concat(kp, ignore_index=True).to_csv(OUT / "kprime_distribution.csv", index=False)
    pd.concat(inf, ignore_index=True).to_csv(OUT / "feasibility.csv", index=False)
    info = {"label": LABEL, "level_definitions": LEVEL_DEFS, **checks,
            "unsupported_counts": unsup}  # fmt: skip
    (OUT / "checks.json").write_text(json.dumps(info, indent=1))
    print(json.dumps(checks, indent=1))


def _policies() -> list[str]:
    from slowburn.utils.config import load_config

    return list(load_config("configs/dev_v3_d81_synthetic.yaml")["policies"])


def _hp() -> dict:
    from slowburn.bench.byte_matched import base_hp
    from slowburn.utils.config import load_config

    return base_hp(load_config("configs/dev_v3_d81_synthetic.yaml"))


if __name__ == "__main__":
    main()
