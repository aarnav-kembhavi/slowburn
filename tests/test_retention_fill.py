"""D37 regression tests (K = 12 bug): retention deletes a snapshot only when the budget is
exceeded, and ties are broken by the rule fixed in advance (smallest largest gap, then delete
the newest). The pre-fix code kept 2-4 snapshots at every K and lost its old anchor."""

import numpy as np
import pytest

from slowburn.retention.base import PosteriorDP, RetentionContext, replay
from slowburn.retention.dp import (
    brute_force_select,
    discovery_survival,
    dp_select,
    expected_loss,
    retention_posterior,
)

S60 = discovery_survival("uniform", 60)
H = 1 - 0.95 ** (1 / 60)


def _prior_pi(day):
    """Attack-free prior-like posterior: constant hazard, conditioned on non-discovery."""
    s = np.arange(day + 1)
    post = np.r_[H * (1 - H) ** (day - s), 0.0]
    post[-1] = 1 - post[:-1].sum()
    return retention_posterior(post, day, S60)


def _spiky_pi(seed):
    """Posterior with a random evidence spike (exercises evidence-driven deletions)."""
    rng = np.random.default_rng(seed)

    def f(day):
        p = _prior_pi(day)
        if day > 40 and rng.random() < 0.3:
            k = int(rng.integers(max(0, day - 50), day + 1))
            p = p.copy()
            p[k] += rng.uniform(0.05, 0.5)
            p = p / max(1.0, p.sum())
        return p

    return f


def _extra(pi_fn):
    def extra(day):
        p = pi_fn(day)
        return {"retention_pi": p, "prior_retention_pi": p}

    return extra


CASES = [(K, bb, gate) for K in (4, 6, 8, 12) for bb in (0.0, 0.25, 0.5) for gate in (0.0, 0.8)]


@pytest.mark.parametrize(("K", "bb", "gate"), CASES)
def test_kept_count_is_min_of_budget_and_days(K, bb, gate):
    """(a) |kept| == min(K, days elapsed) on every day, prior-like and spiky posteriors."""
    for pi_fn in (_prior_pi, _spiky_pi(K)):
        hist = replay(PosteriorDP(90.0, gate=gate, backbone=bb), 160, K, _extra(pi_fn))
        assert [len(h) for h in hist] == [min(K, t + 1) for t in range(160)]


@pytest.mark.parametrize(("K", "bb", "gate"), CASES)
def test_nothing_deleted_while_free_slots_exist(K, bb, gate):
    """(b) a snapshot (in particular the old anchor) is deleted only on a day when held + today
    exceeds K, and then exactly one is deleted."""
    hist = replay(PosteriorDP(90.0, gate=gate, backbone=bb), 160, K, _extra(_spiky_pi(7 + K)))
    for t in range(1, 160):
        before = hist[t - 1] | {t}
        dropped = before - hist[t]
        if len(before) <= K:
            assert not dropped
        else:
            assert len(dropped) == 1


def test_anchor_with_zero_marginal_value_is_kept_while_slots_are_free():
    """The pre-fix DP dropped an old anchor whose marginal value was zero today; with a free
    slot it must stay."""
    day = 150
    pi = _prior_pi(day)
    held = {3: 3, 140: 140, 149: 149, 150: 150}
    ctx = RetentionContext(day=day, snapshot_days=held, budget=6, daily_stat=np.zeros(day + 1),
                           start_posterior=np.r_[np.zeros(day + 1), 1.0], retention_pi=pi,
                           prior_retention_pi=pi)  # fmt: skip
    for bb in (0.0, 0.5):
        assert PosteriorDP(90.0, gate=0.8, backbone=bb).decide(ctx) == set(held)


def test_tie_break_smallest_largest_gap_then_delete_newest():
    pi = np.zeros(6)
    pi[3] = 0.5  # only day 2 matters; adding 0, 1, 3 or 4 has zero marginal value
    cand = list(range(6))
    # sets {2, x, 5}: loss 0 for every x; largest gap 3, 3, 2, 2 for x = 0, 1, 3, 4; then the
    # smaller day sum (delete the newer of 3 and 4) -> {2, 3, 5}
    assert dp_select(cand, pi, 3, 100.0) == [2, 3, 5]
    assert brute_force_select(cand, pi, 3, 100.0)[1] == [2, 3, 5]
    # all-zero posterior: every set ties on loss; the rule measures gaps between kept snapshots
    # only (not their span), so the tightest cluster wins
    assert dp_select(list(range(9)), np.zeros(9), 3, 100.0) == [6, 7, 8]


@pytest.mark.parametrize("gate", [0.0, 0.5, 0.8, 0.95])
@pytest.mark.parametrize("seed", range(25))
def test_dp_matches_brute_force_on_tie_rich_posteriors(seed, gate):
    """(c) exact agreement with brute force (same set) when many options tie: posteriors with
    zero-mass regions, forced backbone days, budgets up to all candidates."""
    rng = np.random.default_rng(900 + seed)
    T = int(rng.integers(8, 15))
    pi = np.zeros(T)
    support = rng.choice(T, size=int(rng.integers(0, 4)), replace=False)
    pi[support] = rng.dirichlet(np.ones(len(support))) * rng.uniform(0.1, 1.0) if len(
        support) else []  # fmt: skip
    cand = sorted(rng.choice(T, size=int(rng.integers(3, min(T, 10) + 1)), replace=False))
    forced = sorted({cand[-1], *rng.choice(cand, size=int(rng.integers(0, 3)), replace=False)}) \
        if rng.random() < 0.5 else []  # fmt: skip
    K = int(rng.integers(1, len(cand) + 1))
    chosen = dp_select(cand, pi, K, 40.0, forced=forced, gate=gate)
    best, arg = brute_force_select(cand, pi, K, 40.0, forced=forced, gate=gate)
    assert chosen == arg
    assert expected_loss(chosen, pi, 40.0, gate) == pytest.approx(best, abs=1e-12)


@pytest.mark.parametrize("gate", [0.0, 0.8])
@pytest.mark.parametrize("seed", range(30))
def test_single_deletion_fast_path_matches_brute_force(seed, gate):
    """The online case (K held + today, one deletion) takes the direct-evaluation fast path;
    it must select the same set as the exhaustive tie-broken minimum."""
    rng = np.random.default_rng(1700 + seed)
    day = int(rng.integers(30, 120))
    pi = _prior_pi(day) if seed % 2 else _spiky_pi(seed)(day)
    cand = sorted({*rng.choice(day, size=int(rng.integers(3, 12)), replace=False), day})
    forced = sorted({day, *rng.choice(cand, size=int(rng.integers(0, 2)), replace=False)}) \
        if seed % 3 == 0 else []  # fmt: skip
    K = len(set(cand) - set(forced)) - 1
    if K < 1:
        return
    assert (
        dp_select(cand, pi, K, 90.0, forced=forced, gate=gate)
        == brute_force_select(cand, pi, K, 90.0, forced=forced, gate=gate)[1]
    )
