"""Loaders for external public datasets. Nothing is downloaded; missing data fails loudly.

The NapierOne directory layout is not yet confirmed (see OPEN_QUESTIONS.md), so file selection
is driven by glob patterns from config rather than a hardcoded structure.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterator
from pathlib import Path

from slowburn.utils.config import resolve_path


class DatasetMissingError(RuntimeError):
    pass


def napierone_root(path: str | Path) -> Path:
    root = resolve_path(path)
    if not root.is_dir() or not any(root.iterdir()):
        raise DatasetMissingError(
            f"NapierOne not found at {root}. Download it manually (registration may be required) "
            "and place it there; see data/README.md. Until then use damage_source: "
            "synthetic_random and benign_source: synthetic."
        )
    return root


def _files(root: Path, pattern: str) -> list[Path]:
    paths = sorted(p for p in root.glob(pattern) if p.is_file())
    if not paths:
        raise DatasetMissingError(f"no files match {pattern!r} under {root}; see data/README.md")
    return paths


class NapierOneDamageSource:
    """Real ransomware-encrypted bytes, spliced offset-aligned into our damage masks.

    Each logical file key is mapped deterministically to one encrypted sample; bytes are read at
    the requested offset, wrapping around if the sample is shorter than the target file.
    """

    name = "napierone"

    def __init__(self, root: str | Path, encrypted_glob: str = "encrypted/**/*",
                 samples: list[Path] | None = None):  # fmt: skip
        self.root = napierone_root(root)
        # numbered samples only: each family folder also holds a descriptor PDF (D67)
        self.samples = (
            samples
            if samples is not None
            else [p for p in _files(self.root, encrypted_glob) if re.match(r"\d{4}-", p.name)]
        )
        if not self.samples:
            raise DatasetMissingError(f"no encrypted samples under {self.root}")
        self._cache: dict[Path, bytes] = {}

    def _sample(self, file_key: str) -> bytes:
        h = int.from_bytes(hashlib.blake2b(file_key.encode(), digest_size=8).digest(), "little")
        path = self.samples[h % len(self.samples)]
        if path not in self._cache:
            data = path.read_bytes()
            if not data:
                raise DatasetMissingError(f"empty encrypted sample {path}")
            self._cache[path] = data
        return self._cache[path]

    def bytes_for(self, file_key: str, offset: int, length: int) -> bytes:
        data = self._sample(file_key)
        start = offset % len(data)
        reps = (start + length) // len(data) + 1
        return (data * reps)[start : start + length]


def iter_napierone_benign(
    root: str | Path, benign_glob: str = "benign/**/*"
) -> Iterator[tuple[str, bytes]]:
    """Yield (file_type, bytes) for benign originals; type is the lower-case extension."""
    base = napierone_root(root)
    for p in _files(base, benign_glob):
        yield p.suffix.lower().lstrip(".") or "unknown", p.read_bytes()
