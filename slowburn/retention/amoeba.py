"""AMOEBA-style per-write version retention (reimplemented; not the authors' code).

Per write (a changed file on a day) the risk is
    rho = sigmoid(alpha * SIM + beta * EVID + gamma * INT + delta)
    SIM   byte-level similarity of old and new data (here: share of the file's chunks unchanged)
    EVID  the shared detector evidence for this file today (1 flagged / 0 not); every policy in
          a comparison sees the same evidence, so the comparison stays detector-agnostic. The
          original uses the entropy of the written data, which token-mode simulation has no bytes
          for; with the byte-level detector this term is that detector's flag.
    INT   write intensity: files changed today relative to the mean of the previous 7 days
The old version is kept as the file's backup if rho > 0.5 (one backup per file; a new backup
replaces the file's previous one). When backups exceed 90% of the byte budget, the
lowest-risk backups are evicted until usage is back under 90%.
Weights are fitted by logistic regression on training machines (labels: damaging writes).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from sklearn.linear_model import LogisticRegression

from slowburn.store.restore import HOURS_PER_DAY


@dataclass(frozen=True)
class Write:
    file_id: str
    day: int
    sim: float
    evidence: float
    intensity: float
    old_version_day: int  # day of the version being overwritten
    old_bytes: int
    damaging: bool  # ground truth (only used to fit weights and to evaluate)

    def x(self) -> list[float]:
        return [self.sim, self.evidence, self.intensity]


def fit_weights(writes: list[Write], seed: int = 0) -> np.ndarray:
    """(alpha, beta, gamma, delta) by logistic regression on labelled training writes."""
    X = np.array([w.x() for w in writes])
    y = np.array([int(w.damaging) for w in writes])
    if len(set(y)) < 2:
        raise ValueError("training writes need both damaging and benign examples")
    lr = LogisticRegression(class_weight="balanced", random_state=seed, max_iter=1000).fit(X, y)
    return np.r_[lr.coef_[0], lr.intercept_[0]]


class AmoebaStyle:
    name = "amoeba_style"

    def __init__(self, weights: np.ndarray, threshold: float = 0.5, high_water: float = 0.9):
        self.w = np.asarray(weights, float)
        self.threshold = threshold
        self.high_water = high_water
        self.backups: dict[str, tuple[int, float, int]] = {}  # file -> (version day, rho, bytes)

    def risk(self, w: Write) -> float:
        z = float(np.dot(self.w[:3], w.x()) + self.w[3])
        return 1.0 / (1.0 + np.exp(-z))

    def step(self, writes: list[Write], budget_bytes: float) -> None:
        for w in writes:
            rho = self.risk(w)
            if rho > self.threshold:
                self.backups[w.file_id] = (w.old_version_day, rho, w.old_bytes)
        used = sum(b for _, _, b in self.backups.values())
        if used > self.high_water * budget_bytes:
            for fid, _ in sorted(self.backups.items(), key=lambda kv: kv[1][1]):
                if used <= self.high_water * budget_bytes:
                    break
                used -= self.backups.pop(fid)[2]

    @property
    def used_bytes(self) -> int:
        return sum(b for _, _, b in self.backups.values())

    def recover(self, histories: dict, discovery_day: int) -> dict:
        """Per-file recovery: a damaged file is recovered iff its backup predates the damage."""
        residual, lost_days = 0, 0
        for fid, h in histories.items():
            if h.damaged_day is None or h.damaged_day > discovery_day:
                continue
            b = self.backups.get(fid)
            if b is None or b[0] >= h.damaged_day:
                residual += 1
                continue
            lost_days += sum(1 for d in h.change_days if b[0] < d < h.damaged_day)
        return {"residual_damaged_files": residual, "clean_recovery": int(residual == 0),
                "work_lost_selective_file_hours": lost_days * HOURS_PER_DAY,
                "work_lost_whole_system_hours": np.nan, "restore_point": None,
                "restore_point_clean": None, "files_restored": None, "estimated_start": None,
                "start_gap_days": None, "backups": len(self.backups),
                "backup_bytes": self.used_bytes}  # fmt: skip
