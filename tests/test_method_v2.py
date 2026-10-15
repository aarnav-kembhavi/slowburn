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
