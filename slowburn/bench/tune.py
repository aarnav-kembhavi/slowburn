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
    # ties (D24 v2): the file statistic first, then the smaller alpha
    near = near.assign(is_chunk=[not str(i).startswith("file") for i in near.index])
    choice = near.sort_values(["is_chunk", "alpha"]).index[0]
    return board.sort_values("score", ascending=False), str(choice)


def _alpha_of(name: str) -> float:
    m = re.search(r"a([0-9.]+)$", name)
    return float(m.group(1)) if m else np.nan


SHARED_STAGE_POLICIES = ("keep_last_n", "gfs", "tower_of_hanoi", "threshold_vault",
                         "prior_only", "slowburn")  # fmt: skip


def _pick(board: pd.DataFrame, tie: float) -> tuple:
    best = board.clean_recovery.max()
    near = board[board.clean_recovery >= best - tie]
    return near.sort_values("work_lost_whole_system_hours").index[0]


def retention_stage1(df: pd.DataFrame, tie: float = 0.005) -> tuple[pd.DataFrame, tuple]:
    """Rule D30 stage 1: (p_attack_within_window, restore gate) maximising mean clean recovery
    over all snapshot baselines except the oracle, averaged over every scenario-grid cell."""
    if set(df.split) != {"dev"}:
        raise ValueError("tuning must use DEV machines only")
    d = df[df.policy.isin(SHARED_STAGE_POLICIES)]
    board = d.groupby(["hp_p_attack_within_window", "hp_gate"]).agg(
        clean_recovery=("clean_recovery", "mean"),
        work_lost_whole_system_hours=("work_lost_whole_system_hours", "mean"),
        n=("clean_recovery", "size"))  # fmt: skip
    return board.sort_values("clean_recovery", ascending=False), _pick(board, tie)


def retention_stage2(df: pd.DataFrame, tie: float = 0.005) -> tuple[pd.DataFrame, tuple]:
    """Rule D30 stage 2: (penalty, assumed discovery max days, backbone fraction) maximising
    SlowBurn's mean clean recovery over every scenario-grid cell."""
    if set(df.split) != {"dev"}:
        raise ValueError("tuning must use DEV machines only")
    d = df[df.policy == "slowburn"]
    board = d.groupby(["hp_penalty", "hp_assumed_discovery_max", "hp_backbone"]).agg(
        clean_recovery=("clean_recovery", "mean"),
        work_lost_whole_system_hours=("work_lost_whole_system_hours", "mean"),
        n=("clean_recovery", "size"))  # fmt: skip
    return board.sort_values("clean_recovery", ascending=False), _pick(board, tie)
