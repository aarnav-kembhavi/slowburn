"""Chunk classifiers. All take the full feature matrix (base features + file-validity column)
and select the columns their feature set uses."""

from __future__ import annotations

import numpy as np
from lightgbm import LGBMClassifier

from slowburn.detector.features import FILE_VALID_INDEX, N_FEATURES, N_FEATURES_WITH_VALIDITY

FEATURE_SETS = {"base": N_FEATURES, "validity": N_FEATURES_WITH_VALIDITY}


class ChunkClassifier:
    """LightGBM benign-vs-damaged classifier on the ``base`` or ``validity`` feature set."""

    def __init__(self, params: dict, seed: int, feature_set: str = "base"):
        if feature_set not in FEATURE_SETS:
            raise ValueError(f"feature_set must be one of {sorted(FEATURE_SETS)}")
        self.params = dict(params)
        self.feature_set = feature_set
        self.name = f"lgbm_{feature_set}"
        self.model = LGBMClassifier(random_state=seed, verbose=-1, **self.params)

    @property
    def uses_validity(self) -> bool:
        return self.feature_set == "validity"

    def _cols(self, X: np.ndarray) -> np.ndarray:
        n = FEATURE_SETS[self.feature_set]
        if X.shape[1] < n:
            raise ValueError(f"{self.name} needs {n} feature columns, got {X.shape[1]}")
        return X[:, :n]

    def fit(self, X: np.ndarray, y: np.ndarray) -> ChunkClassifier:
        self.model.fit(self._cols(X), y)
        return self

    def raw_scores(self, X: np.ndarray) -> np.ndarray:
        """Uncalibrated P(damaged); a ranking score, used for AUROC."""
        return self.model.predict_proba(self._cols(X))[:, 1]


class ValidityRule:
    """Format validity alone: invalid file -> 1, valid -> 0, no check for the type -> 0.5."""

    name = "validity_rule"
    uses_validity = True

    def fit(self, X: np.ndarray, y: np.ndarray) -> ValidityRule:
        return self

    def raw_scores(self, X: np.ndarray) -> np.ndarray:
        v = X[:, FILE_VALID_INDEX]
        return np.where(v < 0, 0.5, 1.0 - v)
