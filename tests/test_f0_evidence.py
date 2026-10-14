"""F0: benign validation failures, token mode, file-level statistic, abstract detector."""

import numpy as np
import pytest

from slowburn.inference.daily import DayScores, file_pvalues, make_aggregator
from slowburn.inference.pipeline import AbstractFileDetector
from slowburn.sim.damage import RandomDamageSource
from slowburn.sim.scenario import Scenario, ScenarioConfig


def _days(cfg: ScenarioConfig, seed=0, aux=True):
    rng = np.random.default_rng(seed)
    scen = Scenario(cfg)
    aux_rng = np.random.default_rng(seed + 100) if aux else None
    return scen, list(scen.run(rng, RandomDamageSource(np.random.default_rng(seed + 1)), aux_rng))


TOK = dict(n_files=20, file_kib=(16, 64), days=30, attack_start=15, attack_files_per_day=1.0,
           content="tokens")  # fmt: skip


# ---- benign validation failures --------------------------------------------------------


def test_zero_rate_draws_nothing_and_matches_old_stream():
    cfg = ScenarioConfig(**{**TOK, "benign_invalid_rate": 0.0})
    _, with_aux = _days(cfg, aux=True)
    _, without = _days(cfg, aux=False)
    assert all(d.benign_invalid == frozenset() for d in with_aux)
    assert [d.files for d in with_aux] == [d.files for d in without]


def test_rate_one_marks_every_clean_changed_file_never_damaged_ones():
    _, days = _days(ScenarioConfig(**{**TOK, "benign_invalid_rate": 1.0}))
    for d in days:
        files = d.changed_files
        assert d.benign_invalid == {f for f, dmg in files.items() if dmg == 0}


def test_positive_rate_requires_aux_stream():
    with pytest.raises(ValueError, match="aux_rng"):
        _days(ScenarioConfig(**{**TOK, "benign_invalid_rate": 0.1}), aux=False)


def test_benign_invalid_rate_is_close_to_target():
    n_clean = n_bad = 0
    for seed in range(5):  # pooled: one 60-day machine has only ~200 clean changed files
        _, days = _days(ScenarioConfig(**{**TOK, "days": 60, "attack_start": None,
                                          "benign_invalid_rate": 0.2}), seed=seed)  # fmt: skip
        n_clean += sum(len(d.changed_files) for d in days[1:])
        n_bad += sum(len(d.benign_invalid) for d in days[1:])
    assert n_bad / n_clean == pytest.approx(0.2, abs=0.03)


# ---- token mode ------------------------------------------------------------------------


def test_token_mode_shapes_and_labels():
    scen, days = _days(ScenarioConfig(**TOK))
    first = days[0]
    assert all(len(c) == 16 for chunks in first.files.values() for c in chunks)
    assert all(4 <= len(chunks) <= 16 for chunks in first.files.values())  # 16-64 KiB / 4 KiB
    for d in days:
        assert all(c.damage == 0 for c in d.changed) == (d.day not in scen.damaged_on.values())


@pytest.mark.parametrize("model", ["striped", "whole"])
def test_token_mode_damage_models(model):
    scen, days = _days(ScenarioConfig(**{**TOK, "damage_model": model,
                                         "damage_fraction": 0.25}))  # fmt: skip
    d = days[15]
    dmg = [c.damage for c in d.changed if c.damage > 0]
    if model == "striped":
        assert set(dmg) == {0.25}
    else:
        assert set(dmg) == {1.0}


# ---- file-level statistic --------------------------------------------------------------


def test_file_pvalues_min_and_file_exceed_counts_files():
    d = DayScores(0, np.zeros(5), np.array([0.004, 0.5, 0.3, 0.2, 0.9]),
                  ("a", "a", "b", "c", "c"))  # fmt: skip
    fp = file_pvalues(d)
    assert fp == {"a": 0.004, "b": 0.3, "c": 0.2}
    obs = make_aggregator("file_exceed", alpha=0.01)(d)
    assert (obs.k, obs.n) == (1, 3)
    with pytest.raises(ValueError, match="file_ids"):
        file_pvalues(DayScores(0, np.zeros(2), np.zeros(2)))


# ---- abstract detector -----------------------------------------------------------------


@pytest.mark.parametrize("q", [0.0, 1.0])
def test_abstract_detector_extremes(q):
    scen, days = _days(ScenarioConfig(**{**TOK, "benign_invalid_rate": 0.0}))
    det = AbstractFileDetector(q, np.random.default_rng(0))
    agg = make_aggregator("file_exceed", alpha=0.5)
    for d in days:
        obs = agg(det.score_day(d))
        n_damaged = sum(v > 0 for v in d.changed_files.values())
        assert obs.k == (n_damaged if q == 1.0 else 0)


def test_abstract_detector_flags_benign_invalid_files():
    _, days = _days(ScenarioConfig(**{**TOK, "attack_start": None, "benign_invalid_rate": 0.3}))
    det = AbstractFileDetector(1.0, np.random.default_rng(0))
    agg = make_aggregator("file_exceed", alpha=0.5)
    for d in days:
        assert agg(det.score_day(d)).k == len(d.benign_invalid)


def test_abstract_detector_rate():
    _, days = _days(ScenarioConfig(**{**TOK, "n_files": 60, "days": 60, "attack_start": 1,
                                      "attack_files_per_day": 2.0}))  # fmt: skip
    det = AbstractFileDetector(0.5, np.random.default_rng(2))
    hits = total = 0
    for d in days:
        s = det.score_day(d)
        dmg = {f for f, v in d.changed_files.items() if v > 0}
        flagged = {f for f, p in zip(s.file_ids, s.pvals, strict=True) if p == 0}
        hits += len(flagged & dmg)
        total += len(dmg)
    assert total > 40 and hits / total == pytest.approx(0.5, abs=0.15)
    with pytest.raises(ValueError):
        AbstractFileDetector(1.5, np.random.default_rng(0))


def test_score_day_marks_benign_invalid_files_invalid():
    from slowburn.detector.calibrate import CalibratedDetector
    from slowburn.detector.model import ValidityRule
    from slowburn.inference.pipeline import score_day

    cfg = ScenarioConfig(n_files=6, file_types=("txt", "zip"), file_kib=(8, 12), days=6,
                         attack_start=None, benign_invalid_rate=1.0)  # fmt: skip
    _, days = _days(cfg)
    rule = ValidityRule()
    det = CalibratedDetector(rule)
    det._benign_cal = np.zeros(1000)  # benign calibration scores: an invalid file is extreme
    det._iso.fit([0.0, 1.0], [0, 1])
    for d in days[1:]:
        s = score_day(det, d)
        for fid, p in file_pvalues(s).items():
            assert (p < 1.0) == (fid in d.benign_invalid)


def test_file_exceed_prefers_detector_file_pvalues():
    d = DayScores(0, np.zeros(3), np.array([0.001, 0.9, 0.9]), ("a", "b", "b"),
                  file_pvals={"a": 0.5, "b": 0.001})  # fmt: skip
    obs = make_aggregator("file_exceed", alpha=0.01)(d)
    assert (obs.k, obs.n) == (1, 2)
    assert file_pvalues(d) == {"a": 0.5, "b": 0.001}
