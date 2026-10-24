"""D75: the pool sample order is seeded and reproducible, and the split gives DEV the extra file."""

from slowburn.datasets.napierone_v2 import _place, sample_order


def test_sample_order_is_seeded_and_name_order_independent():
    names = [f"f{i:03d}" for i in range(50)]
    a = sample_order("txt", names)
    assert a == sample_order("txt", list(reversed(names)))
    assert sorted(a) == sorted(names)
    assert a != sample_order("csv", names)


def test_place_splits_dev_first(tmp_path):
    rec = _place(tmp_path, "txt", [(f"S/m{i}", bytes([i])) for i in range(5)])
    assert [r["name"] for r in rec["dev"]] == ["S/m0", "S/m1", "S/m2"]
    assert len(rec["test"]) == 2
    assert (tmp_path / "txt" / "dev" / "S__m0").read_bytes() == b"\x00"
