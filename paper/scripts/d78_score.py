"""D78 criteria (amendment 1 as committed, implementation notes) for candidates against the
unchanged detector on one half ("v2fix" for selection, "v2check" for the single scoring):
1. benign rewrite-version flag rate at injected rate 0 <= 0.005 (point) and upper 95%
   machine-cluster CI <= 0.008;
2. (a) uniform type mean of the paired damaged-version detection difference, lower 95% CI >=
   -0.02 (one shared machine-cluster bootstrap); (b) every type's point difference >= -0.05;
   per-type CIs secondary;
3. file-level AUROC (striped 10%, uniform type mean) on the half's files not lower than the
   unchanged detector's by more than 0.01.
Run from the repo root:

    uv run python paper/scripts/d78_score.py <pool> <candidate> [<candidate> ...]
"""

import json
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from slowburn.detector.datasets import NapierOneDamageSource
from slowburn.detector.napierone import d78_split, encrypted_samples, family_splits
from slowburn.utils.config import load_config, resolve_path

sys.path.insert(0, str(Path(__file__).parent))
from d75_auroc import rows_for, score  # noqa: E402
from d78_build import CFG, transition_column  # noqa: E402

OUT = Path("results/dev_d78")
KEY = ["world", "rep", "true_start", "file_id", "day"]
N_BOOT = 2000


def _boot(n_cl, values_by_type, seed=0):
    """Uniform type mean of per-type means with one shared cluster resample; returns draws."""
    w = np.random.default_rng(seed).multinomial(n_cl, np.full(n_cl, 1 / n_cl), size=N_BOOT)
    means = [(w @ np.bincount(c, v, n_cl)) / (w @ np.bincount(c, None, n_cl))
             for c, v in values_by_type]  # fmt: skip
    return np.mean(means, axis=0)


def criteria(pool: str, cand: str) -> dict:
    a = pd.read_csv(OUT / f"recount_{pool}_{cand}.csv.gz")
    b = pd.read_csv(OUT / f"recount_{pool}_unchanged.csv.gz")
    m = a.merge(b, on=[*KEY, "file_type", "version"], suffixes=("", "_u"), validate="one_to_one")
    if len(m) != len(a) or len(a) != len(b):
        raise ValueError(f"{cand}: versions do not pair ({len(a)} / {len(b)} / {len(m)})")
    m["cl"] = m.world + "|" + m.rep.astype(str) + "|" + m.true_start.astype(str)
    codes_all = np.unique(m.cl, return_inverse=True)[1].ravel()
    m["code"] = codes_all
    n_cl = int(codes_all.max()) + 1
    rw = m[m.version == "rewrite"]
    w = np.random.default_rng(0).multinomial(n_cl, np.full(n_cl, 1 / n_cl), size=N_BOOT)
    fr = (w @ np.bincount(rw.code, rw.flagged, n_cl)) / (w @ np.bincount(rw.code, None, n_cl))
    out = {"candidate": cand, "pool": pool, "benign_rewrite_versions": len(rw),
           "benign_flags": int(rw.flagged.sum()), "benign_flag_rate": float(rw.flagged.mean()),
           "benign_flag_rate_hi": float(np.quantile(fr, 0.975)),
           "benign_flag_rate_unchanged": float(rw.flagged_u.mean())}  # fmt: skip
    out["c1"] = out["benign_flag_rate"] <= 0.005 and out["benign_flag_rate_hi"] <= 0.008
    dm = m[m.version == "damaged"]
    types = sorted(dm.file_type.unique())
    vals = [(dm[dm.file_type == t].code.to_numpy(),
             (dm[dm.file_type == t].flagged - dm[dm.file_type == t].flagged_u).to_numpy(float))
            for t in types]  # fmt: skip
    draws = _boot(n_cl, vals)
    pooled = float(np.mean([v.mean() for _, v in vals]))
    per_type = {t: {"n": len(v), "detection": float(dm[dm.file_type == t].flagged.mean()),
                    "detection_unchanged": float(dm[dm.file_type == t].flagged_u.mean()),
                    "diff": float(v.mean())}
                for t, (_, v) in zip(types, vals, strict=True)}  # fmt: skip
    for t, (c, v) in zip(types, vals, strict=True):
        d = (w @ np.bincount(c, v, n_cl)) / np.maximum(w @ np.bincount(c, None, n_cl), 1)
        per_type[t]["diff_lo"], per_type[t]["diff_hi"] = map(float, np.quantile(d, [0.025, 0.975]))
    out |= {"detection_diff_pooled": pooled, "detection_diff_lo": float(np.quantile(draws, 0.025)),
            "detection_diff_hi": float(np.quantile(draws, 0.975)),
            "min_type_diff": min(p["diff"] for p in per_type.values()),
            "per_type": per_type}  # fmt: skip
    out["c2a"] = out["detection_diff_lo"] >= -0.02
    out["c2b"] = out["min_type_diff"] >= -0.05
    return out


def auroc(pool: str, names: list[str]) -> dict:
    cfg = load_config(CFG)
    d, seed = cfg["data"], int(cfg["seed"])
    root = str(resolve_path(d["napierone_dir"]))
    fams = family_splits(root)["test"]  # the detector's held-out damage families (as in D75)
    source = NapierOneDamageSource(root, samples=encrypted_samples(root, fams))
    half = 0 if pool == "v2fix" else 1
    files = [(f"{t}_d78{pool}_{p.name}", t, p.read_bytes())
             for t in d["file_types"] for p in d78_split(root, t)[half]]  # fmt: skip
    m, X = rows_for(files, d, source, seed)
    res = {}
    for name in names:
        with (OUT / "detectors" / f"{name}.pkl").open("rb") as fh:
            det = pickle.load(fh)
        Xd = transition_column(m, X) if getattr(det, "validity_mode", "") == "transition" else X
        t = score(det, m, Xd, cfg, f"{pool}_{name}")
        r = t[(t.damage_model == "striped") & (t.fraction == 0.1) & (t.file_type == "WAVG_ALL")
              & (t.level == "file")]  # fmt: skip
        res[name] = float(r.auroc.iloc[0])
    return res


def main(pool, cands):
    au = auroc(pool, ["unchanged", *cands])
    rows = []
    for c in cands:
        r = criteria(pool, c)
        r["auroc"], r["auroc_unchanged"] = au[c], au["unchanged"]
        r["c3"] = r["auroc"] >= au["unchanged"] - 0.01
        r["all"] = bool(r["c1"] and r["c2a"] and r["c2b"] and r["c3"])
        rows.append(r)
    (OUT / f"criteria_{pool}.json").write_text(json.dumps(rows, indent=1))
    flat = pd.DataFrame([{k: v for k, v in r.items() if k != "per_type"} for r in rows])
    flat.to_csv(OUT / f"criteria_{pool}.csv", index=False)
    print(flat.round(4).to_string(index=False))
    for r in rows:
        print(r["candidate"], pd.DataFrame(r["per_type"]).T.round(3).to_string())
    if pool == "v2fix":
        ok = flat[flat["all"]]
        if len(ok):
            pick, adoptable = ok.sort_values("benign_flag_rate").candidate.iloc[0], True
        else:
            c23 = flat[flat.c2a & flat.c2b & flat.c3]
            pool_ = c23 if len(c23) else flat
            pick, adoptable = pool_.sort_values("benign_flag_rate").candidate.iloc[0], False
        sel = {"selected": pick, "adoptable": adoptable}
        (OUT / "selection.json").write_text(json.dumps(sel, indent=1))
        print("== selection on FIX:", sel)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2:])
