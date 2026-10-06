"""Detector interface shared by the placeholder and the trained, calibrated detector."""

from __future__ import annotations

from typing import Protocol

import numpy as np

from slowburn.detector.features import features


class Detector(Protocol):
    name: str

    def score_features(self, X: np.ndarray) -> np.ndarray:
        """Calibrated P(damaged) for each feature row, in [0, 1]."""
        ...


def score(
    detector: Detector, chunk: bytes, declared_type: str | None = None, at_file_start: bool = False
) -> float:
    """Convenience: calibrated probability for a single raw chunk."""
    return float(detector.score_features(features(chunk, declared_type, at_file_start)[None, :])[0])


class EntropyDetector:
    """M0 placeholder: entropy / 8. Not calibrated; kept as a naive reference baseline."""

    name = "entropy_placeholder"

    def score_features(self, X: np.ndarray) -> np.ndarray:
        return np.clip(X[:, 256] / 8.0, 0.0, 1.0)
