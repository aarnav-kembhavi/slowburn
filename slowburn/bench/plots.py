"""Benchmark figures."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from slowburn.bench.plotstyle import INK_2, MUTED, apply_style, series_color

FRACTION_TICKS = [5, 10, 25, 50, 100]
DAMAGE_LABELS = {"striped": "striped within chunk", "whole": "whole chunks"}


def _fraction_axis(ax) -> None:
    ax.set_xscale("log")
    ax.set_xticks(FRACTION_TICKS)
    ax.set_xticklabels([f"{t}%" for t in FRACTION_TICKS])
    ax.minorticks_off()
    ax.set_xlim(4, 125)


DETECTOR_ORDER = ["lgbm_base", "lgbm_validity", "validity_rule"]
DETECTOR_LABELS = {
    "lgbm_base": "LightGBM, chunk features",
    "lgbm_validity": "LightGBM + format validity",
    "validity_rule": "format validity alone",
}
GROUP_TITLES = {
    "WAVG_ALL": "All types (weighted average)",
    "WAVG_HIGH_ENTROPY": "High-entropy types (weighted average)",
}


def _auroc_lines(ax, sub: pd.DataFrame, label_ends: bool) -> None:
    """One line per detector variant (fixed colours), with CI bands. The rule is drawn dashed
    with open markers on top, so it stays readable where it coincides with another line."""
    from slowburn.bench.plotstyle import CATEGORICAL

    ax.axhline(0.5, color=MUTED, lw=1, ls=(0, (3, 3)))
    for slot, det in enumerate(DETECTOR_ORDER):
        s = sub[sub.detector == det].sort_values("fraction")
        if s.empty:
            continue
        x, c = s.fraction * 100, CATEGORICAL[slot]
        if s.ci_low.notna().any():
            ax.fill_between(x, s.ci_low, s.ci_high, color=c, alpha=0.15, lw=0)
        style = ({"ls": (0, (4, 2)), "mfc": "none", "lw": 1.5, "zorder": 4}
                 if det == "validity_rule" else {"zorder": 3})  # fmt: skip
        ax.plot(x, s.auroc, marker="o", color=c, label=DETECTOR_LABELS.get(det, det), **style)
        if label_ends and det == "lgbm_base":  # the only curve whose level varies
            first = s.iloc[0]
            ax.annotate(f"{first.auroc:.3f}", (first.fraction * 100, first.auroc),
                        xytext=(0, -12), textcoords="offset points", ha="center",
                        color=INK_2, fontsize=7)  # fmt: skip
    _fraction_axis(ax)


def _source_tag(df: pd.DataFrame) -> str:
    srcs = sorted(set(df.benign_source) | set(df.damage_source))
    return "benign + damage data: " + ", ".join(srcs)


def _footnote(fig, df: pd.DataFrame, extra: str = "") -> None:
    fig.text(0.01, 0.01, _source_tag(df) + "  |  shaded: 95% file-cluster bootstrap CI" + extra,
             color=MUTED, fontsize=7, ha="left", va="bottom")  # fmt: skip


def plot_auroc_vs_fraction(auroc: pd.DataFrame, out: Path) -> Path:
    """Headline: weighted-average chunk AUROC vs damaged fraction, per detector variant.

    Rows: damage placement. Columns: all types / high-entropy types (weighted averages with the
    configured type weights; no pooled AUROC).
    """
    apply_style()
    chunk = auroc[auroc.level == "chunk"]
    models = [m for m in ("striped", "whole") if (chunk.damage_model == m).any()]
    groups = [g for g in GROUP_TITLES if (chunk.file_type == g).any()]
    fig, axes = plt.subplots(len(models), len(groups), figsize=(4.4 * len(groups),
                             3.0 * len(models) + 0.6), sharex=True, sharey=True,
                             squeeze=False)  # fmt: skip
    for r, model in enumerate(models):
        for c, g in enumerate(groups):
            ax = axes[r][c]
            _auroc_lines(ax, chunk[(chunk.damage_model == model) & (chunk.file_type == g)], True)
            ax.set_title(f"{DAMAGE_LABELS[model].capitalize()}: {GROUP_TITLES[g]}", fontsize=9)
        axes[r][0].set_ylabel("Chunk AUROC")
    for ax in axes[-1]:
        ax.set_xlabel("Damaged bytes per file")
    axes[0][0].set_ylim(0.45, 1.01)
    handles, labels = axes[0][0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper right", ncol=3, fontsize=8)
    fig.suptitle("Detector AUROC vs damaged fraction", x=0.01, ha="left", fontsize=10,
                 fontweight="bold")  # fmt: skip
    _footnote(fig, chunk, "  |  grey dashed line: chance")
    fig.tight_layout(rect=(0, 0.03, 1, 0.95))
    path = out / "auroc_vs_fraction.png"
    fig.savefig(path, dpi=200)
    plt.close(fig)
    return path


def plot_auroc_by_type(auroc: pd.DataFrame, out: Path, damage_model: str = "striped") -> Path:
    """Small multiples: one panel per file type (shared axes), one line per detector variant."""
    apply_style()
    chunk = auroc[(auroc.level == "chunk") & (auroc.damage_model == damage_model)]
    types = sorted(t for t in chunk.file_type.unique() if not t.startswith("WAVG_"))
    ncol = min(5, len(types))
    nrow = -(-len(types) // ncol)
    fig, axes = plt.subplots(nrow, ncol, figsize=(2.3 * ncol, 2.1 * nrow + 0.7), sharex=True,
                             sharey=True, squeeze=False)  # fmt: skip
    for ax, t in zip(axes.flat, types, strict=False):
        _auroc_lines(ax, chunk[chunk.file_type == t], label_ends=False)
        ax.set_title(t, fontsize=9)
    for ax in axes.flat[len(types) :]:
        ax.set_visible(False)
    axes[0][0].set_ylim(0.45, 1.01)
    for ax in axes[:, 0]:
        ax.set_ylabel("AUROC")
    for ax in axes[-1, :]:
        ax.set_xlabel("Damaged bytes")
    handles, labels = axes[0][0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper right", ncol=3, fontsize=8)
    fig.suptitle(f"Chunk AUROC per file type: {DAMAGE_LABELS[damage_model]}", x=0.01,
                 ha="left", fontsize=10, fontweight="bold")  # fmt: skip
    _footnote(fig, chunk)
    fig.tight_layout(rect=(0, 0.03, 1, 0.93))
    path = out / f"auroc_by_type_{damage_model}.png"
    fig.savefig(path, dpi=200)
    plt.close(fig)
    return path


def plot_recovery_vs_fraction(df: pd.DataFrame, out: Path) -> Path:
    """Headline: clean recovery rate vs damage fraction, one line per retention policy."""
    apply_style()
    fig, ax = plt.subplots(figsize=(5.2, 3.4))
    g = df.groupby(["policy", "damage_fraction"], as_index=False)["clean_recovery"].mean()
    for i, (pol, sub) in enumerate(g.groupby("policy")):
        sub = sub.sort_values("damage_fraction")
        c = series_color(pol, i)
        ax.plot(sub["damage_fraction"] * 100, sub["clean_recovery"], marker="o", color=c, label=pol)
        last = sub.iloc[-1]
        ax.annotate(
            pol,
            (last["damage_fraction"] * 100, last["clean_recovery"]),
            xytext=(6, 0),
            textcoords="offset points",
            va="center",
            color=INK_2,
        )
    ax.set_xscale("log")
    ax.set_xlabel("Damaged fraction of each file (%)")
    ax.set_ylabel("Clean recovery rate")
    ax.set_ylim(-0.03, 1.05)
    src = ", ".join(sorted(set(df["benign_source"]) | set(df["damage_source"])))
    ax.set_title(f"Clean recovery vs damage fraction  (data: {src})")
    ax.legend(loc="lower right")
    fig.tight_layout()
    path = out / "recovery_vs_fraction.png"
    fig.savefig(path, dpi=200)
    plt.close(fig)
    return path


# ---- M2: start-day inference ------------------------------------------------------------

COMBO_ORDER = [
    ("single_cp", "exceed"),
    ("single_cp", "trimmed_mean"),
    ("bocpd", "exceed"),
    ("bocpd", "trimmed_mean"),
]
COMBO_LABEL = {
    ("single_cp", "exceed"): "single-CP, exceedances",
    ("single_cp", "trimmed_mean"): "single-CP, trimmed mean",
    ("bocpd", "exceed"): "BOCPD, exceedances",
    ("bocpd", "trimmed_mean"): "BOCPD, trimmed mean",
}
TARGET_TITLE = {
    "all": "Attacker damages any file type",
    "high_entropy": "Attacker damages high-entropy types only",
}


def plot_start_accuracy(df: pd.DataFrame, p_win: float, out: Path, delay: int = 14) -> Path:
    """Posterior mass within +-3 days of the true start vs damage fraction.

    Rows: detector. Columns: attacker target set. One line per (start model, statistic).
    """
    from slowburn.bench.plotstyle import CATEGORICAL

    apply_style()
    a = df[(df.attack == 1) & np.isclose(df.p_attack_within_window, p_win)
           & (df.discovery_delay == delay)]  # fmt: skip
    dets = [d for d in DETECTOR_ORDER if (a.detector == d).any()]
    targets = [t for t in ("all", "high_entropy") if (a.attack_target_types == t).any()]
    fig, axes = plt.subplots(len(dets), len(targets), figsize=(4.4 * len(targets),
                             2.9 * len(dets) + 0.8), sharex=True, sharey=True,
                             squeeze=False)  # fmt: skip
    for r, det in enumerate(dets):
        for c, tgt in enumerate(targets):
            ax = axes[r][c]
            sub = a[(a.detector == det) & (a.attack_target_types == tgt)]
            for slot, combo in enumerate(COMBO_ORDER):
                s = sub[(sub.model == combo[0]) & (sub.statistic == combo[1])]
                if s.empty:
                    continue
                g = s.groupby("damage_fraction").mass_within_3.agg(["mean", "sem"]).sort_index()
                x, col = g.index.to_numpy() * 100, CATEGORICAL[slot]
                sem = g["sem"].fillna(0)
                ax.fill_between(x, g["mean"] - sem, g["mean"] + sem, color=col, alpha=0.15, lw=0)
                ax.plot(x, g["mean"], marker="o", color=col, label=COMBO_LABEL[combo])
            _fraction_axis(ax)
            short = {"all": "any file type", "high_entropy": "high-entropy types only"}
            title = f"{DETECTOR_LABELS.get(det, det)}\nattacker damages {short.get(tgt, tgt)}"
            ax.set_title(title, fontsize=8.5)
        axes[r][0].set_ylabel(f"Mass within ±3 days\n(day +{delay})")
    for ax in axes[-1]:
        ax.set_xlabel("Damaged bytes per file (striped)")
    axes[0][0].set_ylim(-0.02, 1.02)
    handles, labels = axes[0][0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper right", ncol=2, fontsize=8)
    fig.suptitle("Attack start-day recovery", x=0.01, ha="left", fontsize=10, fontweight="bold")
    fig.text(0.01, 0.01, f"{_source_tag(a)}  |  P(attack within 60 d) = {p_win}  |  "
             "shaded: ±1 s.e. over machines", color=MUTED, fontsize=7, ha="left",
             va="bottom")  # fmt: skip
    fig.tight_layout(rect=(0, 0.03, 1, 0.92))
    path = out / f"start_accuracy_vs_fraction_p{p_win}.png"
    fig.savefig(path, dpi=200)
    plt.close(fig)
    return path


def plot_example_trace(traces: pd.DataFrame, out: Path, fraction: float, target: str,
                       p_win: float, true_start: int) -> Path | None:  # fmt: skip
    """P(attack started) day by day on one example machine, per detector and start model."""
    from slowburn.bench.plotstyle import CATEGORICAL

    t = traces[np.isclose(traces.damage_fraction, fraction) & (traces.attack_target_types == target)
               & (traces.statistic == "exceed")
               & np.isclose(traces.p_attack_within_window, p_win)]  # fmt: skip
    if t.empty:
        return None
    apply_style()
    fig, ax = plt.subplots(figsize=(6.4, 3.4))
    slot = 0
    for det in DETECTOR_ORDER:
        for kind in ("single_cp", "bocpd"):
            s = t[(t.detector == det) & (t.model == kind)].sort_values("day")
            if s.empty:
                continue
            ls = "-" if kind == "single_cp" else (0, (4, 2))
            ax.plot(s.day, s.p_started, color=CATEGORICAL[slot], ls=ls,
                    label=f"{DETECTOR_LABELS.get(det, det)}, {kind}")  # fmt: skip
            slot += 1
    ax.axvline(true_start, color=MUTED, lw=1, ls=(0, (3, 3)))
    ax.annotate("true start", (true_start, 1.0), xytext=(3, -10), textcoords="offset points",
                color=MUTED, fontsize=8)  # fmt: skip
    ax.set_ylim(-0.02, 1.02)
    ax.set_xlabel("Day")
    ax.set_ylabel("P(attack started)")
    ax.legend(loc="center left", fontsize=7)
    fig.suptitle(f"Example machine: striped {fraction:.0%}, targets {target}, "
                 f"P(attack within 60 d) = {p_win}", x=0.01, ha="left", fontsize=9.5,
                 fontweight="bold")  # fmt: skip
    fig.tight_layout()
    path = out / f"example_trace_f{int(fraction * 100)}_{target}_p{p_win}.png"
    fig.savefig(path, dpi=200)
    plt.close(fig)
    return path
