"""Detector interface shared by the placeholder and the trained, calibrated detector."""

from __future__ import annotations

from typing import Protocol

import numpy as np

from slowburn.detector.features import features, with_file_validity


class Detector(Protocol):
    name: str

    def score_features(self, X: np.ndarray) -> np.ndarray:
        """Calibrated P(damaged) for each feature row, in [0, 1]."""
        ...


def score(
    detector: Detector,
    chunk: bytes,
    declared_type: str | None = None,
    at_file_start: bool = False,
    file_valid: float = -1.0,
) -> float:
    """Convenience: calibrated probability for a single raw chunk (``file_valid``: whole-file
    validity of the chunk's file, -1 if unknown)."""
    X = with_file_validity(features(chunk, declared_type, at_file_start)[None, :], [file_valid])
    return float(detector.score_features(X)[0])


class EntropyDetector:
    """M0 placeholder: entropy / 8. Not calibrated; kept as a naive reference baseline."""

    name = "entropy_placeholder"

    def score_features(self, X: np.ndarray) -> np.ndarray:
        return np.clip(X[:, 256] / 8.0, 0.0, 1.0)
