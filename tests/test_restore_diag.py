"""D71: per-file oracle ceiling and the verify_snap restore diagnosis."""

import numpy as np

from slowburn.store.restore import (
    FileHistory,
    oracle_file_restore,
    restore_diagnosis,
    verified_restore,
)

# attack starts day 10: f1 damaged day 10, f2 damaged day 12; f3 never damaged
H = {
    "f1": FileHistory((0, 5, 10), 10, frozenset({10})),
    "f2": FileHistory((0, 8, 12), 12),  # damage missed by the detector
    "f3": FileHistory((0, 3, 9, 14), None),
}


def flat_post(n):
    """Start posterior uniform over days 0..n-1, nothing on 'not started'."""
    return np.r_[np.full(n, 1.0 / n), 0.0]


def test_per_file_oracle_uses_newest_clean_held_version():
    r = oracle_file_restore([4, 9, 15], 15, H)
    # f1 -> version 5 (held at day 9), f2 -> version 8; f3 untouched
    assert r["clean_recovery"] == 1 and r["files_restored"] == 2
    assert r["work_lost_selective_file_hours"] == 0  # no benign change after 5 / 8 is discarded
    r = oracle_file_restore([12, 15], 15, H)  # only dirty versions of f1 and f2 are held
    assert r["clean_recovery"] == 0 and r["residual_damaged_files"] == 2


def test_diagnosis_labels():
    post = np.r_[np.zeros(9), 1.0, np.zeros(6), 0.0]  # all mass on start day 9: gate admits j < 9
    d = restore_diagnosis([4, 9, 15], post, H, 10, 0.8, 4, 1)
    assert d["diag_clean_held"] == 1 and d["diag_cause"] == "gated_out"  # j* = 9 fails the gate
    d = restore_diagnosis([4, 9, 15], flat_post(16), H, 10, 0.0, 15, 0)
    assert d["diag_cause"] == "missed_damage"
    d = restore_diagnosis([4, 9, 15], flat_post(16), H, 10, 0.0, 9, 1)
    assert d["diag_cause"] == "picked_clean_point"
    assert restore_diagnosis([12, 15], flat_post(16), H, 10, 0.0, 12, 0)["diag_clean_held"] == 0


def test_diagnosis_false_flag_on_day0_version():
    h = {**H, "f4": FileHistory((0,), None, frozenset({0}))}  # creation version falsely flagged
    r = verified_restore([4, 9, 15], flat_post(16), 15, h, 10, 0.0, old_flags="verify_snap")
    assert r["restore_point"] == 4 or r["verified"] == 0  # every snapshot holds the flagged f4
    d = restore_diagnosis([4, 9, 15], flat_post(16), h, 10, 0.0, r["restore_point"],
                          r["clean_recovery"])  # fmt: skip
    assert d["diag_cause"] == "false_flag" and d["diag_false_flag_day0"] == 1
