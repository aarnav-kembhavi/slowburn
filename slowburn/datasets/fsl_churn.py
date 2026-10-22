"""Per-file rewrite churn from FSL Homes ``2011-8kb-only`` (D66 retention audit).

``extract`` streams every complete, checksum-verified daily archive of the D58 block (read-only:
tar members are read as data, nothing is extracted or executed) and records, per user, on which
snapshot each file's content changed. A file is "rewritten" on snapshot k when its content
digest (``hashfile.iter_file_digests``) differs from snapshot k - 1. Empty snapshots (0 files)
are treated as missing days. Only regular files present in EVERY non-empty snapshot of the user
are kept, so each kept file has a complete rewrite record.

``machine_schedule`` turns one user's record into the benign-edit schedule of a simulated
machine: ``n_files`` files sampled uniformly from that user's kept files, rewritten on the days
their real counterparts were, replayed in order from a random offset and wrapping around.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import re
import stat
import tarfile
from concurrent.futures import ProcessPoolExecutor
from functools import lru_cache
from pathlib import Path

import numpy as np

from slowburn.datasets.hashfile import iter_file_digests, read_header
from slowburn.utils.config import resolve_path

ARCHIVE_RE = re.compile(r"fslhomes-(user\d+)-(\d{4}-\d{2}-\d{2})\.tar\.bz2$")
DEFAULT_OUT = "data/derived/fsl_churn_48d.json.gz"


def _key(b: bytes) -> int:
    return int.from_bytes(hashlib.blake2b(b, digest_size=8).digest(), "little")


def archive_digests(path: str) -> tuple[str, str, dict[int, int]]:
    """(user, date, {path key: content digest}) for the regular files of one daily archive."""
    m = ARCHIVE_RE.search(Path(path).name)
    if not m:
        raise ValueError(f"not an FSL Homes daily archive: {path}")
    out: dict[int, int] = {}
    with tarfile.open(path, mode="r|bz2") as tf:  # streamed; members are only read as bytes
        for member in tf:
            if not member.isfile() or not member.name.endswith(".hash.anon"):
                continue
            f = tf.extractfile(member)
            h = read_header(f)
            for p, _size, perm, digest in iter_file_digests(f, h):
                if stat.S_ISREG(perm) or perm == 0:
                    out[_key(p.encode())] = int.from_bytes(digest, "little")
    return m[1], m[2], out


def complete_archives(manifest_path: str | Path, last_day: str) -> list[Path]:
    """Archives with a published SHA-256 match on days <= ``last_day`` (the complete block)."""
    man = json.loads(Path(manifest_path).read_text())
    got = man["fsl_homes_2011_8kb"]
    out = []
    for name, rec in got.items():
        m = ARCHIVE_RE.search(name)
        if m and rec.get("published_hash_match") is True and m[2] <= last_day:
            out.append(Path(rec["file"]))
    return sorted(out, key=lambda p: ARCHIVE_RE.search(p.name).groups())


def extract(archives: list[Path], out_path: str = DEFAULT_OUT, workers: int = 6,
            log=print) -> dict:  # fmt: skip
    users: dict[str, dict] = {}
    state: dict[str, dict] = {}
    with ProcessPoolExecutor(workers) as ex:
        for user, date, cur in ex.map(archive_digests, [str(a) for a in archives]):
            u = users.setdefault(user, {"dates": [], "empty_dates": []})
            s = state.setdefault(user, {"prev": None, "present": None, "changes": {}})
            if not cur:
                u["empty_dates"].append(date)
                log(f"  {user} {date}: empty snapshot (treated as missing)")
                continue
            k = len(u["dates"])
            u["dates"].append(date)
            if s["prev"] is not None:
                prev = s["prev"]
                for key, dig in cur.items():
                    if key in prev and prev[key] != dig:
                        s["changes"].setdefault(key, []).append(k)
            s["present"] = set(cur) if s["present"] is None else s["present"] & cur.keys()
            s["prev"] = cur
            log(f"  {user} {date}: {len(cur)} files")
    for user, u in users.items():
        s = state[user]
        keep = s["present"] or set()
        changing = sorted(key for key in keep if key in s["changes"])
        u["n_present_all_days"] = len(keep)
        u["changes"] = [s["changes"][key] for key in changing]
        n_tr = max(len(u["dates"]) - 1, 1)
        rates = [len(c) / n_tr for c in u["changes"]]
        u["mean_rewrites_per_file_day"] = sum(rates) / max(len(keep), 1)
        u["frac_files_ever_rewritten"] = len(changing) / max(len(keep), 1)
    out = resolve_path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(out, "wt") as fh:
        json.dump({"source": "FSL Homes 2011-8kb-only", "archives": len(archives),
                   "users": users}, fh)  # fmt: skip
    return users


@lru_cache(maxsize=2)
def load_churn(path: str = DEFAULT_OUT) -> dict:
    with gzip.open(resolve_path(path), "rt") as fh:
        return json.load(fh)["users"]


def machine_schedule(churn: dict, rng: np.random.Generator, n_files: int,
                     n_days: int) -> tuple[str, list[list[int]]]:  # fmt: skip
    """(user, per-day lists of file indices 0..n_files-1 to rewrite) for one simulated machine.
    Day 0 has no edits (creation). Sim day t >= 1 replays transition 1 + (o + t - 1) mod (L - 1)
    of the user's L non-empty snapshots, o drawn uniformly."""
    users = sorted(u for u, rec in churn.items()
                   if len(rec["dates"]) >= 2 and rec["n_present_all_days"] >= n_files)  # fmt: skip
    user = users[int(rng.integers(len(users)))]
    rec = churn[user]
    picks = rng.choice(rec["n_present_all_days"], size=n_files, replace=False)
    n_tr = len(rec["dates"]) - 1
    by_tr: dict[int, list[int]] = {}
    for i, idx in enumerate(picks):
        if idx < len(rec["changes"]):  # the first len(changes) indices are the rewritten files
            for k in rec["changes"][idx]:
                by_tr.setdefault(int(k), []).append(i)
    o = int(rng.integers(n_tr))
    sched = [[] for _ in range(n_days)]
    for t in range(1, n_days):
        sched[t] = sorted(by_tr.get(1 + (o + t - 1) % n_tr, []))
    return user, sched


def main() -> None:
    man = resolve_path("data/MANIFEST.json")
    arch = complete_archives(man, "2011-11-03")
    print(f"{len(arch)} complete verified archives through 2011-11-03")
    users = extract(arch)
    for u, rec in sorted(users.items()):
        print(u, len(rec["dates"]), "days,", len(rec["empty_dates"]), "empty,",
              rec["n_present_all_days"], "files,", f"{rec['frac_files_ever_rewritten']:.4f}",
              "ever rewritten,", f"{rec['mean_rewrites_per_file_day']:.5f}",
              "rewrites/file/day")  # fmt: skip


if __name__ == "__main__":
    main()
