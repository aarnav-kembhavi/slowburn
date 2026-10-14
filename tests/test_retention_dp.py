"""C / Theorem 3 numerical check: the DP is exactly optimal per decision (brute force)."""

import numpy as np
import pytest

from slowburn.retention.dp import (
    brute_force_select,
    discovery_survival,
    dp_select,
    expected_loss,
    retention_posterior,
)


def _random_pi(rng, T, started_mass=None):
    w = rng.dirichlet(np.full(T, rng.uniform(0.2, 2.0)))
    m = rng.uniform(0.05, 1.0) if started_mass is None else started_mass
    return w * m  # remaining mass = not started


def test_expected_loss_hand_computed():
    pi = np.zeros(10)
    pi[5] = 0.5  # attack started on day 5 with prob 0.5
    pi[2] = 0.2
    # keep {1, 4, 9}: s=2 -> newest clean 1 -> loss 0; s=5 -> newest clean 4 -> loss 0
    assert expected_loss([1, 4, 9], pi, penalty=100.0) == pytest.approx(0.0)
    # keep {3, 9}: s=2 -> no clean -> 100; s=5 -> 5-1-3 = 1
    assert expected_loss([3, 9], pi, penalty=100.0) == pytest.approx(0.2 * 100 + 0.5 * 1)
    # symmetric: no clean at s=2 costs s = 2
    assert expected_loss([3, 9], pi, penalty=None) == pytest.approx(0.2 * 2 + 0.5 * 1)


@pytest.mark.parametrize("penalty", [None, 5.0, 50.0])
@pytest.mark.parametrize("seed", range(40))
def test_dp_matches_brute_force(seed, penalty):
    rng = np.random.default_rng(seed)
    T = int(rng.integers(6, 14))
    pi = _random_pi(rng, T)
    cand = sorted(rng.choice(T, size=int(rng.integers(3, min(T, 9) + 1)), replace=False))
    K = int(rng.integers(1, len(cand) + 1))
    chosen = dp_select(cand, pi, K, penalty)
    best, _ = brute_force_select(cand, pi, K, penalty)
    assert expected_loss(chosen, pi, penalty) == pytest.approx(best, abs=1e-12)
    assert len(chosen) <= K and cand[-1] in chosen and set(chosen) <= set(cand)


def test_dp_without_keep_newest_matches_brute_force():
    rng = np.random.default_rng(7)
    for _ in range(20):
        pi = _random_pi(rng, 10)
        cand = list(range(10))
        chosen = dp_select(cand, pi, 3, 20.0, keep_newest=False)
        best, _ = brute_force_select(cand, pi, 3, 20.0, keep_newest=False)
        assert expected_loss(chosen, pi, 20.0) == pytest.approx(best, abs=1e-12)


def test_dp_keeps_snapshot_just_before_a_certain_start():
    pi = np.zeros(20)
    pi[12] = 1.0
    assert 11 in dp_select(list(range(20)), pi, 2, penalty=100.0)


def test_heavy_penalty_pushes_retention_older():
    rng = np.random.default_rng(3)
    pi = _random_pi(rng, 30, started_mass=0.5)
    cand = list(range(30))
    light = dp_select(cand, pi, 4, penalty=None)
    heavy = dp_select(cand, pi, 4, penalty=1000.0)
    assert min(heavy) <= min(light)


def test_retention_posterior_conditions_on_no_discovery():
    post = np.r_[np.full(11, 0.05), 0.45]  # days 0..10 then not-started
    S = discovery_survival("uniform", 5)
    pi = retention_posterior(post, 10, S)
    assert np.all(pi[:6] == 0)  # starts >= 5 days ago would already have been discovered
    assert pi[10] > pi[7] > 0
    assert pi.sum() < 1  # 'not started' keeps the rest
    with pytest.raises(ValueError):
        retention_posterior(post[:-1], 10, S)


def test_discovery_survival_shapes():
    for kind in ("uniform", "geometric"):
        S = discovery_survival(kind, 30)
        assert S(0) == pytest.approx(1.0)
        assert S(30) == pytest.approx(0.0)
        assert np.all(np.diff(S(np.arange(31))) <= 1e-12)


# ---- D29: gated restore rule and forced (backbone) days ---------------------------------


def _restore_rule_loss(keep, pi, penalty, gate):
    """Independent per-start evaluation of the verified restore rule with reliable verification:
    walk kept snapshots newest first among those with P(clean) >= gate, take the first clean
    one; if there is none, fall back to the oldest kept snapshot."""
    pi = np.asarray(pi, float)
    total = pi.sum()
    kept = sorted(keep)
    loss = 0.0
    for s in range(len(pi)):
        if pi[s] == 0:
            continue
        gated = [j for j in kept if gate <= 0 or pi[j + 1 :].sum() / total >= gate - 1e-12]
        clean = [j for j in gated if j < s]
        j_r = max(clean) if clean else kept[0]
        loss += pi[s] * ((s - 1 - j_r) if j_r < s else penalty)
    return loss


@pytest.mark.parametrize("gate", [0.0, 0.3, 0.6, 0.9, 0.99])
@pytest.mark.parametrize("seed", range(12))
def test_gated_expected_loss_equals_the_restore_rule(seed, gate):
    rng = np.random.default_rng(100 + seed)
    T = int(rng.integers(6, 16))
    pi = _random_pi(rng, T)
    keep = sorted(rng.choice(T, size=int(rng.integers(1, 6)), replace=False))
    assert expected_loss(keep, pi, 25.0, gate) == pytest.approx(
        _restore_rule_loss(keep, pi, 25.0, gate), abs=1e-12
    )


@pytest.mark.parametrize("gate", [0.0, 0.5, 0.9])
@pytest.mark.parametrize("seed", range(20))
def test_gated_forced_dp_matches_brute_force(seed, gate):
    rng = np.random.default_rng(500 + seed)
    T = int(rng.integers(6, 14))
    pi = _random_pi(rng, T)
    cand = sorted(rng.choice(T, size=int(rng.integers(3, min(T, 9) + 1)), replace=False))
    n_forced = int(rng.integers(0, 3))
    forced = sorted(rng.choice(cand, size=n_forced, replace=False)) if n_forced else []
    if rng.random() < 0.5 and cand[-1] not in forced:
        forced = sorted([*forced, cand[-1]])  # the hybrid's backbone always holds today
    K = int(rng.integers(1, len(cand) + 1))
    chosen = dp_select(cand, pi, K, 30.0, forced=forced, gate=gate)
    best, _ = brute_force_select(cand, pi, K, 30.0, forced=forced, gate=gate)
    assert expected_loss(chosen, pi, 30.0, gate) == pytest.approx(best, abs=1e-12)
    assert set(forced) <= set(chosen) and cand[-1] in chosen
    assert len(set(chosen) - set(forced)) <= K


def test_discovery_posterior_uses_the_delay_pmf():
    from slowburn.retention.dp import discovery_posterior

    t = 40
    post = np.r_[np.full(t + 1, 0.5 / (t + 1)), 0.5]
    S = discovery_survival("uniform", 10)
    d = discovery_posterior(post, t, S)
    assert d[-1] == 0 and d.sum() == pytest.approx(1.0)
    assert (d[: t - 10] == 0).all()  # starts more than 10 days back are impossible
    assert d[t] == 0  # delay 0 has probability 0 under uniform on {1..10}
    assert np.allclose(d[t - 10 : t], 0.1)
