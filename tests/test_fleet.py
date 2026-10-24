"""D73: the forkable machine simulator reproduces ``simulate`` exactly, and a fork equals a fresh
simulation with that attack start."""

from pathlib import Path

import pytest

from slowburn.bench.retention_experiment import RetentionTask, simulate, task_seed_key, trace_days
from slowburn.fleet.machine import MachineSim
from slowburn.utils.config import load_config

CFGS = {
    "abstract": "configs/dev_d72_full.yaml",
    "synthetic_bytes": "configs/dev_d72_bytes_synthetic.yaml",
    "napierone_bytes": "configs/dev_d72_bytes_napierone.yaml",
}


def _setup(arm, start, days=None):
    cfg = load_config(CFGS[arm])
    if arm == "napierone_bytes" and not Path(cfg["scenario"]["napierone_dir"]).exists():
        pytest.skip("NapierOne data not present")
    cfg["discovery_delay"] = [6]
    sc = {**cfg["scenario"], "attack_start": start, "benign_invalid_rate": 0.05,
          "n_files": 12, "attack_files_per_day": 2.0}  # fmt: skip
    if arm == "abstract":
        sc["detect_prob"] = 0.5
    return cfg, sc


def _same(sim, tr):
    """``tr``: a MachineTrace or another MachineSim."""
    other = tr.histories() if isinstance(tr, MachineSim) else tr.histories
    types = tr.scen.file_types if isinstance(tr, MachineSim) else tr.file_types
    assert sim.obs == tr.obs
    assert sim.histories() == other
    assert sim.scen.file_types == types


@pytest.mark.parametrize("arm", list(CFGS))
def test_stepper_matches_simulate(arm):
    cfg, sc = _setup(arm, 9)
    task = RetentionTask("dev", "eval", sc, 3)
    tr = simulate(cfg, task)
    n = trace_days(cfg, 9)
    sim = MachineSim(cfg, sc, task_seed_key(int(cfg["seed"]), task), n).run_to(n)
    _same(sim, tr)
    assert any(h.damaged_day is not None for h in tr.histories.values())


@pytest.mark.parametrize("arm", list(CFGS))
def test_fork_equals_fresh(arm):
    cfg, sc = _setup(arm, None)
    key = (202, "fleet-test", 1)
    n = 16
    benign = MachineSim(cfg, sc, key, n).run_to(7)
    forked = benign.fork(7).run_to(n)
    fresh = MachineSim(cfg, {**sc, "attack_start": 7}, key, n).run_to(n)
    _same(forked, fresh)
    assert forked.histories() != benign.run_to(n).histories()  # the attack did something
    assert benign.start is None and forked.start == 7


def test_machine_lik_matches_single_changepoint():
    import numpy as np

    from slowburn.fleet.posterior import MachineLik
    from slowburn.inference.changepoint import SingleChangepoint, geometric_log_prior
    from slowburn.inference.obsmodels import BetaBinomialExceedance

    cfg, sc = _setup("abstract", 30)
    sim = MachineSim(cfg, sc, (202, "fleet-test", 2), 45).run_to(45)
    prior, warm, h = (2.0, 300.0), 14, 0.001
    lik = MachineLik(sim.obs, warm, prior, 0.75)
    model = SingleChangepoint(BetaBinomialExceedance(null_prior=prior, blind_weight=0.75), h, warm)
    for T in (10, 20, 38, 45):
        ref = model.posterior_path(sim.obs, [T])[T]
        lp = geometric_log_prior(T, h, warm) + lik.loglik(T, np.arange(T + 1))
        mine = np.exp(lp - np.logaddexp.reduce(lp))
        np.testing.assert_allclose(mine, ref, atol=1e-12)


def test_fleet_marginals_brute_force():
    import itertools

    import numpy as np

    from slowburn.fleet.posterior import fleet_marginals, lag_log_pmf, rho_log_weights

    rng = np.random.default_rng(5)
    N, D, t, lag = 3, 6, 9, 3
    days = np.arange(t - D + 1, t + 1)
    ratios = rng.normal(0, 2, (N, D))
    log_ca = rng.normal(-3, 1, D)
    log_c_none = -1.0
    rhos, mus = (0.1, 0.4), (0.5, 3.0)
    logP, logZ = fleet_marginals(ratios, days, log_ca, log_c_none, rhos, mus, lag)
    lr, lm = rho_log_weights(rhos), np.log([0.5, 0.5])
    Z, marg = np.exp(log_c_none), np.zeros(D)
    for (rho, wr), (mu, wm) in itertools.product(
        zip(rhos, lr, strict=True), zip(mus, lm, strict=True)
    ):
        g = np.exp(lag_log_pmf(mu, lag))
        for k, a in enumerate(days):
            states = [None, *range(lag + 1)]  # None: not infected, else lag L
            for st in itertools.product(states, repeat=N):
                w = np.exp(log_ca[k] + wr + wm)
                for j, L in enumerate(st):
                    if L is None:
                        w *= 1 - rho
                        continue
                    s = a + L
                    w *= rho * g[L] * (np.exp(ratios[j][s - days[0]]) if s <= t else 1.0)
                Z += w
                if st[0] is not None and a + st[0] <= t:
                    marg[a + st[0] - days[0]] += w
    np.testing.assert_allclose(np.exp(logZ), Z, rtol=1e-10)
    np.testing.assert_allclose(np.exp(logP[0]), marg, rtol=1e-10)


def _random_machines(rng, n_machines):
    import numpy as np

    from slowburn.fleet.allocate import MachineLoss

    out = []
    for _ in range(n_machines):
        t = int(rng.integers(30, 60))
        pi = np.zeros(t + 1)
        lo = int(rng.integers(0, t - 5))
        pi[lo:] = rng.random(t + 1 - lo)
        pi *= rng.uniform(0.05, 0.9) / pi.sum()
        cands = sorted({*rng.choice(t, int(rng.integers(3, 8)), replace=False).tolist(), t})
        forced = [cands[0]] if rng.random() < 0.5 else []
        out.append(MachineLoss(cands, forced, pi, 90.0, 0.8, float(rng.uniform(0.5, 3.0))))
    return out


def test_small_removal_losses_match_dp():
    import numpy as np

    rng = np.random.default_rng(11)
    for m in _random_machines(rng, 40):
        for r in range(min(3, m.max_removals + 1)):
            assert abs(m.loss(r) - m._eval(m.select(r))) < 1e-9 * (1 + m.loss(r))


def test_greedy_equals_brute_force_when_concave():
    import numpy as np

    from slowburn.fleet.allocate import brute_force_allocate, greedy_allocate, total_loss

    rng = np.random.default_rng(12)
    checked = 0
    for _ in range(150):
        ms = _random_machines(rng, int(rng.integers(2, 5)))
        room = sum(m.max_removals for m in ms)
        budget = sum(m.n for m in ms) - int(rng.integers(1, 1 + min(6, room)))
        g = greedy_allocate(ms, budget)
        best, _ = brute_force_allocate(ms, budget)
        assert total_loss(ms, g) >= best - 1e-9
        concave = all(m.step_cost(r) <= m.step_cost(r + 1) + 1e-12
                      for m in ms for r in range(m.max_removals - 1))  # fmt: skip
        if concave:
            checked += 1
            assert abs(total_loss(ms, g) - best) <= 1e-9 * (1 + best)
    assert checked >= 10


@pytest.mark.parametrize("arm", ["abstract", "synthetic_bytes"])
def test_trace_matches_simulate_snapshots(arm):
    cfg, sc = _setup(arm, 9)
    task = RetentionTask("dev", "eval", sc, 3)
    tr = simulate(cfg, task)
    n = trace_days(cfg, 9)
    sim = MachineSim(cfg, sc, task_seed_key(int(cfg["seed"]), task), n, keep_snapshots=True)
    mt = sim.run_to(n).trace()
    assert mt.snapshots == tr.snapshots and mt.obs == tr.obs and mt.histories == tr.histories
    assert mt.n_days == tr.n_days and mt.start == tr.start


def test_fork_with_attack_overrides_equals_fresh():
    cfg, sc = _setup("synthetic_bytes", None)
    key, n = (202, "fleet-test", 4), 16
    ov = {"attack_files_per_day": 3.0, "damage_fraction": 0.5, "attack_target_types": ("csv",)}
    forked = MachineSim(cfg, sc, key, n).run_to(6).fork(6, **ov).run_to(n)
    fresh = MachineSim(cfg, {**sc, "attack_start": 6, **ov}, key, n).run_to(n)
    _same(forked, fresh)
    hit = [f for f, h in forked.histories().items() if h.damaged_day is not None]
    assert hit and all(forked.scen.file_types[f] == "csv" for f in hit)
