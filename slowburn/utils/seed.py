"""Single source of randomness.

Every stochastic component receives an explicit ``np.random.Generator`` derived from the one
global seed in the experiment config. Nothing in the package touches ``np.random``'s global
state or ``os.urandom`` (which cannot be seeded and would break reproducibility).
"""

from __future__ import annotations

import hashlib
import random

import numpy as np


def make_rng(seed: int) -> np.random.Generator:
    """Root generator for an experiment."""
    return np.random.default_rng(seed)


def child_rng(seed: int, *keys: int | str) -> np.random.Generator:
    """Independent, reproducible stream for a named sub-component.

    ``child_rng(seed, "sim", 3)`` always yields the same stream for the same seed, regardless of
    how many other streams were drawn before, so adding a component never shifts the others.
    """
    words = [seed] + [_key_to_int(k) for k in keys]
    return np.random.default_rng(np.random.SeedSequence(words))


def seed_everything(seed: int) -> None:
    """Seed stdlib ``random`` too, for third-party code that relies on it."""
    random.seed(seed)


def _key_to_int(key: int | str) -> int:
    if isinstance(key, int):
        return key
    # stable across runs (unlike hash(), which is salted per process)
    return int.from_bytes(hashlib.blake2b(key.encode("utf-8"), digest_size=8).digest(), "little")
