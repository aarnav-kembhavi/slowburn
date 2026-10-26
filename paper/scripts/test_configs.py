"""Generate configs/test_*.yaml from the DEV configs listed in configs/frozen_v2.yaml, and check
them (OPEN_QUESTIONS "TEST content path"). Reads configs only; opens no data and runs nothing.

Generation is textual (comments kept): ``split: dev`` -> ``split: test``, ``napierone_pool: v2``
-> ``v2test``, and ``dev_`` -> ``test_`` in ``experiment`` and ``output_dir``. The check parses
both files and fails if any other key differs, then reruns the registry gate
(check_split_allowed) on each test config's hyperparameters. Run from the repo root:

    uv run python paper/scripts/test_configs.py            # write, then check
    uv run python paper/scripts/test_configs.py --check    # check only
"""

import difflib
import re
import sys
from pathlib import Path

import yaml

from slowburn.bench.registry import FrozenGateError, check_split_allowed
from slowburn.bench.retention_experiment import scenario_grid_of

FROZEN_V2 = Path("configs/frozen_v2.yaml")
ALLOWED = {("split",): ("dev", "test"), ("scenario", "napierone_pool"): ("v2", "v2test")}
RENAMED = (("experiment",), ("output_dir",))


def dev_configs() -> list[Path]:
    items = yaml.safe_load(FROZEN_V2.read_text(encoding="utf-8"))["items"]
    out = []
    for it in items:
        cfgs = it.get("dev_config")
        for c in [cfgs] if isinstance(cfgs, str) else cfgs or []:
            if c.startswith("configs/") and Path(c) not in out:
                out.append(Path(c))
    return out


def test_path(dev: Path) -> Path:
    return dev.with_name("test_" + dev.name.removeprefix("dev_"))


def convert(text: str) -> str:
    text = re.sub(r"(?m)^split: dev\b", "split: test", text)
    text = re.sub(r"(?m)^(\s+napierone_pool: )v2\b.*$",
                  r"\1v2test         # TEST: v1 sim_test + benign_v2/<type>/test", text)
    text = re.sub(r"(?m)^((?:experiment|output_dir): (?:results/)?)dev_", r"\1test_", text)
    return text


def flatten(d, prefix=()):
    if isinstance(d, dict):
        out = {}
        for k, v in d.items():
            out.update(flatten(v, (*prefix, k)))
        return out
    return {prefix: d}


def check(dev: Path, test: Path) -> list[str]:
    a = flatten(yaml.safe_load(dev.read_text(encoding="utf-8")))
    b = flatten(yaml.safe_load(test.read_text(encoding="utf-8")))
    errors = []
    for key in sorted(set(a) | set(b), key=str):
        if a.get(key) == b.get(key):
            continue
        if key in ALLOWED and (a.get(key), b.get(key)) == ALLOWED[key]:
            continue
        if key in RENAMED and b.get(key) == str(a.get(key)).replace("dev_", "test_", 1):
            continue
        errors.append(f"{'.'.join(map(str, key))}: {a.get(key)!r} -> {b.get(key)!r}")
    if b.get(("split",)) != "test":
        errors.append("split is not test")
    try:  # the registry gate on the run's hyperparameters (configs only)
        cfg = yaml.safe_load(test.read_text(encoding="utf-8"))
        params = dict(cfg.get("hp", {}))
        if "budgets" in cfg:  # as run_retention_experiment does
            params["scenario_grid"] = scenario_grid_of(cfg)
        check_split_allowed("test", params)
    except FrozenGateError as e:
        errors.append(f"registry gate: {e}")
    return errors


def main(argv):
    write = "--check" not in argv
    failed = False
    for dev in dev_configs():
        test = test_path(dev)
        if write:
            test.write_text(convert(dev.read_text(encoding="utf-8")), encoding="utf-8")
        diff = difflib.unified_diff(dev.read_text(encoding="utf-8").splitlines(),
                                    test.read_text(encoding="utf-8").splitlines(),
                                    str(dev), str(test), n=0, lineterm="")  # fmt: skip
        print("\n".join(line for line in diff if not line.startswith("@@")))
        errors = check(dev, test)
        print(f"CHECK {test}: " + ("OK" if not errors else "FAIL " + "; ".join(errors)) + "\n")
        failed |= bool(errors)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main(sys.argv[1:])
