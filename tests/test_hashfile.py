"""fs-hasher hash-file reader: round trip on a hash file built from the format spec (v7)."""

import io
import stat
import struct

import pytest

from slowburn.datasets.hashfile import (
    FH_V5,
    HDR_V1,
    HDR_V3_EXTRA,
    HDR_V5_EXTRA,
    iter_files,
    read_header,
)


def _v7(files):
    params = struct.pack("<I", 0).ljust(44, b"\0")
    nchunks = sum(len(c) for _, _, c in files)
    out = HDR_V1.pack(0xDEADDEAD, 7, len(files), b"/home", nchunks, 2, params, 3, 48)
    out += HDR_V3_EXTRA.pack(b"sys", 1, 2) + HDR_V5_EXTRA.pack(sum(s for _, s, _ in files))
    for path, size, chunks in files:
        p = path.encode()
        out += FH_V5.pack(size, 8, 1, 2, stat.S_IFREG | 0o644, 3, 4, 5, 1, 9, 77, len(chunks),
                          len(p), 0) + p  # fmt: skip
        for h, cs, cr in chunks:
            out += struct.pack("<I", cs) + h + bytes([cr])
    return out


def test_round_trip_v7_variable_chunks():
    files = [("/home/u/a.docx", 10, [(b"abcdef", 6, 1), (b"ghijkl", 4, 2)]),
             ("/home/u/notes", 3, [(b"mnopqr", 3, 0)])]  # fmt: skip
    f = io.BytesIO(_v7(files))
    h = read_header(f)
    recs = list(iter_files(f, h))
    assert f.read() == b""  # consumed exactly
    assert (h.version, h.files, h.chunks, h.bytes, h.hash_bits) == (7, 2, 3, 13, 48)
    assert [r.path for r in recs] == ["/home/u/a.docx", "/home/u/notes"]
    assert recs[0].chunks == [(b"abcdef", 6, 1), (b"ghijkl", 4, 2)]
    assert recs[0].extension == "docx" and recs[1].extension == "" and recs[0].is_regular
    assert recs[0].mtime == 4 and recs[0].inode == 77


def test_rejects_bad_magic_and_truncation():
    good = _v7([("/a.txt", 1, [(b"zzzzzz", 1, 0)])])
    with pytest.raises(ValueError, match="magic"):
        read_header(io.BytesIO(b"\0" * len(good)))
    f = io.BytesIO(good[:-3])
    h = read_header(f)
    with pytest.raises(EOFError):
        list(iter_files(f, h))


def test_file_digests_match_records_and_change_with_chunks():
    from slowburn.datasets.hashfile import iter_file_digests

    a = [("/home/u/a.docx", 10, [(b"abcdef", 6, 1), (b"ghijkl", 4, 2)]),
         ("/home/u/notes", 3, [(b"mnopqr", 3, 0)])]  # fmt: skip
    b = [a[0], ("/home/u/notes", 3, [(b"mnopqX", 3, 0)])]  # one chunk hash differs
    f = io.BytesIO(_v7(a))
    da = list(iter_file_digests(f))
    assert f.read() == b""  # consumed exactly, like iter_files
    db = list(iter_file_digests(io.BytesIO(_v7(b))))
    assert [(p, s) for p, s, _, _ in da] == [("/home/u/a.docx", 10), ("/home/u/notes", 3)]
    assert stat.S_ISREG(da[0][2])
    assert da[0][3] == db[0][3] and da[1][3] != db[1][3]
