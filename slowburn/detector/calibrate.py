"""Calibration wrappers that give a raw detector score a known meaning.

* ``score_features`` - isotonic-calibrated P(damaged), fitted on a held-out calibration split
  with class-balanced weights, i.e. calibrated under a 50/50 prior. Convert to another prior pi
  via odds: p' = p*pi / (p*pi + (1-p)*(1-pi)).
* ``pvalues`` - split-conformal outlier p-values (Bates et al., 2023, "Testing for outliers with
  conformal p-values") against benign calibration chunks. Under exchangeability with benign data,
  P(p <= alpha | benign) <= alpha. With ``groups`` they are *type-conditional (Mondrian)*
  conformal p-values (Vovk et al.'s Mondrian taxonomy, here by declared file type): the
  guarantee then holds within each file type. Chunks of one file are correlated, so
  exchangeability is approximate; the test-set check is reported.
"""

from __future__ import annotations

import numpy as np
from sklearn.isotonic import IsotonicRegression

from slowburn.detector.model import ChunkClassifier


def conformal_pvalues(benign_cal_scores: np.ndarray, scores: np.ndarray) -> np.ndarray:
    """p(x) = (1 + #{benign calibration scores >= s(x)}) / (n + 1)."""
    cal = np.sort(np.asarray(benign_cal_scores))
    n_ge = len(cal) - np.searchsorted(cal, scores, side="left")
    return (1.0 + n_ge) / (len(cal) + 1.0)


class CalibratedDetector:
    """Isotonic probabilities plus marginal and type-conditional (Mondrian) conformal p-values.

    Type-conditional p-values compare a chunk only against benign calibration chunks of the same
    declared file type (known from the backup manifest), giving the alpha guarantee *per type*.
    Types with fewer than ``min_group`` benign calibration chunks fall back to the marginal set.
    Wraps any object with ``raw_scores(X)`` (a ``ChunkClassifier`` or a rule).
    """

    def __init__(self, classifier: ChunkClassifier, min_group: int = 50):
        self.classifier = classifier
        self.name = getattr(classifier, "name", "detector")
        self.uses_validity = bool(getattr(classifier, "uses_validity", False))
        self.min_group = min_group
        self._iso = IsotonicRegression(y_min=0.0, y_max=1.0, out_of_bounds="clip")
        self._benign_cal: np.ndarray | None = None
        self._benign_by_group: dict[str, np.ndarray] = {}

    def fit(
        self, X_cal: np.ndarray, y_cal: np.ndarray, groups: np.ndarray | None = None
    ) -> CalibratedDetector:
        s = self.classifier.raw_scores(X_cal)
        y = np.asarray(y_cal)
        pos, neg = max(1, y.sum()), max(1, (1 - y).sum())
        w = np.where(y == 1, 0.5 / pos, 0.5 / neg)
        self._iso.fit(s, y, sample_weight=w)
        self._benign_cal = s[y == 0]
        self._benign_by_group = {}
        if groups is not None:
            g = np.asarray(groups)
            for key in np.unique(g[y == 0]):
                cal = s[(y == 0) & (g == key)]
                if len(cal) >= self.min_group:
                    self._benign_by_group[str(key)] = cal
        return self

    def raw_scores(self, X: np.ndarray) -> np.ndarray:
        return self.classifier.raw_scores(X)

    def score_features(self, X: np.ndarray) -> np.ndarray:
        return self._iso.predict(self.raw_scores(X))

    def pvalues(self, X: np.ndarray, groups: np.ndarray | None = None) -> np.ndarray:
        """Marginal p-values, or type-conditional p-values when ``groups`` (file types) given."""
        if self._benign_cal is None:
            raise RuntimeError("call fit() first")
        raw = self.raw_scores(X)
        out = conformal_pvalues(self._benign_cal, raw)
        if groups is not None:
            g = np.asarray(groups)
            for key, cal in self._benign_by_group.items():
                sel = g == key
                if sel.any():
                    out[sel] = conformal_pvalues(cal, raw[sel])
        return out
