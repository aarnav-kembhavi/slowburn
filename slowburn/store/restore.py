"""Selective restore at discovery time, and its ground-truth evaluation.

Inputs are per-file version histories: for every file, the day each new version appeared and
whether that change was the damaging one. Snapshot j holds, for every file, its newest version
with day <= j.

Two restore rules, each shared by every retention policy (retention is the only variable):

``verified_restore`` (primary, decision D29): restore-time verification.
    P_clean(j) = P(start > j | evidence, an attack happened)
    L          = lower ``scan_eps`` quantile of the start posterior (versions older than L are
                 treated as clean and are not re-scanned)
    walk the kept snapshots newest first, skipping those with P_clean(j) < ``gate``; for each
    candidate run the detector on its file versions written on or after L; restore from the
    first candidate with no flagged version. If none verifies, fall back to the oldest kept
    snapshot. Every file with a change on a day >= max(j_r + 1, L) is restored to its version
    in snapshot j_r; all other files stay at their current version.
    The detector is deterministic: re-scanning a version gives the flag it got when it was
    written (``FileHistory.flagged_days``), so a missed damaged version stays missed.

``selective_restore`` (ablation: the earlier fixed-quantile rule).
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
    # days whose new version the detector flags (damaged and detected, or failing validation)
    flagged_days: frozenset[int] = frozenset()


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


def _restore_files(histories, j_r, s_sel, discovery_day):
    """Restore every file changed on a day >= s_sel to its version in snapshot j_r."""
    residual, lost_file_days, restored = 0, 0, 0
    for h in histories.values():
        if any(d >= s_sel for d in h.change_days if d <= discovery_day):
            restored += 1
            v = version_day_at(h, j_r)
            dirty = h.damaged_day is not None and h.damaged_day <= v
            # benign versions discarded: changes after the restored version, excluding damage
            lost_file_days += sum(1 for d in h.change_days
                                  if v < d <= discovery_day and d != h.damaged_day)  # fmt: skip
        else:
            dirty = h.damaged_day is not None and h.damaged_day <= discovery_day
        residual += int(dirty)
    return residual, lost_file_days, restored


def _outcome(j_r, true_start, discovery_day, residual, lost_file_days, restored) -> dict:
    whole_clean = j_r < true_start
    worst = discovery_day * HOURS_PER_DAY  # unrecovered: everything since day 0 is suspect
    return {
        "restore_point": j_r,
        "restore_point_clean": int(whole_clean),
        "files_restored": restored,
        "residual_damaged_files": residual,
        "clean_recovery": int(residual == 0),
        "work_lost_selective_file_hours": lost_file_days * HOURS_PER_DAY,
        "work_lost_whole_system_hours": (
            (discovery_day - j_r) * HOURS_PER_DAY if whole_clean else worst
        ),  # fmt: skip
        "start_gap_days": (true_start - 1 - j_r) if whole_clean else None,
    }


def p_clean(post: np.ndarray, days) -> np.ndarray:
    """P(start > j | evidence, started) for each day j (``post`` as in lower_quantile_start)."""
    started = np.asarray(post[:-1], float)
    total = started.sum()
    if total <= 0:
        return np.ones(len(np.atleast_1d(days)))
    cdf = np.cumsum(started / total)
    d = np.asarray(days, int)
    return np.where(d >= len(cdf), 0.0, 1.0 - cdf[np.clip(d, 0, len(cdf) - 1)])


def verified_restore(
    kept_days: Sequence[int],
    post: np.ndarray,
    discovery_day: int,
    histories: dict[str, FileHistory],
    true_start: int,
    gate: float,
    scan_eps: float = 0.001,
) -> dict:
    kept = sorted(kept_days)
    L = lower_quantile_start(post, scan_eps)
    pc = p_clean(post, kept)
    candidates = [
        j for j, p in sorted(zip(kept, pc, strict=True), reverse=True) if p >= gate - 1e-12
    ]
    j_r, scanned, files_scanned, verified = kept[0], 0, 0, 0
    for j in candidates:
        scanned += 1
        flagged = False
        for h in histories.values():
            v = version_day_at(h, j)
            if v >= L:
                files_scanned += 1
                flagged |= v in h.flagged_days
        if not flagged:
            j_r, verified = j, 1
            break
    s_sel = max(j_r + 1, L)
    out = _outcome(j_r, true_start, discovery_day, *_restore_files(histories, j_r, s_sel,
                                                                    discovery_day))  # fmt: skip
    # the restore point the DP's loss assumes: newest gated kept snapshot that is truly clean
    model = [j for j in candidates if j < true_start]
    model_point = max(model) if model else kept[0]
    return {**out, "estimated_start": L, "verified": verified, "snapshots_scanned": scanned,
            "files_scanned": files_scanned, "gate_candidates": len(candidates),
            "restore_matches_dp_model": int(j_r == model_point)}  # fmt: skip


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
    out = _outcome(j_r, true_start, discovery_day, *_restore_files(histories, j_r, s_hat,
                                                                    discovery_day))  # fmt: skip
    return {**out, "estimated_start": s_hat}


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
