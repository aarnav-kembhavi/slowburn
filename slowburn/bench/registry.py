"""Seed / split registry and the frozen-hyperparameter gate.

Seed namespaces (every random stream is ``child_rng(base_seed, *key)``):

    ("file", <file id>)                                  detector training / calib / test files
    ("split", ...), ("bootstrap", ...)                   detector experiment internals
    ("machine", <split>, <family>, <setting>, <rep>)     simulated machines (inference, retention)

Detector files and machines live in disjoint namespaces, so no machine reuses a file the
detector was trained or calibrated on. ``dev`` and ``test`` machines differ in the split
element of the key, so they never share randomness.

The gate: any run on the ``test`` split requires ``configs/frozen.yaml`` with ``frozen: true``,
and the run's config may not override a frozen hyperparameter. Hyperparameters are chosen on
``dev`` only.
"""

from __future__ import annotations

import datetime as dt
import subprocess
from pathlib import Path
from typing import Any

import yaml

from slowburn.utils.config import REPO_ROOT, resolve_path

SPLITS = ("dev", "test")
FROZEN_PATH = "configs/frozen.yaml"


class FrozenGateError(RuntimeError):
    pass


def machine_key(base_seed: int, split: str, family: str, setting: dict, rep: int) -> tuple:
    if split not in SPLITS:
        raise ValueError(f"split must be one of {SPLITS}")
    return (int(base_seed), "machine", split, family, int(rep),
            *(f"{k}={setting[k]!r}" for k in sorted(setting)))  # fmt: skip


def load_frozen(path: str | Path = FROZEN_PATH) -> dict[str, Any]:
    p = resolve_path(path)
    if not p.exists():
        return {"frozen": False, "params": {}}
    with p.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {"frozen": False, "params": {}}


def check_split_allowed(split: str, run_params: dict[str, Any],
                        path: str | Path = FROZEN_PATH) -> dict[str, Any]:  # fmt: skip
    """Raise unless this run may use ``split``. Returns the frozen parameters (possibly empty).

    ``run_params`` are the hyperparameters the run would use; on ``test`` every key present in
    the frozen file must match exactly.
    """
    if split not in SPLITS:
        raise ValueError(f"split must be one of {SPLITS}")
    frozen = load_frozen(path)
    params = frozen.get("params", {}) or {}
    if split == "dev":
        return params
    if not frozen.get("frozen", False):
        raise FrozenGateError(
            f"test split refused: {path} is not frozen. Choose hyperparameters on dev, then freeze."
        )
    mismatched = {k: (run_params[k], v) for k, v in params.items()
                  if k in run_params and run_params[k] != v}  # fmt: skip
    if mismatched:
        raise FrozenGateError(f"test run overrides frozen hyperparameters: {mismatched}")
    return params


def _git_commit() -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=REPO_ROOT,
                             capture_output=True, text=True, check=True)  # fmt: skip
        return out.stdout.strip()
    except Exception:
        return "unknown"


def update_frozen(updates: dict[str, Any], note: str, freeze: bool = False,
                  path: str | Path = FROZEN_PATH) -> dict[str, Any]:  # fmt: skip
    """Record hyperparameters chosen on dev (with provenance). Refuses to edit a frozen file."""
    current = load_frozen(path)
    if current.get("frozen", False):
        raise FrozenGateError(f"{path} is frozen; unfreezing must be a deliberate manual edit")
    params = dict(current.get("params", {}) or {})
    params.update(updates)
    history = list(current.get("history", []) or [])
    history.append({"date": dt.date.today().isoformat(), "commit": _git_commit(),
                    "set": sorted(updates), "note": note})  # fmt: skip
    doc = {"frozen": bool(freeze), "params": params, "history": history}
    with resolve_path(path).open("w", encoding="utf-8", newline="\n") as fh:
        fh.write("# Hyperparameters chosen on DEV machines only. Written by "
                 "slowburn.bench.registry.update_frozen;\n# do not hand-edit values. "
                 "Test-split runs require frozen: true.\n")  # fmt: skip
        yaml.safe_dump(doc, fh, sort_keys=False)
    return doc
