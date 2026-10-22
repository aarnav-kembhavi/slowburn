"""NapierOne files for the detector and the byte-mode simulator (rule D67, OPEN_QUESTIONS.md).

Benign files are read in memory from the per-subset inner zips under ``<root>/benign`` (never
extracted); encrypted samples are the extracted family folders under ``<root>/encrypted``.
Only numbered samples (``0001-...``) are used: every inner zip and family folder also holds a
descriptor PDF, which is not a sample.
"""

from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np

from slowburn.utils.config import resolve_path
from slowburn.utils.seed import child_rng

# simulator type -> NapierOne-tiny subsets (D67); lzma has no NapierOne counterpart
TYPE_SUBSETS: dict[str, tuple[str, ...]] = {
    "txt": ("TXT",),
    "csv": ("CSV",),
    "bin": ("BIN",),
    "docx": ("DOCX",),
    "zip": ("ZIP-DEFLATE", "ZIP-BZIP2", "ZIP-LZMA", "ZIP-PPMD", "ZIP-HIGH-COMPRESSION"),
    "png": ("PNG-c0", "PNG-c3", "PNG-c5", "PNG-c7", "PNG-c9", "PNG-FROM-WEB"),
    "jpg": ("JPG-q001", "JPG-q025", "JPG-q050", "JPG-q075", "JPG-q100", "JPG-from-web"),
    "mp3": ("MP3",),
    "zlib": ("ZLIB",),
}
SAMPLE = re.compile(r"^\d{4}-")
SPLIT_SEED = 202
PER_TYPE = 100
SIM_MAX_BYTES = 1 << 20


@dataclass(frozen=True)
class BenignFile:
    file_type: str
    subset: str
    member: str
    size: int

    @property
    def key(self) -> str:
        return f"{self.subset}/{self.member}"


def _inner_zip(root: Path, subset: str) -> Path:
    return root / "benign" / f"{subset}-tiny.zip"


@lru_cache(maxsize=4)
def benign_index(root: str) -> tuple[BenignFile, ...]:
    base = Path(root)
    out = []
    for ftype, subsets in TYPE_SUBSETS.items():
        for sub in subsets:
            with zipfile.ZipFile(_inner_zip(base, sub)) as z:
                out += [BenignFile(ftype, sub, m.filename, m.file_size) for m in z.infolist()
                        if not m.is_dir() and SAMPLE.match(Path(m.filename).name)]  # fmt: skip
    return tuple(sorted(out, key=lambda f: (f.file_type, f.key)))


def read_benign(root: str | Path, f: BenignFile) -> bytes:
    with zipfile.ZipFile(_inner_zip(Path(root), f.subset)) as z:
        return z.read(f.member)


@lru_cache(maxsize=4)
def benign_splits(root: str) -> dict[str, dict[str, list[BenignFile]]]:
    """type -> {"train", "calib", "test", "sim_dev", "sim_test"}: per type the pooled files are
    permuted (seed 202, stream "napierone_split"), capped at 100, split 50 / 20 / 30; the held-out
    30% is the detector AUROC test set and the only simulation content (first half DEV, second
    half TEST)."""
    idx = benign_index(root)
    out = {}
    for ftype in TYPE_SUBSETS:
        pool = [f for f in idx if f.file_type == ftype]
        perm = child_rng(SPLIT_SEED, "napierone_split", ftype).permutation(len(pool))
        files = [pool[i] for i in perm[:PER_TYPE]]
        n = len(files)
        a, b = round(0.5 * n), round(0.7 * n)
        held, h = files[b:], (n - b) // 2
        out[ftype] = {"train": files[:a], "calib": files[a:b], "test": held,
                      "sim_dev": held[:h], "sim_test": held[h:]}  # fmt: skip
    return out


def family_splits(root: str | Path) -> dict[str, list[str]]:
    """30 families permuted (seed 202, stream "napierone_families"): 18 train, 6 calibration,
    6 held out (3 DEV, 3 TEST)."""
    fams = sorted(p.name for p in (Path(root) / "encrypted").iterdir() if p.is_dir())
    perm = child_rng(SPLIT_SEED, "napierone_families").permutation(len(fams))
    f = [fams[i] for i in perm]
    return {"train": f[:18], "calib": f[18:24], "test": f[24:30], "sim_dev": f[24:27],
            "sim_test": f[27:30]}  # fmt: skip


def encrypted_samples(root: str | Path, families: list[str]) -> list[Path]:
    base = Path(root) / "encrypted"
    return sorted(p for fam in families for p in (base / fam).iterdir()
                  if p.is_file() and SAMPLE.match(p.name))  # fmt: skip


class ContentPool:
    """Benign content for byte-mode simulated machines (D67): files of each type from one pool
    (``sim_dev``), at most ``SIM_MAX_BYTES``; ``draw`` returns the bytes of a random pool file."""

    def __init__(self, root: str | Path, pool: str = "sim_dev"):
        if pool == "sim_test":
            raise ValueError("the TEST content pool is not read before the fresh test set")
        self.root = str(resolve_path(root))
        sp = benign_splits(self.root)
        self.files = {t: [f for f in s[pool] if f.size <= SIM_MAX_BYTES] for t, s in sp.items()}
        empty = [t for t, fs in self.files.items() if not fs]
        if empty:
            raise ValueError(f"no {pool} file <= {SIM_MAX_BYTES} bytes for types {empty}")
        self._cache: dict[str, bytes] = {}

    def draw(self, ftype: str, rng: np.random.Generator) -> bytes:
        fs = self.files[ftype]
        f = fs[int(rng.integers(len(fs)))]
        if f.key not in self._cache:
            self._cache[f.key] = read_benign(self.root, f)
        return self._cache[f.key]
