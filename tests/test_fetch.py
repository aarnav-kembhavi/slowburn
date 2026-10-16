"""Dataset fetch guards (D58): budget checks, zip safety, FSL contiguous-day plan. No network."""

import zipfile

import pytest

from slowburn.datasets.fetch import Budget, StopFetch, plan_contiguous_block, safe_members


def test_budget_refuses_cap_and_reserve(tmp_path):
    (tmp_path / "a.bin").write_bytes(b"x" * 100)
    b = Budget(tmp_path, cap_bytes=150, reserve_bytes=0)
    b.check(50, "ok")
    with pytest.raises(StopFetch, match="cap"):
        b.check(51, "too big")
    huge = Budget(tmp_path, cap_bytes=10**18, reserve_bytes=10**18)
    with pytest.raises(StopFetch, match="reserve"):
        huge.check(1, "reserve")


def test_safe_members_skips_types_and_refuses_traversal(tmp_path):
    p = tmp_path / "z.zip"
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("NapierOne/PDF/a.pdf", b"1")
        z.writestr("NapierOne/EXE/b.exe", b"2")
    with zipfile.ZipFile(p) as z:
        names = [m.filename for m in safe_members(z, {"EXE"})]
    assert names == ["NapierOne/PDF/a.pdf"]
    bad = tmp_path / "bad.zip"
    with zipfile.ZipFile(bad, "w") as z:
        z.writestr("../evil.txt", b"x")
    with zipfile.ZipFile(bad) as z, pytest.raises(ValueError, match="unsafe"):
        safe_members(z)


def test_fsl_plan_is_a_contiguous_block_from_the_fullest_day():
    files = [(f"f-{u}-{d}", u, d) for d, us in
             (("d1", ["u1"]), ("d2", ["u1", "u2"]), ("d3", ["u1", "u2"]), ("d4", ["u1", "u2"]))
             for u in us]  # fmt: skip
    sizes = {f: 10 for f, _, _ in files}
    chosen, s = plan_contiguous_block(files, sizes, room=45)
    assert s["first_day"] == "d2" and s["last_day"] == "d3" and s["days"] == 2
    assert s["users"] == ["u1", "u2"] and s["bytes"] == 40
    assert "f-u1-d1" not in chosen and "f-u1-d4" not in chosen


def test_napierone_published_sha256_parses_utf8_and_utf16():
    from slowburn.datasets.fetch import napierone_published_sha256

    h = "b7eadda70d854bb19f10c6fdb0910345bda6e78522413a524b9e6537872027a3"
    txt = f" MD5   16   e2add58330e7556145e6ddd505b81bd0\n SHA256      32      {h.upper()}\n"
    assert napierone_published_sha256(txt.encode()) == h
    assert napierone_published_sha256(txt.encode("utf-16")) == h
    assert napierone_published_sha256(b"nothing") is None
