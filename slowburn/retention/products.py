"""Product retention defaults (D66 audit; rules and sources in docs/baselines.md).

Per-file products keep, for each file, a subset of its versions (a version is identified by the
day it was written; the current version is always kept). Snapshot products keep a subset of
the daily whole-machine snapshots. Days are simulation days; calendar periods (restic) count
from ``DAY0``, the first day of the FSL Homes block the churn comes from.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Sequence

from slowburn.store.restore import FileHistory

DAY0 = dt.date(2011, 9, 16)


# ---- per-file version histories --------------------------------------------------------


def _versions(h: FileHistory, td: int) -> list[int]:
    return sorted(d for d in h.change_days if d <= td)


def keep_versions(td: int, versions: Sequence[int], *, superseded_within: int | None = None,
                  created_within: int | None = None,
                  max_versions: int | None = None) -> list[int]:  # fmt: skip
    """Versions retained at the end of day ``td``. A historical version i (written on
    versions[i], superseded on versions[i + 1]) is dropped if any limit applies:
    ``superseded_within`` W: superseded on or before td - W (it was not current at any point of
    the last W days); ``created_within`` W: written on or before td - W; ``max_versions`` N: only
    the newest N versions are kept, current included (N - 1 or more newer versions drop it)."""
    n = len(versions)
    keep = []
    for i, v in enumerate(versions):
        if i == n - 1:
            keep.append(v)  # the current version is never deleted
            continue
        if superseded_within is not None and versions[i + 1] <= td - superseded_within:
            continue
        if created_within is not None and v <= td - created_within:
            continue
        if max_versions is not None and n - i > max_versions:
            continue
        keep.append(v)
    return keep


PER_FILE: dict[str, dict] = {
    "dropbox_30d": {"superseded_within": 30},
    "dropbox_180d": {"superseded_within": 180},
    "dropbox_365d": {"superseded_within": 365},
    "gdrive_30d_100v": {"superseded_within": 30, "max_versions": 100},  # dropped at 100 newer
    "gdrive_30d_100v_created": {"created_within": 30, "max_versions": 100},
    "onedrive_personal_25v": {"max_versions": 25},
    "onedrive_personal_25v_30d": {"max_versions": 25, "superseded_within": 30},
    "onedrive_business_500v": {"max_versions": 500},
}


def retained_versions(name: str, histories: dict[str, FileHistory], td: int) -> dict[str, list]:
    rule = PER_FILE[name]
    return {f: keep_versions(td, _versions(h, td), **rule) for f, h in histories.items()}


# ---- snapshot products ---------------------------------------------------------------


def _date(day: int) -> dt.date:
    return DAY0 + dt.timedelta(days=day)


def _newest_per_period(days: Sequence[int], period: Callable[[dt.date], tuple],
                       n: int | None = None, since: dt.date | None = None) -> set[int]:  # fmt: skip
    """restic: the newest snapshot of each of the last ``n`` periods that hold a snapshot (or of
    every period, restricted to snapshots on or after ``since``)."""
    best: dict[tuple, int] = {}
    for d in days:
        if since is not None and _date(d) < since:
            continue
        k = period(_date(d))
        best[k] = max(best.get(k, d), d)
    keys = sorted(best, reverse=True)
    return {best[k] for k in (keys[:n] if n is not None else keys)}


def _day(x: dt.date) -> tuple:
    return (x.year, x.month, x.day)


def _week(x: dt.date) -> tuple:
    return tuple(x.isocalendar()[:2])


def _month(x: dt.date) -> tuple:
    return (x.year, x.month)


def _year(x: dt.date) -> tuple:
    return (x.year,)


def _minus_months(x: dt.date, m: int) -> dt.date:
    y, mo = divmod(x.year * 12 + x.month - 1 - m, 12)
    mo += 1
    last = (dt.date(y + (mo == 12), mo % 12 + 1, 1) - dt.timedelta(days=1)).day
    return dt.date(y, mo, min(x.day, last))


def restic_dwmy(td: int) -> set[int]:
    """--keep-daily 7 --keep-weekly 5 --keep-monthly 12 --keep-yearly 75 (daily backups)."""
    days = range(td + 1)
    keep = _newest_per_period(days, _day, 7) | _newest_per_period(days, _week, 5)
    return keep | _newest_per_period(days, _month, 12) | _newest_per_period(days, _year, 75)


def restic_within(td: int) -> set[int]:
    """--keep-within-daily 7d --keep-within-weekly 1m --keep-within-monthly 1y
    --keep-within-yearly 75y, measured back from the latest snapshot (day td)."""
    days, last = range(td + 1), _date(td)
    return (_newest_per_period(days, _day, since=last - dt.timedelta(days=7))
            | _newest_per_period(days, _week, since=_minus_months(last, 1))
            | _newest_per_period(days, _month, since=_minus_months(last, 12))
            | _newest_per_period(days, _year, since=_minus_months(last, 12 * 75)))  # fmt: skip


def netapp_arpai(td: int, histories: dict[str, FileHistory]) -> set[int]:
    """12 h periodic retention (at daily resolution: today and yesterday), plus the snapshot of
    the day before the first flagged damaged write, locked until the administrator responds."""
    kept = {td, max(td - 1, 0)}
    hits = [h.damaged_day for h in histories.values()
            if h.damaged_day is not None and h.damaged_day <= td
            and h.damaged_day in h.flagged_days]  # fmt: skip
    if hits:
        kept.add(max(min(hits) - 1, 0))
    return kept


SNAPSHOT: dict[str, Callable[[int, dict], set[int]]] = {
    "restic_docs_dwmy": lambda td, h: restic_dwmy(td),
    "restic_docs_within": lambda td, h: restic_within(td),
    "restic_keep_within_7d": lambda td, h: set(range(max(td - 7, 0), td + 1)),
    "restic_keep_last_1": lambda td, h: {td},
    "netapp_arpai": netapp_arpai,
}

PRODUCTS = (*PER_FILE, *SNAPSHOT)
