"""Benchmark figures."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from slowburn.bench.plotstyle import INK_2, apply_style, series_color


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
