"""Benchmark figures."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
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


def _auroc_lines(ax, sub: pd.DataFrame, label_ends: bool) -> None:
    ax.axhline(0.5, color=MUTED, lw=1, ls=(0, (3, 3)))
    for i, model in enumerate(["striped", "whole"]):
        s = sub[sub.damage_model == model].sort_values("fraction")
        if s.empty:
            continue
        x, c = s.fraction * 100, series_color(model, i)
        if s.ci_low.notna().any():
            ax.fill_between(x, s.ci_low, s.ci_high, color=c, alpha=0.15, lw=0)
        ax.plot(x, s.auroc, marker="o", color=c, label=DAMAGE_LABELS[model])
        if label_ends:
            first = s.iloc[0]
            ax.annotate(
                f"{first.auroc:.2f}",
                (first.fraction * 100, first.auroc),
                xytext=(-6, 0),
                textcoords="offset points",
                ha="right",
                va="center",
                color=INK_2,
                fontsize=8,
            )
    _fraction_axis(ax)


def _source_tag(df: pd.DataFrame) -> str:
    srcs = sorted(set(df.benign_source) | set(df.damage_source))
    return "benign + damage data: " + ", ".join(srcs)


def _footnote(fig, df: pd.DataFrame) -> None:
    fig.text(
        0.01,
        0.01,
        _source_tag(df) + "  |  shaded: 95% file-cluster bootstrap CI",
        color=MUTED,
        fontsize=7,
        ha="left",
        va="bottom",
    )


def plot_auroc_vs_fraction(auroc: pd.DataFrame, out: Path) -> Path:
    """Phase I headline: chunk-level AUROC vs damaged fraction, all types vs hard negatives."""
    apply_style()
    chunk = auroc[auroc.level == "chunk"]
    panels = [
        ("ALL", "All file types"),
        ("HIGH_ENTROPY", "High-entropy types only (docx, zip, png, jpg, mp3, zlib, lzma)"),
    ]
    panels = [p for p in panels if (chunk.file_type == p[0]).any()]
    fig, axes = plt.subplots(
        1, len(panels), figsize=(4.4 * len(panels), 3.5), sharey=True, squeeze=False
    )
    for ax, (key, title) in zip(axes[0], panels, strict=True):
        _auroc_lines(ax, chunk[chunk.file_type == key], label_ends=True)
        ax.set_title(title, fontsize=9)
        ax.set_xlabel("Damaged bytes per file")
    axes[0][0].set_ylabel("Chunk-level AUROC (95% CI)")
    axes[0][0].set_ylim(0.45, 1.01)
    axes[0][0].annotate(
        "chance",
        (110, 0.5),
        xytext=(0, 3),
        textcoords="offset points",
        ha="right",
        va="bottom",
        color=MUTED,
        fontsize=8,
    )
    handles, labels = axes[0][0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper right", ncol=2, fontsize=8)
    fig.suptitle(
        "Detector AUROC vs damaged fraction",
        x=0.01,
        ha="left",
        fontsize=10,
        fontweight="bold",
    )
    _footnote(fig, chunk)
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    path = out / "auroc_vs_fraction.png"
    fig.savefig(path, dpi=200)
    plt.close(fig)
    return path


def plot_auroc_by_type(auroc: pd.DataFrame, out: Path) -> Path:
    """Small multiples: one panel per file type (shared axes), both damage placements."""
    apply_style()
    chunk = auroc[auroc.level == "chunk"]
    groups = {"ALL", "HIGH_ENTROPY", "LOW_ENTROPY"}
    types = sorted(t for t in chunk.file_type.unique() if t not in groups)
    ncol = min(5, len(types))
    nrow = -(-len(types) // ncol)
    fig, axes = plt.subplots(
        nrow, ncol, figsize=(2.3 * ncol, 2.1 * nrow + 0.6), sharex=True, sharey=True, squeeze=False
    )
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
    fig.legend(handles, labels, loc="upper right", ncol=2, fontsize=8)
    fig.suptitle(
        "Chunk AUROC per file type",
        x=0.01,
        ha="left",
        fontsize=10,
        fontweight="bold",
    )
    _footnote(fig, chunk)
    fig.tight_layout(rect=(0, 0.03, 1, 0.97))
    path = out / "auroc_by_type.png"
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


def plot_start_accuracy(df: pd.DataFrame, hazard: float, out: Path, delay: int = 14) -> Path:
    """Posterior mass within +-3 days of the true start vs damage fraction, per model."""
    from slowburn.bench.plotstyle import CATEGORICAL

    apply_style()
    a = df[(df.attack == 1) & (df.hazard == hazard) & (df.discovery_delay == delay)]
    targets = [t for t in ("all", "high_entropy") if (a.attack_target_types == t).any()]
    fig, axes = plt.subplots(
        1, len(targets), figsize=(4.4 * len(targets), 3.5), sharey=True, squeeze=False
    )
    for ax, tgt in zip(axes[0], targets, strict=True):
        sub = a[a.attack_target_types == tgt]
        for slot, combo in enumerate(COMBO_ORDER):
            s = sub[(sub.model == combo[0]) & (sub.statistic == combo[1])]
            if s.empty:
                continue
            g = s.groupby("damage_fraction").mass_within_3.agg(["mean", "sem"]).sort_index()
            x, c = g.index.to_numpy() * 100, CATEGORICAL[slot]
            ax.fill_between(
                x,
                g["mean"] - g["sem"].fillna(0),
                g["mean"] + g["sem"].fillna(0),
                color=c,
                alpha=0.15,
                lw=0,
            )
            ax.plot(x, g["mean"], marker="o", color=c, label=COMBO_LABEL[combo])
        _fraction_axis(ax)
        ax.set_title(TARGET_TITLE.get(tgt, tgt), fontsize=9)
        ax.set_xlabel("Damaged bytes per file (striped)")
    axes[0][0].set_ylabel(f"Posterior mass within ±3 days\nof true start (day +{delay})")
    axes[0][0].set_ylim(-0.02, 1.02)
    handles, labels = axes[0][0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper right", ncol=2, fontsize=8)
    fig.suptitle("Attack start-day recovery", x=0.01, ha="left", fontsize=10, fontweight="bold")
    fig.text(
        0.01,
        0.01,
        f"{_source_tag(a)}  |  hazard {hazard}  |  shaded: ±1 s.e. over reps",
        color=MUTED,
        fontsize=7,
        ha="left",
        va="bottom",
    )
    fig.tight_layout(rect=(0, 0.04, 1, 0.9))
    path = out / "start_accuracy_vs_fraction.png"
    fig.savefig(path, dpi=200)
    plt.close(fig)
    return path


def plot_example_trace(
    trace: pd.DataFrame,
    out: Path,
    fraction: float = 0.1,
    target: str = "all",
    true_start: int | None = None,
) -> Path | None:
    """Daily exceedance rate (top) and the start posterior at discovery (bottom), one machine."""
    from slowburn.bench.plotstyle import CATEGORICAL

    t = trace[(trace.damage_fraction == fraction) & (trace.attack_target_types == target)
              & (trace.statistic == "exceed")]  # fmt: skip
    if t.empty:
        return None
    apply_style()
    fig, (top, bot) = plt.subplots(
        2, 1, figsize=(6.4, 4.6), sharex=True, gridspec_kw={"height_ratios": [1, 1]}
    )
    first = t[t.model == t.model.iloc[0]]
    top.plot(first.day, first.value, color=INK_2, lw=1.2, marker="o", ms=3)
    top.set_ylabel("Exceedance rate k/n")
    for slot, kind in ((0, "single_cp"), (2, "bocpd")):
        s = t[t.model == kind]
        if not s.empty:
            label = (
                COMBO_LABEL[(kind, "exceed")] + f"  (P(not started) {s.p_not_started.iloc[0]:.3f})"
            )
            bot.plot(s.day, s.posterior, color=CATEGORICAL[slot], label=label)
    bot.set_ylabel("P(start = day)")
    bot.set_xlabel("Day")
    for ax in (top, bot):
        if true_start is not None:
            ax.axvline(true_start, color=MUTED, lw=1, ls=(0, (3, 3)))
    if true_start is not None:
        top.annotate(
            "true start",
            (true_start, top.get_ylim()[1]),
            xytext=(3, -10),
            textcoords="offset points",
            color=MUTED,
            fontsize=8,
        )
    bot.legend(loc="upper right", fontsize=8)
    fig.suptitle(
        f"Example machine: striped damage {fraction:.0%}, targets: {target}",
        x=0.01,
        ha="left",
        fontsize=10,
        fontweight="bold",
    )
    fig.tight_layout()
    path = out / f"example_trace_f{int(fraction * 100)}_{target}.png"
    fig.savefig(path, dpi=200)
    plt.close(fig)
    return path
