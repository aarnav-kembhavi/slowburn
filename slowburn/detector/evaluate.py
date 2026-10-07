"""Detector evaluation, per file type.

Headline numbers are per-type AUROCs and their *weighted averages* with explicit type weights
from config (never a pooled AUROC: pooling mixes types with different base rates and lets easy
types hide hard ones). Confidence intervals come from a file-cluster bootstrap inside each type;
a weighted average's CI combines the per-type bootstrap draws with the same weights (stratified
bootstrap).
"""

from __future__ import annotations

from collections.abc import Mapping

import numpy as np
import pandas as pd

from slowburn.sim.content import HIGH_ENTROPY_TYPES

GROUP_PREFIX = "WAVG_"


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


def bootstrap_draws(
    scores: np.ndarray, labels: np.ndarray, file_ids: np.ndarray, n_boot: int,
    rng: np.random.Generator,
) -> tuple[float, np.ndarray]:  # fmt: skip
    """Point AUROC and ``n_boot`` file-cluster bootstrap AUROCs (NaN where degenerate)."""
    point = weighted_auroc(scores, labels)
    uniq, fidx = np.unique(file_ids, return_inverse=True)
    draws = np.full(n_boot, np.nan)
    if np.isnan(point):
        return point, draws
    for b in range(n_boot):
        counts = rng.multinomial(len(uniq), np.full(len(uniq), 1 / len(uniq)))
        draws[b] = weighted_auroc(scores, labels, counts[fidx].astype(float))
    return point, draws


def bootstrap_auroc(scores, labels, file_ids, n_boot, ci, rng) -> tuple[float, float, float]:
    """Point AUROC and a percentile CI from resampling whole files with replacement."""
    point, draws = bootstrap_draws(scores, labels, file_ids, n_boot, rng)
    lo, hi = _percentile_ci(draws, ci)
    return point, lo, hi


def _percentile_ci(draws: np.ndarray, ci: float) -> tuple[float, float]:
    d = draws[~np.isnan(draws)]
    if len(d) == 0:
        return float("nan"), float("nan")
    q = (1 - ci) / 2
    return float(np.quantile(d, q)), float(np.quantile(d, 1 - q))


def type_weights(types: list[str], spec: str | Mapping[str, float] = "uniform") -> dict:
    """Explicit per-type weights (normalised). ``uniform`` gives every type equal weight."""
    if spec == "uniform":
        return {t: 1.0 / len(types) for t in types}
    missing = set(types) - set(spec)
    if missing:
        raise ValueError(f"type_weights missing types: {sorted(missing)}")
    total = sum(float(spec[t]) for t in types)
    return {t: float(spec[t]) / total for t in types}


def type_groups(types: list[str]) -> dict[str, list[str]]:
    groups = {"ALL": list(types)}
    hi = [t for t in types if t in HIGH_ENTROPY_TYPES]
    lo = [t for t in types if t not in HIGH_ENTROPY_TYPES]
    if hi:
        groups["HIGH_ENTROPY"] = hi
    if lo:
        groups["LOW_ENTROPY"] = lo
    return groups


def _weighted(values: Mapping[str, float], weights: Mapping[str, float], members: list[str]):
    w = np.array([weights[t] for t in members])
    v = np.array([values[t] for t in members], dtype=float)
    return float((w * v).sum() / w.sum())


def auroc_table(
    meta: pd.DataFrame,
    raw: np.ndarray,
    pvals: dict[str, np.ndarray],
    alphas: list[float],
    n_boot: int,
    ci: float,
    rng: np.random.Generator,
    weights_spec: str | Mapping[str, float] = "uniform",
) -> pd.DataFrame:
    """Per-type AUROC (chunk and file level) plus weighted-average group rows ``WAVG_*``.

    ``pvals`` maps a conformal variant name to per-row p-values; TPR/FPR at each alpha are
    reported per type and weight-averaged the same way. File level: a file's score is the max
    over its changed chunks.
    """
    m = meta.reset_index(drop=True).assign(raw=raw, **{f"pv_{k}": v for k, v in pvals.items()})
    types = sorted(m.file_type.unique())
    weights = type_weights(types, weights_spec)
    rows = []
    for (model, frac), pos_all in m[m.label == 1].groupby(["damage_model", "fraction"]):
        per = {"chunk": {}, "file": {}}
        for t in types:
            pos = pos_all[pos_all.file_type == t]
            neg = m[(m.label == 0) & (m.file_type == t)]
            if pos.empty or neg.empty:
                continue
            base = {"damage_model": model, "fraction": frac, "file_type": t,
                    "weight": weights[t],
                    "damage_source": "+".join(sorted(pos.damage_source.unique())),
                    "benign_source": "+".join(sorted(pd.concat([pos, neg]).benign_source
                                                     .unique())),
                    "mean_damaged_byte_frac": float(pos.damaged_byte_frac.mean())}  # fmt: skip
            both = pd.concat([pos, neg])
            pt, draws = bootstrap_draws(both.raw.values, both.label.values, both.file_id.values,
                                        n_boot, rng)  # fmt: skip
            row = {**base, "level": "chunk", "auroc": pt, "n_pos": len(pos), "n_neg": len(neg)}
            row["ci_low"], row["ci_high"] = _percentile_ci(draws, ci)
            for name in pvals:
                for al in alphas:
                    row[f"tpr_{name}_a{al}"] = float(np.mean(pos[f"pv_{name}"] <= al))
                    row[f"fpr_{name}_a{al}"] = float(np.mean(neg[f"pv_{name}"] <= al))
            rows.append(row)
            per["chunk"][t] = (row, draws)
            fpos, fneg = pos.groupby("file_id").raw.max(), neg.groupby("file_id").raw.max()
            fs = np.r_[fpos.values, fneg.values]
            fy = np.r_[np.ones(len(fpos)), np.zeros(len(fneg))]
            fid = np.r_[fpos.index.values, fneg.index.values]
            pt, fdraws = bootstrap_draws(fs, fy, fid, n_boot, rng)
            frow = {**base, "level": "file", "auroc": pt, "n_pos": len(fpos), "n_neg": len(fneg)}
            frow["ci_low"], frow["ci_high"] = _percentile_ci(fdraws, ci)
            rows.append(frow)
            per["file"][t] = (frow, fdraws)
        for level, entries in per.items():
            for gname, members in type_groups(types).items():
                members = [t for t in members if t in entries]
                if not members:
                    continue
                vals = {t: entries[t][0]["auroc"] for t in members}
                draws = sum(weights[t] * entries[t][1] for t in members) / sum(
                    weights[t] for t in members
                )
                g = {"damage_model": model, "fraction": frac, "file_type": GROUP_PREFIX + gname,
                     "weight": sum(weights[t] for t in members), "level": level,
                     "auroc": _weighted(vals, weights, members),
                     "n_pos": sum(entries[t][0]["n_pos"] for t in members),
                     "n_neg": sum(entries[t][0]["n_neg"] for t in members),
                     "damage_source": entries[members[0]][0]["damage_source"],
                     "benign_source": entries[members[0]][0]["benign_source"],
                     "mean_damaged_byte_frac": _weighted(
                         {t: entries[t][0]["mean_damaged_byte_frac"] for t in members},
                         weights, members)}  # fmt: skip
                g["ci_low"], g["ci_high"] = _percentile_ci(draws, ci)
                if level == "chunk":
                    for col in entries[members[0]][0]:
                        if col.startswith(("tpr_", "fpr_")):
                            g[col] = _weighted({t: entries[t][0][col] for t in members},
                                               weights, members)  # fmt: skip
                rows.append(g)
    return pd.DataFrame(rows)


def calibration_table(
    meta: pd.DataFrame,
    pvals: dict[str, np.ndarray],
    alphas: list[float],
    weights_spec: str | Mapping[str, float] = "uniform",
) -> pd.DataFrame:
    """Empirical false-alarm rate of each conformal variant on benign TEST chunks, per type,
    plus weighted averages over the type groups."""
    m = meta.reset_index(drop=True).assign(**{f"pv_{k}": v for k, v in pvals.items()})
    neg = m[m.label == 0]
    types = sorted(m.file_type.unique())
    weights = type_weights(types, weights_spec)
    rows = []
    for name in pvals:
        for al in alphas:
            per = {t: float(np.mean(neg.loc[neg.file_type == t, f"pv_{name}"] <= al))
                   for t in types}  # fmt: skip
            for t in types:
                rows.append({"file_type": t, "variant": name, "alpha": al,
                             "empirical_fpr": per[t],
                             "n_benign": int((neg.file_type == t).sum())})  # fmt: skip
            for gname, members in type_groups(types).items():
                rows.append({"file_type": GROUP_PREFIX + gname, "variant": name, "alpha": al,
                             "empirical_fpr": _weighted(per, weights, members),
                             "n_benign": int(neg.file_type.isin(members).sum())})  # fmt: skip
    return pd.DataFrame(rows)
