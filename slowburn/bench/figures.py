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
                "threshold_vault", "amoeba_style", "oracle"]  # fmt: skip
POLICY_LABEL = {"slowburn": "SlowBurn", "prior_only": "Prior only (blind DP)",
                "tower_of_hanoi": "Tower of Hanoi", "gfs": "GFS", "keep_last_n": "Keep last N",
                "threshold_vault": "Threshold vault", "amoeba_style": "AMOEBA-style (reimpl.)",
                "oracle": "Oracle (knows start)"}  # fmt: skip
BASELINES = ["prior_only", "tower_of_hanoi", "gfs", "keep_last_n", "threshold_vault",
             "amoeba_style"]  # fmt: skip

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


def load_headline(path: str = HEADLINE_CSV) -> tuple[pd.DataFrame, int]:
    import yaml

    df = pd.read_csv(resolve_path(path))
    cfg = yaml.safe_load(resolve_path("configs/headline.yaml").read_text(encoding="utf-8"))
    return df, int(cfg.get("headline_delay", 14))


def _headline_panels(metric: str, ylabel: str, stem: str, title: str, ylim=None) -> list[Path]:
    df, delay = load_headline()
    d = df[df.discovery_delay == delay]
    rates = sorted(d.benign_invalid_rate.unique())
    apply_style()
    fig, axes = plt.subplots(1, len(rates), figsize=(3.2 * len(rates), 3.3), sharey=True,
                             squeeze=False)  # fmt: skip
    rng = np.random.default_rng(0)
    for ax, b in zip(axes[0], rates, strict=True):
        sub = d[d.benign_invalid_rate == b]
        for pol in POLICY_ORDER:
            s = sub[sub.policy == pol]
            if s.empty or s[metric].isna().all():
                continue
            qs = sorted(s.detect_prob.unique(), reverse=True)
            stats = [bootstrap_mean_ci(s[s.detect_prob == q][metric].dropna().to_numpy(),
                                       rng=rng) for q in qs]  # fmt: skip
            m = np.array([x[0] for x in stats])
            lo, hi = np.array([x[1] for x in stats]), np.array([x[2] for x in stats])
            st = _style(pol)
            if pol != "oracle":
                ax.fill_between(qs, lo, hi, color=st["color"], alpha=0.12, lw=0)
            ax.plot(qs, m, label=POLICY_LABEL[pol], **st)
        ax.set_title(f"benign validation failures {b:.1%}", fontsize=8.5)
        ax.set_xlabel("Per-file detection probability")
        ax.set_xlim(1.03, -0.03)
    axes[0][0].set_ylabel(ylabel)
    if ylim:
        axes[0][0].set_ylim(*ylim)
    handles, labels = axes[0][0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper center", ncol=4, fontsize=7.5,
               bbox_to_anchor=(0.5, 1.0))  # fmt: skip
    fig.suptitle(title, x=0.01, y=0.86, ha="left", fontsize=9.5, fontweight="bold")
    n = int(d.groupby(["policy", "detect_prob", "benign_invalid_rate"]).size().min())
    fig.text(0.01, 0.01, f"synthetic machines (token mode), {n} test seeds per point, discovery "
             f"delay {delay} d; shaded: 95% bootstrap CI", color=MUTED, fontsize=6.5)  # fmt: skip
    fig.tight_layout(rect=(0, 0.03, 1, 0.82))
    return _save(fig, stem)


@figure("headline-recovery")
def headline_recovery() -> list[Path]:
    return _headline_panels("clean_recovery", "Clean recovery rate", "fig_headline_recovery",
                            "Clean recovery vs detector quality", (-0.03, 1.03))  # fmt: skip


@figure("headline-worklost")
def headline_worklost() -> list[Path]:
    return _headline_panels("work_lost_whole_system_hours", "Work lost (hours, whole system)",
                            "fig_headline_worklost", "Work lost vs detector quality")  # fmt: skip


@figure("table-headline")
def table_headline() -> list[Path]:
    df, delay = load_headline()
    d = df[df.discovery_delay == delay]
    rng = np.random.default_rng(0)
    rows = []
    for (q, b), sub in d.groupby(["detect_prob", "benign_invalid_rate"]):
        row = {"q": q, "b": b}
        for pol in POLICY_ORDER:
            x = sub[sub.policy == pol].clean_recovery.to_numpy()
            if len(x):
                m, lo, hi = bootstrap_mean_ci(x, rng=rng)
                row[POLICY_LABEL[pol].split(" (")[0]] = f"{m:.2f} [{lo:.2f}, {hi:.2f}]"
        rows.append(row)
    tab = pd.DataFrame(rows).sort_values(["b", "q"], ascending=[True, False])
    p = write_latex_table(tab, _out("table_headline.tex"),
                          caption=f"Clean recovery rate (95% bootstrap CI), delay {delay} d",
                          label="tab:headline")  # fmt: skip
    return [p]


def paired_tests(df: pd.DataFrame, delay: int) -> pd.DataFrame:
    """SlowBurn vs each baseline per (q, b) cell: exact McNemar + risk difference (clean
    recovery), Wilcoxon + rank-biserial (work lost), Holm across baselines within each cell."""
    d = df[df.discovery_delay == delay]
    out = []
    rng = np.random.default_rng(0)
    for (q, b), sub in d.groupby(["detect_prob", "benign_invalid_rate"]):
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
            cell.append({"q": q, "b": b, "baseline": base, "n": len(reps),
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


@figure("table-stats")
def table_stats() -> list[Path]:
    df, delay = load_headline()
    t = paired_tests(df, delay)
    t.to_csv(resolve_path("results/headline/paired_tests.csv"), index=False)
    show = t[["q", "b", "baseline", "recovery_diff", "rd_ci_low", "rd_ci_high",
              "mcnemar_p_holm", "worklost_rank_biserial", "wilcoxon_p_holm"]]  # fmt: skip
    p = write_latex_table(show, _out("table_stats.tex"), floatfmt="{:.3f}",
                          caption=f"SlowBurn vs each baseline (paired by seed, delay {delay} d; "
                          "Holm-adjusted within each cell)", label="tab:stats")  # fmt: skip
    return [p]


@figure("table-theory")
def table_theory() -> list[Path]:
    t = pd.read_csv(resolve_path("results/theory/toh_tightness.csv"))
    p = write_latex_table(t, _out("table_theory_tightness.tex"), floatfmt="{:.3f}",
                          caption="Theorem 2(a) numerical check: Tower of Hanoi, all cases "
                          "within the horizon", label="tab:theory")  # fmt: skip
    return [p]


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
