"""Fetch the approved datasets into data/ (team decision D58, 2026-10-17).

Rules enforced here, before EVERY archive:
* data/ may hold at most ``cap_bytes`` (100 GB) and the drive must keep ``reserve_bytes``
  (45 GB) free; if the next archive (or the next extraction) would break either, stop and report.
  Nothing is ever deleted to make room.
* Downloads land in ``<name>.part`` and are renamed only after the byte count matches the
  server's Content-Length (and the published SHA-256 where one exists). An interrupted download
  resumes from its ``.part`` with an HTTP range request (D61); the server's Content-Range must
  start at the partial size and name the expected total, otherwise the file restarts from 0. The
  SHA-256 covers the partial bytes plus the resumed ones, so a corrupt partial fails the check.
* Archives are treated as untrusted data: nothing in them is executed; zip members with absolute
  paths or ``..`` are refused; executable and script type folders are not extracted.

Order: NapierOne encrypted 100 per family (30 ``<FAMILY>-tiny.zip``), NapierOne benign 100 per type
(``NapierOne-tiny.zip``), then FSL Homes ``2011-8kb-only`` kept compressed, as one contiguous block
of days with every user present on those days, until the cap or the reserve is reached.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import threading
import time
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

S3 = "https://s3.eu-north-1.amazonaws.com/napierone.com"
FSL = "https://tracer.filesystems.org/traces/fslhomes/2011-8kb-only/"
GB = 10**9
SKIP_TYPES = {"APK", "DLL", "ELF", "EXE", "POWERSHELL"}  # executables / scripts: not extracted
UA = {"User-Agent": "slowburn-research-fetch/1.0"}
# tracer.filesystems.org serves ~100 KB/s per connection; 4 connections (D58, modest load)
FSL_CONNECTIONS = 4


class StopFetch(Exception):
    """The next step would break the cap or the free-space reserve."""


@dataclass
class Budget:
    root: Path
    cap_bytes: int = 100 * GB
    reserve_bytes: int = 45 * GB

    def used(self) -> int:
        return sum(p.stat().st_size for p in self.root.rglob("*") if p.is_file())

    def free(self) -> int:
        return shutil.disk_usage(self.root).free

    def check(self, need: int, what: str) -> None:
        used, free = self.used(), self.free()
        if used + need > self.cap_bytes:
            raise StopFetch(f"{what}: data/ would hold {used + need} bytes > cap {self.cap_bytes}")
        if free - need < self.reserve_bytes:
            raise StopFetch(f"{what}: free space would drop to {free - need} bytes < reserve "
                            f"{self.reserve_bytes}")  # fmt: skip


def _open(url: str, method: str = "GET", headers: dict | None = None):
    return urllib.request.urlopen(urllib.request.Request(url, headers={**UA, **(headers or {})},
                                                         method=method), timeout=120)  # fmt: skip


def content_length(url: str) -> int:
    with _open(url, "HEAD") as r:
        return int(r.headers["Content-Length"])


def s3_keys(prefix: str) -> dict[str, int]:
    """Key -> size for one S3 prefix (no delimiter; follows continuation tokens)."""
    ns = {"s": "http://s3.amazonaws.com/doc/2006-03-01/"}
    out, token = {}, None
    while True:
        q = f"{S3}?list-type=2&prefix={prefix}" + (f"&continuation-token={token}" if token else "")
        with _open(q) as r:
            root = ET.fromstring(r.read())
        for c in root.findall("s:Contents", ns):
            out[c.find("s:Key", ns).text] = int(c.find("s:Size", ns).text)
        if root.findtext("s:IsTruncated", namespaces=ns) != "true":
            return out
        token = urllib.request.quote(root.findtext("s:NextContinuationToken", namespaces=ns))


def download(url: str, dest: Path, budget: Budget, log, expected: int | None = None) -> dict:
    size = expected if expected is not None else content_length(url)
    if dest.exists() and dest.stat().st_size == size:
        log(f"  have {dest.name} ({size} bytes)")
        return {"file": str(dest), "bytes": size, "sha256": _sha256(dest)}
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(dest.suffix + ".part")
    have = part.stat().st_size if part.exists() else 0
    if have > size:
        log(f"  {dest.name}: partial ({have} bytes) is longer than the file; restarting from 0")
        have = 0
    budget.check(size - have, dest.name)
    h, t0 = hashlib.sha256(), time.time()
    if have:
        with part.open("rb") as fh:
            while chunk := fh.read(1 << 20):
                h.update(chunk)
    with _open(url, headers={"Range": f"bytes={have}-"} if have else None) as r:
        if have:
            cr = r.headers.get("Content-Range", "")
            ok = r.status == 206 and cr.startswith(f"bytes {have}-") and cr.endswith(f"/{size}")
            if not ok:
                log(f"  {dest.name}: range not honoured ({r.status}, {cr!r}); restarting from 0")
                have, h = 0, hashlib.sha256()
            else:
                log(f"  {dest.name}: resuming at {have} of {size} bytes")
        n = have
        with part.open("ab" if have else "wb") as fh:
            while chunk := r.read(1 << 20):
                fh.write(chunk)
                h.update(chunk)
                n += len(chunk)
    if n != size:
        raise OSError(f"{dest.name}: got {n} bytes, expected {size} (kept as .part)")
    part.replace(dest)
    log(f"  got {dest.name}: {n} bytes in {time.time() - t0:.0f} s")
    return {"file": str(dest), "bytes": n, "sha256": h.hexdigest()}


def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        while chunk := fh.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


def safe_members(z: zipfile.ZipFile, skip_types=frozenset()) -> list[zipfile.ZipInfo]:
    keep = []
    for m in z.infolist():
        parts = Path(m.filename.replace("\\", "/")).parts
        if m.filename.startswith(("/", "\\")) or ".." in parts or (parts and ":" in parts[0]):
            raise ValueError(f"unsafe zip member {m.filename!r}")
        if m.is_dir() or any(p.upper() in skip_types for p in parts):
            continue
        keep.append(m)
    return keep


def extract(zpath: Path, out: Path, budget: Budget, log, skip_types=frozenset(),
            password: bytes = b"napierone") -> dict:  # fmt: skip
    done = out / ".extracted"
    if done.exists():
        return json.loads(done.read_text())
    with zipfile.ZipFile(zpath) as z:
        members = safe_members(z, skip_types)
        need = sum(m.file_size for m in members)
        budget.check(need, f"extract {zpath.name}")
        for m in members:
            z.extract(m, out, pwd=password if m.flag_bits & 0x1 else None)
    info = {"archive": str(zpath), "files": len(members), "bytes": need,
            "skipped_types": sorted(skip_types)}  # fmt: skip
    done.write_text(json.dumps(info))
    log(f"  extracted {zpath.name}: {len(members)} files, {need} bytes")
    return info


def napierone_published_sha256(raw: bytes) -> str | None:
    """SHA-256 from a NapierOne ``*_zip_hashes.txt`` (Hash Console output, UTF-8 or UTF-16)."""
    bom16 = (b"\xff\xfe", b"\xfe\xff")
    txt = raw.decode("utf-16") if raw[:2] in bom16 else raw.decode("utf-8", "replace")
    m = re.search(r"SHA256\s+32\s+([0-9a-fA-F]{64})", txt)
    return m.group(1).lower() if m else None


# ---- FSL Homes ---------------------------------------------------------------------------

_FSL_RE = re.compile(r'href="(fslhomes-(user\d+)-(\d{4}-\d{2}-\d{2})\.tar\.bz2)"')


def fsl_listing() -> list[tuple[str, str, str]]:
    with _open(FSL) as r:
        html = r.read().decode("utf-8", "replace")
    return sorted(set(_FSL_RE.findall(html)), key=lambda x: (x[2], x[1]))


def plan_contiguous_block(files: list[tuple[str, str, str]], sizes: dict[str, int],
                          room: int) -> tuple[list[str], dict]:  # fmt: skip
    """Days in date order from the first date on which the largest number of users is present;
    each day takes every user present that day; stop before the first day that does not fit.
    Returns (file names, summary)."""
    by_day: dict[str, list[str]] = {}
    for name, _user, day in files:
        by_day.setdefault(day, []).append(name)
    days = sorted(by_day)
    most = max(len(v) for v in by_day.values())
    start = next(d for d in days if len(by_day[d]) == most)
    chosen, total, last = [], 0, None
    for d in days[days.index(start) :]:
        cost = sum(sizes[f] for f in by_day[d])
        if total + cost > room:
            break
        chosen += by_day[d]
        total += cost
        last = d
    users = sorted({u for n, u, d in files if n in set(chosen)})
    return chosen, {"first_day": start, "last_day": last, "days": len({d for n, u, d in files
                    if n in set(chosen)}), "users": users, "bytes": total,
                    "days_available": len(days), "first_day_available": days[0],
                    "last_day_available": days[-1]}  # fmt: skip


def run(root: str = "data", log=print) -> dict:
    budget = Budget(Path(root).resolve())
    budget.root.mkdir(parents=True, exist_ok=True)
    manifest_path = budget.root / "MANIFEST.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}

    def save():
        manifest_path.write_text(json.dumps(manifest, indent=1))

    try:
        # 1. NapierOne encrypted, 100 per family
        log("NapierOne encrypted (tiny, 30 families)")
        keys = s3_keys("NapierOne/Data/EXTRA/")
        fams = sorted(k for k in keys if k.endswith("-tiny.zip")
                      and not k.split("/")[-1].startswith("RANSOMWARE-"))  # fmt: skip
        enc = manifest.setdefault("napierone_encrypted_tiny", {})
        for k in fams:
            name = k.split("/")[-1]
            fam = name[: -len("-tiny.zip")]
            dest = budget.root / "napierone" / "encrypted_zips" / name
            enc[fam] = download(f"{S3}/{k}", dest, budget, log, keys[k])
            hk = k.replace(".zip", "_zip_hashes.txt")
            if hk in keys:
                hp = dest.with_name(hk.split("/")[-1])
                download(f"{S3}/{hk}", hp, budget, log, keys[hk])
                enc[fam]["published_sha256"] = napierone_published_sha256(hp.read_bytes())
                enc[fam]["published_hash_match"] = (
                    enc[fam]["published_sha256"] == enc[fam]["sha256"]
                )
            enc[fam]["extract"] = extract(dest, budget.root / "napierone" / "encrypted" / fam,
                                          budget, log)  # fmt: skip
            save()
        # 2. NapierOne benign, 100 per type
        log("NapierOne benign (NapierOne-tiny.zip)")
        k = "NapierOne/Data/NapierOne-tiny.zip"
        size = s3_keys(k)[k]
        dest = budget.root / "napierone" / "benign_zip" / "NapierOne-tiny.zip"
        ben = download(f"{S3}/{k}", dest, budget, log, size)
        ben["extract"] = extract(dest, budget.root / "napierone" / "benign", budget, log,
                                 skip_types=SKIP_TYPES)  # fmt: skip
        manifest["napierone_benign_tiny"] = ben
        save()
        # 3. FSL Homes 2011-8kb-only, compressed, contiguous block of days
        log("FSL Homes 2011-8kb-only: listing and sizes")
        files = fsl_listing()
        sizes = manifest.get("fsl_sizes") or {}
        missing = [n for n, _, _ in files if n not in sizes]
        with ThreadPoolExecutor(FSL_CONNECTIONS) as ex:
            sizes.update(
                zip(missing, ex.map(lambda n: content_length(FSL + n), missing), strict=True)
            )
        manifest["fsl_sizes"] = sizes
        if "fsl_plan" in manifest:  # resume: the block fixed on the first run stays the block
            summary = manifest["fsl_plan"]
            chosen = [n for n, _, d in files if summary["first_day"] <= d <= summary["last_day"]]
        else:
            room = min(budget.cap_bytes - budget.used(), budget.free() - budget.reserve_bytes)
            chosen, summary = plan_contiguous_block(files, sizes, room)
            summary["listing_files"] = len(files)
            summary["listing_bytes"] = sum(sizes.values())
            manifest["fsl_plan"] = summary
        save()
        log(f"  plan: {summary}")
        got = manifest.setdefault("fsl_homes_2011_8kb", {})
        lock = threading.Lock()

        def one(n):
            rec = download(FSL + n, budget.root / "fslhomes" / "2011-8kb-only" / n, budget, log,
                           sizes[n])  # fmt: skip
            with _open(FSL + n + ".sha256") as r:
                published = r.read().decode("ascii", "replace").split()[0].lower()
            rec["published_hash_match"] = published == rec["sha256"]
            with lock:
                got[n] = rec
                save()
            if not rec["published_hash_match"]:
                # set aside (never deleted) so the next attempt downloads it again from 0
                bad = Path(rec["file"])
                bad.replace(bad.with_name(bad.name + ".corrupt"))
                raise OSError(f"{n}: SHA-256 does not match the published .sha256; "
                              "moved to .corrupt")  # fmt: skip

        todo = [n for n in chosen if not got.get(n, {}).get("published_hash_match")]
        with ThreadPoolExecutor(FSL_CONNECTIONS) as ex:  # the server limits each connection
            for fut in [ex.submit(one, n) for n in todo]:
                fut.result()
        log("DONE")
    except StopFetch as e:
        manifest["stopped"] = str(e)
        save()
        log(f"STOP: {e}")
    return manifest


if __name__ == "__main__":
    run()
