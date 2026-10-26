"""D67 NapierOne integration: fixed disjoint splits, numbered samples only, DEV-only content."""

import zipfile

import numpy as np
import pytest

from slowburn.detector import napierone as na


def _fake_root(tmp_path, n=40):
    (tmp_path / "benign").mkdir()
    for subs in na.TYPE_SUBSETS.values():
        for sub in subs:
            with zipfile.ZipFile(tmp_path / "benign" / f"{sub}-tiny.zip", "w") as z:
                for i in range(1, n + 1):
                    z.writestr(f"{i:04d}-{sub.lower()}.x", f"{sub} {i}".encode() * (1 + i))
                z.writestr(f"{sub}.pdf", b"descriptor")
    for f in range(30):
        d = tmp_path / "encrypted" / f"FAM{f:02d}"
        d.mkdir(parents=True)
        (d / "0001-a.locked").write_bytes(b"\x01" * 64)
        (d / f"FAM{f:02d}.pdf").write_bytes(b"descriptor")
    return str(tmp_path)


def test_splits_are_disjoint_capped_and_deterministic(tmp_path):
    root = _fake_root(tmp_path)
    sp = na.benign_splits(root)
    for t, s in sp.items():
        n = len(na.TYPE_SUBSETS[t]) * 40
        assert len(s["train"]) + len(s["calib"]) + len(s["test"]) == min(n, na.PER_TYPE)
        keys = [f.key for part in ("train", "calib", "test") for f in s[part]]
        assert len(keys) == len(set(keys))  # no file in two splits
        assert s["sim_dev"] + s["sim_test"] == s["test"]
        assert not any(f.member.endswith(".pdf") for f in s["train"])
    na.benign_splits.cache_clear()
    na.benign_index.cache_clear()
    assert na.benign_splits(root) == sp  # same seed, same split
    fam = na.family_splits(root)
    assert [len(fam[k]) for k in ("train", "calib", "test", "sim_dev", "sim_test")] == [
        18,
        6,
        6,
        3,
        3,
    ]
    assert not set(fam["train"]) & set(fam["test"])
    assert all(p.name == "0001-a.locked" for p in na.encrypted_samples(root, fam["sim_dev"]))


def test_content_pool_reads_dev_only(tmp_path):
    root = _fake_root(tmp_path)
    with pytest.raises(ValueError, match="TEST"):
        na.ContentPool(root, "sim_test")
    pool = na.ContentPool(root)
    dev = {na.read_benign(root, f) for f in na.benign_splits(root)["txt"]["sim_dev"]}
    rng = np.random.default_rng(0)
    assert all(pool.draw("txt", rng) in dev for _ in range(20))


def _flags(tmp_path, frozen, approved):
    f, f2 = tmp_path / "frozen.yaml", tmp_path / "frozen_v2.yaml"
    f.write_text(f"frozen: {str(frozen).lower()}\n")
    f2.write_text(f"approved: {str(approved).lower()}\n")
    return {"frozen_path": str(f), "frozen_v2_path": str(f2)}


def test_test_pool_needs_frozen_and_approved(tmp_path):
    root = _fake_root(tmp_path)
    for frozen, approved in ((False, False), (True, False), (False, True)):
        with pytest.raises(ValueError, match="TEST content refused"):
            na.ContentPool(root, "sim_test", "v2test", **_flags(tmp_path, frozen, approved))
    with pytest.raises(ValueError, match="v2test only"):
        na.ContentPool(root, "sim_test", "v2", **_flags(tmp_path, True, True))
    with pytest.raises(ValueError, match="unknown pool"):
        na.ContentPool(root, "sim_dev", "v2test")


def test_test_pool_reads_test_files_only(tmp_path):
    root = _fake_root(tmp_path)
    (tmp_path / "benign_v2").mkdir()
    (tmp_path / "benign_v2" / "manifest.json").write_text("{}")
    for t in na.TYPE_SUBSETS:
        for half in ("dev", "test"):
            d = tmp_path / "benign_v2" / t / half
            d.mkdir(parents=True)
            (d / f"{half}.x").write_bytes(f"{t} {half}".encode())
    pool = na.ContentPool(root, "sim_test", "v2test", **_flags(tmp_path, True, True))
    test = {na.read_benign(root, f) for f in na.benign_splits(root)["txt"]["sim_test"]}
    rng = np.random.default_rng(0)
    seen = {pool.draw("txt", rng) for _ in range(200)}
    assert seen <= test | {b"txt test"} and b"txt test" in seen
    dev = na.ContentPool(root, "sim_dev", "v2")
    assert b"txt dev" in {dev.draw("txt", rng) for _ in range(200)}
