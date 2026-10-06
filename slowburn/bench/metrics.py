"""Recovery metrics. Convention: the snapshot of day d is taken at the end of day d, so it is
clean iff d < true_start (damage begins during the start day)."""

from __future__ import annotations

HOURS_PER_DAY = 24


def recovery_metrics(retained_days: list[int], true_start: int, discovery_day: int) -> dict:
    clean = [d for d in retained_days if d < true_start]
    if not clean:
        return {
            "clean_recovery": 0,
            "newest_clean_day": None,
            "start_gap_days": None,
            "data_lost_hours_whole_system": None,
            "snapshots_retained": len(retained_days),
        }
    best = max(clean)
    return {
        "clean_recovery": 1,
        "newest_clean_day": best,
        # 0 means the snapshot taken just before the attack began survived
        "start_gap_days": true_start - 1 - best,
        # whole-system rollback discards all work after the restored snapshot
        "data_lost_hours_whole_system": (discovery_day - best) * HOURS_PER_DAY,
        "snapshots_retained": len(retained_days),
    }
