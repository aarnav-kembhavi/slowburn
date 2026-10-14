"""C: retention experiment end to end (token mode, abstract evidence)."""

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
    assert ta.histories == tb.histories
    flags_a = sum(o.k for o in ta.obs)
    assert flags_a == sum(1 for h in ta.histories.values() if h.damaged_day is not None)


@pytest.fixture(scope="module")
def results(cfg, tmp_path_factory):
    out = tmp_path_factory.mktemp("ret")
    return run_retention_experiment({**cfg, "output_dir": str(out)}, log=lambda *a: None)


def test_retention_experiment_rows(results, cfg):
    df = results
    n_cells = 4
    n_policies = 8  # 7 snapshot policies + amoeba_style
    assert len(df) == n_cells * cfg["reps"] * len(cfg["discovery_delay"]) * n_policies
    snap = df[df.policy != "amoeba_style"]
    assert (snap.snapshots_retained <= cfg["hp"]["budget"]).all()
    assert df.clean_recovery.isin([0, 1]).all()
    assert (df.residual_damaged_files >= 0).all()


def test_oracle_always_recovers_and_keep_last_n_obeys_proposition_1(results, cfg):
    df = results
    oracle = df[df.policy == "oracle"]
    assert (oracle.clean_snapshot_retained == 1).all()
    kln = df[df.policy == "keep_last_n"]
    late = kln[kln.discovery_delay >= cfg["hp"]["budget"] - 1]
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
            "stage1": {"p_attack_within_window": [0.01, 0.2], "restore_quantile": [0.05, 0.25]},
            "stage2": {"penalty": [30.0, 120.0], "assumed_discovery_max_days": [30]},
        },
    }
    res = run_retention_tuning(tcfg, log=lambda *a: None)
    assert len(res["stage1"]) == 4 and len(res["stage2"]) == 2
    frozen = yaml.safe_load((tmp_path / "f.yaml").read_text())
    assert frozen["frozen"] is False
    assert frozen["params"]["penalty"] in (30.0, 120.0)
    assert frozen["params"]["p_attack_within_window"] in (0.01, 0.2)


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
            "hp_restore_quantile": [0.1],
            "hp_penalty": [60.0],
            "hp_assumed_discovery_max": [30],
        }
    )
    with pytest.raises(ValueError, match="DEV"):
        retention_stage1(df)
    with pytest.raises(ValueError, match="DEV"):
        retention_stage2(df)
