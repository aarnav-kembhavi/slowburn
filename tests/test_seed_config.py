import numpy as np
import pytest

from slowburn.utils.config import load_config
from slowburn.utils.seed import child_rng, make_rng


def test_make_rng_reproducible():
    assert make_rng(3).integers(0, 1 << 30) == make_rng(3).integers(0, 1 << 30)


def test_child_rng_independent_of_draw_order():
    a = child_rng(1, "sim", 2).random(4)
    child_rng(1, "other").random(100)  # drawing elsewhere must not shift the stream
    b = child_rng(1, "sim", 2).random(4)
    np.testing.assert_array_equal(a, b)


def test_child_rng_long_string_keys_do_not_collide():
    # regression: keys that share a long prefix must still give different streams
    k1 = "('damage_fraction', 0.05)" + "x" * 40 + "a"
    k2 = "('damage_fraction', 0.05)" + "x" * 40 + "b"
    assert child_rng(0, k1).random() != child_rng(0, k2).random()


def test_load_config_requires_seed(tmp_path):
    p = tmp_path / "c.yaml"
    p.write_text("experiment: x\n")
    with pytest.raises(ValueError, match="seed"):
        load_config(p)


def test_smoke_config_loads():
    cfg = load_config("configs/smoke.yaml")
    assert isinstance(cfg["seed"], int)
