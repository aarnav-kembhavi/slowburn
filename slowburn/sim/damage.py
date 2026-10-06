"""Abstract damage model for evaluating detectors and retention policies.

No encryption is ever performed. A "damaged" byte range is overwritten with high-entropy bytes
taken from a ``DamageSource``: either a seeded RNG (synthetic) or, when available, the bytes of
a real ransomware-encrypted sample from a public dataset at the same offset (see
``slowburn.detector.datasets``). The only outputs are the modified buffer and per-chunk labels.

Two placement models (agreed with the team):

* ``whole``   - a fraction ``f`` of the file's chunks is fully overwritten; other chunks untouched.
* ``striped`` - every chunk has a fraction ``f`` of its bytes overwritten in periodic stripes of
  ``stripe_bytes`` (the pattern intermittent encryptors use). This is the headline model: at
  small ``f`` each changed chunk only carries a weak signal.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np

DAMAGE_MODELS = ("whole", "striped")


class DamageSource(Protocol):
    """Supplies replacement bytes for a damaged range."""

    name: str

    def bytes_for(self, file_key: str, offset: int, length: int) -> bytes: ...


class RandomDamageSource:
    """Seeded high-entropy bytes; statistically equivalent to os.urandom but reproducible."""

    name = "synthetic_random"

    def __init__(self, rng: np.random.Generator):
        self._rng = rng

    def bytes_for(self, file_key: str, offset: int, length: int) -> bytes:
        return self._rng.bytes(length)


@dataclass(frozen=True)
class DamageResult:
    data: bytes
    # fraction of bytes overwritten in each fixed-size chunk (0.0 = untouched)
    chunk_damage: np.ndarray
    # achieved fraction of damaged bytes over the whole file
    damaged_fraction: float
    source: str


def apply_damage(
    data: bytes,
    model: str,
    fraction: float,
    chunk_size: int,
    rng: np.random.Generator,
    source: DamageSource,
    file_key: str = "",
    stripe_bytes: int = 16,
) -> DamageResult:
    if not 0.0 < fraction <= 1.0:
        raise ValueError(f"fraction must be in (0, 1], got {fraction}")
    if model == "whole":
        return _apply_whole(data, fraction, chunk_size, rng, source, file_key)
    if model == "striped":
        return _apply_striped(data, fraction, chunk_size, rng, source, file_key, stripe_bytes)
    raise ValueError(f"unknown damage model {model!r}; known: {DAMAGE_MODELS}")


def _n_chunks(n: int, chunk_size: int) -> int:
    return max(1, -(-n // chunk_size))


def _overwrite(data: bytes, mask: np.ndarray, source, file_key, chunk_size) -> DamageResult:
    """Replace masked bytes with offset-aligned bytes from ``source``."""
    n = len(data)
    arr = np.frombuffer(data, dtype=np.uint8).copy()
    if mask.any():
        repl = np.frombuffer(source.bytes_for(file_key, 0, n), dtype=np.uint8)
        arr[mask] = repl[mask]
    n_chunks = _n_chunks(n, chunk_size)
    padded = np.zeros(n_chunks * chunk_size, dtype=bool)
    padded[:n] = mask
    lens = np.clip(n - np.arange(n_chunks) * chunk_size, 1, chunk_size)
    damage = padded.reshape(n_chunks, chunk_size).sum(axis=1) / lens
    return DamageResult(arr.tobytes(), damage, float(mask.mean()) if n else 0.0, source.name)


def _apply_whole(data, fraction, chunk_size, rng, source, file_key) -> DamageResult:
    n = len(data)
    n_chunks = _n_chunks(n, chunk_size)
    k = min(n_chunks, max(1, round(fraction * n_chunks)))
    chosen = rng.choice(n_chunks, size=k, replace=False)
    mask = np.zeros(n, dtype=bool)
    for c in chosen:
        mask[c * chunk_size : (c + 1) * chunk_size] = True
    return _overwrite(data, mask, source, file_key, chunk_size)


def _apply_striped(data, fraction, chunk_size, rng, source, file_key, stripe_bytes):
    n = len(data)
    period = max(stripe_bytes, int(round(stripe_bytes / fraction)))
    phase = int(rng.integers(0, period))  # random per file, so headers are not always hit
    mask = ((np.arange(n) - phase) % period) < stripe_bytes
    return _overwrite(data, mask, source, file_key, chunk_size)
