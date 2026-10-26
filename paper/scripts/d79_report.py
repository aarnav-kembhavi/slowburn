"""D79 report (OPEN_QUESTIONS D79): SlowBurn with its maximum retention age capped at the
equal-horizon baseline's held age vs that baseline. Primary: slowburn_age_gfs vs gfs_eqh (K 12),
slowburn_age_toh vs toh_eqh (K 8 and 12 pooled); Holm across the two per arm; NapierOne v2
decides, synthetic reported. Same paired machine-cluster bootstrap as d72_c2r_holm. Also the
sanity check (slowburn / eqh rows reproduce D72) and secondary rows. Run from the repo root:

    uv run python paper/scripts/d79_report.py
"""

import sys
from pathlib import Path

import pandas as pd

from slowburn.bench import method_v2 as mv
from slowburn.bench.stats import holm

sys.path.insert(0, str(Path(__file__).parent))
from d72_c2r_holm import WL, boot_p  # noqa: E402

OUT = Path("results/dev_d79_report")
ARMS = {"napierone_bytes": ("results/dev_d79_eqh_napierone",
                            "results/dev_d72_bytes_napierone_v2pool"),
        "synthetic_bytes": ("results/dev_d79_eqh_synthetic", "results/dev_d72_bytes_synthetic")}
PRIMARY = (("slowburn_age_gfs", "gfs_eqh"), ("slowburn_age_toh", "toh_eqh"))
SECONDARY = (("slowburn", "gfs_eqh"), ("slowburn", "toh_eqh"),
             ("slowburn_age_gfs", "slowburn"), ("slowburn_age_toh", "slowburn"))  # fmt: skip
pd.set_option("display.width", 250, "display.max_columns", 30)


def load(run: str) -> pd.DataFrame:
    d = pd.read_csv(Path(run) / "tuning_sweep.csv", low_memory=False)
    return d[(d.variant == "method_v2_w075_vsnap") & (d.budget_kind == "count")]


def compare(d: pd.DataFrame, a: str, b: str, by=()) -> pd.DataFrame:
    key = [k for k in mv._row_key(d) if k != "policy"]
    r = mv.policy_vs_policy(d, a, b, by)
    if not by:
        xa, xb = (d[d.policy == p][[*key, WL]] for p in (a, b))
        r["p_boot"] = boot_p(xa.merge(xb, on=key, suffixes=("_a", "_b")))
    return r


def sanity(d: pd.DataFrame, old: pd.DataFrame) -> dict:
    k = [c for c in ("world", "rep", "true_start", "benign_invalid_rate", "discovery_delay",
                     "budget", "policy", "variant") if c in d.columns]  # fmt: skip
    pol = ["slowburn", "gfs_eqh", "toh_eqh"]
    m = d[d.policy.isin(pol)].merge(old[old.policy.isin(pol)], on=k, suffixes=("_n", "_o"))
    same = (m[f"{WL}_n"].fillna(-1) == m[f"{WL}_o"].fillna(-1)) & (
        m.clean_recovery_n == m.clean_recovery_o)
    return {"rows": int(d.policy.isin(pol).sum()), "matched": len(m), "identical": int(same.sum())}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    prim, sec, by, checks = [], [], [], {}
    for arm, (run, d72) in ARMS.items():
        if not (Path(run) / "tuning_sweep.csv").exists():
            print(f"{arm}: no output yet ({run})")
            continue
        d = load(run)
        checks[arm] = sanity(d, load(d72))
        part = pd.concat([compare(d, a, b).assign(arm=arm) for a, b in PRIMARY], ignore_index=True)
        part["p_holm"] = holm(part.p_boot.to_numpy())
        part["success"] = ((part.work_lost_rel_hi < 0) & (part.p_holm < 0.05)
                           & (part.recovery_diff_lo >= -0.02))  # fmt: skip
        prim.append(part)
        sec += [compare(d, a, b).assign(arm=arm) for a, b in SECONDARY]
        sec += [compare(d, b, a).assign(arm=arm, direction="baseline vs variant")
                for a, b in PRIMARY]  # fmt: skip
        by += [compare(d, a, b, (g,)).assign(arm=arm) for a, b in PRIMARY
               for g in ("world", "budget")]  # fmt: skip
    if not prim:
        return
    cols = ["arm", "policy", "vs", "pairs", "work_lost_rel", "work_lost_rel_lo",
            "work_lost_rel_hi", "recovery_diff", "recovery_diff_lo", "recovery_diff_hi"]
    p = pd.concat(prim, ignore_index=True)
    p.to_csv(OUT / "primary.csv", index=False)
    s = pd.concat(sec, ignore_index=True)
    s.to_csv(OUT / "secondary.csv", index=False)
    b = pd.concat(by, ignore_index=True)
    b.to_csv(OUT / "by_world_budget.csv", index=False)
    print("== sanity: slowburn / eqh rows vs D72", checks)
    print("== primary (Holm across the two per arm; success = wl upper CI < 0, Holm p < 0.05,"
          " recovery lower CI >= -0.02)")
    print(p[cols + ["p_boot", "p_holm", "success"]].round(4).to_string(index=False))
    print("== secondary (unadjusted)")
    print(s[cols + ["p_boot"]].round(4).to_string(index=False))
    print("== by world / budget (secondary, unadjusted)")
    print(b[[c for c in ["arm", "policy", "vs", "world", "budget", "pairs"] if c in b] + cols[4:]]
          .round(4).to_string(index=False))  # fmt: skip


if __name__ == "__main__":
    main()
