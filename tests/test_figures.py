"""H: figure/table generation and the paired-test table (SlowBurn vs baselines)."""

import numpy as np
import pandas as pd
import pytest

from slowburn.bench.figures import BASELINES, REGISTRY, generate, paired_tests


def _fake(n=30):
    rng = np.random.default_rng(0)
    rows = []
    for rep in range(n):
        for pol, p_rec in [("slowburn", 0.9)] + [(b, 0.4) for b in BASELINES]:
            rec = int(rng.random() < p_rec)
            rows.append(
                {
                    "policy": pol,
                    "rep": rep,
                    "detect_prob": 0.5,
                    "benign_invalid_rate": 0.0,
                    "discovery_delay": 14,
                    "clean_recovery": rec,
                    "work_lost_whole_system_hours": float(rng.uniform(10, 50) if rec else 999),
                    "work_lost_selective_file_hours": float(rng.uniform(0, 20)),
                }
            )
    return pd.DataFrame(rows)


def test_paired_tests_columns_and_holm():
    t = paired_tests(_fake())
    assert set(t.baseline) == set(BASELINES)
    assert (t.n == 30).all()
    assert (t.recovery_diff > 0).all()  # SlowBurn recovers more often in the fake data
    assert (t.mcnemar_p_holm >= t.mcnemar_p).all()
    assert (t.rd_ci_low <= t.recovery_diff).all() and (t.recovery_diff <= t.rd_ci_high).all()


def test_registry_and_unknown_name():
    assert {
        "headline-recovery",
        "headline-worklost",
        "table-headline",
        "table-stats",
        "table-theory",
        "table-grid",
        "grid-heatmap",
        "auroc",
    } <= set(REGISTRY)
    with pytest.raises(ValueError, match="unknown figure"):
        generate("nope")
