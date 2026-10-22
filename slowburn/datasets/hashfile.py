"""Pure-Python reader for fs-hasher hash files (FSL Homes traces), versions 1-7.

Written from the format description and reader in fs-hasher 0.9.5 (`libhashfile.h`,
`libhashfile.c`, GPLv3; no code copied, the layout re-implemented). All structs are packed and
little-endian:

* header v1/v2 (4176 bytes): magic 0xDEADDEAD, version, files, path_root[4096], chunks,
  chunking method (1 fixed, 2 variable), chunking params union (44 bytes), hashing method,
  hash_size (bits). v3/v4 append sysid[4096], start_time, end_time (8288 bytes); v5-v7 also
  bytes (8296 bytes).
* file header: v1 path[4096], size, chunks; v2/v3 size, chunks, pathlen + path; v4 size, uid,
  gid, perm, atime, mtime, ctime, hardlinks, deviceid, inode, chunks, pathlen, target_pathlen
  (88 bytes); v5-v7 adds blocks after size (96 bytes). Then the path; then, for symlinks
  (v4+), the target path.
* per chunk: [size: uint64 for variable chunking in v3-v6, uint32 in v7] hash[hash_size/8]
  [cratio: uint8 in v6+]. With fixed chunking the size is implied by the chunk size.
"""

from __future__ import annotations

import stat
import struct
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import BinaryIO

MAGIC = 0xDEADDEAD
PATH = 4096
HDR_V1 = struct.Struct("<IIQ4096sQI44sII")  # 4176
HDR_V3_EXTRA = struct.Struct("<4096sQQ")  # +4112 -> 8288
HDR_V5_EXTRA = struct.Struct("<Q")  # +8 -> 8296
FH_V1 = struct.Struct("<4096sQQ")
FH_V2 = struct.Struct("<QQI")
FH_V4 = struct.Struct("<QIIQQQQQQQQII")  # 88
FH_V5 = struct.Struct("<QQIIQQQQQQQQII")  # 96
FIXED, VARIABLE = 1, 2


@dataclass
class Header:
    version: int
    files: int
    root: str
    chunks: int
    chunking: int
    fixed_chunk_size: int
    hashing: int
    hash_bits: int
    sysid: str = ""
    start_time: int = 0
    end_time: int = 0
    bytes: int = 0


@dataclass
class FileRecord:
    path: str
    size: int
    chunks: list[tuple[bytes, int, int]] = field(default_factory=list)  # (hash, size, cratio)
    blocks: int = 0
    uid: int = 0
    gid: int = 0
    perm: int = 0
    atime: int = 0
    mtime: int = 0
    ctime: int = 0
    inode: int = 0
    target: str = ""

    @property
    def extension(self) -> str:
        name = self.path.rsplit("/", 1)[-1]
        return name.rsplit(".", 1)[-1].lower() if "." in name[1:] else ""

    @property
    def is_regular(self) -> bool:
        return stat.S_ISREG(self.perm) if self.perm else True


def _cstr(b: bytes) -> str:
    return b.split(b"\0", 1)[0].decode("utf-8", "replace")


def _read(f: BinaryIO, n: int) -> bytes:
    b = f.read(n)
    if len(b) != n:
        raise EOFError(f"truncated hash file: wanted {n} bytes, got {len(b)}")
    return b


def read_header(f: BinaryIO) -> Header:
    magic, ver, files, root, chunks, cm, params, hm, hbits = HDR_V1.unpack(_read(f, HDR_V1.size))
    if magic != MAGIC:
        raise ValueError(f"not an fs-hasher hash file (magic {magic:#x})")
    if not 1 <= ver <= 7:
        raise ValueError(f"unsupported hash file version {ver}")
    h = Header(ver, files, _cstr(root), chunks, cm, struct.unpack_from("<I", params)[0], hm,
               hbits)  # fmt: skip
    if ver >= 3:
        sysid, h.start_time, h.end_time = HDR_V3_EXTRA.unpack(_read(f, HDR_V3_EXTRA.size))
        h.sysid = _cstr(sysid)
    if ver >= 5:
        (h.bytes,) = HDR_V5_EXTRA.unpack(_read(f, HDR_V5_EXTRA.size))
    return h


def iter_file_digests(f: BinaryIO, header: Header | None = None) -> Iterator[tuple]:
    """Fast path for churn: yield (path, size, perm, digest) per file, where ``digest`` is an
    8-byte BLAKE2b of the file's raw chunk records (sizes, hashes, ratios), so it changes
    exactly when the chunk list changes. Reads each file's chunk block in one call."""
    import hashlib

    h = header or read_header(f)
    if h.version < 4:
        raise ValueError("iter_file_digests needs hash file version >= 4 (per-file metadata)")
    rec = h.hash_bits // 8 + (h.version >= 6)
    if h.chunking == VARIABLE:
        rec += 4 if h.version >= 7 else 8
    fh = FH_V5 if h.version >= 5 else FH_V4
    for _ in range(h.files):
        vals = fh.unpack(_read(f, fh.size))
        fsize, perm = vals[0], vals[4] if h.version >= 5 else vals[3]
        nch, plen, tlen = vals[-3], vals[-2], vals[-1]
        path = _read(f, plen).decode("utf-8", "replace")
        if stat.S_ISLNK(perm):
            _read(f, tlen)
        digest = hashlib.blake2b(_read(f, nch * rec), digest_size=8).digest()
        yield path, fsize, perm, digest


def iter_files(f: BinaryIO, header: Header | None = None) -> Iterator[FileRecord]:
    """Yield every file record with its chunks. ``f`` is positioned after the header if
    ``header`` is given, otherwise the header is read first."""
    h = header or read_header(f)
    hb = h.hash_bits // 8
    size_fmt = None
    if h.chunking == VARIABLE:
        size_fmt = "<I" if h.version >= 7 else ("<Q" if h.version >= 3 else None)
    has_cratio = h.version >= 6
    for _ in range(h.files):
        if h.version >= 5:
            (fsize, blocks, uid, gid, perm, at, mt, ct, _hl, _dev, ino, nch, plen,
             tlen) = FH_V5.unpack(_read(f, FH_V5.size))  # fmt: skip
            rec = FileRecord("", fsize, [], blocks, uid, gid, perm, at, mt, ct, ino)
        elif h.version == 4:
            (fsize, uid, gid, perm, at, mt, ct, _hl, _dev, ino, nch, plen,
             tlen) = FH_V4.unpack(_read(f, FH_V4.size))  # fmt: skip
            rec = FileRecord("", fsize, [], 0, uid, gid, perm, at, mt, ct, ino)
        elif h.version >= 2:
            fsize, nch, plen = FH_V2.unpack(_read(f, FH_V2.size))
            tlen, rec = 0, FileRecord("", fsize)
        else:
            path, fsize, nch = FH_V1.unpack(_read(f, FH_V1.size))
            plen, tlen, rec = 0, 0, FileRecord(_cstr(path), fsize)
        if h.version >= 2:
            rec.path = _read(f, plen).decode("utf-8", "replace")
            if h.version >= 4 and stat.S_ISLNK(rec.perm):
                rec.target = _read(f, tlen).decode("utf-8", "replace")
        for i in range(nch):
            if size_fmt:
                (csize,) = struct.unpack(size_fmt, _read(f, struct.calcsize(size_fmt)))
            elif h.chunking == FIXED:
                csize = h.fixed_chunk_size
                if i == nch - 1:
                    csize = min(csize, fsize - (nch - 1) * h.fixed_chunk_size)
            else:
                csize = 0
            hsh = _read(f, hb)
            cr = _read(f, 1)[0] if has_cratio else 0
            rec.chunks.append((hsh, csize, cr))
        yield rec
