"""D73: run the fleet experiment for one config (stages: calib, machines, fleets). DEV only.

uv run python paper/scripts/d73_run.py configs/dev_d73_fleet_synthetic.yaml [stage ...]
"""

import sys

from slowburn.fleet.experiment import run_fleet_experiment
from slowburn.utils.config import load_config

if __name__ == "__main__":
    cfg = load_config(sys.argv[1])
    stages = tuple(sys.argv[2:]) or ("calib", "machines", "fleets")
    run_fleet_experiment(cfg, log=lambda *a: print(*a, flush=True), stages=stages)
