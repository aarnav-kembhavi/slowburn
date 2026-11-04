"""D90 limitation test report (OPEN_QUESTIONS 2026-11-04; exploratory_dev_v3, DEV only).

Threshold-aware attacker (flag cap 2) against the N3 restore, on the D90 runs
(``d81_{arm}/d90_machines_rows.csv.gz``). No success or kill criterion. Tables:
* checks: every D90 machine is in the ed3f273 check half; retention identical N1 vs N3;
* per policy, pooled and per cell (arm x level x rate): absolute work lost and recovery at N1
  and N3 (machine-cluster bootstrap CIs) and N3 vs N1 (method_v2.policy_vs_policy);
* reference: the D89 honest-attacker check-half rows for the same policies, cells and rules;
* attacker flags kept / removed per machine.

    uv run python -m slowburn.bench.d90_report
"""

from __future__ import annotations

import json

import pandas as pd

from slowburn.bench import method_v2 as mv
from slowburn.bench.byte_matched import D90_POLICIES, D90_RATES, LABEL
from slowburn.bench.byte_matched_report import REC, ROOT, WL
from slowburn.bench.d82_precheck import halves
from slowburn.bench.d89_report import KEY, RET, _pairframe
from slowburn.bench.d89_report import load as load_d89
from slowburn.bench.stats import cluster_bootstrap_ratio

OUT = ROOT / "d90_report"
ARMS = ("napierone", "synthetic")
CELLS = ("sbmax_K8", "sbmax_K12")
RULES = ("N1", "N3")
CELL = ["arm_name", "d81_level", "benign_invalid_rate"]


def load(arm: str) -> pd.DataFrame:
    d = pd.read_csv(ROOT / f"d81_{arm}" / "d90_machines_rows.csv.gz", low_memory=False)
    return d[d.policy.isin(D90_POLICIES) & d.d81_level.isin(CELLS)].assign(arm_name=arm)


def _cl(x: pd.DataFrame) -> pd.Series:
    return (x.arm_name + "|" + x.world.astype(str) + "|" + x.true_start.astype(str) + "|"
            + x.rep.astype(str))  # fmt: skip


def absolute(x: pd.DataFrame, by: list[str], source: str) -> pd.DataFrame:
    rows = []
    x = x.assign(cl=_cl(x))
    for (rule, pol, *g), y in x.groupby(["d89_rule", "policy", *by]):
        wl = cluster_bootstrap_ratio(y[WL], [1] * len(y), y.cl)
        rc = cluster_bootstrap_ratio(y[REC], [1] * len(y), y.cl)
        rows.append({"source": source, "rule": rule, "policy": pol,
                     **dict(zip(by, g, strict=True)), "rows": len(y), "work_lost_h": wl[0],
                     "wl_lo": wl[1], "wl_hi": wl[2], "recovery": rc[0], "rec_lo": rc[1],
                     "rec_hi": rc[2]})  # fmt: skip
    return pd.DataFrame(rows)


def n3_vs_n1(x: pd.DataFrame, by: list[str], source: str) -> pd.DataFrame:
    out = []
    for (pol, *g), y in x.groupby(["policy", *by]):
        r = mv.policy_vs_policy(_pairframe(y, True), "N3", "N1")
        out.append(r.assign(source=source, pol=pol, **dict(zip(by, g, strict=True))))
    return pd.concat(out, ignore_index=True)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    d = pd.concat([load(a) for a in ARMS], ignore_index=True)
    ref = pd.concat([load_d89(a) for a in ARMS], ignore_index=True)
    h = halves(ref)
    ref["half"] = [h[k] for k in zip(ref.world, ref.true_start, ref.rep, strict=True)]
    halves_d90 = {h.get(k) for k in zip(d.world, d.true_start, d.rep, strict=True)}
    ref = ref[(ref.half == "check") & ref.policy.isin(D90_POLICIES) & ref.d81_level.isin(CELLS)
              & ref.benign_invalid_rate.isin(D90_RATES) & ref.d89_rule.isin(RULES)]  # fmt: skip
    g = d.groupby(KEY)[RET].nunique(dropna=False)
    chk = {"label": LABEL, "limitation_test": True, "rows": len(d),
           "machines": int(d[["world", "true_start", "rep"]].drop_duplicates().shape[0]),
           "halves_of_d90_machines": sorted(map(str, halves_d90)),
           "retention_identical_N1_N3": bool((g == 1).all().all()),
           "every_row_has_both_rules": bool((d.groupby(KEY).d89_rule.nunique() == 2).all())}
    (OUT / "checks.json").write_text(json.dumps(chk, indent=1))
    print(json.dumps(chk, indent=1))
    if halves_d90 != {"check"} or not chk["retention_identical_N1_N3"] \
            or not chk["every_row_has_both_rules"]:
        raise SystemExit("D90 checks failed: stop and report")
    f = d[~d.d81_infeasible.astype(bool)]
    fr = ref[~ref.d81_infeasible.astype(bool)]
    pd.concat([absolute(f, [], "d90_capped"), absolute(fr, [], "d89_honest"),
               absolute(f, CELL, "d90_capped"), absolute(fr, CELL, "d89_honest")]
              ).to_csv(OUT / "absolute.csv", index=False)  # fmt: skip
    pd.concat([n3_vs_n1(f, [], "d90_capped"), n3_vs_n1(fr, [], "d89_honest"),
               n3_vs_n1(f, CELL, "d90_capped"), n3_vs_n1(fr, CELL, "d89_honest")]
              ).to_csv(OUT / "n3_vs_n1.csv", index=False)  # fmt: skip
    m = d.drop_duplicates(["arm_name", "world", "true_start", "rep", "benign_invalid_rate"])
    fl = m.groupby(["arm_name", "benign_invalid_rate"]).agg(
        machines=("d90_flags_kept", "size"), kept_mean=("d90_flags_kept", "mean"),
        removed_mean=("d90_flags_removed", "mean"), removed_median=("d90_flags_removed", "median"),
        removed_max=("d90_flags_removed", "max")).reset_index()
    fl.to_csv(OUT / "attacker_flags.csv", index=False)
    print(fl.round(2).to_string(index=False))


if __name__ == "__main__":
    main()
