"""A1: every synthetic type is produced by a real encoder and decodes with a real decoder;
whole-file validity flags damaged files."""

import io
import lzma
import zipfile
import zlib

import numpy as np
import pytest
from PIL import Image

from slowburn.detector.validity import CHECKED_TYPES, file_validity
from slowburn.sim.content import GENERATORS, generate_file
from slowburn.sim.damage import RandomDamageSource, apply_damage

SIZE = 48 * 1024


def _gen(ftype, seed=0):
    return generate_file(ftype, np.random.default_rng(seed), SIZE)


# ---- A1: real decoders accept the synthetic files ----------------------------------------


@pytest.mark.parametrize("seed", range(3))
def test_images_decode_with_pillow(seed):
    for ftype, fmt in (("png", "PNG"), ("jpg", "JPEG")):
        with Image.open(io.BytesIO(_gen(ftype, seed))) as im:
            assert im.format == fmt
            im.load()  # full decode of the pixel data
            assert im.size[0] >= 32


@pytest.mark.parametrize("seed", range(3))
def test_containers_decode_with_zipfile(seed):
    for ftype in ("zip", "docx"):
        with zipfile.ZipFile(io.BytesIO(_gen(ftype, seed))) as zf:
            assert zf.testzip() is None
            assert all(i.compress_type in (zipfile.ZIP_DEFLATED, zipfile.ZIP_STORED)
                       for i in zf.infolist())  # fmt: skip
    with zipfile.ZipFile(io.BytesIO(_gen("docx", seed))) as zf:
        assert b"<w:document" in zf.read("word/document.xml")


@pytest.mark.parametrize("seed", range(3))
def test_streams_decompress(seed):
    assert len(zlib.decompress(_gen("zlib", seed))) > SIZE
    assert len(lzma.decompress(_gen("lzma", seed))) > SIZE


def test_mp3_is_a_chain_of_mpeg_frames():
    data = _gen("mp3")
    assert file_validity(data, "mp3") == 1.0
    assert data[0] == 0xFF and (data[1] & 0xE0) == 0xE0  # frame sync at offset 0


# ---- validity checker ------------------------------------------------------------------


@pytest.mark.parametrize("ftype", sorted(GENERATORS))
@pytest.mark.parametrize("seed", range(4))
def test_pristine_files_are_valid(ftype, seed):
    expected = 1.0 if ftype in CHECKED_TYPES else -1.0
    assert file_validity(_gen(ftype, seed), ftype) == expected


def test_type_mismatch_and_garbage_are_invalid():
    assert file_validity(_gen("png"), "jpg") == 0.0
    assert file_validity(_gen("jpg"), "png") == 0.0
    assert file_validity(b"", "zip") == 0.0
    assert file_validity(np.random.default_rng(0).bytes(4096), "lzma") == 0.0
    assert file_validity(b"\xff\xfe\x00bad", "txt") == 0.0
    assert file_validity(b"anything", "bin") == -1.0


def _damaged(ftype, model, frac, seed):
    rng = np.random.default_rng(seed)
    data = _gen(ftype, seed)
    return apply_damage(data, model, frac, 4096, rng, RandomDamageSource(rng)).data


@pytest.mark.parametrize("ftype", ["zip", "docx", "png", "zlib", "lzma"])
def test_crc_protected_types_catch_light_striped_damage(ftype):
    hits = [file_validity(_damaged(ftype, "striped", 0.05, s), ftype) == 0.0 for s in range(10)]
    assert all(hits)


@pytest.mark.parametrize("ftype", ["zip", "png", "zlib", "lzma", "jpg"])
def test_whole_chunk_damage_is_caught(ftype):
    hits = [file_validity(_damaged(ftype, "whole", 0.05, s), ftype) == 0.0 for s in range(10)]
    assert np.mean(hits) >= 0.9


def test_text_damage_is_caught():
    hits = [file_validity(_damaged("txt", "striped", 0.05, s), "txt") == 0.0 for s in range(10)]
    assert all(hits)


def _ppmd_zip(payload: bytes, name: bytes = b"a.txt") -> bytes:
    """A one-member zip with compression method 98 (PPMd I rev 1), which zipfile cannot write."""
    import struct

    import pyppmd

    order, mem_mib, restore = 6, 16, 0
    enc = pyppmd.Ppmd8Encoder(order, mem_mib << 20, restore_method=restore)
    body = struct.pack("<H", (order - 1) | ((mem_mib - 1) << 4) | (restore << 12))
    body += enc.encode(payload) + enc.flush(endmark=False)
    crc, n = zlib.crc32(payload), len(payload)
    local = struct.pack("<IHHHHHIIIHH", 0x04034B50, 63, 0, 98, 0, 0, crc, len(body), n,
                        len(name), 0) + name  # fmt: skip
    central = struct.pack("<IHHHHHHIIIHHHHHII", 0x02014B50, 63, 63, 0, 98, 0, 0, crc,
                          len(body), n, len(name), 0, 0, 0, 0, 0, 0) + name  # fmt: skip
    cd_off = len(local) + len(body)
    end = struct.pack("<IHHHHIIH", 0x06054B50, 0, 0, 1, 1, len(central), cd_off, 0)
    return local + body + central + end


def test_ppmd_zip_members_are_checked_not_rejected():
    """D71b: zipfile raises NotImplementedError on PPMd members; 7-Zip reads them. A valid PPMd
    zip is valid, and a flipped byte in the member data is caught by the CRC-32."""
    payload = b"benign text, repeated for the model. " * 200
    data = _ppmd_zip(payload)
    with zipfile.ZipFile(io.BytesIO(data)) as zf, pytest.raises(NotImplementedError):
        zf.testzip()
    assert file_validity(data, "zip") == 1.0
    bad = bytearray(data)
    bad[30 + len(b"a.txt") + 40] ^= 0xFF
    assert file_validity(bytes(bad), "zip") == 0.0


def test_napierone_dev_ppmd_zips_are_valid():
    from pathlib import Path

    from slowburn.detector.napierone import ContentPool, read_benign

    if not Path("data/napierone/benign/ZIP-PPMD-tiny.zip").exists():
        pytest.skip("NapierOne data not present")
    pool = ContentPool("data/napierone")
    ppmd = [f for f in pool.files["zip"] if f.subset == "ZIP-PPMD"]
    assert len(ppmd) == 2
    assert all(file_validity(read_benign(pool.root, f), "zip") == 1.0 for f in ppmd)
