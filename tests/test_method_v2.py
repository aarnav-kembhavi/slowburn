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


def _sweep_rows():
    import pandas as pd

    rows = []
    # (variant, world, policy, q, recovery, vfail-ness via retained/recovery, work lost)
    spec = {"a": {"slowburn": (0.30, 0.9, 10.0)}, "b": {"slowburn": (0.10, 0.95, 12.0)},
            "c": {"slowburn": (0.12, 0.95, 11.0)}}  # fmt: skip
    for v, pols in spec.items():
        for w in ("u", "l"):
            for pol, (q0fail, rec, wl) in {**pols, "prior_only": (0.10, 0.9, 10.0)}.items():
                for q in (0.0, 1.0):
                    n = 100
                    k = int(round(q0fail * n)) if q == 0.0 else 0
                    for i in range(n):
                        fail = i < k
                        ok = (not fail) and (i < k + rec * n or q == 0.0)
                        rows.append({"split": "dev", "variant": v, "world": w, "policy": pol,
                                     "detect_prob": q, "clean_snapshot_retained": 1,
                                     "clean_recovery": int(ok),
                                     "work_lost_whole_system_hours": wl})  # fmt: skip
    return pd.DataFrame(rows)


def test_stage_a_rule():
    from slowburn.bench.method_v2 import select_stage_a

    v, met, board = select_stage_a(_sweep_rows())
    assert not board.loc["a", "eligible"] and board.loc["b", "eligible"]
    assert not board.loc["c", "eligible"]  # q = 0 excess 0.02 > 0.01
    assert met and v == "b"


def test_stage_a_refuses_test_rows():
    from slowburn.bench.method_v2 import select_stage_a

    df = _sweep_rows()
    df.loc[0, "split"] = "test"
    with pytest.raises(ValueError, match="DEV"):
        select_stage_a(df)


def test_soft_delay_never_reaches_zero_and_lets_evidence_move_the_gate():
    from slowburn.retention.dp import discovery_posterior, discovery_survival, gate_day

    S = discovery_survival("soft", 30, tail=0.1, alpha=1.0)
    k = np.arange(-1, 1000)
    s = S(k)
    assert s[0] == 1.0 and S(0) == 1.0 and np.all(np.diff(s) <= 1e-15) and S(999) > 0
    assert S(30) == pytest.approx(0.1 * 2**-1)  # core exhausted, tail remains
    with pytest.raises(ValueError):
        discovery_survival("soft", 30, tail=0.0)
    # evidence says the attack started on day 10; discovery on day 100; assumed core 30 days
    T = 100
    post = np.r_[np.full(T + 1, 1e-4), 0.0]
    post[10] = 1.0
    post /= post.sum()
    hard = discovery_posterior(post, T, discovery_survival("uniform", 30))
    soft = discovery_posterior(post, T, S)
    assert gate_day(hard[:-1], 0.8) >= 70  # the hard bound overrides the evidence
    assert gate_day(soft[:-1], 0.8) < 10  # the soft tail lets the evidence through


def test_select_blind_safe_hard_constraint():
    import pandas as pd

    from slowburn.bench.method_v2 import select_blind_safe

    def rows(variant, grid_worlds, sb_fail, n=200, rec=1):
        out = []
        for unit in grid_worlds:
            for i in range(n):
                for pol, fail in (("slowburn", i < sb_fail), ("prior_only", i < 10)):
                    out.append({"split": "dev", "variant": variant, "policy": pol,
                                "detect_prob": 0.0, "rep": i, "discovery_delay": 7,
                                "benign_invalid_rate": 0.01, "attack_start": 100,
                                "clean_snapshot_retained": 1, "clean_recovery": int(not fail),
                                "work_lost_whole_system_hours": 10.0, **unit})  # fmt: skip
        return out

    worlds = [{"world": w, "budget": 4} for w in ("u", "e", "l", "b")]
    worst = [{"budget": k} for k in (4, 6, 8, 12)]
    wdf = pd.DataFrame(rows("ok", worlds, 11) + rows("bad", worlds, 11))
    xdf = pd.DataFrame(
        rows("ok", worst, 11) + rows("bad", worst[:3], 11) + rows("bad", worst[3:], 40)
    )
    v, board, units = select_blind_safe(wdf, xdf)
    assert v == "ok" and board.loc["ok", "eligible"] and not board.loc["bad", "eligible"]
    bad = units[(units.variant == "bad") & ~units.passes]
    assert list(bad.unit) == [12] and bad.excess.iloc[0] == pytest.approx(0.15)


# ---- D60 scoring ---------------------------------------------------------------------------

import pandas as pd  # noqa: E402

from slowburn.bench import method_v2 as mv  # noqa: E402


def _rows(variant, policy, q, rec, n, world="uniform", delay=60, budget=4, wl=1644.030625):
    return pd.DataFrame({"split": "dev", "variant": variant, "policy": policy, "detect_prob": q,
                         "attack_start": 100, "world": world, "benign_invalid_rate": 0.01,
                         "rep": range(n), "discovery_delay": delay, "budget": budget,
                         "clean_recovery": rec, "clean_snapshot_retained": 1,
                         "work_lost_whole_system_hours": wl})  # fmt: skip


def _grids(v4_rec_q, v4_wl):
    n = 40
    normal = pd.concat(
        [_rows(v, pol, q, 1, n, world=w, wl=wl)
         for w in ("uniform", "early", "late", "bursty") for q in (0.0, 1.0)
         for v, pol, wl in (("hard", "prior_only", 1700.0), ("hard", "slowburn", 1644.030625),
                            ("v4_60", "slowburn", v4_wl))])  # fmt: skip
    worst = pd.concat([_rows(v, pol, 0.0, 1, n, world="x", budget=k).drop(columns="world")
                       for k in (4, 6, 8, 12) for v, pol in (("hard", "prior_only"),
                                                             ("v4_60", "slowburn"))])  # fmt: skip
    under = pd.concat(
        [_rows(f"v4_{M}", "slowburn", q, (np.arange(n) < n * r).astype(int), n)
         for M in (14, 30) for q, r in v4_rec_q.items()])  # fmt: skip
    return normal, worst, under


def test_d60_adopts_only_with_rescue_below_q1_and_within_cost():
    tails = {0.05: {60: "v4_60", 14: "v4_14", 30: "v4_30"}}
    rec = {0.0: 0.1, 0.2: 0.15, 0.5: 0.6, 1.0: 0.9}
    out = mv.d60_select(*_grids(rec, 1700.0), tails, "hard")
    b = out["board"].iloc[0]
    assert b.c1 and b.c2 and out["chosen_tail"] == 0.05
    assert b.rescue_q == "0.5,1.0" and out["adopt"]  # 0.2: gain 0.05 < 0.10
    # rescue only at q = 1 does not count
    out = mv.d60_select(*_grids({0.0: 0.1, 0.2: 0.1, 0.5: 0.1, 1.0: 0.9}, 1700.0), tails, "hard")
    assert out["board"].iloc[0].rescue_q == "1.0" and not out["adopt"]
    # C2: work lost above 1.10 x v2 -> not eligible, nothing chosen
    out = mv.d60_select(*_grids(rec, 1808.44), tails, "hard")
    assert not out["board"].iloc[0].c2 and out["chosen_tail"] is None and not out["adopt"]


def test_d60_refuses_unreproduced_hard_variant():
    normal, worst, under = _grids({0.0: 0.1, 0.2: 0.5, 0.5: 0.6, 1.0: 0.9}, 1700.0)
    normal.loc[(normal.variant == "hard") & (normal.policy == "slowburn"),
               "work_lost_whole_system_hours"] = 1600.0  # fmt: skip
    with pytest.raises(ValueError, match="reproduce"):
        mv.d60_select(normal, worst, under, {0.05: {60: "v4_60", 14: "v4_14", 30: "v4_30"}},
                      "hard")  # fmt: skip
