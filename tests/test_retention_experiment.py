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


def test_timing_prior_reaches_dp_and_restore_gate(cfg):
    """D39: the assumed attack-timing prior (misspecification sweep) changes both the retention
    DP's kept set and the restore gate day, for SlowBurn and for the prior-only policy; and it
    changes the end-to-end restore."""
    import numpy as np

    from slowburn.bench.retention_experiment import evaluate_trace, start_posteriors
    from slowburn.retention.base import PosteriorDP, RetentionContext
    from slowburn.retention.dp import (
        discovery_posterior,
        discovery_survival,
        gate_day,
        retention_posterior,
    )

    params = {**cfg["scenario"], "detect_prob": 0.5, "benign_invalid_rate": 0.01,
              "null_prior": (0.5, 100.5)}  # fmt: skip
    task = RetentionTask("dev", "eval", params, 0)
    trace = simulate(cfg, task)
    hp = cfg["hp"]
    S = discovery_survival(hp["assumed_discovery"]["kind"], hp["assumed_discovery"]["max_days"])
    td = trace.start + cfg["discovery_delay"][-1]

    def gauss(name, center):
        tp = {"name": name, "kind": "gaussian", "center": center, "sd": 2, "p_attack": 0.99}
        return {**hp, "timing_prior": tp}

    def run(h):
        path, prior = start_posteriors(trace, h, cfg["warmup_days"], params["null_prior"], {})
        gates, kept = {}, {}
        for ev in (True, False):
            post = (path if ev else prior)[td + 1]
            gates[ev] = gate_day(discovery_posterior(post, td, S), hp["gate"])
            pol = PosteriorDP(hp["penalty"], use_evidence=ev, gate=hp["gate"])
            held: dict[int, int] = {}
            for t in range(td + 1):
                held[t] = t
                rpi = retention_posterior(path[t + 1], t, S)
                ppi = retention_posterior(prior[t + 1], t, S)
                ctx = RetentionContext(day=t, snapshot_days=dict(held), budget=4,
                                       daily_stat=np.zeros(t + 1), start_posterior=path[t + 1],
                                       retention_pi=rpi, prior_retention_pi=ppi)  # fmt: skip
                held = {sid: held[sid] for sid in pol.decide(ctx)}
            kept[ev] = sorted(held.values())
        return gates, kept

    g_early, k_early = run(gauss("early", 8))
    g_late, k_late = run(gauss("late", 20))
    for ev in (True, False):
        assert g_early[ev] < g_late[ev]
        assert k_early[ev] != k_late[ev]
    cols = ["policy", "budget", "discovery_delay", "restore_point", "oldest_retained_age"]
    pols = ("slowburn", "prior_only")
    a = pd.DataFrame(evaluate_trace(cfg, task, trace, gauss("early", 8), pols))[cols]
    b = pd.DataFrame(evaluate_trace(cfg, task, trace, gauss("late", 20), pols))[cols]
    for pol in pols:
        assert not a[a.policy == pol].equals(b[b.policy == pol])


def test_dev_sweep_runs_on_test_split_behind_the_gates(cfg, tmp_path):
    """TEST path of the sweep entrypoint (C2/D72, D79, D71): token mode, temporary gate files,
    no real TEST file opened. A missing grid entry is refused; with the entry the machines are
    test-keyed and differ from the DEV machines."""
    from slowburn.bench.registry import FrozenGateError, grid_sha256
    from slowburn.bench.retention_experiment import run_dev_sweep, scenario_grid_of

    frozen, v2 = tmp_path / "frozen.yaml", tmp_path / "frozen_v2.yaml"
    frozen.write_text("frozen: true\nparams: {}\n")
    scfg = {**cfg, "reps": 1, "budgets": cfg["budgets"][:1], "split": "test",
            "experiment": "test_tiny", "frozen_path": str(frozen), "frozen_v2_path": str(v2),
            "variants": [{"name": "base", "hp": {}}], "policies": ["slowburn", "gfs"]}
    v2.write_text("scenario_grids: {}\n")
    with pytest.raises(FrozenGateError, match="no scenario_grids entry"):
        run_dev_sweep({**scfg, "output_dir": str(tmp_path / "t0")}, log=lambda *a: None)
    digest = grid_sha256(scenario_grid_of(scfg))
    v2.write_text(f"scenario_grids:\n  test_tiny:\n    sha256: {digest}\n")
    test = run_dev_sweep({**scfg, "output_dir": str(tmp_path / "t")}, log=lambda *a: None)
    dev = run_dev_sweep({**scfg, "split": "dev", "output_dir": str(tmp_path / "d")},
                        log=lambda *a: None)  # fmt: skip
    assert len(test) == len(dev) > 0
    cols = ["work_lost_h"]  # summary over the same cells: other machines, other values
    assert not test[cols].reset_index(drop=True).equals(dev[cols].reset_index(drop=True))
