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
