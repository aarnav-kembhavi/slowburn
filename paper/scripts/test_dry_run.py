"""TEST path dry run (OPEN_QUESTIONS "TEST content path"; frozen_v2.yaml prerequisite). Only after
approval and after the inventory is committed. For each configs/test_*.yaml: one test-keyed
machine (family "dry_run", never used by any experiment), one simulated day, into a scratch dir
that no analysis script reads. Checked: the exit code, that the content pool and damage samples
load from TEST paths only, the config diff script (paper/scripts/test_configs.py --check), and
the gate check of each config's experiment entrypoint (the same function the runner calls).
Nothing simulated is read: the scratch dir is deleted unread and the deletion logged to
results/test_dry_run.log. Run from the repo root:

    uv run python paper/scripts/test_dry_run.py
"""

import datetime as dt
import pickle
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from d74_alarm_holdout import alarm_gate

from slowburn.bench.attacker_experiment import attack_gate
from slowburn.bench.registry import machine_key
from slowburn.bench.retention_experiment import sweep_gate
from slowburn.detector.napierone import PoolFile, benign_splits, family_splits
from slowburn.fleet.experiment import fleet_gate
from slowburn.fleet.machine import MachineSim
from slowburn.utils.config import load_config

LOG = Path("results/test_dry_run.log")


def test_paths_only(sim) -> str:
    """'' if every content file and damage sample is a TEST one, else the first offender."""
    pool = getattr(sim.scen, "content_pool", None)
    if pool is None:
        return ""  # synthetic arm: no NapierOne files
    sp = benign_splits(pool.root)
    for t, files in pool.files.items():
        test_keys = {f.key for f in sp[t]["sim_test"]}
        for f in files:
            v2 = isinstance(f, PoolFile)
            ok = Path(f.path).parent.name == "test" if v2 else f.key in test_keys
            if not ok:
                return f"{t}: {f.key}"
    fams = set(family_splits(pool.root)["sim_test"])
    bad = [p for p in sim.damage_source.samples if p.parent.name not in fams]
    return f"damage sample {bad[0]}" if bad else ""


def entrypoint_gates(cfg) -> str:
    """Run the gate(s) of the entrypoint(s) that will run this config; returns their names."""
    name = cfg["experiment"]
    if name.startswith(("test_d72", "test_d79", "test_d71")):
        sweep_gate(cfg)
        return "sweep"
    if name.startswith("test_d74"):
        attack_gate(cfg)
        alarm_gate()
        return "attack+alarm"
    if name.startswith("test_d73"):
        fleet_gate(cfg)
        return "fleet"
    raise ValueError(f"no entrypoint for {name}")


def main():
    diff = subprocess.run([sys.executable, "paper/scripts/test_configs.py", "--check"],
                          capture_output=True, text=True)  # fmt: skip
    lines = [f"{dt.datetime.now().isoformat(timespec='seconds')} config check exit "
             f"{diff.returncode}"]  # fmt: skip
    failed = diff.returncode != 0
    for path in sorted(Path("configs").glob("test_*.yaml")):
        cfg = load_config(path)
        scratch = Path(tempfile.mkdtemp(prefix="slowburn_dry_"))
        gates = "?"
        try:
            gates = entrypoint_gates(cfg)
            p = {**cfg["scenario"], "attack_start": None}
            key = machine_key(int(cfg["seed"]), "test", "dry_run", {}, 0)
            sim = MachineSim(cfg, p, key, 1).run_to(1)
            with (scratch / "machine.pkl").open("wb") as fh:
                pickle.dump(sim.obs, fh)
            bad = test_paths_only(sim)
            status = "OK" if not bad else f"FAIL non-TEST file {bad}"
        except Exception as e:  # noqa: BLE001 - the dry run reports every failure
            status = f"FAIL {type(e).__name__}: {e}"
        shutil.rmtree(scratch)
        failed |= status != "OK"
        lines.append(f"{path}: {status}; gates {gates}; scratch {scratch} deleted unread")
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    print("\n".join(lines))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
