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


def write_flag(fid: str, h: FileHistory, v: int) -> bool:
    """The flag version ``v`` got from the daily detector when it was written (D29)."""
    return v in h.flagged_days


def _restore_files(histories, j_r, s_sel, discovery_day, flag=None):
    """Restore every file changed on a day >= s_sel to its version in snapshot j_r (and, with a
    ``flag`` function, every file whose current version is flagged and newer than j_r)."""
    residual, lost_file_days, restored = 0, 0, 0
    for fid, h in histories.items():
        cur = version_day_at(h, discovery_day)
        if any(d >= s_sel for d in h.change_days if d <= discovery_day) or (
            flag is not None and cur > j_r and flag(fid, h, cur)
        ):
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
    old_flags: str = "skip",
    accept_test: tuple | None = None,
) -> dict:
    """``old_flags``: "skip" = D29 as pre-registered; D62 diagnostics: "select" also restores
    files whose current version is flagged, "verify" additionally rejects a candidate holding any
    flagged version newer than the oldest kept snapshot; "verify_snap" (D64a) scans EVERY version
    in the candidate and selects as "select". Flags are the per-version detector draws made when
    each version was written (one draw per version, shared with the daily evidence).
    ``accept_test`` = (null_prior, alpha), method v2.1 (D65, verify_snap only): a candidate is
    rejected only if its flag count over every version it holds is significant under the D60
    test (``deep_damage``), instead of on any flag."""
    if old_flags not in ("skip", "select", "verify", "verify_snap"):
        raise ValueError(f"unknown old_flags {old_flags!r}")
    if accept_test is not None and old_flags != "verify_snap":
        raise ValueError("the D65 accept test applies to verify_snap only")
    kept = sorted(kept_days)
    L = lower_quantile_start(post, scan_eps)
    pc = p_clean(post, kept)
    candidates = [
        j for j, p in sorted(zip(kept, pc, strict=True), reverse=True) if p >= gate - 1e-12
    ]
    j_r, scanned, files_scanned, verified = kept[0], 0, 0, 0
    for j in candidates:
        scanned += 1
        if accept_test is not None:
            flagged, _, n = deep_damage(histories, j, -1, *accept_test)
            files_scanned += n
            if not flagged:
                j_r, verified = j, 1
                break
            continue
        flagged = False
        for h in histories.values():
            v = version_day_at(h, j)
            if (v >= L or (old_flags == "verify" and v > kept[0])
                    or (old_flags == "verify_snap" and v >= 0)):  # fmt: skip
                files_scanned += 1
                flagged |= v in h.flagged_days
        if not flagged:
            j_r, verified = j, 1
            break
    s_sel = max(j_r + 1, L)
    out = _outcome(j_r, true_start, discovery_day,
                   *_restore_files(histories, j_r, s_sel, discovery_day,
                                   None if old_flags == "skip" else write_flag))  # fmt: skip
    # the restore point the DP's loss assumes: newest gated kept snapshot that is truly clean
    model = [j for j in candidates if j < true_start]
    model_point = max(model) if model else kept[0]
    # measured gate (P0): newest day the gate admits, and the clean probability of the restore
    ok = np.flatnonzero(p_clean(post, np.arange(discovery_day + 1)) >= gate - 1e-12)
    return {**out, "estimated_start": L, "verified": verified, "snapshots_scanned": scanned,
            "files_scanned": files_scanned, "gate_candidates": len(candidates),
            "gate_day": int(ok[-1]) if len(ok) else -1,
            "restore_p_clean": float(p_clean(post, [j_r])[0]),
            "restore_matches_dp_model": int(j_r == model_point)}  # fmt: skip


def deep_damage(histories: dict[str, FileHistory], j: int, j0: int, null_prior: tuple,
                alpha: float, flag=write_flag) -> tuple[bool, int, int]:  # fmt: skip
    """Method v4 deep check (D60) of snapshot ``j``: scan every version it holds written after
    the oldest kept snapshot ``j0``; damage is found iff the flag count exceeds the benign rate,
    one-sided Beta-Binomial tail with the fleet-pooled benign prior ``null_prior`` < ``alpha``.
    Returns (damage found, flagged, scanned)."""
    from scipy import stats

    x = n = 0
    for fid, h in histories.items():
        v = version_day_at(h, j)
        if v > j0:
            n += 1
            x += flag(fid, h, v)
    if x == 0:
        return False, 0, n
    a0, b0 = null_prior
    return bool(stats.betabinom.sf(x - 1, n, a0, b0) < alpha), x, n


def walkback_restore(
    kept_days: Sequence[int],
    post: np.ndarray,
    discovery_day: int,
    histories: dict[str, FileHistory],
    true_start: int,
    gate: float,
    null_prior: tuple,
    alpha: float = 0.05,
    scan_eps: float = 0.001,
    old_flags: str = "skip",
    accept_test: tuple | None = None,
) -> dict:
    """Method v4 restore (D60): ``verified_restore`` on the hard-bound posterior ``post`` gives
    j_v2; while the deep check finds damage at the restore point, step to the next older kept
    snapshot (the oldest kept one ends the walk). If the point moved, every file changed after
    it is restored."""
    r = verified_restore(kept_days, post, discovery_day, histories, true_start, gate, scan_eps,
                         old_flags, accept_test)  # fmt: skip
    kept = sorted(kept_days)
    j_r, j0 = r["restore_point"], kept[0]
    older = [j for j in reversed(kept) if j < j_r]
    steps, files = 0, 0
    while j_r != j0:
        found, _, n = deep_damage(histories, j_r, j0, null_prior, alpha)
        files += n
        if not found:
            break
        j_r = older[steps]
        steps += 1
    out = {**r, "walkback_steps": steps, "walkback_from": r["restore_point"],
           "snapshots_scanned": r["snapshots_scanned"] + steps,
           "files_scanned": r["files_scanned"] + files}  # fmt: skip
    if steps:
        out.update(_outcome(j_r, true_start, discovery_day,
                            *_restore_files(histories, j_r, j_r + 1, discovery_day)))  # fmt: skip
        out["restore_p_clean"] = float(p_clean(post, [j_r])[0])
    return out


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


def resolve_version(retained: Sequence[int], day: int) -> int:
    """Per-file point-in-time restore: the newest retained version written on or before ``day``,
    or the oldest retained version if the product kept none that old."""
    older = [v for v in retained if v <= day]
    return max(older) if older else min(retained)


def point_in_time_restore(
    retained: dict[str, Sequence[int]],
    post: np.ndarray,
    discovery_day: int,
    histories: dict[str, FileHistory],
    true_start: int,
    gate: float,
    scan_eps: float = 0.001,
) -> dict:
    """verify_snap (D64a) for per-file version histories (D66): candidate restore points are
    every day 0..discovery that passes the gate, newest first; at candidate T each file resolves
    to ``resolve_version(retained[f], T)``; a candidate is rejected if any resolved version is
    flagged. Fallback: day 0. Selection ("select") and the accounting are verify_snap's."""
    L = lower_quantile_start(post, scan_eps)
    days = np.arange(discovery_day + 1)
    pc = p_clean(post, days)
    candidates = [int(j) for j in days[::-1] if pc[j] >= gate - 1e-12]
    j_r, scanned, verified = 0, 0, 0
    for j in candidates:
        scanned += 1
        if not any(resolve_version(retained[f], j) in h.flagged_days
                   for f, h in histories.items()):  # fmt: skip
            j_r, verified = j, 1
            break
    s_sel = max(j_r + 1, L)
    residual, lost_file_days, restored = 0, 0, 0
    for f, h in histories.items():
        cur = version_day_at(h, discovery_day)
        if any(d >= s_sel for d in h.change_days if d <= discovery_day) or (
            cur > j_r and write_flag(f, h, cur)
        ):
            restored += 1
            v = resolve_version(retained[f], j_r)
            dirty = h.damaged_day is not None and h.damaged_day <= v
            lost_file_days += sum(1 for d in h.change_days
                                  if v < d <= discovery_day and d != h.damaged_day)  # fmt: skip
        else:
            dirty = h.damaged_day is not None and h.damaged_day <= discovery_day
        residual += int(dirty)
    out = _outcome(j_r, true_start, discovery_day, residual, lost_file_days, restored)
    return {**out, "estimated_start": L, "verified": verified, "snapshots_scanned": scanned,
            "gate_candidates": len(candidates)}  # fmt: skip


def clean_point_held(retained: dict[str, Sequence[int]], histories: dict[str, FileHistory],
                     true_start: int, discovery_day: int) -> int:  # fmt: skip
    """1 if restoring every file to its version at day ``true_start - 1`` (per-file resolution
    over what the product retained) leaves no damaged file."""
    for f, h in histories.items():
        if (h.damaged_day is not None and h.damaged_day <= discovery_day
                and h.damaged_day <= resolve_version(retained[f], true_start - 1)):  # fmt: skip
            return 0
    return 1


def oracle_restore(kept_days: Sequence[int], discovery_day: int,
                   histories: dict[str, FileHistory], true_start: int) -> dict:  # fmt: skip
    """D69 (ii): restore from the newest kept snapshot older than the true start (the oldest kept
    if none), every file changed after it restored. Separates retention quality from restore
    quality: the rollback point is known, as in the online-checkpointing model."""
    kept = sorted(kept_days)
    clean = [j for j in kept if j < true_start]
    j_r = max(clean) if clean else kept[0]
    return _outcome(j_r, true_start, discovery_day,
                    *_restore_files(histories, j_r, j_r + 1, discovery_day))  # fmt: skip


def oracle_file_restore(kept_days: Sequence[int], discovery_day: int,
                        histories: dict[str, FileHistory]) -> dict:  # fmt: skip
    """D71 (c): per-file oracle ceiling. Every file damaged by discovery is restored to the
    newest of its versions held in any kept snapshot that is truly clean (version day < damage
    day); undamaged files are untouched. Recovery fails iff a damaged file has no clean held
    version. Work lost counts the benign versions discarded (``work_lost_selective_file_hours``)."""
    residual, lost_file_days, restored = 0, 0, 0
    for h in histories.values():
        if h.damaged_day is None or h.damaged_day > discovery_day:
            continue
        restored += 1
        held = {version_day_at(h, j) for j in kept_days}
        clean = [v for v in held if 0 <= v < h.damaged_day]
        if not clean:
            residual += 1
            continue
        v = max(clean)
        lost_file_days += sum(1 for d in h.change_days
                              if v < d <= discovery_day and d != h.damaged_day)  # fmt: skip
    return {"files_restored": restored, "residual_damaged_files": residual,
            "clean_recovery": int(residual == 0),
            "work_lost_selective_file_hours": lost_file_days * HOURS_PER_DAY}  # fmt: skip


def restore_diagnosis(kept_days: Sequence[int], post: np.ndarray, histories: dict[str, FileHistory],
                      true_start: int, gate: float, restore_point: int,
                      clean_recovery: int) -> dict:  # fmt: skip
    """D71: why verify_snap's restore point ``restore_point`` differs from j*, the newest kept
    snapshot older than the true start. Cause labels as pre-registered (OPEN_QUESTIONS D71)."""
    clean = [j for j in kept_days if j < true_start]
    if not clean:
        return {"diag_clean_held": 0, "diag_cause": "no_clean_held", "diag_false_flag_day0": 0}
    js = max(clean)
    day0 = 0
    if restore_point == js:
        cause = "picked_clean_point" if clean_recovery else "residual_outside_scope"
    elif restore_point >= true_start:
        cause = "missed_damage"
    elif float(p_clean(post, [js])[0]) < gate - 1e-12:
        cause = "gated_out"
    else:
        flagged = [(h, version_day_at(h, js)) for h in histories.values()
                   if version_day_at(h, js) in h.flagged_days]  # fmt: skip
        cause = "false_flag" if flagged else "other"
        day0 = int(any(v == 0 for _, v in flagged))
    return {"diag_clean_held": 1, "diag_cause": cause, "diag_false_flag_day0": day0}
