"""The file access audit of paper/scripts/test_analysis.py (OPEN_QUESTIONS 2026-10-29)."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

AUDIT = Path(__file__).resolve().parents[1] / "paper" / "scripts" / "audit"
sys.path.insert(0, str(AUDIT))
import analysis_audit as audit  # noqa: E402


def test_verdict_rules():
    test = {"mode": "test", "runs": []}
    dev = {"mode": "dev", "runs": ["results/dev_d71_oracle_gap"]}
    assert audit.verdict("results/dev_d71_oracle_gap/tuning_sweep.csv", "read", test)
    assert audit.verdict("results/dev_d74_alarm_calib/threshold.json", "read", test) is None
    assert audit.verdict("results/dev_d74_alarm_calib/machines_x/0.json", "read", test)
    assert audit.verdict("results/test_d71_oracle_gap/tuning_sweep.csv", "read", test) is None
    assert audit.verdict("results/test_d71_oracle_gap/x.csv", "write", test)
    assert audit.verdict("results/analysis_test/d71_report/x.csv", "write", test) is None
    assert audit.verdict("results/analysis_dev/d71_report/x.csv", "write", test)
    assert audit.verdict("results/dev_d71_oracle_gap/tuning_sweep.csv", "read", dev) is None
    assert audit.verdict("results/dev_d72_full/tuning_sweep.csv", "read", dev)
    assert audit.verdict("results/test_d71_oracle_gap/tuning_sweep.csv", "read", dev)
    assert audit.verdict("data/napierone/x.txt", "read", test) is None


def test_denied_read_raises_in_process_and_in_a_worker(tmp_path):
    log = tmp_path / "audit.log"
    rules = {"mode": "test", "runs": [], "log": str(log)}
    target = Path(audit.ROOT) / "results" / "dev_d71_oracle_gap" / "tuning_sweep.csv"
    audit.start(rules)
    try:
        with pytest.raises(PermissionError):
            open(target)  # noqa: SIM115
    finally:
        audit.stop()
    env = {**os.environ, audit.ENV: json.dumps(rules), "PYTHONPATH": str(AUDIT)}
    code = f"open({str(target)!r})"
    r = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True)
    assert r.returncode != 0 and "PermissionError" in r.stderr
    lines = [x for p in tmp_path.glob("audit.log.*") for x in p.read_text().splitlines()]
    deny = [x for x in lines if "\tDENY: results/dev_* read in mode test" in x]
    assert len({x.split("\t")[0] for x in deny}) == 2  # this process and the worker
