"""Per-chunk features. Everything except the magic flag derives from the byte histogram.

Layout of the feature vector (``N_FEATURES`` = 260):
    [0:256]  normalised byte-value histogram (sums to 1)
    [256]    Shannon entropy, bits per byte, in [0, 8]
    [257]    chi-square statistic against the uniform byte distribution
    [258]    printable-byte ratio (0x20-0x7E plus \\t \\n \\r)
    [259]    magic-byte consistency flag: 1 consistent, 0 inconsistent, -1 not applicable

Optional whole-file context column (``with_file_validity``):
    [260]    file_valid: does the *whole changed file* still decode as its declared type
             (1 valid, 0 invalid, -1 no check); see ``slowburn.detector.validity``
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

N_HIST = 256
N_FEATURES = N_HIST + 4
FEATURE_NAMES = [f"hist_{i:02x}" for i in range(N_HIST)] + [
    "entropy",
    "chi2_uniform",
    "printable_ratio",
    "magic_consistent",
]

FILE_VALID_INDEX = N_FEATURES
N_FEATURES_WITH_VALIDITY = N_FEATURES + 1
FEATURE_NAMES_WITH_VALIDITY = [*FEATURE_NAMES, "file_valid"]

# Known leading signatures per declared type. Types with no signature (txt, csv, bin) are n/a.
MAGIC: dict[str, tuple[bytes, ...]] = {
    "png": (b"\x89PNG\r\n\x1a\n",),
    "jpg": (b"\xff\xd8\xff",),
    "zip": (b"PK\x03\x04",),
    "docx": (b"PK\x03\x04",),
    "mp3": (b"ID3", b"\xff\xfb", b"\xff\xf3", b"\xff\xf2", b"\xff\xe3"),
    "zlib": (b"\x78\x01", b"\x78\x5e", b"\x78\x9c", b"\x78\xda"),
    "lzma": (b"\xfd7zXZ\x00",),
}

_PRINTABLE = np.zeros(N_HIST, dtype=bool)
_PRINTABLE[0x20:0x7F] = True
_PRINTABLE[[0x09, 0x0A, 0x0D]] = True


def magic_flag(buf: bytes, declared_type: str | None, at_file_start: bool) -> float:
    """1/0 if this is the first chunk of a file of a type with a known signature, else -1."""
    if not at_file_start or declared_type is None or declared_type not in MAGIC:
        return -1.0
    return 1.0 if any(buf.startswith(m) for m in MAGIC[declared_type]) else 0.0


def _from_counts(counts: np.ndarray, n: np.ndarray) -> np.ndarray:
    """Histogram-derived features for a (k, 256) count matrix and (k,) lengths."""
    n = np.maximum(n, 1).astype(np.float64)[:, None]
    p = counts / n
    with np.errstate(divide="ignore", invalid="ignore"):
        logp = np.where(p > 0, np.log2(p), 0.0)
    entropy = -(p * logp).sum(axis=1)
    expected = n / N_HIST
    chi2 = ((counts - expected) ** 2 / expected).sum(axis=1)
    printable = counts[:, _PRINTABLE].sum(axis=1) / n[:, 0]
    return np.column_stack([p, entropy, chi2, printable])


def features(
    buf: bytes, declared_type: str | None = None, at_file_start: bool = False
) -> np.ndarray:
    """Feature vector of one changed chunk. Pure function of its inputs."""
    arr = np.frombuffer(buf, dtype=np.uint8)
    counts = np.bincount(arr, minlength=N_HIST).astype(np.float64)[None, :]
    base = _from_counts(counts, np.array([len(arr)]))[0]
    return np.append(base, magic_flag(buf, declared_type, at_file_start))


def features_batch(
    bufs: Sequence[bytes],
    declared_types: Sequence[str | None] | None = None,
    at_file_start: Sequence[bool] | None = None,
) -> np.ndarray:
    """Vectorised ``features`` over many chunks; row i equals ``features(bufs[i], ...)``."""
    k = len(bufs)
    if k == 0:
        return np.zeros((0, N_FEATURES))
    declared_types = declared_types if declared_types is not None else [None] * k
    at_file_start = at_file_start if at_file_start is not None else [False] * k
    lengths = np.fromiter((len(b) for b in bufs), dtype=np.int64, count=k)
    flat = np.frombuffer(b"".join(bufs), dtype=np.uint8).astype(np.int64)
    rows = np.repeat(np.arange(k, dtype=np.int64), lengths)
    counts = np.bincount(rows * N_HIST + flat, minlength=k * N_HIST).reshape(k, N_HIST)
    base = _from_counts(counts.astype(np.float64), lengths)
    flags = np.fromiter(
        (magic_flag(b, t, s) for b, t, s in zip(bufs, declared_types, at_file_start, strict=True)),
        dtype=np.float64,
        count=k,
    )
    return np.column_stack([base, flags])


def validity_transition(prev: float | None, cur: float) -> float:
    """D78 F2: the file-validity column as a transition. 0 = the previous version was valid and
    this one is not; -1 = no check for the type; 1 otherwise (a file already invalid before, or
    a first version, does not look damaged by validity alone)."""
    if cur < 0:
        return -1.0
    return 0.0 if prev is not None and prev >= 1 and cur < 1 else 1.0


def with_file_validity(X: np.ndarray, file_valid: Sequence[float]) -> np.ndarray:
    """Append the whole-file validity flag of each row's file as column ``FILE_VALID_INDEX``."""
    v = np.asarray(file_valid, dtype=np.float64).reshape(-1, 1)
    if X.shape[0] != v.shape[0]:
        raise ValueError("one validity flag per feature row is required")
    return np.hstack([X, v])
