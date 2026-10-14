"""DEV-only hyperparameter selection with pre-registered rules (OPEN_QUESTIONS.md).

Each rule is a pure function of a results table, so the choice is reproducible and auditable.
"""

from __future__ import annotations

import re

import numpy as np
import pandas as pd


def statistic_rule(
    df: pd.DataFrame,
    model: str = "single_cp",
    delay: int = 14,
    max_clean_fa: float = 0.05,
    tie: float = 0.01,
) -> tuple[pd.DataFrame, str]:
    """Rule D24. Returns (scoreboard, chosen statistic name).

    score       mean mass within +-3 days at ``delay`` over all attack cells
    clean_fa    mean rate of P(started) > 0.5 at ``delay`` on clean machines
    """
    if set(df.split) != {"dev"}:
        raise ValueError("tuning must use DEV machines only")
    d = df[(df.model == model) & (df.discovery_delay == delay)]
    att, cln = d[d.attack == 1], d[d.attack == 0]
    cells = ["detector", "damage_fraction", "attack_target_types", "benign_invalid_rate"]
    per_cell = att.groupby(["statistic", *cells]).mass_within_3.mean()
    board = pd.DataFrame({
        "score": per_cell.groupby("statistic").mean(),
        "n_cells": per_cell.groupby("statistic").size(),
        "clean_fa": cln.groupby(["statistic", "detector", "benign_invalid_rate"])
        .false_alarm_p05.mean().groupby("statistic").mean(),
        "late_gt3": att.groupby("statistic").map_signed_error_days.apply(
            lambda v: float((v > 3).mean())),
        "missed": att.groupby("statistic").missed.mean(),
    })  # fmt: skip
    board["alpha"] = [_alpha_of(s) for s in board.index]
    board["eligible"] = board.clean_fa <= max_clean_fa
    elig = board[board.eligible]
    if elig.empty:
        raise ValueError("no candidate meets the clean false-alarm constraint")
    best = elig.score.max()
    near = elig[elig.score >= best - tie]
    choice = near.sort_values("alpha").index[0]  # ties: smaller alpha
    return board.sort_values("score", ascending=False), str(choice)


def _alpha_of(name: str) -> float:
    m = re.search(r"a([0-9.]+)$", name)
    return float(m.group(1)) if m else np.nan
