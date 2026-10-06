"""Synthetic *benign* file content, one generator per file type.

The compressed/media types are produced by the real encoders (zipfile, Pillow, LAME, zlib,
lzma) applied to synthetic source material, so their bytes have genuine high-entropy structure.
They are the hard negatives: a detector that only learned "high entropy = damaged" fails on them.

Every generator is a pure function of (rng, target_size) and returns bytes of roughly that size.
"""

from __future__ import annotations

import io
import lzma
import zipfile
import zlib
from collections.abc import Callable

import numpy as np

_SYLLABLES = [
    "ka", "ri", "to", "men", "sa", "lo", "ver", "di", "an", "que", "por", "el", "tra", "ne",
    "bi", "un", "co", "st", "ar", "in", "re", "pe", "mo", "la", "ti", "on", "es", "da", "ge",
]  # fmt: skip
_PUNCT = [".", ",", ".", ";", "?", "!"]


def _vocabulary(rng: np.random.Generator, size: int = 2000) -> list[str]:
    lengths = rng.integers(1, 4, size)
    syl = rng.integers(0, len(_SYLLABLES), (size, 3))
    return ["".join(_SYLLABLES[j] for j in syl[i, : lengths[i]]) for i in range(size)]


def _zipf_words(rng: np.random.Generator, n_words: int) -> list[str]:
    vocab = _vocabulary(rng)
    ranks = np.arange(1, len(vocab) + 1)
    p = 1.0 / ranks
    p /= p.sum()
    idx = rng.choice(len(vocab), size=n_words, p=p)
    return [vocab[i] for i in idx]


def gen_txt(rng: np.random.Generator, size: int) -> bytes:
    n = max(16, size // 5)
    words = _zipf_words(rng, n)
    punct = rng.random(n) < 0.08
    marks = rng.integers(0, len(_PUNCT), n)
    breaks = np.cumsum(rng.integers(8, 16, n // 8 + 2))
    out, start = [], 0
    for end in breaks:
        end = min(int(end), n)
        if start >= end:
            break
        line = [
            w + _PUNCT[marks[i]] if punct[i] else w for i, w in enumerate(words[start:end], start)
        ]
        line[0] = line[0].capitalize()
        out.append(" ".join(line) + ".")
        start = end
    return "\n".join(out).encode("utf-8")[:size]


def gen_csv(rng: np.random.Generator, size: int) -> bytes:
    n = size // 40 + 2  # rows are ~45 bytes
    stations = np.array(["north", "south", "east", "west", "depot"])
    status = np.array(["ok", "ok", "ok", "warn", "fail"])
    month, mday = rng.integers(1, 13, n), rng.integers(1, 29, n)
    st, stat = stations[rng.integers(0, 5, n)], status[rng.integers(0, 5, n)]
    temp, hum, cnt = rng.normal(18, 7, n), rng.uniform(20, 95, n), rng.poisson(40, n)
    rows = ["id,date,station,temp_c,humidity,count,status"] + [
        f"{i + 1},2024-{month[i]:02d}-{mday[i]:02d},{st[i]},{temp[i]:.2f},{hum[i]:.1f},"
        f"{cnt[i]},{stat[i]}"
        for i in range(n)
    ]
    return "\n".join(rows).encode("ascii")[:size]


def gen_bin(rng: np.random.Generator, size: int) -> bytes:
    """Uncompressed numeric dump (sensor log / raw PCM style): smooth signals, float32/int16."""
    if rng.random() < 0.5:
        n = size // 4 + 1
        x = np.cumsum(rng.normal(0, 0.05, n)).astype("<f4")
    else:
        n = size // 2 + 1
        t = np.arange(n)
        x = (3000 * np.sin(t / rng.uniform(5, 50)) + rng.normal(0, 200, n)).astype("<i2")
    return x.tobytes()[:size]


def _docx_xml(rng: np.random.Generator, n_chars: int) -> bytes:
    paras = []
    text = gen_txt(rng, n_chars).decode("utf-8").split("\n")
    for p in text:
        paras.append(f'<w:p><w:r><w:rPr><w:lang w:val="en-GB"/></w:rPr><w:t>{p}</w:t></w:r></w:p>')
    body = "".join(paras)
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{body}</w:body></w:document>"
    ).encode()


def _write(zf: zipfile.ZipFile, name: str, data, compress: int = zipfile.ZIP_DEFLATED) -> None:
    """writestr with a fixed timestamp; the default stamps the wall clock (non-reproducible)."""
    info = zipfile.ZipInfo(name, date_time=(2024, 1, 1, 0, 0, 0))
    info.compress_type = compress
    zf.writestr(info, data)


def gen_docx(rng: np.random.Generator, size: int) -> bytes:
    """OOXML-shaped zip container (deflated XML), as Word writes it."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        _write(
            zf,
            "[Content_Types].xml",
            '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/'
            'content-types"><Default Extension="xml" ContentType="application/xml"/></Types>',
        )
        _write(zf, "word/document.xml", _docx_xml(rng, size * 3))
        _write(zf, "docProps/core.xml", f"<cp:coreProperties rev='{rng.integers(1, 99)}'/>")
        if rng.random() < 0.5:  # embedded image, common in real documents
            _write(zf, "word/media/image1.png", gen_png(rng, size // 3), zipfile.ZIP_STORED)
    return buf.getvalue()


def gen_zip(rng: np.random.Generator, size: int) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        k = int(rng.integers(2, 6))
        for i in range(k):
            g = [gen_txt, gen_csv, gen_bin][int(rng.integers(0, 3))]
            _write(zf, f"member_{i}.dat", g(rng, size * 2 // k))
    return buf.getvalue()


def _synthetic_image(rng: np.random.Generator, side: int) -> np.ndarray:
    """Smooth gradients + random shapes + sensor noise, uint8 RGB."""
    y, x = np.mgrid[0:side, 0:side].astype(np.float32) / side
    img = np.zeros((side, side, 3), np.float32)
    for c in range(3):
        a, b, ph = rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(0, 6.3)
        img[..., c] = 128 + 90 * np.sin(3 * (a * x + b * y) + ph)
    for _ in range(int(rng.integers(3, 12))):
        cx, cy, r = rng.uniform(0, 1), rng.uniform(0, 1), rng.uniform(0.03, 0.25)
        mask = (x - cx) ** 2 + (y - cy) ** 2 < r**2
        img[mask] = rng.uniform(0, 255, 3)
    img += rng.normal(0, rng.uniform(1, 12), img.shape)
    return np.clip(img, 0, 255).astype(np.uint8)


def _encode_image(rng: np.random.Generator, size: int, fmt: str, **save_kw) -> bytes:
    """Encode a synthetic image, growing it until the file reaches about ``size`` bytes."""
    from PIL import Image

    side = int(np.clip(np.sqrt(size), 32, 2048))
    for _ in range(6):
        buf = io.BytesIO()
        Image.fromarray(_synthetic_image(rng, side)).save(buf, format=fmt, **save_kw)
        out = buf.getvalue()
        if len(out) >= 0.6 * size or side >= 2048:
            return out
        side = min(2048, int(side * np.sqrt(size / max(len(out), 1)) * 1.1))
    return out


def gen_png(rng: np.random.Generator, size: int) -> bytes:
    return _encode_image(rng, size, "PNG")


def gen_jpg(rng: np.random.Generator, size: int) -> bytes:
    return _encode_image(rng, size, "JPEG", quality=int(rng.integers(70, 96)))


def gen_mp3(rng: np.random.Generator, size: int) -> bytes:
    """Real MPEG-1 Layer III (LAME) encoding of synthetic tones + noise."""
    import lameenc

    rate, kbps = 22050, 64
    seconds = max(0.5, size / (kbps * 1000 / 8))
    t = np.arange(int(rate * seconds)) / rate
    sig = np.zeros_like(t)
    for _ in range(int(rng.integers(2, 6))):
        f = rng.uniform(80, 2000)
        env = 0.5 + 0.5 * np.sin(2 * np.pi * rng.uniform(0.1, 2) * t)
        sig += env * np.sin(2 * np.pi * f * t)
    sig = sig / np.max(np.abs(sig)) * 0.6 + rng.normal(0, 0.02, t.shape)
    pcm = (sig * 32767).astype("<i2")
    enc = lameenc.Encoder()
    enc.set_bit_rate(kbps)
    enc.set_in_sample_rate(rate)
    enc.set_channels(1)
    enc.set_quality(7)
    return bytes(enc.encode(pcm.tobytes()) + enc.flush())


def _plain_source(rng: np.random.Generator, size: int) -> bytes:
    g = [gen_txt, gen_csv, gen_bin][int(rng.integers(0, 3))]
    return g(rng, size)


def gen_zlib(rng: np.random.Generator, size: int) -> bytes:
    return zlib.compress(_plain_source(rng, size * 3), level=int(rng.integers(1, 10)))


def gen_lzma(rng: np.random.Generator, size: int) -> bytes:
    return lzma.compress(_plain_source(rng, size * 4))


GENERATORS: dict[str, Callable[[np.random.Generator, int], bytes]] = {
    "txt": gen_txt,
    "csv": gen_csv,
    "bin": gen_bin,
    "docx": gen_docx,
    "zip": gen_zip,
    "png": gen_png,
    "jpg": gen_jpg,
    "mp3": gen_mp3,
    "zlib": gen_zlib,
    "lzma": gen_lzma,
}

# types whose bytes are already high-entropy; reported separately as hard negatives
HIGH_ENTROPY_TYPES = frozenset({"docx", "zip", "png", "jpg", "mp3", "zlib", "lzma"})

# types where a save rewrites the whole (compressed) stream rather than a few chunks in place
WHOLE_FILE_REWRITE_TYPES = HIGH_ENTROPY_TYPES


def generate_file(file_type: str, rng: np.random.Generator, size: int) -> bytes:
    try:
        gen = GENERATORS[file_type]
    except KeyError:
        raise ValueError(f"unknown file type {file_type!r}; known: {sorted(GENERATORS)}") from None
    return gen(rng, size)


def chunk_bytes(buf: bytes, chunk_size: int) -> list[bytes]:
    """Fixed-size chunking (the last chunk may be short)."""
    return [buf[i : i + chunk_size] for i in range(0, len(buf), chunk_size)]
