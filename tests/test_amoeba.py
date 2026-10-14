"""C: AMOEBA-style per-write retention (reimplemented)."""

import numpy as np
import pytest

from slowburn.retention.amoeba import AmoebaStyle, Write, fit_weights
from slowburn.store.restore import FileHistory


def _w(fid, day, sim, ev, damaging, old_day=0, nbytes=100):
    return Write(fid, day, sim, ev, 1.0, old_day, nbytes, damaging)


def test_fit_weights_learns_evidence_and_similarity():
    rng = np.random.default_rng(0)
    writes = []
    for i in range(400):
        dmg = i % 4 == 0
        writes.append(
            _w(
                f"f{i}",
                1,
                sim=float(rng.uniform(0, 0.3) if dmg else rng.uniform(0.5, 1)),
                ev=float(rng.random() < (0.8 if dmg else 0.05)),
                damaging=dmg,
            )
        )
    w = fit_weights(writes)
    assert w[1] > 0  # evidence raises risk
    assert w[0] < 0  # high similarity lowers risk
    with pytest.raises(ValueError):
        fit_weights([_w("a", 1, 0.5, 0, False)])


def test_backup_kept_only_for_risky_writes_and_one_per_file():
    a = AmoebaStyle(np.array([0.0, 10.0, 0.0, -5.0]))  # risky iff evidence == 1
    a.step([_w("x", 3, 0.5, 1.0, True, old_day=2), _w("y", 3, 0.5, 0.0, False)], 1e9)
    assert set(a.backups) == {"x"}
    a.step([_w("x", 5, 0.5, 1.0, False, old_day=3)], 1e9)
    assert a.backups["x"][0] == 3  # replaced by the newer backup


def test_eviction_drops_lowest_risk_first():
    a = AmoebaStyle(np.array([-5.0, 10.0, 0.0, -2.0]))
    a.step([_w("hi", 1, 0.0, 1.0, True), _w("lo", 1, 0.9, 1.0, True)], budget_bytes=1000)
    assert set(a.backups) == {"hi", "lo"}
    a.step([], budget_bytes=150)  # 200 bytes used > 90% of 150 -> evict lowest risk
    assert set(a.backups) == {"hi"}


def test_recover():
    a = AmoebaStyle(np.array([0.0, 10.0, 0.0, -5.0]))
    a.step([_w("x", 12, 0.1, 1.0, True, old_day=4)], 1e9)
    hist = {"x": FileHistory((0, 4, 8, 12), 12), "y": FileHistory((0, 13), 13),
            "z": FileHistory((0, 5), None)}  # fmt: skip
    r = a.recover(hist, discovery_day=20)
    assert r["residual_damaged_files"] == 1  # y had no risky write -> no backup
    assert r["work_lost_selective_file_hours"] == 24  # x's day-8 edit is lost
    assert np.isnan(r["work_lost_whole_system_hours"])
