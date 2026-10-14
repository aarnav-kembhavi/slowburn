"""C: snapshot retention policies (online contract, characteristic behaviour), Proposition 1."""

import numpy as np
import pytest

from slowburn.retention.base import (
    GFS,
    KeepLastN,
    Oracle,
    PosteriorDP,
    ThresholdVault,
    TowerOfHanoi,
    gfs_split,
    replay,
)
from slowburn.retention.dp import discovery_survival, retention_posterior


def test_keep_last_n():
    assert replay(KeepLastN(), 20, 5)[-1] == {15, 16, 17, 18, 19}


@pytest.mark.parametrize("N", [3, 5, 8])
@pytest.mark.parametrize("d", [0, 2, 5, 8, 12])
def test_proposition_1_keep_last_n_has_no_clean_snapshot_when_d_ge_N(N, d):
    """Prop. 1 check: at discovery day s + d, keep-last-N holds days s+d-N+1..s+d; all are
    >= s (dirty) iff d >= N - 1 ... with 'clean iff j < s' this is d >= N - 1; see theory.md."""
    s = 30
    kept = replay(KeepLastN(), s + d + 1, N)[-1]
    clean = [j for j in kept if j < s]
    assert (len(clean) == 0) == (d >= N - 1)


def test_gfs_split_and_spread():
    assert gfs_split(8) == (4, 3, 1)
    assert sum(gfs_split(5)) == 5
    kept = replay(GFS(), 120, 8)[-1]
    assert kept == {116, 117, 118, 119, 111, 104, 97, 83}  # 4 daily, 3 week-ends, 1 month-end


def test_tower_of_hanoi_ages_are_roughly_powers_of_two():
    kept = sorted(replay(TowerOfHanoi(), 128, 7)[-1])
    ages = sorted(127 - d for d in kept)
    assert len(kept) == 7 and ages[0] == 0
    assert ages[-1] >= 32  # oldest medium is about 2^(K-1) days old
    gaps = np.diff(ages)
    assert np.all(gaps >= 0)


def test_threshold_vault_protects_pre_alarm_snapshot():
    stat = np.zeros(40)
    stat[25] = 1.0  # alarm on day 25

    def extra(day):
        return {"daily_stat": stat[: day + 1].copy()}

    kept = replay(ThresholdVault(threshold=0.5, vault_size=1), 40, 5, extra)[-1]
    assert 24 in kept  # newest snapshot before the alarm day is vaulted
    assert {36, 37, 38, 39} <= kept


def test_oracle_keeps_day_before_start():
    def extra(day):
        return {"oracle_start": 20}

    kept = replay(Oracle(), 50, 4, extra)[-1]
    assert 19 in kept and 49 in kept


def _point_mass_ctx(start, survival_days=60):
    S = discovery_survival("uniform", survival_days)

    def extra(day):
        post = np.zeros(day + 2)
        if day >= start:
            post[start] = 1.0
        else:
            post[-1] = 1.0
        pi = retention_posterior(post, day, S)
        return {
            "start_posterior": post,
            "retention_pi": pi,
            "prior_retention_pi": np.zeros(day + 1),
        }

    return extra


def test_posterior_dp_keeps_snapshot_before_a_certain_start():
    kept = replay(PosteriorDP(penalty=100.0), 45, 4, _point_mass_ctx(30))[-1]
    assert 29 in kept


def test_prior_only_spreads_snapshots_back_in_time():
    h = 0.001
    S = discovery_survival("uniform", 30)

    def extra(day):
        post = np.r_[h * (1 - h) ** np.arange(day + 1), 0.0]
        post[-1] = 1 - post[:-1].sum()
        return {
            "start_posterior": post,
            "retention_pi": None,
            "prior_retention_pi": retention_posterior(post, day, S),
        }

    kept = sorted(replay(PosteriorDP(penalty=100.0, use_evidence=False), 90, 6, extra)[-1])
    assert len(kept) == 6 and kept[-1] == 89
    assert 89 - kept[0] >= 15  # reaches back towards the 30-day discovery horizon
    # but not much beyond it: starts are at most 29 days old (older ones would have been
    # discovered), so the oldest useful snapshot is about 31 days old (online slack +1)
    assert 89 - kept[0] <= 32


def test_policy_contract_is_enforced():
    class Bad:
        name = "bad"

        def decide(self, ctx):
            return set(ctx.snapshot_days)  # never deletes

    with pytest.raises(AssertionError, match="contract"):
        replay(Bad(), 10, 3)
