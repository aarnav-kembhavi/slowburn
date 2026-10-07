"""Glue between the simulator, the detector and the daily statistic (shared by all runners)."""

from __future__ import annotations

import numpy as np

from slowburn.detector.features import features_batch, with_file_validity
from slowburn.detector.validity import file_validity
from slowburn.inference.daily import DayScores
from slowburn.sim.scenario import Day


def score_day(detector, day: Day) -> DayScores:
    """Score one day's changed chunks: calibrated probabilities plus conformal p-values.

    Detectors with ``pvalues`` get type-conditional (Mondrian) conformal p-values grouped by
    declared file type (decision D1).
    The M0 placeholder has none; it falls back to 1 - score, which is NOT a valid p-value.
    """
    chunks = day.changed
    types = [c.file_type for c in chunks]
    X = features_batch([c.data for c in chunks], types, [c.index == 0 for c in chunks])
    # whole-file validity, computed once per changed file from today's full file contents
    validity = {
        fid: file_validity(b"".join(day.files[fid]), ftype)
        for fid, ftype in {(c.file_id, c.file_type) for c in chunks}
    }
    X = with_file_validity(X, [validity[c.file_id] for c in chunks])
    probs = detector.score_features(X) if len(chunks) else np.zeros(0)
    if hasattr(detector, "pvalues") and len(chunks):
        pvals = detector.pvalues(X, groups=np.array(types))
    else:
        pvals = 1.0 - probs
    return DayScores(day=day.day, probs=probs, pvals=pvals)


def start_map(post: np.ndarray) -> int | None:
    """MAP start day, or None when "not started" is the most probable state."""
    i = int(np.argmax(post))
    return None if i == len(post) - 1 else i
