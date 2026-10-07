import numpy as np
import pytest

from slowburn.bench.detector_experiment import run_detector_experiment
from slowburn.bench.inference_experiment import (
    MachineTask,
    alarm_thresholds,
    detection_table,
    machine_key,
    run_inference_experiment,
    start_metrics,
    summarise,
)
from slowburn.utils.config import load_config


def test_start_metrics_attack():
    post = np.zeros(11)
    post[[4, 5, 9]] = [0.2, 0.7, 0.1]
    m = start_metrics(post, prior_p_started=0.3, true_start=5)
    assert m["p_started"] == pytest.approx(1.0)
    assert m["map_start"] == 5 and m["map_error_days"] == 0 and m["missed"] == 0
    assert m["mass_within_0"] == pytest.approx(0.7)
    assert m["mass_within_1"] == pytest.approx(0.9)
    assert m["expected_abs_error_days"] == pytest.approx(0.2 * 1 + 0.1 * 4)


def test_start_metrics_missed_and_clean():
    post = np.zeros(11)
    post[-1], post[5] = 0.8, 0.2
    m = start_metrics(post, 0.3, true_start=5)
    assert m["missed"] == 1 and m["map_error_days"] is None
    c = start_metrics(post, 0.3, true_start=None)
    assert c["false_alarm_p05"] == 0 and c["false_alarm_p09"] == 0
    assert "mass_within_3" not in c


def test_dev_and_test_machines_have_different_seeds():
    params = {"damage_fraction": 0.1}
    dev = machine_key(1, MachineTask("dev", params, True, 0))
    test = machine_key(1, MachineTask("test", params, True, 0))
    assert dev != test


def _fake_result(split, attack, traj, start_days=(5, 6, 7, 8, 9, 10)):
    return {"task": MachineTask(split, {"damage_fraction": 0.1}, attack, 0),
            "traj": {("d", "exceed", "single_cp", 0.01): np.asarray(traj, dtype=float)},
            "traj_days": list(start_days)}  # fmt: skip


def test_alarm_thresholds_hit_target_rate_on_dev_only():
    clean = [_fake_result("dev", False, [0, p, 0, 0, 0, 0]) for p in np.linspace(0, 1, 101)]
    th = alarm_thresholds(clean, [0.1])
    assert th.empirical_fa.iloc[0] <= 0.1
    assert th.n_clean_machines.iloc[0] == 101
    with pytest.raises(ValueError, match="dev"):
        alarm_thresholds([_fake_result("test", False, [0] * 6)], [0.1])


def test_detection_table_delay_and_pre_start_alarm():
    th = alarm_thresholds([_fake_result("dev", False, [0.2] * 6)] * 10, [0.1])
    # trajectory entries are for days 4..9 (T - 1); attack starts on day 6
    attack = _fake_result("dev", True, [0.0, 0.5, 0.0, 0.0, 0.9, 0.9])
    det = detection_table([attack], th, start=6)
    assert det.pre_start_alarm.iloc[0] == 1  # day 5 exceeded before the start
    assert det.detection_delay_days.iloc[0] == 2.0  # first post-start alarm on day 8


@pytest.fixture(scope="module")
def smoke_results(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("m2")
    dcfg = load_config("configs/detector_smoke.yaml")
    dcfg["output_dir"] = str(tmp / "det")
    run_detector_experiment(dcfg)
    cfg = load_config("configs/inference_smoke.yaml")
    cfg["detectors"] = {
        "lgbm_base": str(tmp / "det" / "detector_base.pkl"),
        "lgbm_validity": str(tmp / "det" / "detector_validity.pkl"),
    }
    cfg["output_dir"] = str(tmp / "inf")
    return cfg, run_inference_experiment(cfg, log=lambda *a, **k: None), tmp


def test_inference_experiment_end_to_end(smoke_results):
    cfg, res, tmp = smoke_results
    df = res["results"]
    assert (tmp / "inf" / "inference_results.csv").exists()
    n_machines = 1 + cfg["clean_reps"]
    n_combos = (len(cfg["discovery_delay"]) * 2 * len(cfg["inference_models"]) * 4
                * len(cfg["detectors"]))  # 2 statistics, 4 priors  # fmt: skip
    assert len(df) == n_machines * n_combos
    assert set(df.detector) == set(cfg["detectors"])
    assert set(df.split) == {"dev"}
    assert df.p_started.between(0, 1).all()
    assert (df[df.attack == 1].damage_source == "synthetic_random").all()
    # prior-only ignores data: identical p_started for attack and clean machines
    po = (
        df[df.model == "prior_only"]
        .groupby(["discovery_delay", "statistic", "p_attack_within_window"])
        .p_started.nunique()
    )
    assert (po == 1).all()
    assert not res["thresholds"].empty and not res["detection"].empty


def test_inference_summary_tables(smoke_results):
    _, res, _ = smoke_results
    tables = summarise(res["results"], 0.01, delay=res["headline_delay"])
    assert not tables["errors"].empty and not tables["clean"].empty


def test_run_machines_resumes_from_cache(smoke_results, tmp_path):
    from slowburn.bench.inference_experiment import make_tasks, run_machines

    cfg, _, _ = smoke_results
    tasks = make_tasks(cfg, "dev")[:2]
    first = run_machines(cfg, tasks, log=lambda *a, **k: None, cache_dir=tmp_path)
    assert len(list(tmp_path.glob("*.pkl"))) == 2
    logs = []
    again = run_machines(cfg, tasks, log=logs.append, cache_dir=tmp_path)
    assert any("resuming: 2/2" in m for m in logs)
    import pandas as pd

    def frame(res):
        return pd.DataFrame([row for r in res for row in r["rows"]])

    assert frame(again).equals(frame(first))  # NaN-aware equality
    assert all(r["peak_rss_mb"] > 0 for r in first)
