"""D69: Bar-On et al. online checkpointing schedules reproduce the paper's efficiencies."""

import pytest

from slowburn.retention import checkpointing as cp
from slowburn.retention.base import replay


@pytest.mark.parametrize("alg,q", [
    (cp.exact(3), 1.5278641),           # Prop. 3.2 (golden-ratio Round-Robin)
    (cp.exact(4), 1.5398927),           # Prop. 3.4 (Table 1)
    (cp.exact(5), 1.4707341),           # Prop. 3.3 (Table 1)
    (cp.round_robin(4), 1.5883608),     # Prop. 3.4: best geometric 4-checkpoint, 5 r~4
])  # fmt: skip
def test_closed_form_schedules_match_the_paper(alg, q):
    assert cp.efficiency(alg) == pytest.approx(q, abs=1e-6)


def test_team_normalisation_is_q_times_k_over_k_plus_1():
    # the team's targets c3 ~ 1.1459, c5 ~ 1.2256, geometric c4 ~ 1.2707 (ideal gap T/k)
    for alg, c in ((cp.exact(3), 1.1459), (cp.exact(5), 1.2256), (cp.round_robin(4), 1.2707)):
        assert cp.efficiency(alg) * alg.k / (alg.k + 1) == pytest.approx(c, abs=1e-4)


@pytest.mark.parametrize("k,table4", [(3, 1.145898034), (7, 1.318433761), (15, 1.408092224)])
def test_recursive_matches_table_4(k, table4):
    a = cp.recursive(k)
    assert cp.efficiency(a) * k / (k + 1) == pytest.approx(table4, abs=1e-6)


@pytest.mark.parametrize("k", [4, 8, 16])
def test_recursive_equals_theorem_4_1(k):
    """Simulated efficiency equals (k + 1) r(G, K*) (Theorem 4.1). With the paper's stated
    'smallest root' rule this is below Table 3's tabled value for k = 4, 8, 16 (Table 3 lists
    a larger G*; noted in D69)."""
    a = cp.recursive(k)
    G = a.period[0][0] ** (1 / (k + 1))
    assert cp.efficiency(a) == pytest.approx((k + 1) * cp.recursive_r(G, cp.recursive_K(k)),
                                             abs=1e-9)  # fmt: skip


def test_daily_discretisation_error_is_small():
    for alg in (cp.exact(3), cp.exact(5), cp.recursive(7), cp.recursive(11)):
        q, dq = cp.efficiency(alg), cp.discrete_efficiency(alg, 2000, 20000)
        assert q <= dq <= q * 1.005


@pytest.mark.parametrize("family", ["exact", "rr", "recursive"])
@pytest.mark.parametrize("K", [4, 6, 8, 12])
def test_policy_respects_the_retention_contract(family, K):
    pol = cp.OnlineCheckpointing(family)
    if not pol.supports(K):
        assert family == "exact" and K in (8, 12)
        return
    kept = replay(pol, 700, K)  # raises if > K, today missing, or a dropped snapshot is needed
    assert max(len(h) for h in kept[50:]) == K
