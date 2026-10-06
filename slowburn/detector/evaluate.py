"""Detector evaluation: AUROC per damage model x fraction x file type, with file-cluster
bootstrap confidence intervals, plus TPR at conformal false-alarm levels."""

from __future__ import annotations

import numpy as np
import pandas as pd

from slowburn.sim.content import HIGH_ENTROPY_TYPES


def weighted_auroc(
    scores: np.ndarray, labels: np.ndarray, weights: np.ndarray | None = None
) -> float:
    """Mann-Whitney AUROC with optional sample weights; ties count one half."""
    scores, labels = np.asarray(scores), np.asarray(labels)
    w = np.ones(len(scores)) if weights is None else np.asarray(weights, dtype=float)
    _, inv = np.unique(scores, return_inverse=True)
    pos = np.bincount(inv, weights=w * (labels == 1))
    neg = np.bincount(inv, weights=w * (labels == 0))
    P, N = pos.sum(), neg.sum()
    if P == 0 or N == 0:
        return float("nan")
    neg_below = np.cumsum(neg) - neg
    return float((pos * (neg_below + 0.5 * neg)).sum() / (P * N))


def bootstrap_auroc(
    scores: np.ndarray,
    labels: np.ndarray,
    file_ids: np.ndarray,
    n_boot: int,
    ci: float,
    rng: np.random.Generator,
) -> tuple[float, float, float]:
    """Point AUROC and a percentile CI from resampling whole files with replacement."""
    point = weighted_auroc(scores, labels)
    if n_boot <= 0 or np.isnan(point):
        return point, float("nan"), float("nan")
    uniq, fidx = np.unique(file_ids, return_inverse=True)
    boots = []
    for _ in range(n_boot):
        counts = rng.multinomial(len(uniq), np.full(len(uniq), 1 / len(uniq)))
        a = weighted_auroc(scores, labels, counts[fidx].astype(float))
        if not np.isnan(a):
            boots.append(a)
    if not boots:
        return point, float("nan"), float("nan")
    q = (1 - ci) / 2
    return point, float(np.quantile(boots, q)), float(np.quantile(boots, 1 - q))


def _type_groups(types: list[str]) -> dict[str, list[str]]:
    groups = {"ALL": types}
    hi = [t for t in types if t in HIGH_ENTROPY_TYPES]
    lo = [t for t in types if t not in HIGH_ENTROPY_TYPES]
    if hi:
        groups["HIGH_ENTROPY"] = hi
    if lo:
        groups["LOW_ENTROPY"] = lo
    groups.update({t: [t] for t in types})
    return groups


def auroc_table(
    meta: pd.DataFrame,
    raw: np.ndarray,
    pvals: dict[str, np.ndarray],
    alphas: list[float],
    n_boot: int,
    ci: float,
    rng: np.random.Generator,
) -> pd.DataFrame:
    """Tidy AUROC table at chunk level and file level (file score = max chunk score).

    ``pvals`` maps a conformal variant name (e.g. marginal, mondrian) to per-row p-values;
    TPR/FPR at each alpha are reported per variant.
    """
    m = meta.reset_index(drop=True).assign(raw=raw, **{f"pv_{k}": v for k, v in pvals.items()})
    neg_all = m[m.label == 0]
    rows = []
    for (model, frac), pos_all in m[m.label == 1].groupby(["damage_model", "fraction"]):
        for gname, gtypes in _type_groups(sorted(m.file_type.unique())).items():
            pos = pos_all[pos_all.file_type.isin(gtypes)]
            neg = neg_all[neg_all.file_type.isin(gtypes)]
            if pos.empty or neg.empty:
                continue
            both = pd.concat([pos, neg])
            base = {
                "damage_model": model, "fraction": frac, "file_type": gname,
                "damage_source": "+".join(sorted(pos.damage_source.unique())),
                "benign_source": "+".join(sorted(both.benign_source.unique())),
                "mean_damaged_byte_frac": float(pos.damaged_byte_frac.mean()),
            }  # fmt: skip
            a, lo_, hi_ = bootstrap_auroc(
                both.raw.values, both.label.values, both.file_id.values, n_boot, ci, rng
            )
            row = {**base, "level": "chunk", "auroc": a, "ci_low": lo_, "ci_high": hi_,
                   "n_pos": len(pos), "n_neg": len(neg)}  # fmt: skip
            for name in pvals:
                for al in alphas:
                    row[f"tpr_{name}_a{al}"] = float(np.mean(pos[f"pv_{name}"] <= al))
                    row[f"fpr_{name}_a{al}"] = float(np.mean(neg[f"pv_{name}"] <= al))
            rows.append(row)
            # file level: a benign file vs its damaged version, scored by max chunk score
            fpos = pos.groupby("file_id").raw.max()
            fneg = neg.groupby("file_id").raw.max()
            fs = np.r_[fpos.values, fneg.values]
            fy = np.r_[np.ones(len(fpos)), np.zeros(len(fneg))]
            fid = np.r_[fpos.index.values, fneg.index.values]
            a, lo_, hi_ = bootstrap_auroc(fs, fy, fid, n_boot, ci, rng)
            rows.append({**base, "level": "file", "auroc": a, "ci_low": lo_, "ci_high": hi_,
                         "n_pos": len(fpos), "n_neg": len(fneg)})  # fmt: skip
    return pd.DataFrame(rows)


def calibration_table(
    meta: pd.DataFrame, pvals: dict[str, np.ndarray], alphas: list[float]
) -> pd.DataFrame:
    """Empirical false-alarm rate of each conformal variant on benign TEST chunks, per type."""
    m = meta.reset_index(drop=True).assign(**{f"pv_{k}": v for k, v in pvals.items()})
    neg = m[m.label == 0]
    rows = []
    for gname, gtypes in _type_groups(sorted(m.file_type.unique())).items():
        g = neg[neg.file_type.isin(gtypes)]
        for name in pvals:
            for al in alphas:
                fpr = float(np.mean(g[f"pv_{name}"] <= al))
                rows.append({"file_type": gname, "variant": name, "alpha": al,
                             "empirical_fpr": fpr, "n_benign": len(g)})  # fmt: skip
    return pd.DataFrame(rows)
