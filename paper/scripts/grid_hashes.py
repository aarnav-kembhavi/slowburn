"""scenario_grids for configs/frozen_v2.yaml (OPEN_QUESTIONS 2026-10-27, grid-hash gate): for each
DEV config listed there whose run has a scenario grid, the canonical grid (registry.canonical_grid)
and its SHA-256, keyed by the test experiment name. Reads configs only. Run from the repo root:

    uv run python paper/scripts/grid_hashes.py           # print the YAML block
    uv run python paper/scripts/grid_hashes.py --write   # replace the block in frozen_v2.yaml
"""

import json
import re
import sys

import yaml
from test_configs import FROZEN_V2, dev_configs, test_path

from slowburn.bench.registry import canonical_grid, grid_sha256
from slowburn.bench.retention_experiment import scenario_grid_of

BEGIN = "# --- scenario_grids (paper/scripts/grid_hashes.py) ---"
END = "# --- end scenario_grids ---"


def block() -> str:
    lines = [BEGIN, "scenario_grids:   # SHA-256 of the canonical grid of the DEV config"]
    for dev in dev_configs():
        cfg = yaml.safe_load(dev.read_text(encoding="utf-8"))
        if "budgets" not in cfg:
            continue  # D74 / D73: no scenario grid in the gate (their grids are checked by diff)
        grid = scenario_grid_of(cfg)
        name = yaml.safe_load(test_path(dev).read_text(encoding="utf-8"))["experiment"]
        lines += [f"  {name}:", f"    dev_config: {dev.as_posix()}",
                  f"    sha256: {grid_sha256(grid)}",
                  f"    canonical: {json.dumps(canonical_grid(grid))}"]  # fmt: skip
    return "\n".join(lines + [END]) + "\n"


def main(argv):
    b = block()
    if "--write" in argv:
        s = FROZEN_V2.read_text(encoding="utf-8")
        if BEGIN in s:
            s = re.sub(re.escape(BEGIN) + ".*?" + re.escape(END) + "\n", lambda _: b, s, flags=re.S)
        else:
            s = s.replace("\nitems:\n", "\n" + b + "\nitems:\n", 1)
        FROZEN_V2.write_text(s, encoding="utf-8")
    print(b)


if __name__ == "__main__":
    main(sys.argv[1:])
