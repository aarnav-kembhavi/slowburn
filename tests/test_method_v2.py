"""Method v2 (DEV design): uncertain detector sensitivity (D48)."""

import numpy as np
import pytest

from slowburn.inference.changepoint import SingleChangepoint, hazard_from_window
from slowburn.inference.daily import DailyObs
from slowburn.inference.obsmodels import BetaBinomialExceedance

H = hazard_from_window(0.05, 60)


def _obs(T, flag_from=None, n=4):
    """n changed files a day; from ``flag_from`` on, one of them is flagged every day."""
    return [DailyObs(d, 0.0, int(flag_from is not None and d >= flag_from), n) for d in range(T)]


def _post(obs, w):
    m = SingleChangepoint(BetaBinomialExceedance(null_prior=(0.5, 200.5), blind_weight=w), H, 14)
    return m.posterior(obs)


def _start_given_started(post):
    p = post[:-1] / post[:-1].sum()
    return float(np.dot(np.arange(len(p)), p))


def test_blind_weight_zero_is_v1():
    obs = _obs(80, flag_from=50)
    v1 = SingleChangepoint(BetaBinomialExceedance(null_prior=(0.5, 200.5)), H, 14).posterior(obs)
    assert np.array_equal(_post(obs, 0.0), v1)


def test_no_flags_moves_the_start_less_with_a_possibly_blind_detector():
    obs = _obs(100)  # no flag ever: a blind detector looks exactly like this
    prior = SingleChangepoint(BetaBinomialExceedance(), H, 14, use_data=False).posterior(obs)
    m_prior, m_v1, m_v2 = (_start_given_started(p) for p in (prior, _post(obs, 0.0),
                                                              _post(obs, 0.5)))  # fmt: skip
    assert m_v1 > m_v2 > m_prior  # v1 pushes the start late; v2 much less
    assert m_v2 - m_prior < 0.5 * (m_v1 - m_prior)


def test_flags_still_locate_the_start():
    obs = _obs(100, flag_from=60)
    for w in (0.0, 0.5, 0.9):
        p = _post(obs, w)
        assert np.argmax(p[:-1]) == 60
        assert p[55:66].sum() / p[:-1].sum() > 0.9


def test_blind_weight_validated():
    with pytest.raises(ValueError):
        BetaBinomialExceedance(blind_weight=1.0)


def test_adaptive_gate_follows_concentration():
    from slowburn.bench.retention_experiment import adaptive_gate

    spec = {"min": 0.5, "window": 7}
    sharp = np.r_[np.zeros(50), np.ones(3) / 3, np.zeros(10), 0.0]
    flat = np.r_[np.ones(70) / 70, 0.0]
    assert adaptive_gate(sharp, spec, 0.8) == pytest.approx(0.5)
    assert adaptive_gate(flat, spec, 0.8) == pytest.approx(0.5 + 0.3 * (1 - 7 / 70))
    assert adaptive_gate(np.r_[np.zeros(5), 1.0], spec, 0.8) == 0.8  # nothing started


def test_adaptive_gate_leaves_prior_only_and_default_unchanged():
    import pandas as pd

    from slowburn.bench.retention_experiment import RetentionTask, evaluate_trace, simulate
    from slowburn.utils.config import load_config

    cfg = load_config("configs/retention_smoke.yaml")
    params = {**cfg["scenario"], "detect_prob": 0.9, "benign_invalid_rate": 0.01,
              "null_prior": (0.5, 100.5)}  # fmt: skip
    task = RetentionTask("dev", "eval", params, 0)
    trace = simulate(cfg, task)
    pols = ("slowburn", "prior_only")
    cols = ["policy", "budget", "discovery_delay", "restore_point", "restore_gate"]
    hp1 = {**cfg["hp"], "gate": 0.8}
    a = pd.DataFrame(evaluate_trace(cfg, task, trace, hp1, pols))
    hp2 = {**hp1, "adaptive_gate": {"min": 0.5, "window": 7}}
    b = pd.DataFrame(evaluate_trace(cfg, task, trace, hp2, pols))
    po = a.policy == "prior_only"
    assert a.loc[po, cols].equals(b.loc[po, cols])  # no detector: fixed gate, same restore
    assert (a.restore_gate == 0.8).all()
    assert (b.loc[~po, "restore_gate"] < 0.8).all()
