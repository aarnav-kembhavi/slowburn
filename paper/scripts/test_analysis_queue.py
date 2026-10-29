"""Runs paper/scripts/test_analysis.py one script per process, one at a time, DEV mode then TEST
mode (OPEN_QUESTIONS amendment fe42e5f). Before each script free RAM >= 16 GB, else poll every
5 minutes. A script process that is killed or crashes (exit code other than 0 / 1) has its
partial output deleted unread and is rerun (analysis only, up to 3 attempts); exit 1 (hash
mismatch, audit DENY, error inside main) stops the queue for a wrapper fix. Scripts with a done
file are skipped, so the queue resumes. Log: results/test_analysis_runs.log.

    uv run python -u paper/scripts/test_analysis_queue.py
    uv run python -u paper/scripts/test_analysis_queue.py --remaining   # amendment 2 (bc38c2c)
"""

import ctypes
import gzip
import io
import json
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import pandas as pd

ORDER = ("d72_c2r_holm", "d72_report", "d79_report", "d71_report", "d73_report", "d74_report",
         "d74_alarm_holdout")  # fmt: skip
LOG = Path("results/test_analysis_runs.log")
RAM_GB, POLL_S, ATTEMPTS = 16, 300, 3
GATE_22 = 22  # amendment 2: DEV d74_report peak 17.6 GB + 4 GB


def free_ram_gb() -> float:
    class MS(ctypes.Structure):
        _fields_ = [
            ("dwLength", ctypes.c_ulong),
            ("dwMemoryLoad", ctypes.c_ulong),
            *[
                (n, ctypes.c_ulonglong)
                for n in (
                    "ullTotalPhys",
                    "ullAvailPhys",
                    "ullTotalPageFile",
                    "ullAvailPageFile",
                    "ullTotalVirtual",
                    "ullAvailVirtual",
                    "ullAvailExtendedVirtual",
                )
            ],
        ]

    m = MS()
    m.dwLength = ctypes.sizeof(m)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
    return m.ullAvailPhys / 2**30


def log(msg: str) -> None:
    line = f"{datetime.now().astimezone().isoformat(timespec='seconds')} {msg}"
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")
    print(line, flush=True)


def key(name: str) -> str:
    return name.replace(":", "_")


def partial(mode: str, name: str) -> list[Path]:
    out = Path(f"results/analysis_{mode}")
    base, *arm_sub = name.split(":")
    folder = out / f"d74_report_{arm_sub[1]}" / arm_sub[0] if arm_sub else out / base
    k = key(name)
    return [folder, out / f"{k}.txt", out / f"hashes_{k}.txt", *out.glob("audit.log.*")]


def worker_peaks(mode: str, name: str) -> list[str]:
    """Peak lines of worker processes in this script's section of audit.log."""
    lines = Path(f"results/analysis_{mode}/audit.log").read_text(encoding="utf-8").splitlines()
    start = max(i for i, x in enumerate(lines) if x.startswith(f"== {name}:"))
    sec = []
    for x in lines[start + 1 :]:
        if x.startswith("== "):
            break
        if "\tpeak\t" in x:
            sec.append(f"pid {x.split(chr(9))[0]} {x.split(chr(9))[-1]}")
    return sec


def run(mode: str, name: str, gate: float = RAM_GB) -> bool:
    done = Path(f"results/analysis_{mode}/done_{key(name)}.json")
    if done.exists():
        log(f"analysis {mode} {name}: already done, skipped")
        return True
    for attempt in range(1, ATTEMPTS + 1):
        while (ram := free_ram_gb()) < gate:
            log(f"analysis {mode} {name}: free RAM {ram:.1f} GB < {gate}, waiting {POLL_S} s")
            time.sleep(POLL_S)
        log(f"START analysis {mode} {name} attempt {attempt} (free RAM {ram:.1f} GB)")
        Path(f"results/analysis_{mode}").mkdir(parents=True, exist_ok=True)
        con = Path(f"results/analysis_{mode}/console_{key(name)}_{attempt}.log")
        with con.open("w", encoding="utf-8") as fh:
            cmd = [sys.executable, "-u", "paper/scripts/test_analysis.py", mode, name]
            rc = subprocess.run(cmd, stdout=fh, stderr=subprocess.STDOUT).returncode
        if rc == 0:
            peak = json.loads(done.read_text())["peak_mb"]
            w = worker_peaks(mode, key(name))
            log(f"END analysis {mode} {name} exit 0, peak working set {peak} MB"
                + (f"; workers: {', '.join(w)}" if w else ""))  # fmt: skip
            return True
        if rc == 1:
            log(f"END analysis {mode} {name} exit 1 (abort: hash, audit or error in main); "
                f"queue stopped, see {con}")  # fmt: skip
            return False
        gone = [str(p) for p in partial(mode, name) if p.exists()]
        for p in partial(mode, name):
            if p.is_dir():
                shutil.rmtree(p)
            elif p.exists():
                p.unlink()
        log(f"END analysis {mode} {name} exit {rc} (killed or crashed); partial output deleted "
            f"unread: {', '.join(gone) or 'none'}")  # fmt: skip
    log(f"analysis {mode} {name}: {ATTEMPTS} attempts failed; queue stopped")
    return False


ARMS = ("napierone_bytes", "synthetic_bytes")  # NapierOne first, as d74_report's ordered()
FALLBACK_AFTER_S = 1800


def merged(per: Path, f: str) -> bytes:
    """One d74_report output file of the per-arm runs, rows concatenated NapierOne first;
    false_alarms.csv comes from the DEV calibration for both arms in every call."""
    parts = [per / ARMS[0] / f] if f == "false_alarms.csv" else [per / a / f for a in ARMS]
    texts = [gzip.decompress(p.read_bytes()) if f.endswith(".gz") else p.read_bytes()
             for p in parts]  # fmt: skip
    return texts[0] + b"".join(t.split(b"\n", 1)[1] for t in texts[1:])


def compare(per: Path, combined: Path) -> tuple[bool, list[str]]:
    """Amendment 2: byte identical (.gz after decompression), else identical after sorting rows."""
    ok, rows = True, []
    for c in sorted(p for p in combined.iterdir() if p.is_file()):
        f = c.name
        try:
            m = merged(per, f)
        except FileNotFoundError as e:
            ok, rows = False, [*rows, f"{f}: DIFFERENT (missing {e.filename})"]
            continue
        ref = gzip.decompress(c.read_bytes()) if f.endswith(".gz") else c.read_bytes()
        if m == ref:
            rows.append(f"{f}: byte identical")
            continue
        a, b = (pd.read_csv(io.BytesIO(x), low_memory=False) for x in (m, ref))
        same = list(a.columns) == list(b.columns) and a.sort_values(list(a.columns)).reset_index(
            drop=True).equals(b.sort_values(list(b.columns)).reset_index(drop=True))  # fmt: skip
        ok &= same
        rows.append(f"{f}: {'identical after sorting rows' if same else 'DIFFERENT'}")
    return ok, rows


def remaining() -> int:
    """Amendment 2 (bc38c2c): TEST d74_report at a 22 GB gate, else after 30 minutes below it
    the per-arm fallback (validated on DEV first); then the TEST ALARM copy at 22 GB."""
    git = ["git", "rev-parse", "--short", "HEAD"]
    head = subprocess.run(git, capture_output=True, text=True).stdout.strip()
    log(f"ANALYSIS REMAINING start (amendment 2), commit {head}")
    t0, done = time.monotonic(), Path("results/analysis_test/done_d74_report.json")
    while not done.exists():
        if (ram := free_ram_gb()) >= GATE_22:
            if not run("test", "d74_report", GATE_22):
                return 1
            break
        if time.monotonic() - t0 >= FALLBACK_AFTER_S:
            log(f"free RAM {ram:.1f} GB < {GATE_22} for 30 minutes: per-arm fallback")
            if not fallback():
                return 1
            break
        log(f"analysis test d74_report: free RAM {ram:.1f} GB < {GATE_22}, waiting {POLL_S} s")
        time.sleep(POLL_S)
    if not run("test", "d74_alarm_holdout", GATE_22):
        return 1
    log("ANALYSIS QUEUE DONE: dev and test, all scripts")
    return 0


def fallback() -> bool:
    for arm in ARMS:
        if not run("dev", f"d74_report:{arm}:per_arm_check"):
            return False
    ok, rows = compare(Path("results/analysis_dev/d74_report_per_arm_check"),
                       Path("results/analysis_dev/d74_report"))  # fmt: skip
    log("per-arm DEV check vs combined DEV d74_report: " + "; ".join(rows))
    if not ok:
        log("per-arm mode NOT identical on DEV: not used on TEST; stopped, report to Aarnav")
        return False
    for arm in ARMS:
        if not run("test", f"d74_report:{arm}:per_arm"):
            return False
    per, out = (
        Path("results/analysis_test/d74_report_per_arm"),
        Path("results/analysis_test/d74_report"),
    )
    out.mkdir(parents=True, exist_ok=True)
    for c in sorted(p for p in Path("results/analysis_dev/d74_report").iterdir() if p.is_file()):
        m = merged(per, c.name)
        (out / c.name).write_bytes(gzip.compress(m, mtime=0) if c.name.endswith(".gz") else m)
    Path("results/analysis_test/done_d74_report.json").write_text(json.dumps(
        {"mode": "test", "script": "d74_report", "per_arm": True, "merged_from": str(per)},
        indent=1))  # fmt: skip
    log(f"TEST d74_report per arm merged into {out}")
    return True


def main() -> int:
    if sys.argv[1:] == ["--remaining"]:
        return remaining()
    git = ["git", "rev-parse", "--short", "HEAD"]
    head = subprocess.run(git, capture_output=True, text=True).stdout.strip()
    log(f"ANALYSIS QUEUE start, commit {head}")
    for mode in ("dev", "test"):
        for name in ORDER:
            if not run(mode, name):
                return 1
    log("ANALYSIS QUEUE DONE: dev and test, all scripts")
    return 0


if __name__ == "__main__":
    sys.exit(main())
