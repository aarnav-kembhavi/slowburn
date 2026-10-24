"""D75: enlarge the NapierOne simulation content pools (OPEN_QUESTIONS D75 rule, 2026-10-23).

For txt, csv, bin, docx, mp3, zlib: download ``NapierOne/Data/<T>/<T>-small.zip`` (one archive at
a time; cap and reserve checked by ``fetch.Budget``), verify bytes and the published SHA-256,
pick the candidates <= 1 MiB whose content hash is not in the tiny set (all of the type's tiny
files are in a detector split) and not a duplicate, draw the seeded sample of up to 200, extract
only those, delete the archive. For zip, png, jpg: the unused tiny files are the candidates
(no download). Sampled files are split by sample order: first half DEV, second half TEST.

Output: ``<root>/napierone/benign_v2/<type>/<dev|test>/<subset>__<member basename>`` plus
``<root>/napierone/benign_v2/manifest.json``. Archives are untrusted data: members are read in
memory, nothing is executed, unsafe member names are refused (``fetch.safe_members``).
"""

from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

from slowburn.datasets.fetch import (
    S3,
    Budget,
    StopFetch,
    download,
    napierone_published_sha256,
    s3_keys,
    safe_members,
)
from slowburn.detector.napierone import (
    SAMPLE,
    SIM_MAX_BYTES,
    benign_index,
    benign_splits,
    read_benign,
)
from slowburn.utils.seed import child_rng

DOWNLOAD = {"txt": "TXT", "csv": "CSV", "bin": "BIN", "docx": "DOCX", "mp3": "MP3", "zlib": "ZLIB"}
UNUSED_TINY = ("zip", "png", "jpg")
N_SAMPLE = 200


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def tiny_hashes(root: str, ftype: str) -> set[str]:
    """Content hashes of every tiny file of the type in any detector split (train, calib, test;
    sim pools are part of the held-out test split)."""
    sp = benign_splits(root)[ftype]
    return {_sha(read_benign(root, f)) for f in sp["train"] + sp["calib"] + sp["test"]}


def sample_order(ftype: str, names: list[str]) -> list[str]:
    """Seeded permutation of the candidate names (sorted first, so the order is reproducible)."""
    names = sorted(names)
    perm = child_rng(202, "d75_pool", ftype).permutation(len(names))
    return [names[i] for i in perm]


def _place(out: Path, ftype: str, chosen: list[tuple[str, bytes]]) -> dict:
    h = len(chosen) - len(chosen) // 2  # DEV gets the extra file
    rec = {"dev": [], "test": []}
    for k, (name, data) in enumerate(chosen):
        part = "dev" if k < h else "test"
        dest = out / ftype / part / name.replace("/", "__")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        rec[part].append({"name": name, "bytes": len(data), "sha256": _sha(data)})
    return rec


def _from_archive(zpath: Path, tiny: set[str]) -> tuple[dict, dict]:
    """Candidates from a downloaded archive: numbered samples <= 1 MiB whose content hash is
    neither in the tiny set nor already seen (members in name order, first kept)."""
    cands, seen = {}, set()
    stats = {"members": 0, "too_big": 0, "in_tiny": 0, "duplicate": 0}
    with zipfile.ZipFile(zpath) as z:
        for m in sorted(safe_members(z), key=lambda m: m.filename):
            if not SAMPLE.match(Path(m.filename).name):
                continue
            stats["members"] += 1
            if m.file_size > SIM_MAX_BYTES:
                stats["too_big"] += 1
                continue
            data = z.read(m, pwd=b"napierone" if m.flag_bits & 0x1 else None)
            h = _sha(data)
            if h in tiny or h in seen:
                stats["in_tiny" if h in tiny else "duplicate"] += 1
                continue
            seen.add(h)
            cands[m.filename] = data
    return cands, stats


def run(root: str = "data", log=print) -> dict:
    root_p = Path(root).resolve()
    nap = str(root_p / "napierone")
    out = root_p / "napierone" / "benign_v2"
    mpath = out / "manifest.json"
    manifest = json.loads(mpath.read_text()) if mpath.exists() else {}
    budget = Budget(root_p)

    def save():
        out.mkdir(parents=True, exist_ok=True)
        mpath.write_text(json.dumps(manifest, indent=1))

    try:
        for ftype in UNUSED_TINY:
            if ftype in manifest:
                continue
            sp = benign_splits(nap)[ftype]
            used = {f.key for k in ("train", "calib", "test") for f in sp[k]}
            seen = tiny_hashes(nap, ftype)
            cands, dup = {}, 0
            for f in benign_index(nap):
                if f.file_type != ftype or f.key in used or f.size > SIM_MAX_BYTES:
                    continue
                data = read_benign(nap, f)
                if _sha(data) in seen:
                    dup += 1
                    continue
                seen.add(_sha(data))
                cands[f.key] = data
            order = sample_order(ftype, list(cands))[:N_SAMPLE]
            manifest[ftype] = {"source": "NapierOne-tiny unused files", "candidates": len(cands),
                               "excluded_hash_match_or_duplicate": dup,
                               **_place(out, ftype, [(n, cands[n]) for n in order])}  # fmt: skip
            save()
            log(f"{ftype}: {len(cands)} candidates, sampled {len(order)}")
        keys = s3_keys("NapierOne/Data/")
        for ftype, T in DOWNLOAD.items():
            if ftype in manifest:
                continue
            k = f"NapierOne/Data/{T}/{T}-small.zip"
            hk = k.replace(".zip", "_zip_hashes.txt")
            size = keys[k]
            budget.check(size, f"download {k}")  # stops before the archive if it cannot fit
            dest = root_p / "napierone" / "small_zips" / Path(k).name
            rec = download(f"{S3}/{k}", dest, budget, log, size)
            hp = dest.with_name(Path(hk).name)
            download(f"{S3}/{hk}", hp, budget, log, keys[hk])
            rec["published_sha256"] = napierone_published_sha256(hp.read_bytes())
            rec["published_hash_match"] = rec["published_sha256"] == rec["sha256"]
            if not rec["published_hash_match"]:
                raise OSError(f"{k}: SHA-256 does not match the published hash (archive kept)")
            cands, stats = _from_archive(dest, tiny_hashes(nap, ftype))
            order = sample_order(ftype, list(cands))[:N_SAMPLE]
            manifest[ftype] = {"source": k, "url": f"{S3}/{k}", "archive_bytes": size,
                               "archive_sha256": rec["sha256"],
                               "published_sha256": rec["published_sha256"],
                               "candidates": len(cands), **stats,
                               **_place(out, ftype, [(n, cands[n]) for n in order])}  # fmt: skip
            dest.unlink()
            hp.unlink()
            manifest[ftype]["archive_deleted"] = True
            save()
            log(f"{ftype}: {stats}, {len(cands)} candidates, sampled {len(order)}; archive deleted")
        log("DONE")
    except StopFetch as e:
        manifest["stopped"] = str(e)
        save()
        log(f"STOP: {e}")
    return manifest


if __name__ == "__main__":
    run(log=lambda *a: print(*a, flush=True))
