"""`slowburn fig <name>`: every paper figure and table, generated from result CSVs.

Outputs go to paper/generated/ (PDF + PNG figures, LaTeX tables, numbers.tex macros).
No number is typed by hand anywhere in the paper.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from slowburn.bench.latex import write_latex_table
from slowburn.bench.plotstyle import CATEGORICAL, INK_2, MUTED, apply_style
from slowburn.bench.stats import (
    bootstrap_mean_ci,
    holm,
    mcnemar_exact,
    risk_difference,
    wilcoxon_rank_biserial,
)
from slowburn.utils.config import resolve_path

GEN = "paper/generated"
HEADLINE_CSV = "results/headline/retention_results.csv"
POLICY_ORDER = ["slowburn", "prior_only", "tower_of_hanoi", "gfs", "keep_last_n",
                "threshold_vault", "amoeba_style", "keep_first", "oracle"]  # fmt: skip
POLICY_LABEL = {"slowburn": "SlowBurn", "prior_only": "Prior only (blind DP)",
                "tower_of_hanoi": "Tower of Hanoi", "gfs": "GFS", "keep_last_n": "Keep last N",
                "threshold_vault": "Threshold vault", "amoeba_style": "AMOEBA-style (reimpl.)",
                "keep_first": "Keep first backup",
                "oracle": "Oracle (knows start)"}  # fmt: skip
BASELINES = ["prior_only", "tower_of_hanoi", "gfs", "keep_last_n", "threshold_vault",
             "amoeba_style", "keep_first"]  # fmt: skip

REGISTRY: dict[str, Callable[[], list[Path]]] = {}


def figure(name: str):
    def deco(fn):
        REGISTRY[name] = fn
        return fn

    return deco


def _out(name: str) -> Path:
    p = resolve_path(GEN) / name
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _save(fig, stem: str) -> list[Path]:
    paths = [_out(f"{stem}.pdf"), _out(f"{stem}.png")]
    for p in paths:
        fig.savefig(p, dpi=200)
    plt.close(fig)
    return paths


def _style(policy: str) -> dict:
    if policy == "oracle":
        return {"color": INK_2, "ls": (0, (4, 2)), "marker": None, "lw": 1.5}
    slot = POLICY_ORDER.index(policy)
    return {"color": CATEGORICAL[slot], "marker": "o", "ms": 3.5,
            "lw": 2.4 if policy == "slowburn" else 1.6}  # fmt: skip


GRID_CELL = ["budget", "discovery_delay", "attack_start", "detect_prob", "benign_invalid_rate"]
FIXED = ["keep_last_n", "gfs", "tower_of_hanoi", "threshold_vault", "keep_first"]
DEV_CSV = "results/headline_dev/retention_results.csv"


def load_headline(path: str = HEADLINE_CSV, curve: bool = False) -> pd.DataFrame:
    df = pd.read_csv(resolve_path(path))
    if not curve:
        df = df[df.policy != "slowburn_curve"]
    for k in GRID_CELL:
        if k not in df:
            df[k] = 0  # single-scenario result files (no grid column)
    return df


def _machine_means(d: pd.DataFrame, metric: str, by: list[str]) -> pd.DataFrame:
    """Average a metric over grid cells within each simulated machine (rep x attack start), so
    bootstrap CIs resample machines, not correlated rows."""
    return d.groupby([*by, "rep", "attack_start"])[metric].mean().reset_index()


def _headline_panels(metric: str, ylabel: str, stem: str, title: str, ylim=None) -> list[Path]:
    df = load_headline()
    rates = sorted(df.benign_invalid_rate.unique())
    apply_style()
    fig, axes = plt.subplots(1, len(rates), figsize=(3.2 * len(rates), 3.3), sharey=True,
                             squeeze=False)  # fmt: skip
    rng = np.random.default_rng(0)
    for ax, b in zip(axes[0], rates, strict=True):
        sub = df[df.benign_invalid_rate == b]
        for pol in POLICY_ORDER:
            s = sub[sub.policy == pol]
            if s.empty or s[metric].isna().all():
                continue
            mm = _machine_means(s, metric, ["detect_prob"])
            qs = sorted(mm.detect_prob.unique(), reverse=True)
            stats = [bootstrap_mean_ci(mm[mm.detect_prob == q][metric].dropna().to_numpy(),
                                       rng=rng) for q in qs]  # fmt: skip
            m = np.array([x[0] for x in stats])
            lo, hi = np.array([x[1] for x in stats]), np.array([x[2] for x in stats])
            st = _style(pol)
            if pol != "oracle":
                ax.fill_between(qs, lo, hi, color=st["color"], alpha=0.12, lw=0)
            ax.plot(qs, m, label=POLICY_LABEL[pol], **st)
        if metric == "work_lost_whole_system_hours":
            o = _machine_means(sub[sub.policy == "oracle"], "work_lost_ideal_hours",
                               ["detect_prob"])  # fmt: skip
            ideal = o.groupby("detect_prob")["work_lost_ideal_hours"].mean()
            ax.plot(ideal.index, ideal.values, color=MUTED, ls=":", lw=1.2,
                    label="Ideal (restore day s-1)")  # fmt: skip
        ax.set_title(f"benign validation failures {b:.1%}", fontsize=8.5)
        ax.set_xlabel("Per-file detection probability")
        ax.set_xlim(1.03, -0.03)
    axes[0][0].set_ylabel(ylabel)
    if ylim:
        axes[0][0].set_ylim(*ylim)
    handles, labels = axes[0][0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper center", ncol=5, fontsize=7.5,
               bbox_to_anchor=(0.5, 1.0))  # fmt: skip
    fig.suptitle(title, x=0.01, y=0.86, ha="left", fontsize=9.5, fontweight="bold")
    n_mach = df.groupby(["rep", "attack_start"]).ngroups
    fig.text(0.01, 0.01, f"synthetic machines (token mode), {n_mach} test machines per point, "
             "averaged over every pre-registered grid cell (budget x delay x start offset); "
             "shaded: 95% bootstrap CI over machines", color=MUTED, fontsize=6.5)  # fmt: skip
    fig.tight_layout(rect=(0, 0.03, 1, 0.80))
    return _save(fig, stem)


@figure("headline-recovery")
def headline_recovery() -> list[Path]:
    return _headline_panels("clean_recovery", "Clean recovery rate", "fig_headline_recovery",
                            "Clean recovery vs detector quality", (-0.03, 1.03))  # fmt: skip


@figure("headline-worklost")
def headline_worklost() -> list[Path]:
    return _headline_panels("work_lost_whole_system_hours", "Work lost (hours, whole system)",
                            "fig_headline_worklost", "Work lost vs detector quality")  # fmt: skip


def _cells(df: pd.DataFrame) -> pd.DataFrame:
    from slowburn.bench.retention_experiment import cell_table

    return cell_table(df)


def slowburn_vs_best_fixed(cells: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Per grid cell: SlowBurn minus the best fixed schedule, the best chosen per cell AFTER the
    fact (this favours the baselines)."""
    out = {}
    for metric, use_max in (("clean_recovery", True), ("work_lost_whole_system_hours", False)):
        c = cells.pivot_table(index=GRID_CELL, columns="policy", values=metric)
        best = c[FIXED].max(axis=1) if use_max else c[FIXED].min(axis=1)
        out[metric] = (c["slowburn"] - best).rename("diff").reset_index()
    return out


@figure("grid-heatmap")
def grid_heatmap() -> list[Path]:
    diffs = slowburn_vs_best_fixed(_cells(load_headline()))
    apply_style()
    fig, axes = plt.subplots(1, 2, figsize=(9.0, 3.4))
    titles = {"clean_recovery": "Clean recovery: SlowBurn - best fixed (higher = SlowBurn better)",
              "work_lost_whole_system_hours": "Work lost (h): SlowBurn - best fixed "
              "(lower = SlowBurn better)"}  # fmt: skip
    for ax, (metric, d) in zip(axes, diffs.items(), strict=True):
        m = d.pivot_table(index="budget", columns="discovery_delay", values="diff")
        v = float(np.nanmax(np.abs(m.values))) or 1.0
        cmap = "RdBu" if metric == "clean_recovery" else "RdBu_r"
        im = ax.imshow(m.values, cmap=cmap, vmin=-v, vmax=v, aspect="auto")
        ax.set_xticks(range(m.shape[1]), [str(x) for x in m.columns])
        ax.set_yticks(range(m.shape[0]), [str(x) for x in m.index])
        ax.set_xlabel("Discovery delay (days)")
        ax.set_ylabel("Budget K (snapshots)")
        ax.set_title(titles[metric], fontsize=8)
        fmt = "{:+.2f}" if metric == "clean_recovery" else "{:+.0f}"
        for i in range(m.shape[0]):
            for j in range(m.shape[1]):
                ax.text(j, i, fmt.format(m.values[i, j]), ha="center", va="center", fontsize=7)
        fig.colorbar(im, ax=ax, shrink=0.8)
    fig.text(0.01, 0.01, "mean over start offsets, detection probabilities and benign failure "
             "rates; best fixed schedule = best of keep-last-N, GFS, ToH, threshold vault per cell",
             color=MUTED, fontsize=6.5)  # fmt: skip
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    return _save(fig, "fig_grid_heatmap")


@figure("table-grid")
def table_grid() -> list[Path]:
    from slowburn.bench.retention_experiment import grid_summary

    g = grid_summary(_cells(load_headline())).reset_index()
    g["policy"] = g.policy.map(lambda x: POLICY_LABEL.get(x, x))
    p = write_latex_table(g, _out("table_grid_summary.tex"), floatfmt="{:.3f}",
                          caption="Every pre-registered grid cell: average and worst cell per "
                          "policy (clean recovery; whole-system work lost in hours; oracle-ideal "
                          "work lost alongside)", label="tab:grid")  # fmt: skip
    return [p]


@figure("table-headline")
def table_headline() -> list[Path]:
    df = load_headline()
    rng = np.random.default_rng(0)
    rows = []
    for (q, b), sub in df.groupby(["detect_prob", "benign_invalid_rate"]):
        row = {"q": q, "b": b}
        for pol in POLICY_ORDER:
            mm = _machine_means(sub[sub.policy == pol], "clean_recovery", [])
            if len(mm):
                m, lo, hi = bootstrap_mean_ci(mm.clean_recovery.to_numpy(), rng=rng)
                row[POLICY_LABEL[pol].split(" (")[0]] = f"{m:.2f} [{lo:.2f}, {hi:.2f}]"
        rows.append(row)
    tab = pd.DataFrame(rows).sort_values(["b", "q"], ascending=[True, False])
    p = write_latex_table(tab, _out("table_headline.tex"),
                          caption="Clean recovery rate averaged over the grid (95% bootstrap CI "
                          "over machines)", label="tab:headline")  # fmt: skip
    return [p]


def paired_tests(
    df: pd.DataFrame, cell_keys=("detect_prob", "benign_invalid_rate")
) -> pd.DataFrame:
    """SlowBurn vs each baseline per cell, paired by machine (rep): exact McNemar + risk
    difference (clean recovery), Wilcoxon + rank-biserial (work lost), Holm across baselines
    within each cell."""
    out = []
    rng = np.random.default_rng(0)
    keys = list(cell_keys)
    for vals, sub in df.groupby(keys):
        vals = vals if isinstance(vals, tuple) else (vals,)
        sb = sub[sub.policy == "slowburn"].set_index("rep")
        cell = []
        for base in BASELINES:
            bs = sub[sub.policy == base].set_index("rep")
            reps = sb.index.intersection(bs.index)
            if not len(reps):
                continue
            a, c = sb.loc[reps, "clean_recovery"], bs.loc[reps, "clean_recovery"]
            mc = mcnemar_exact(a.to_numpy(), c.to_numpy())
            rd = risk_difference(a.to_numpy(), c.to_numpy(), rng=rng)
            metric = ("work_lost_selective_file_hours" if base == "amoeba_style"
                      else "work_lost_whole_system_hours")  # fmt: skip
            wl = wilcoxon_rank_biserial(sb.loc[reps, metric].to_numpy(),
                                        bs.loc[reps, metric].to_numpy())  # fmt: skip
            cell.append({**dict(zip(keys, vals, strict=True)), "baseline": base, "n": len(reps),
                         "recovery_diff": rd["risk_difference"], "rd_ci_low": rd["ci_low"],
                         "rd_ci_high": rd["ci_high"], "mcnemar_p": mc["p_value"],
                         "work_lost_metric": metric, "worklost_rank_biserial":
                         wl["rank_biserial"], "wilcoxon_p": wl["p_value"]})  # fmt: skip
        if cell:
            cdf = pd.DataFrame(cell)
            cdf["mcnemar_p_holm"] = holm(cdf.mcnemar_p.to_numpy())
            cdf["wilcoxon_p_holm"] = holm(cdf.wilcoxon_p.to_numpy())
            out.append(cdf)
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame()


def significance_counts(t: pd.DataFrame, alpha: float = 0.05) -> pd.DataFrame:
    """Per baseline: cells where SlowBurn is significantly better / worse (Holm p < alpha)."""
    rows = []
    for base, g in t.groupby("baseline", sort=False):
        sr, sw = g.mcnemar_p_holm < alpha, g.wilcoxon_p_holm < alpha
        rows.append({"baseline": POLICY_LABEL.get(base, base), "cells": len(g),
                     "recovery better": int((sr & (g.recovery_diff > 0)).sum()),
                     "recovery worse": int((sr & (g.recovery_diff < 0)).sum()),
                     "work lost better": int((sw & (g.worklost_rank_biserial < 0)).sum()),
                     "work lost worse": int((sw & (g.worklost_rank_biserial > 0)).sum()),
                     })  # fmt: skip
    return pd.DataFrame(rows)


@figure("table-stats")
def table_stats() -> list[Path]:
    """Per grid cell tests (every cell in the CSV); the LaTeX table counts the cells."""
    t = paired_tests(load_headline(), GRID_CELL)
    t.to_csv(resolve_path("results/headline/paired_tests.csv"), index=False)
    p = write_latex_table(significance_counts(t), _out("table_stats.tex"),
                          caption="SlowBurn vs each baseline: grid cells with a significant "
                          "difference (paired by machine; Holm across baselines within each "
                          "cell, p < 0.05)", label="tab:stats")  # fmt: skip
    return [p]


def tradeoff_points(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Mean clean recovery and whole-system work lost over every grid cell: one point per
    policy, and one per SlowBurn setting on the trade-off curve."""
    agg = {"clean_recovery": "mean", "work_lost_whole_system_hours": "mean"}
    pts = df[df.policy != "slowburn_curve"].groupby("policy").agg(agg)
    curve = df[df.policy == "slowburn_curve"]
    keys = ["hp_penalty", "hp_assumed_discovery_max", "hp_backbone"]
    cur = curve.groupby(keys).agg(agg).reset_index() if len(curve) else pd.DataFrame()
    return pts, cur


def _pareto(cur: pd.DataFrame) -> pd.DataFrame:
    c = cur.sort_values(["work_lost_whole_system_hours", "clean_recovery"],
                        ascending=[True, False])  # fmt: skip
    best, keep = -1.0, []
    for i, r in c.iterrows():
        if r.clean_recovery > best:
            best = r.clean_recovery
            keep.append(i)
    return c.loc[keep]


def _tradeoff_figure(path: str, stem: str, split: str) -> list[Path]:
    df = load_headline(path, curve=True)
    pts, cur = tradeoff_points(df)
    apply_style()
    fig, ax = plt.subplots(figsize=(6.4, 4.4))
    if len(cur):
        ax.scatter(cur.work_lost_whole_system_hours, cur.clean_recovery, s=14,
                   color=_style("slowburn")["color"], alpha=0.35, lw=0,
                   label="SlowBurn, other settings")  # fmt: skip
        fr = _pareto(cur)
        ax.plot(fr.work_lost_whole_system_hours, fr.clean_recovery,
                color=_style("slowburn")["color"], lw=1.4, alpha=0.8)  # fmt: skip
    for pol in POLICY_ORDER:
        if pol not in pts.index:
            continue
        r = pts.loc[pol]
        st = _style(pol)
        marker = "*" if pol == "slowburn" else ("D" if pol == "oracle" else "o")
        label = POLICY_LABEL[pol] + (" (frozen setting)" if pol == "slowburn" else "")
        ax.scatter(r.work_lost_whole_system_hours, r.clean_recovery, marker=marker, zorder=3,
                   s=110 if marker == "*" else 40, color=st["color"], label=label)  # fmt: skip
    if "work_lost_ideal_hours" in df:
        ideal = df[df.policy == "oracle"].work_lost_ideal_hours.mean()
        ax.axvline(ideal, color=MUTED, ls=":", lw=1.0, label="Ideal work lost (restore day s-1)")
    ax.set_xlabel("Mean whole-system work lost (hours; unrecovered = all work since day 0)")
    ax.set_ylabel("Mean clean recovery rate")
    ax.set_ylim(-0.03, 1.03)
    ax.legend(fontsize=6.8, loc="lower left", frameon=False)
    ax.set_title(f"Recovery vs work lost, every grid cell ({split.upper()})", fontsize=9.5,
                 loc="left", fontweight="bold")  # fmt: skip
    n_mach = df.groupby(["rep", "attack_start"]).ngroups
    fig.text(0.01, 0.01, f"{n_mach} {split} machines; up and left is better; SlowBurn curve = "
             "penalty x assumed delay x backbone settings (operating point chosen on DEV)",
             color=MUTED, fontsize=6.3)  # fmt: skip
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    return _save(fig, stem)


@figure("tradeoff")
def tradeoff() -> list[Path]:
    out = []
    for path, stem, split in ((HEADLINE_CSV, "fig_tradeoff_test", "test"),
                              (DEV_CSV, "fig_tradeoff_dev", "dev")):  # fmt: skip
        if resolve_path(path).exists():
            out += _tradeoff_figure(path, stem, split)
    if not out:
        raise FileNotFoundError(2, "no result CSV", HEADLINE_CSV)
    return out


@figure("table-theory")
def table_theory() -> list[Path]:
    t = pd.read_csv(resolve_path("results/theory/toh_tightness.csv"))
    p = write_latex_table(t, _out("table_theory_tightness.tex"), floatfmt="{:.3f}",
                          caption="Theorem 2(a) numerical check: Tower of Hanoi, all cases "
                          "within the horizon", label="tab:theory")  # fmt: skip
    h = pd.read_csv(resolve_path("results/theory/hybrid_guarantee.csv"))
    q = write_latex_table(h, _out("table_theory_hybrid.tex"),
                          caption="Theorem 2(c) numerical check: the hybrid holds the R-media "
                          "Tower of Hanoi set every day", label="tab:theory-hybrid")  # fmt: skip
    return [p, q]


@figure("auroc")
def auroc_figure() -> list[Path]:
    from slowburn.bench.plots import plot_auroc_vs_fraction

    a = pd.read_csv(resolve_path("results/detector/auroc_by_fraction.csv"))
    png = plot_auroc_vs_fraction(a, resolve_path(GEN))
    return [png]


def generate(name: str) -> list[Path]:
    if name == "all":
        out = []
        for n, fn in REGISTRY.items():
            try:
                out += fn()
            except FileNotFoundError as e:
                print(f"  skip {n}: missing input ({e.filename})")
        return out
    if name not in REGISTRY:
        raise ValueError(f"unknown figure {name!r}; known: {sorted(REGISTRY)} or 'all'")
    return REGISTRY[name]()
