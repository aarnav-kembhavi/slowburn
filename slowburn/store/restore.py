"""Selective restore at discovery time, and its ground-truth evaluation.

Inputs are per-file version histories: for every file, the day each new version appeared and
whether that change was the damaging one. Snapshot j holds, for every file, its newest version
with day <= j.

Restore rule (shared by every retention policy, so retention is the only variable):
    s_hat = lower ``quantile`` of the start posterior given that an attack happened
    j_r   = newest kept snapshot with day < s_hat (oldest kept snapshot if there is none)
    every file with a change on a day >= s_hat is restored to its version in snapshot j_r;
    all other files stay at their current version.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

HOURS_PER_DAY = 24


@dataclass(frozen=True)
class FileHistory:
    change_days: tuple[int, ...]  # days on which the file got a new version (day 0 = creation)
    damaged_day: int | None  # day of the damaging change, None if never damaged


def lower_quantile_start(post: np.ndarray, quantile: float) -> int:
    """Smallest day s with P(start <= s | started) >= quantile. ``post`` covers days 0..t plus a
    final 'not started' entry, which is dropped (discovery means an attack happened)."""
    started = np.asarray(post[:-1], float)
    total = started.sum()
    if total <= 0:
        return len(started) - 1  # no evidence of a start at all: most recent day
    cdf = np.cumsum(started / total)
    return int(np.searchsorted(cdf, quantile - 1e-12))


def version_day_at(h: FileHistory, day: int) -> int:
    """Day of the file's version held in a snapshot taken at the end of ``day``."""
    v = [d for d in h.change_days if d <= day]
    return max(v) if v else -1


def selective_restore(
    kept_days: Sequence[int],
    post: np.ndarray,
    discovery_day: int,
    histories: dict[str, FileHistory],
    true_start: int,
    quantile: float,
) -> dict:
    kept = sorted(kept_days)
    s_hat = lower_quantile_start(post, quantile)
    before = [j for j in kept if j < s_hat]
    j_r = max(before) if before else kept[0]
    residual, lost_file_days, restored = 0, 0, 0
    for h in histories.values():
        changed_after_estimate = any(d >= s_hat for d in h.change_days if d <= discovery_day)
        if changed_after_estimate:
            restored += 1
            v = version_day_at(h, j_r)
            dirty = h.damaged_day is not None and h.damaged_day <= v
            # benign versions discarded: changes after the restored version, excluding damage
            lost_file_days += sum(1 for d in h.change_days
                                  if v < d <= discovery_day and d != h.damaged_day)  # fmt: skip
        else:
            dirty = h.damaged_day is not None and h.damaged_day <= discovery_day
        residual += int(dirty)
    clean = residual == 0
    whole_clean = j_r < true_start
    worst = discovery_day * HOURS_PER_DAY  # unrecovered: everything since day 0 is suspect
    return {
        "restore_point": j_r,
        "estimated_start": s_hat,
        "restore_point_clean": int(whole_clean),
        "files_restored": restored,
        "residual_damaged_files": residual,
        "clean_recovery": int(clean),
        "work_lost_selective_file_hours": lost_file_days * HOURS_PER_DAY,
        "work_lost_whole_system_hours": (
            (discovery_day - j_r) * HOURS_PER_DAY if whole_clean else worst
        ),  # fmt: skip
        "start_gap_days": (true_start - 1 - j_r) if whole_clean else None,
    }


def snapshots_scanned(kept_days: Sequence[int], true_start: int,
                      first_choice: int | None = None) -> int | None:  # fmt: skip
    """Snapshots an operator with a perfect cleanliness check inspects before finding a clean
    one: starting from ``first_choice`` (default: newest) and moving to older snapshots."""
    order = sorted(kept_days, reverse=True)
    if first_choice is not None and first_choice in order:
        i = order.index(first_choice)
        order = order[i:] + order[:i][::-1]
    for n, j in enumerate(order, start=1):
        if j < true_start:
            return n
    return None
