"""Shared figure style: one palette and chrome for every plot in the paper.

Categorical slots follow a fixed, CVD-validated order (never cycled); a series keeps its colour
across all figures via ``series_color``. More than eight series must be faceted, not recoloured.
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

CATEGORICAL = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7",
               "#e34948"]  # fmt: skip
INK = "#0b0b0b"
INK_2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"
SURFACE = "#fcfcfb"

# stable entity -> slot assignments so colours never depend on plotting order
FIXED_SLOTS = {
    "striped": 0,
    "whole": 1,
    "slowburn_dp": 0,
    "keep_last_n": 1,
    "gfs": 2,
    "threshold_vault": 3,
    "amoeba_style": 4,
    "oracle": 5,
}


def series_color(name: str, fallback_index: int = 0) -> str:
    return CATEGORICAL[FIXED_SLOTS.get(name, fallback_index) % len(CATEGORICAL)]


def apply_style() -> None:
    plt.rcParams.update(
        {
            "figure.facecolor": SURFACE,
            "axes.facecolor": SURFACE,
            "savefig.facecolor": SURFACE,
            "font.family": ["Segoe UI", "DejaVu Sans", "sans-serif"],
            "font.size": 9,
            "text.color": INK,
            "axes.labelcolor": INK_2,
            "axes.edgecolor": AXIS,
            "axes.titlecolor": INK,
            "axes.titlesize": 10,
            "axes.titleweight": "bold",
            "axes.titlelocation": "left",
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.grid": True,
            "axes.grid.axis": "y",
            "grid.color": GRID,
            "grid.linewidth": 0.6,
            "xtick.color": MUTED,
            "ytick.color": MUTED,
            "lines.linewidth": 2.0,
            "lines.markersize": 5,
            "legend.frameon": False,
            "legend.labelcolor": INK_2,
        }
    )
