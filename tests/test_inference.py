import itertools

import numpy as np
import pytest
from scipy import stats
from scipy.special import logsumexp

from slowburn.inference.bocpd import BetaBinomialConj, NormalInvGammaConj, bocpd_run_length
from slowburn.inference.changepoint import (
    SingleChangepoint,
    geometric_log_prior,
    single_changepoint_posterior,
)
from slowburn.inference.daily import DailyObs, DayScores, make_aggregator
from slowburn.inference.obsmodels import BetaBinomialExceedance, GaussianWeekday, fit_betabinom_rho

# ---- daily aggregators -----------------------------------------------------------------


def _day(probs, pvals, day=0):
    return DayScores(day=day, probs=np.asarray(probs, float), pvals=np.asarray(pvals, float))


def test_exceed_aggregator_counts_and_normalises():
    obs = make_aggregator("exceed", alpha=0.05)(_day([0.1] * 4, [0.01, 0.05, 0.2, 0.9], day=9))
    assert (obs.k, obs.n, obs.weekday) == (2, 4, 2)
    assert obs.value == pytest.approx(0.5)


def test_score_aggregators():
    d = _day([0.0, 0.1, 0.2, 0.9, 1.0], [0.5] * 5)
    assert make_aggregator("mean")(d).value == pytest.approx(0.44)
    assert make_aggregator("trimmed_mean", proportion=0.2)(d).value == pytest.approx(0.4)
    assert make_aggregator("frac_above", reference=0.5)(d).value == pytest.approx(0.4)
    empty = make_aggregator("exceed")(_day([], []))
    assert (empty.k, empty.n) == (0, 0)
    with pytest.raises(ValueError):
        make_aggregator("nope")


# ---- synthetic series helpers ----------------------------------------------------------


def _exceed_series(T, start, q0=0.05, q1=0.25, rho=0.02, seed=0, n_mean=40):
    rng = np.random.default_rng(seed)
    obs = []
    for t in range(T):
        n = int(rng.poisson(n_mean * (0.3 if t % 7 >= 5 else 1.0))) + 1
        q = q1 if start is not None and t >= start else q0
        a, b = q * (1 - rho) / rho, (1 - q) * (1 - rho) / rho
        k = int(stats.betabinom.rvs(n, a, b, random_state=rng))
        obs.append(DailyObs(day=t, value=k / n, k=k, n=n))
    return obs


def _gauss_series(T, start, shift=3.0, seed=0):
    rng = np.random.default_rng(seed)
    weekday_mu = np.array([0.30, 0.31, 0.29, 0.30, 0.32, 0.50, 0.55])  # strong weekend effect
    obs = []
    for t in range(T):
        n = int(rng.poisson(40 * (0.3 if t % 7 >= 5 else 1.0))) + 2
        sd = 0.2 / np.sqrt(n)
        mu = weekday_mu[t % 7] + (shift * 0.2 / np.sqrt(40) if start is not None and t >= start
                                  else 0.0)  # fmt: skip
        obs.append(DailyObs(day=t, value=float(rng.normal(mu, sd)), k=0, n=n))
    return obs


# ---- observation models ----------------------------------------------------------------


def test_fit_betabinom_rho_recovers_dispersion():
    obs = _exceed_series(400, None, q0=0.1, rho=0.05, seed=1)
    k, n = np.array([o.k for o in obs]), np.array([o.n for o in obs])
    m, rho = fit_betabinom_rho(k, n)
    assert m == pytest.approx(0.1, abs=0.02)
    assert rho == pytest.approx(0.05, abs=0.03)


def test_exceedance_model_shapes_and_upward_grid():
    obs = _exceed_series(30, None)
    mdl = BetaBinomialExceedance(n_effect=5, n_null=7).fit_null(obs[:14])
    ll0, ll1, logw0, logw1 = mdl.loglik(obs)
    G = 5 * 4  # effects x activity rates
    H = 7 * len(BetaBinomialExceedance.RHO_GRID)  # benign rate x overdispersion
    assert ll0.shape == (30, H) and ll1.shape == (30, H, G)
    assert logw0.shape == (H,) and logw1.shape == (G,)
    assert np.all(mdl.effects > 0)
    assert logsumexp(logw0) == pytest.approx(0.0) and logsumexp(logw1) == pytest.approx(0.0)
    # null grid brackets the warm-up rate
    assert mdl.null_rates.min() < mdl.null_rate < mdl.null_rates.max()


def test_gaussian_weekday_model_learns_weekday_means():
    obs = _gauss_series(28, None)
    mdl = GaussianWeekday().fit_null(obs)
    assert mdl.mu[5] > mdl.mu[2] + 0.1  # weekend baseline is higher


# ---- single changepoint ----------------------------------------------------------------


def test_geometric_prior_normalised():
    lp = geometric_log_prior(50, hazard=0.02, warmup=10)
    assert np.exp(lp).sum() == pytest.approx(1.0)
    assert np.all(np.isneginf(lp[:10]))


def test_single_cp_posterior_matches_brute_force():
    rng = np.random.default_rng(0)
    T, G = 8, 5
    ll0, ll1 = rng.normal(size=T), rng.normal(size=(T, G))
    logw = np.log(np.full(G, 1 / G))
    lp = geometric_log_prior(T, 0.1, warmup=0)
    post = single_changepoint_posterior(ll0, ll1, logw, lp)
    brute = np.empty(T + 1)
    for tau in range(T + 1):
        brute[tau] = lp[tau] + ll0[:tau].sum() + logsumexp(logw + ll1[tau:].sum(axis=0))
    brute = np.exp(brute - logsumexp(brute))
    np.testing.assert_allclose(post, brute, rtol=1e-10)


def test_single_cp_null_grid_matches_brute_force():
    rng = np.random.default_rng(1)
    T, H, G = 7, 3, 4
    ll0, ll1 = rng.normal(size=(T, H)), rng.normal(size=(T, H, G))
    logw0, logw1 = np.log(np.full(H, 1 / H)), np.log(np.full(G, 1 / G))
    lp = geometric_log_prior(T, 0.1, warmup=2)
    post = single_changepoint_posterior(ll0, ll1, logw1, lp, logw0)
    brute = np.empty(T + 1)
    for tau in range(T + 1):
        per_h = [
            logw0[h] + ll0[:tau, h].sum() + logsumexp(logw1 + ll1[tau:, h, :].sum(axis=0))
            for h in range(H)
        ]
        brute[tau] = lp[tau] + logsumexp(per_h)
    brute = np.exp(brute - logsumexp(brute))
    np.testing.assert_allclose(post, brute, rtol=1e-10, atol=1e-300)


@pytest.mark.parametrize("seed", [0, 1, 2])
def test_single_cp_finds_injected_changepoint_exceedance(seed):
    obs = _exceed_series(60, 35, seed=seed)
    cp = SingleChangepoint(BetaBinomialExceedance(), hazard=0.02, warmup=14)
    post = cp.posterior(obs)
    assert post.sum() == pytest.approx(1.0)
    assert abs(int(np.argmax(post)) - 35) <= 1
    assert post[-1] < 0.01  # "not started" is ruled out


@pytest.mark.parametrize("seed", [0, 1, 2])
def test_single_cp_quiet_on_clean_series(seed):
    obs = _exceed_series(60, None, seed=seed)
    post = SingleChangepoint(BetaBinomialExceedance(), hazard=0.02, warmup=14).posterior(obs)
    assert post[-1] > 0.5


def test_initial_full_backup_does_not_set_the_null():
    # day 0 = initial full backup: huge n and a very different rate; must not bias the null
    from slowburn.inference.changepoint import null_window

    obs = _exceed_series(60, None, seed=5)
    obs[0] = DailyObs(day=0, value=0.0, k=0, n=5000)
    assert null_window(obs, 14)[0].day == 1
    post = SingleChangepoint(BetaBinomialExceedance(), hazard=0.02, warmup=14).posterior(obs)
    assert post[-1] > 0.5


def test_gaussian_weekday_effect_is_not_an_attack():
    obs = _gauss_series(63, None, seed=4)
    post = SingleChangepoint(GaussianWeekday(), hazard=0.02, warmup=14).posterior(obs)
    assert post[-1] > 0.5
    obs = _gauss_series(63, 40, shift=4.0, seed=4)
    post = SingleChangepoint(GaussianWeekday(), hazard=0.02, warmup=14).posterior(obs)
    assert post[37:44].sum() > 0.9  # mass within +-3 days of the true start


def test_prior_only_mode_returns_prior():
    obs = _exceed_series(30, 20)
    cp = SingleChangepoint(BetaBinomialExceedance(), hazard=0.05, warmup=5, use_data=False)
    np.testing.assert_allclose(cp.posterior(obs), np.exp(geometric_log_prior(30, 0.05, 5)))


def test_uniform_prior_ablation():
    from slowburn.inference.changepoint import uniform_log_prior

    lp = uniform_log_prior(20, warmup=5)
    assert np.exp(lp).sum() == pytest.approx(1.0) and np.all(np.isneginf(lp[:5]))
    obs = _exceed_series(60, 35, seed=0)
    cp = SingleChangepoint(BetaBinomialExceedance(), hazard=0.02, warmup=14, prior="uniform")
    assert abs(int(np.argmax(cp.posterior(obs))) - 35) <= 1
    with pytest.raises(ValueError):
        SingleChangepoint(BetaBinomialExceedance(), 0.02, 14, prior="bogus")


# ---- BOCPD -----------------------------------------------------------------------------


def _segment_loglik(model, xs):
    """Marginal likelihood of one segment = product of sequential predictives."""
    st = model.init()
    total = 0.0
    for x in xs:
        total += float(model.logpred(x, st)[0])
        st = model.update(st, x)
    return total


@pytest.mark.parametrize("model_name", ["betabinom", "nig"])
def test_bocpd_matches_brute_force_enumeration(model_name):
    rng = np.random.default_rng(3)
    T, H = 6, 0.2
    if model_name == "betabinom":
        model = BetaBinomialConj(a0=1.0, b0=9.0)
        xs = [(int(k), 20) for k in rng.integers(0, 8, T)]
    else:
        model = NormalInvGammaConj()
        xs = list(rng.normal(size=T))
    rl = bocpd_run_length(xs, model, hazard=H)
    brute = np.full(T + 1, -np.inf)
    for cps in itertools.product([0, 1], repeat=T - 1):  # cp before x_1..x_{T-1}
        bounds = [0] + [i + 1 for i, c in enumerate(cps) if c] + [T]
        lp = sum(np.log(H) if c else np.log(1 - H) for c in cps)
        lp += sum(_segment_loglik(model, xs[a:b]) for a, b in itertools.pairwise(bounds))
        r = T - bounds[-2]
        brute[r] = np.logaddexp(brute[r], lp)
    brute = np.exp(brute - logsumexp(brute))
    np.testing.assert_allclose(rl, brute, atol=1e-10)


def test_bocpd_start_posterior_finds_shift():
    obs = _exceed_series(60, 35, seed=0)
    from slowburn.inference.changepoint import BOCPDStart

    post = BOCPDStart(statistic="exceed", hazard=0.02, warmup=14).posterior(obs)
    assert post.sum() == pytest.approx(1.0)
    assert abs(int(np.argmax(post)) - 35) <= 2


@pytest.mark.parametrize("kind", ["single_cp", "bocpd", "prior_only", "single_cp_uniform"])
@pytest.mark.parametrize("obs_model", ["betabinom", "gaussian_weekday"])
def test_posterior_path_equals_daily_recomputation(kind, obs_model):
    from slowburn.inference.changepoint import make_start_model

    obs = _exceed_series(40, 25, seed=1) if obs_model == "betabinom" else _gauss_series(40, 25)
    model = make_start_model(kind, "x", obs_model, hazard=0.01, warmup=10)
    Ts = list(range(5, 41))
    path = model.posterior_path(obs, Ts)
    for T in Ts:
        fresh = make_start_model(kind, "x", obs_model, hazard=0.01, warmup=10)
        np.testing.assert_allclose(path[T], fresh.posterior(obs[:T]), rtol=1e-9, atol=1e-12)


def test_hazard_from_window():
    from slowburn.inference.changepoint import hazard_from_window

    for p in (0.005, 0.01, 0.05, 0.2):
        h = hazard_from_window(p, 60)
        assert 1 - (1 - h) ** 60 == pytest.approx(p)
        lp = geometric_log_prior(60 + 14, h, warmup=14)
        assert 1 - np.exp(lp[-1]) == pytest.approx(p)  # prior P(started) over the window
    with pytest.raises(ValueError):
        hazard_from_window(1.0, 60)


def test_timing_log_prior_specs():
    from slowburn.inference.changepoint import (
        geometric_log_prior,
        timing_log_prior,
        uniform_log_prior,
    )

    T, w = 150, 14
    assert np.array_equal(timing_log_prior(T, {"kind": "geometric", "hazard": 0.01}, w),
                          geometric_log_prior(T, 0.01, w))  # fmt: skip
    assert np.array_equal(timing_log_prior(T, {"kind": "uniform"}, w), uniform_log_prior(T, w))
    spec = {"kind": "gaussian", "center": 121, "sd": 12, "p_attack": 0.99}
    for TT in (10, 100, 121, 200):
        p = np.exp(timing_log_prior(TT, spec, w))
        assert p.sum() == pytest.approx(1.0) and (p[: min(w, TT)] == 0).all()
    p = np.exp(timing_log_prior(300, spec, w))
    assert int(np.argmax(p[:-1])) == 121 and p[-1] == pytest.approx(0.01, abs=1e-6)
    with pytest.raises(ValueError):
        timing_log_prior(T, {"kind": "nope"}, w)
