import numpy as np
import pytest

from slowburn.bench.metrics import recovery_metrics
from slowburn.bench.runner import expand_sweep, run_benchmark
from slowburn.inference.aggregate import make_aggregator
from slowburn.inference.placeholder import naive_start_posterior
from slowburn.retention.base import KeepLastN, RetentionContext
from slowburn.sim.damage import RandomDamageSource
from slowburn.sim.scenario import Scenario, ScenarioConfig
from slowburn.store.snapshot import SnapshotStore


def test_store_dedup_and_refcount():
    st = SnapshotStore()
    a = st.add(0, {"f": [b"x" * 10, b"y" * 10]})
    b = st.add(1, {"f": [b"x" * 10, b"z" * 10]})
    assert st.unique_chunks == 3 and st.unique_bytes == 30
    st.delete(a.id)
    assert st.unique_chunks == 2  # "x" still referenced by b
    assert st.file_bytes(b.id, "f") == b"x" * 10 + b"z" * 10
    st.retain_only(set())
    assert st.unique_chunks == 0 and st.ids() == []


def _run(cfg, seed=0):
    rng = np.random.default_rng(seed)
    scen = Scenario(cfg)
    return scen, list(scen.run(rng, RandomDamageSource(np.random.default_rng(seed + 1))))


def test_clean_scenario_has_no_damage():
    _, days = _run(ScenarioConfig(n_files=6, file_kib=(8, 12), days=10, attack_start=None))
    assert all(c.label == 0 for d in days for c in d.changed)
    assert len(days[0].changed) > 0  # first backup: everything is new


def test_attack_labels_start_on_attack_day():
    cfg = ScenarioConfig(
        n_files=8,
        file_kib=(8, 12),
        days=15,
        attack_start=10,
        attack_files_per_day=1.0,
        damage_fraction=0.5,
    )
    scen, days = _run(cfg)
    for d in days:
        n_bad = sum(c.label for c in d.changed)
        if d.day < 10:
            assert n_bad == 0
    assert sum(c.label for c in days[10].changed) > 0
    assert min(scen.damaged_on.values()) == 10


def test_scenario_is_reproducible():
    cfg = ScenarioConfig(n_files=5, file_kib=(8, 12), days=8, attack_start=4)
    _, d1 = _run(cfg, seed=3)
    _, d2 = _run(cfg, seed=3)
    assert [len(d.changed) for d in d1] == [len(d.changed) for d in d2]
    assert d1[-1].files == d2[-1].files


def test_aggregators():
    s = np.array([0.0, 0.1, 0.2, 0.9, 1.0])
    assert make_aggregator("mean")(s) == pytest.approx(0.44)
    assert make_aggregator("frac_above", reference=0.5)(s) == pytest.approx(0.4)
    assert make_aggregator("trimmed_mean", proportion=0.2)(s) == pytest.approx(0.4)
    assert make_aggregator("mean")(np.array([])) == 0.0
    with pytest.raises(ValueError):
        make_aggregator("nope")


def test_naive_posterior_is_distribution_and_finds_shift():
    x = np.r_[np.zeros(20), np.full(10, 5.0)] + np.random.default_rng(0).normal(0, 0.1, 30)
    p = naive_start_posterior(x)
    assert p.shape == (31,) and p.sum() == pytest.approx(1.0)
    assert abs(int(np.argmax(p)) - 20) <= 1


def test_keep_last_n():
    ctx = RetentionContext(
        day=9,
        snapshot_days={i: i for i in range(10)},
        budget=3,
        daily_stat=np.zeros(10),
        start_posterior=np.ones(11) / 11,
    )
    assert KeepLastN().decide(ctx) == {7, 8, 9}


def test_recovery_metrics():
    m = recovery_metrics([3, 8, 12], true_start=10, discovery_day=15)
    assert m["clean_recovery"] == 1 and m["newest_clean_day"] == 8
    assert m["start_gap_days"] == 1
    assert m["data_lost_hours_whole_system"] == 7 * 24
    assert recovery_metrics([10, 12], 10, 15)["clean_recovery"] == 0


def test_expand_sweep():
    g = expand_sweep({"a": 1}, {"b": [1, 2], "c": [3, 4]})
    assert len(g) == 4 and all(r["a"] == 1 for r in g)


def test_benchmark_end_to_end(tmp_path):
    cfg = {
        "seed": 1,
        "output_dir": str(tmp_path),
        "budget": 3,
        "policies": ["keep_last_n"],
        "aggregator": {"name": "mean"},
        "scenario": {
            "n_files": 4,
            "file_kib": [8, 8],
            "attack_start": 6,
            "file_types": ["txt", "png"],
        },
        "sweep": {"damage_fraction": [0.5], "discovery_delay": [1, 5]},
    }
    df = run_benchmark(cfg)
    assert (tmp_path / "results.csv").exists()
    assert len(df) == 2
    assert {"benign_source", "damage_source", "clean_recovery"} <= set(df.columns)
    # budget 3 survives a 1-day delay but not a 5-day delay
    assert df.set_index("discovery_delay")["clean_recovery"].to_dict() == {1: 1, 5: 0}
