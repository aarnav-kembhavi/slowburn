import numpy as np
import pytest

from slowburn.detector.features import MAGIC
from slowburn.sim.content import GENERATORS, HIGH_ENTROPY_TYPES, chunk_bytes, generate_file
from slowburn.sim.damage import RandomDamageSource, apply_damage


def _entropy(b: bytes) -> float:
    c = np.bincount(np.frombuffer(b, np.uint8), minlength=256) / len(b)
    c = c[c > 0]
    return float(-(c * np.log2(c)).sum())


@pytest.mark.parametrize("ftype", sorted(GENERATORS))
def test_generators_deterministic_and_sized(ftype):
    a = generate_file(ftype, np.random.default_rng(1), 16 * 1024)
    b = generate_file(ftype, np.random.default_rng(1), 16 * 1024)
    assert a == b
    assert 4 * 1024 <= len(a) <= 64 * 1024


@pytest.mark.parametrize("ftype", sorted(MAGIC))
def test_generated_files_carry_real_magic(ftype):
    data = generate_file(ftype, np.random.default_rng(2), 16 * 1024)
    assert any(data.startswith(m) for m in MAGIC[ftype])


def test_hard_negatives_are_high_entropy():
    rng = np.random.default_rng(0)
    for ftype in HIGH_ENTROPY_TYPES - {"docx"}:
        assert _entropy(generate_file(ftype, rng, 32 * 1024)) > 7.0, ftype
    assert _entropy(generate_file("txt", rng, 32 * 1024)) < 5.5


def test_unknown_type_rejected():
    with pytest.raises(ValueError):
        generate_file("exe", np.random.default_rng(0), 1024)


def test_chunk_bytes_roundtrip():
    data = bytes(range(256)) * 50
    chunks = chunk_bytes(data, 4096)
    assert b"".join(chunks) == data
    assert all(len(c) == 4096 for c in chunks[:-1])


def _damage(model, frac, data, seed=0, **kw):
    rng = np.random.default_rng(seed)
    return apply_damage(data, model, frac, 4096, rng, RandomDamageSource(rng), **kw)


def test_whole_chunk_damage_fraction_and_labels():
    data = b"a" * (4096 * 20)
    res = _damage("whole", 0.25, data)
    assert len(res.data) == len(data)
    assert set(np.unique(res.chunk_damage)) <= {0.0, 1.0}
    assert res.chunk_damage.sum() == 5
    assert res.damaged_fraction == pytest.approx(0.25)
    for i, c in enumerate(chunk_bytes(res.data, 4096)):
        assert (c == b"a" * 4096) == (res.chunk_damage[i] == 0)


@pytest.mark.parametrize("frac", [0.05, 0.1, 0.25, 0.5, 1.0])
def test_striped_damage_hits_every_chunk_at_requested_rate(frac):
    data = b"a" * (4096 * 16)
    res = _damage("striped", frac, data, stripe_bytes=16)
    assert len(res.data) == len(data)
    assert np.all(res.chunk_damage > 0)
    assert res.damaged_fraction == pytest.approx(frac, abs=0.01)
    # untouched bytes keep their value: the damaged share matches the mask
    changed = np.mean(np.frombuffer(res.data, np.uint8) != ord("a"))
    assert changed <= res.damaged_fraction + 1e-9


def test_damage_rejects_bad_fraction():
    with pytest.raises(ValueError):
        _damage("striped", 0.0, b"a" * 4096)
    with pytest.raises(ValueError):
        _damage("bogus", 0.5, b"a" * 4096)
