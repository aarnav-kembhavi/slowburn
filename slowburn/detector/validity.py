"""Whole-file format validity: does a changed file still decode as its declared type?

Runs on the complete file, never on a single chunk: a chunk from the middle of a deflate stream
cannot be decoded on its own. Checks use each format's own integrity mechanisms:

    zip, docx  every member's CRC-32 (zipfile.testzip), docx also needs word/document.xml
    png        signature, every chunk's CRC-32, IHDR first, IEND last, IDAT inflates
    jpg        marker structure, and in entropy-coded data every 0xFF is followed by a
               legal byte (0x00 stuffing, RST0-7 or EOI); must end with EOI
    mp3        optional ID3v2 tag, then a contiguous chain of MPEG audio frame headers whose
               lengths tile the file
    zlib       full decompression (Adler-32 checked by zlib)
    lzma       full xz decompression (integrity check verified by lzma)
    txt, csv   strict UTF-8 decoding
    other      not applicable

Returns 1.0 (valid), 0.0 (invalid) or -1.0 (no check for this type). Purely a defender-side
parser; nothing here creates or repairs files.

Caveat for the paper: synthetic benign files are always valid by construction; real benign files
are sometimes truncated or malformed, so validity is likely more discriminative here than in the
wild.
"""

from __future__ import annotations

import io
import lzma
import struct
import zipfile
import zlib

VALID, INVALID, NOT_APPLICABLE = 1.0, 0.0, -1.0
CHECKED_TYPES = frozenset({"zip", "docx", "png", "jpg", "mp3", "zlib", "lzma", "txt", "csv"})


def file_validity(data: bytes, file_type: str) -> float:
    check = _CHECKS.get(file_type)
    if check is None:
        return NOT_APPLICABLE
    try:
        return VALID if check(data) else INVALID
    except Exception:  # any parser error means the file does not decode as its type
        return INVALID


def _zip_ok(data: bytes) -> bool:
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        return zf.testzip() is None


def _docx_ok(data: bytes) -> bool:
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        if zf.testzip() is not None:
            return False
        return zf.read("word/document.xml").lstrip().startswith(b"<?xml")


def _png_ok(data: bytes) -> bool:
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        return False
    pos, types, idat = 8, [], []
    while pos < len(data):
        if pos + 12 > len(data):
            return False
        (length,) = struct.unpack(">I", data[pos : pos + 4])
        ctype = data[pos + 4 : pos + 8]
        body = data[pos + 8 : pos + 8 + length]
        if len(body) != length or pos + 12 + length > len(data):
            return False
        (crc,) = struct.unpack(">I", data[pos + 8 + length : pos + 12 + length])
        if zlib.crc32(ctype + body) & 0xFFFFFFFF != crc:
            return False
        types.append(ctype)
        if ctype == b"IDAT":
            idat.append(body)
        pos += 12 + length
        if ctype == b"IEND":
            break
    if not types or types[0] != b"IHDR" or types[-1] != b"IEND" or pos != len(data):
        return False
    zlib.decompress(b"".join(idat))
    return True


_JPEG_STANDALONE = set(range(0xD0, 0xD8)) | {0x01, 0xD8}


def _jpg_ok(data: bytes) -> bool:
    if not data.startswith(b"\xff\xd8"):
        return False
    pos, n = 2, len(data)
    while pos < n:
        if data[pos] != 0xFF:
            return False
        marker = data[pos + 1] if pos + 1 < n else None
        if marker is None:
            return False
        if marker == 0xD9:  # EOI
            return pos + 2 == n
        if marker in _JPEG_STANDALONE or marker == 0xFF:
            pos += 1 if marker == 0xFF else 2
            continue
        (seg_len,) = struct.unpack(">H", data[pos + 2 : pos + 4])
        if seg_len < 2:
            return False
        pos += 2 + seg_len
        if marker == 0xDA:  # SOS: entropy-coded data follows until the next real marker
            while pos < n - 1:
                if data[pos] == 0xFF:
                    nxt = data[pos + 1]
                    if nxt == 0x00 or 0xD0 <= nxt <= 0xD7:
                        pos += 2
                        continue
                    if nxt == 0xFF:
                        pos += 1
                        continue
                    if nxt in (0xD9, 0xDA, 0xC4, 0xDB, 0xDD) or 0xE0 <= nxt <= 0xEF:
                        break  # a legal marker ends this scan
                    return False  # illegal byte after 0xFF inside entropy-coded data
                pos += 1
    return False


# MPEG audio: bitrate (kbps) tables and sample rates, indexed per version / layer III
_BITRATE_V1_L3 = [0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 0]
_BITRATE_V2_L3 = [0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160, 0]
_SAMPLE_RATES = {3: [44100, 48000, 32000], 2: [22050, 24000, 16000], 0: [11025, 12000, 8000]}


def _mp3_frame_len(h: bytes) -> int | None:
    b1, b2 = h[1], h[2]
    if h[0] != 0xFF or (b1 & 0xE0) != 0xE0:
        return None
    version, layer = (b1 >> 3) & 0x3, (b1 >> 1) & 0x3
    if version == 1 or layer != 1:  # reserved version, or not layer III
        return None
    br_idx, sr_idx, padding = b2 >> 4, (b2 >> 2) & 0x3, (b2 >> 1) & 0x1
    if sr_idx == 3:
        return None
    bitrate = (_BITRATE_V1_L3 if version == 3 else _BITRATE_V2_L3)[br_idx] * 1000
    if bitrate == 0:
        return None
    sr = _SAMPLE_RATES[version][sr_idx]
    coef = 144 if version == 3 else 72
    return coef * bitrate // sr + padding


def _mp3_ok(data: bytes) -> bool:
    pos = 0
    if data.startswith(b"ID3") and len(data) >= 10:
        size = 0
        for b in data[6:10]:
            if b & 0x80:
                return False
            size = (size << 7) | b
        pos = 10 + size
    frames = 0
    while pos + 4 <= len(data):
        flen = _mp3_frame_len(data[pos : pos + 4])
        if flen is None or flen < 4:
            return False
        pos += flen
        frames += 1
    return frames > 0 and pos == len(data)


def _utf8_ok(data: bytes) -> bool:
    data.decode("utf-8", errors="strict")
    return True


_CHECKS = {
    "zip": _zip_ok,
    "docx": _docx_ok,
    "png": _png_ok,
    "jpg": _jpg_ok,
    "mp3": _mp3_ok,
    "zlib": lambda d: zlib.decompress(d) is not None,
    "lzma": lambda d: lzma.decompress(d) is not None,
    "txt": _utf8_ok,
    "csv": _utf8_ok,
}
