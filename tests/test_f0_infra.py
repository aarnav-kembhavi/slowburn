"""F0: parallel runner, registry / frozen gate, statistics, LaTeX output."""

import math
import os

import numpy as np
import pandas as pd
import pytest
from scipy import stats

from slowburn.bench.latex import escape, to_latex_table
from slowburn.bench.parallel import run_tasks
from slowburn.bench.registry import (
    FrozenGateError,
    check_split_allowed,
    load_frozen,
    machine_key,
    update_frozen,
)
from slowburn.bench.stats import (
    bootstrap_mean_ci,
    holm,
    mcnemar_exact,
    risk_difference,
    wilcoxon_rank_biserial,
)

# ---- parallel runner -------------------------------------------------------------------


def test_run_tasks_parallel_preserves_order():
    out = run_tasks(math.sqrt, [1.0, 4.0, 9.0, 16.0], workers=2, log=lambda *a: None)
    assert out == [1.0, 2.0, 3.0, 4.0]


def test_run_tasks_caches_and_resumes(tmp_path):
    out = run_tasks(math.sqrt, [4.0, 9.0], cache_dir=tmp_path, log=lambda *a: None)
    assert len(list(tmp_path.glob("*.pkl"))) == 2
    logs = []
    again = run_tasks(math.sqrt, [4.0, 9.0], cache_dir=tmp_path, log=logs.append)
    assert again == out and any("resuming: 2/2" in m for m in logs)


def test_run_tasks_gives_up_after_pool_restarts():
    # os._exit kills the worker: every pool breaks; the runner retries, then raises
    with pytest.raises(RuntimeError, match="failed after 1 pool restarts"):
        run_tasks(os._exit, [1], workers=2, max_pool_restarts=1, log=lambda *a: None)


# ---- registry and frozen gate ----------------------------------------------------------


def test_machine_keys_differ_by_split_and_are_stable():
    a = machine_key(1, "dev", "retention", {"q": 0.5}, 3)
    assert a == machine_key(1, "dev", "retention", {"q": 0.5}, 3)
    assert a != machine_key(1, "test", "retention", {"q": 0.5}, 3)
    with pytest.raises(ValueError):
        machine_key(1, "train", "retention", {}, 0)


def test_frozen_gate(tmp_path):
    path = tmp_path / "frozen.yaml"
    assert check_split_allowed("dev", {}, path) == {}
    with pytest.raises(FrozenGateError, match="not frozen"):
        check_split_allowed("test", {}, path)
    update_frozen({"file_alpha": 0.01}, "chosen on dev", path=path)
    with pytest.raises(FrozenGateError, match="not frozen"):
        check_split_allowed("test", {"file_alpha": 0.01}, path)
    update_frozen({"restore_quantile": 0.1}, "freeze", freeze=True, path=path)
    doc = load_frozen(path)
    assert doc["frozen"] and doc["params"] == {"file_alpha": 0.01, "restore_quantile": 0.1}
    assert len(doc["history"]) == 2
    assert check_split_allowed("test", {"file_alpha": 0.01}, path)["file_alpha"] == 0.01
    with pytest.raises(FrozenGateError, match="overrides"):
        check_split_allowed("test", {"file_alpha": 0.05}, path)
    with pytest.raises(FrozenGateError, match="is frozen"):
        update_frozen({"file_alpha": 0.05}, "sneaky", path=path)


# ---- statistics ------------------------------------------------------------------------


def test_mcnemar_exact_matches_binomial():
    a = np.array([1] * 12 + [0] * 3 + [1] * 10 + [0] * 5)
    b = np.array([0] * 12 + [1] * 3 + [1] * 10 + [0] * 5)
    r = mcnemar_exact(a, b)
    assert (r["n_method_only"], r["n_baseline_only"]) == (12, 3)
    assert r["p_value"] == pytest.approx(stats.binomtest(12, 15, 0.5).pvalue)
    assert mcnemar_exact(a, a)["p_value"] == 1.0


def test_risk_difference_ci_brackets_estimate():
    rng = np.random.default_rng(0)
    a = rng.random(60) < 0.8
    b = rng.random(60) < 0.4
    r = risk_difference(a, b, rng=rng)
    assert r["risk_difference"] == pytest.approx(a.mean() - b.mean())
    assert r["ci_low"] <= r["risk_difference"] <= r["ci_high"]


def test_wilcoxon_rank_biserial():
    x = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0])
    r = wilcoxon_rank_biserial(x, x - 1)  # method always larger by 1
    assert r["rank_biserial"] == pytest.approx(1.0)
    assert r["p_value"] == pytest.approx(stats.wilcoxon(np.ones(8)).pvalue)
    mixed = wilcoxon_rank_biserial(np.array([1.0, -2.0, 3.0]), np.zeros(3))
    assert mixed["rank_biserial"] == pytest.approx((1 + 3 - 2) / 6)
    assert wilcoxon_rank_biserial(x, x)["p_value"] == 1.0


def test_holm():
    adj = holm([0.01, 0.04, 0.03, 0.2])
    np.testing.assert_allclose(adj, [0.04, 0.09, 0.09, 0.2])
    assert np.all(adj <= 1.0)


def test_bootstrap_mean_ci():
    m, lo, hi = bootstrap_mean_ci(np.arange(100.0))
    assert m == pytest.approx(49.5) and lo < m < hi


# ---- LaTeX -----------------------------------------------------------------------------


def test_latex_table_escapes_and_formats():
    df = pd.DataFrame({"policy": ["keep_last_n", "a&b"], "rate": [0.12345, float("nan")]})
    tex = to_latex_table(df, caption="Rates 100%", label="tab:x")
    assert r"keep\_last\_n & 0.123 \\" in tex
    assert r"a\&b & -- \\" in tex
    assert r"\caption{Rates 100\%}" in tex and r"\toprule" in tex and r"\bottomrule" in tex
    assert escape("x_y") == r"x\_y"


def test_statistic_rule_picks_best_eligible_and_breaks_ties_by_alpha():
    from slowburn.bench.tune import statistic_rule

    rows = []
    spec = {
        "chunk_a0.05": (0.30, 0.0),
        "file_a0.05": (0.50, 0.0),
        "file_a0.01": (0.495, 0.0),
        "file_a0.005": (0.60, 0.20),
    }  # (attack mass, clean false-alarm rate)
    for stat, (mass, fa) in spec.items():
        for rep in range(10):
            base = {
                "split": "dev",
                "model": "single_cp",
                "discovery_delay": 14,
                "statistic": stat,
                "detector": "d",
                "damage_fraction": 0.1,
                "attack_target_types": "all",
                "benign_invalid_rate": 0.0,
                "rep": rep,
            }
            rows.append(
                {
                    **base,
                    "attack": 1,
                    "mass_within_3": mass,
                    "missed": 0,
                    "map_signed_error_days": 1.0,
                    "false_alarm_p05": np.nan,
                }
            )
            rows.append(
                {
                    **base,
                    "attack": 0,
                    "mass_within_3": np.nan,
                    "missed": np.nan,
                    "map_signed_error_days": np.nan,
                    "false_alarm_p05": float(rep < fa * 10),
                }
            )
    board, choice = statistic_rule(pd.DataFrame(rows))
    assert not board.loc["file_a0.005", "eligible"]  # best score but too many false alarms
    assert choice == "file_a0.01"  # within 0.01 of file_a0.05 -> smaller alpha
    with pytest.raises(ValueError, match="DEV"):
        statistic_rule(pd.DataFrame(rows).assign(split="test"))
