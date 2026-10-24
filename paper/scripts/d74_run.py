"""D74: run the adaptive-attacker evaluation for one config (single-machine defences). DEV only.

uv run python paper/scripts/d74_run.py configs/dev_d74_attack_synthetic.yaml
"""

import sys

from slowburn.bench.attacker_experiment import run_attacker_experiment
from slowburn.utils.config import load_config

if __name__ == "__main__":
    run_attacker_experiment(load_config(sys.argv[1]), log=lambda *a: print(*a, flush=True))
