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
    Clean files the scenario marks as failing validation today (``day.benign_invalid``) get
    validity 0, as a mid-write or truncated file would.
    """
    chunks = day.changed
    types = [c.file_type for c in chunks]
    X = features_batch([c.data for c in chunks], types, [c.index == 0 for c in chunks])
    # whole-file validity, computed once per changed file from today's full file contents
    validity = {
        fid: (0.0 if fid in day.benign_invalid else file_validity(b"".join(day.files[fid]), ftype))
        for fid, ftype in {(c.file_id, c.file_type) for c in chunks}
    }
    X = with_file_validity(X, [validity[c.file_id] for c in chunks])
    probs = detector.score_features(X) if len(chunks) else np.zeros(0)
    if hasattr(detector, "pvalues") and len(chunks):
        pvals = detector.pvalues(X, groups=np.array(types))
    else:
        pvals = 1.0 - probs
    fids = tuple(c.file_id for c in chunks)
    file_pvals = None
    if getattr(detector, "_benign_file_max", None) is not None and len(chunks):
        raw = detector.raw_scores(X)
        fmax: dict[str, float] = {}
        for f, r in zip(fids, raw, strict=True):
            fmax[f] = max(fmax.get(f, -np.inf), float(r))
        names = sorted(fmax)
        pv = detector.file_pvalues_from_max(np.array([fmax[f] for f in names]))
        file_pvals = dict(zip(names, map(float, pv), strict=True))
    return DayScores(day.day, probs, pvals, fids, file_pvals)


class AbstractFileDetector:
    """Detector-agnostic evidence model (no bytes needed).

    Each damaged changed file is flagged with probability ``detect_prob``; a clean changed file is
    flagged exactly when it fails validation today (``day.benign_invalid``, rate swept by the
    scenario). Flags become chunk p-values 0 (flagged file) or 1, so ``file_exceed`` counts
    exactly the flagged files. ``detect_prob = 0`` is the blind (null) detector.
    """

    def __init__(self, detect_prob: float, rng: np.random.Generator):
        if not 0.0 <= detect_prob <= 1.0:
            raise ValueError("detect_prob must be in [0, 1]")
        self.detect_prob = detect_prob
        self.rng = rng
        self.name = f"abstract_q{detect_prob}"

    def score_day(self, day: Day) -> DayScores:
        files = day.changed_files
        flagged = set()
        for fid in sorted(files):  # sorted: draws do not depend on dict order
            if files[fid] > 0:
                if self.rng.random() < self.detect_prob:
                    flagged.add(fid)
            elif fid in day.benign_invalid:
                flagged.add(fid)
        p = np.array([0.0 if c.file_id in flagged else 1.0 for c in day.changed])
        fp = {f: (0.0 if f in flagged else 1.0) for f in files}
        return DayScores(day.day, 1.0 - p, p, tuple(c.file_id for c in day.changed), fp)


def start_map(post: np.ndarray) -> int | None:
    """MAP start day, or None when "not started" is the most probable state."""
    i = int(np.argmax(post))
    return None if i == len(post) - 1 else i
