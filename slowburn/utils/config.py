"""YAML config loading. Paths in configs are resolved relative to the repository root."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]


def load_config(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    if not path.is_absolute() and not path.exists():
        path = REPO_ROOT / path
    with path.open("r", encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh) or {}
    if "seed" not in cfg:
        raise ValueError(f"{path}: every experiment config must define a top-level 'seed'")
    cfg["_config_path"] = str(path)
    return cfg


def resolve_path(p: str | Path) -> Path:
    """Resolve a config path relative to the repository root (never the CWD)."""
    p = Path(p)
    return p if p.is_absolute() else REPO_ROOT / p
