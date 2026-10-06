import numpy as np
import pytest

from slowburn.detector.features import (
    FEATURE_NAMES,
    N_FEATURES,
    features,
    features_batch,
    magic_flag,
)

ENT, CHI, PRN, MAG = 256, 257, 258, 259


def test_shape_and_names():
    assert features(b"abc").shape == (N_FEATURES,)
    assert len(FEATURE_NAMES) == N_FEATURES


def test_all_zero_buffer():
    f = features(bytes(4096))
    assert f[0] == pytest.approx(1.0)
    assert f[1:256].sum() == 0
    assert f[ENT] == pytest.approx(0.0)
    # chi2 for all mass in one bin: n*(256-1)
    assert f[CHI] == pytest.approx(4096 * 255)
    assert f[PRN] == 0.0
    assert f[MAG] == -1.0


def test_uniform_buffer_has_max_entropy_and_zero_chi2():
    f = features(bytes(range(256)) * 16)
    np.testing.assert_allclose(f[:256], 1 / 256)
    assert f[ENT] == pytest.approx(8.0)
    assert f[CHI] == pytest.approx(0.0)
    assert f[PRN] == pytest.approx(98 / 256)  # 95 printable ASCII + \t \n \r


def test_ascii_text_is_fully_printable():
    f = features(b"Hello world.\nSecond line\twith tab.\r\n")
    assert f[PRN] == pytest.approx(1.0)
    assert 2.0 < f[ENT] < 5.0


def test_magic_flag():
    png = b"\x89PNG\r\n\x1a\n" + bytes(100)
    assert magic_flag(png, "png", True) == 1.0
    assert magic_flag(png, "jpg", True) == 0.0
    assert magic_flag(png, "png", False) == -1.0  # not a header chunk
    assert magic_flag(png, "txt", True) == -1.0  # type has no signature
    assert magic_flag(png, None, True) == -1.0
    assert features(png, "png", True)[MAG] == 1.0


def test_empty_buffer_is_safe():
    f = features(b"")
    assert np.all(np.isfinite(f))


def test_batch_matches_single():
    rng = np.random.default_rng(0)
    bufs = [rng.bytes(4096), b"text " * 300, bytes(10), b"\x89PNG\r\n\x1a\n" + rng.bytes(50)]
    types = [None, "txt", "bin", "png"]
    starts = [False, True, True, True]
    batch = features_batch(bufs, types, starts)
    for i, b in enumerate(bufs):
        np.testing.assert_allclose(batch[i], features(b, types[i], starts[i]))
    assert features_batch([]).shape == (0, N_FEATURES)
