"""C: retention experiment end to end (token mode, abstract evidence)."""

import pandas as pd
import pytest

from slowburn.bench.retention_experiment import (
    RetentionTask,
    run_retention_experiment,
    simulate,
    task_cache_key,
    task_seed_key,
)
from slowburn.utils.config import load_config


@pytest.fixture(scope="module")
def cfg():
    return load_config("configs/retention_smoke.yaml")


def test_cells_are_paired_across_evidence_parameters(cfg):
    p1 = {**cfg["scenario"], "detect_prob": 1.0, "benign_invalid_rate": 0.0}
    p2 = {**cfg["scenario"], "detect_prob": 0.0, "benign_invalid_rate": 0.05}
    a, b = RetentionTask("dev", "eval", p1, 0), RetentionTask("dev", "eval", p2, 0)
    assert task_seed_key(1, a) == task_seed_key(1, b)
    assert task_cache_key(1, a) != task_cache_key(1, b)
    ta, tb = simulate(cfg, a), simulate(cfg, b)
    assert ta.snapshots == tb.snapshots  # identical churn and attack
    strip = lambda h: {f: (x.change_days, x.damaged_day) for f, x in h.items()}  # noqa: E731
    assert strip(ta.histories) == strip(tb.histories)
    # flags are per version: every damaged version is flagged when detect_prob = 1
    assert all(x.damaged_day in x.flagged_days for x in ta.histories.values() if x.damaged_day)
    flags_a = sum(o.k for o in ta.obs)
    assert flags_a == sum(1 for h in ta.histories.values() if h.damaged_day is not None)


@pytest.fixture(scope="module")
def results(cfg, tmp_path_factory):
    out = tmp_path_factory.mktemp("ret")
    return run_retention_experiment({**cfg, "output_dir": str(out)}, log=lambda *a: None)


def test_retention_experiment_rows(results, cfg):
    df = results
    n_cells = 4
    n_policies = 9  # 8 snapshot policies (incl. keep_first) + amoeba_style
    n_rows = n_cells * cfg["reps"] * len(cfg["discovery_delay"]) * n_policies
    assert len(df) == n_rows * len(cfg["budgets"])
    snap = df[df.policy != "amoeba_style"]
    assert (snap.snapshots_retained <= snap.budget).all()
    assert set(df.budget) == set(cfg["budgets"])
    assert (df.work_lost_ideal_hours > 0).all()
    assert (snap.snapshots_scanned >= 0).all()
    assert df.clean_recovery.isin([0, 1]).all()
    assert (df.residual_damaged_files >= 0).all()


def test_oracle_always_recovers_and_keep_last_n_obeys_proposition_1(results, cfg):
    df = results
    oracle = df[df.policy == "oracle"]
    assert (oracle.clean_snapshot_retained == 1).all()
    kln = df[df.policy == "keep_last_n"]
    late = kln[kln.discovery_delay >= kln.budget - 1]
    assert (late.clean_snapshot_retained == 0).all()  # Proposition 1


def test_perfect_evidence_slowburn_recovers(results):
    df = results
    sb = df[(df.policy == "slowburn") & (df.detect_prob == 1.0) & (df.benign_invalid_rate == 0.0)]
    assert sb.clean_recovery.mean() == 1.0


def test_retention_tuning_two_stage(cfg, tmp_path):
    import yaml

    from slowburn.bench.retention_experiment import run_retention_tuning

    tcfg = {
        **cfg,
        "output_dir": str(tmp_path / "tune"),
        "frozen_path": str(tmp_path / "f.yaml"),
        "reps": 1,
        "tuning": {
            "stage1": {"p_attack_within_window": [0.01, 0.2], "gate": [0.5, 0.9]},
            "stage2": {
                "penalty": [30.0, 120.0],
                "assumed_discovery_max_days": [30],
                "backbone": [0.0, 0.4],
            },
        },
    }
    res = run_retention_tuning(tcfg, log=lambda *a: None)
    assert len(res["stage1"]) == 4 and len(res["stage2"]) == 4
    frozen = yaml.safe_load((tmp_path / "f.yaml").read_text())
    assert frozen["frozen"] is False
    assert frozen["params"]["penalty"] in (30.0, 120.0)
    assert frozen["params"]["p_attack_within_window"] in (0.01, 0.2)
    assert frozen["params"]["gate"] in (0.5, 0.9) and frozen["params"]["backbone"] in (0.0, 0.4)


def test_retention_rules_refuse_test_split():
    import pandas as pd

    from slowburn.bench.tune import retention_stage1, retention_stage2

    df = pd.DataFrame(
        {
            "split": ["test"],
            "policy": ["slowburn"],
            "clean_recovery": [1],
            "work_lost_whole_system_hours": [1.0],
            "hp_p_attack_within_window": [0.01],
            "hp_gate": [0.5],
            "hp_backbone": [0.0],
            "hp_penalty": [60.0],
            "hp_assumed_discovery_max": [30],
        }
    )
    with pytest.raises(ValueError, match="DEV"):
        retention_stage1(df)
    with pytest.raises(ValueError, match="DEV"):
        retention_stage2(df)


def test_scenario_grid_gate_and_summaries(cfg, tmp_path):
    import pandas as pd
    import yaml

    from slowburn.bench.registry import FrozenGateError
    from slowburn.bench.retention_experiment import (
        cell_table,
        grid_summary,
        preregister_grid,
        scenario_grid_of,
    )

    fpath = tmp_path / "f.yaml"
    preregister_grid(cfg, path=str(fpath))
    doc = yaml.safe_load(fpath.read_text())
    assert doc["params"]["scenario_grid"] == scenario_grid_of(cfg)
    doc["frozen"] = True
    doc["params"].update(cfg["hp"])
    fpath.write_text(yaml.safe_dump(doc))
    other = {**cfg, "split": "test", "budgets": [4], "frozen_path": str(fpath),
             "output_dir": str(tmp_path / "o")}  # fmt: skip
    with pytest.raises(FrozenGateError, match="scenario_grid"):
        run_retention_experiment(other, log=lambda *a: None)
    df = pd.DataFrame({"budget": [4, 4, 4, 4], "discovery_delay": [3, 3, 10, 10],
                       "attack_start": 12, "detect_prob": 1.0, "benign_invalid_rate": 0.0,
                       "policy": ["a", "b", "a", "b"], "clean_recovery": [1, 0, 0, 1],
                       "work_lost_whole_system_hours": [10, 20, 30, 40],
                       "work_lost_selective_file_hours": 0, "work_lost_ideal_hours": 5,
                       "snapshots_scanned": 1})  # fmt: skip
    summ = grid_summary(cell_table(df))
    assert summ.loc["a", "recovery_worst"] == 0 and summ.loc["a", "work_lost_worst"] == 30
    assert summ.loc["b", "recovery_avg"] == 0.5 and summ.loc["a", "cells"] == 2


def test_slowburn_never_sees_cell_truth(cfg):
    """SlowBurn's decisions and restore depend only on the trace (flags, churn) and frozen hp:
    relabelling the cell's detection probability / benign rate, or changing which delays are
    evaluated, leaves every SlowBurn and prior-only output unchanged."""
    from slowburn.bench.retention_experiment import evaluate_trace

    params = {**cfg["scenario"], "detect_prob": 0.9, "benign_invalid_rate": 0.05,
              "null_prior": (0.5, 100.5)}  # fmt: skip
    task = RetentionTask("dev", "eval", params, 0)
    trace = simulate(cfg, task)
    cols = ["policy", "budget", "discovery_delay", "restore_point", "clean_recovery",
            "snapshots_scanned", "work_lost_whole_system_hours"]  # fmt: skip
    pols = ("slowburn", "prior_only")
    a = pd.DataFrame(evaluate_trace(cfg, task, trace, cfg["hp"], pols))[cols]
    relabelled = RetentionTask("dev", "eval", {**params, "detect_prob": 0.0,
                                               "benign_invalid_rate": 0.0}, 0)  # fmt: skip
    b = pd.DataFrame(evaluate_trace(cfg, relabelled, trace, cfg["hp"], pols))[cols]
    assert a.equals(b)
    one = {**cfg, "discovery_delay": [cfg["discovery_delay"][-1]]}
    c = pd.DataFrame(evaluate_trace(one, task, trace, cfg["hp"], pols))[cols]
    last = a[a.discovery_delay == cfg["discovery_delay"][-1]].reset_index(drop=True)
    assert c.reset_index(drop=True).equals(last)
