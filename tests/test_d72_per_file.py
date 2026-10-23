"""D72 per-file restore methods (B walk-back, C monotone changepoint) and their accounting."""

import numpy as np
import pytest

from slowburn.store.restore import (
    FileHistory,
    changepoint_clean_probs,
    changepoint_file_choice,
    oracle_file_choice,
    oracle_file_restore,
    per_file_outcome,
    snapshot_choice,
    verified_restore,
    walkback_file_choice,
)


def _step_cdf(s):
    return lambda d: 1.0 if d >= s else 0.0


def test_versions_before_the_start_are_clean():
    pc = changepoint_clean_probs([1, 0, 1, 1], [0, 3, 6, 8], _step_cdf(5), 0.5, 100.0)
    assert pc[0] == pytest.approx(1.0) and pc[1] == pytest.approx(1.0)
    assert pc[2] < 0.05 and pc[3] < 0.05


def test_onset_prior_is_uniform_over_admissible_outcomes():
    # start known at 5; versions 6 and 8 admissible: tau in {v6, v8, none}, mass 1/3 each.
    # Unflagged everywhere, benign rate ~0: likelihoods 1/3 (tau=v6), 1/2 (tau=v8), 1 (none)
    pc = changepoint_clean_probs([0, 0, 0, 0], [0, 3, 6, 8], _step_cdf(5), 1e-9, 1.0)
    tot = 1 / 3 + 1 / 2 + 1
    assert pc[2] == pytest.approx((1 / 2 + 1) / tot, rel=1e-6)
    assert pc[3] == pytest.approx(1 / tot, rel=1e-6)


def test_not_started_mass_means_no_damage():
    pc = changepoint_clean_probs([0, 1], [0, 4], lambda d: 0.0, 0.5, 10.0)
    assert np.allclose(pc, 1.0)


H = {
    "f0": FileHistory((0, 3, 9), None, frozenset({9})),  # benign, live version falsely flagged
    "f1": FileHistory((0, 5, 11), 11, frozenset({11})),  # damaged day 11, detected
    "f2": FileHistory((0, 7, 12), 12, frozenset()),  # damaged day 12, missed
    "f3": FileHistory((0, 2), None, frozenset()),
}
FT = {"f0": "zip", "f1": "txt", "f2": "txt", "f3": "zip"}
KEPT, TD = [4, 8, 10], 13


def test_walkback_restores_from_newest_unflagged_held_version():
    c = walkback_file_choice(KEPT, TD, H)
    assert c == {"f0": 3, "f1": 5}  # f2's live version is unflagged: left damaged
    m = per_file_outcome(c, H, TD, FT)
    assert m["residual_damaged_files"] == 1 and m["residual_nonzip"] == 1
    assert m["work_lost_file_hours"] == 24  # f0 loses its day-9 version
    assert m["work_lost_file_hours_zip"] == 24
    assert m["work_lost_whole_hours"] == (TD - 3) * 24


def test_oracle_choice_matches_d71_oracle():
    c = oracle_file_choice(KEPT, TD, H)
    a, b = per_file_outcome(c, H, TD, FT), oracle_file_restore(KEPT, TD, H)
    assert a["residual_damaged_files"] == b["residual_damaged_files"]
    assert a["work_lost_file_hours"] == b["work_lost_selective_file_hours"]


def test_snapshot_choice_reproduces_verify_snap_accounting():
    post = np.zeros(TD + 2)
    post[9] = 1.0
    r = verified_restore(KEPT, post, TD, H, 11, 0.8, old_flags="verify_snap")
    c = snapshot_choice(H, r["restore_point"], max(r["restore_point"] + 1, r["estimated_start"]),
                        TD, select=True)  # fmt: skip
    m = per_file_outcome(c, H, TD, FT)
    assert m["residual_damaged_files"] == r["residual_damaged_files"]
    assert m["work_lost_file_hours"] == r["work_lost_selective_file_hours"]


def test_changepoint_choice_restores_detected_damage_and_keeps_benign():
    post = np.zeros(TD + 2)
    post[11] = 1.0
    pri = {"zip": (0.5, 50.0), "txt": (0.5, 50.0)}
    c = changepoint_file_choice(KEPT, post, TD, H, FT, pri)
    assert c["f1"] == 5  # flagged version after the start: restored
    assert "f3" not in c  # no version after the start: untouched
    assert "f0" not in c  # live version day 9 precedes the start: clean by the prior
