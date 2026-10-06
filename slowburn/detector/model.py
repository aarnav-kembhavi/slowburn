"""LightGBM benign-vs-damaged chunk classifier."""

from __future__ import annotations

import numpy as np
from lightgbm import LGBMClassifier


class ChunkClassifier:
    def __init__(self, params: dict, seed: int):
        self.params = dict(params)
        self.model = LGBMClassifier(random_state=seed, verbose=-1, **self.params)

    def fit(self, X: np.ndarray, y: np.ndarray) -> ChunkClassifier:
        self.model.fit(X, y)
        return self

    def raw_scores(self, X: np.ndarray) -> np.ndarray:
        """Uncalibrated P(damaged); a ranking score, used for AUROC."""
        return self.model.predict_proba(X)[:, 1]
