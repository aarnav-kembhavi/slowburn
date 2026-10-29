"""Runs paper/scripts/test_analysis.py one script per process, one at a time, DEV mode then TEST
mode (OPEN_QUESTIONS amendment fe42e5f). Before each script free RAM >= 16 GB, else poll every
5 minutes. A script process that is killed or crashes (exit code other than 0 / 1) has its
partial output deleted unread and is rerun (analysis only, up to 3 attempts); exit 1 (hash
mismatch, audit DENY, error inside main) stops the queue for a wrapper fix. Scripts with a done
file are skipped, so the queue resumes. Log: results/test_analysis_runs.log.

    uv run python -u paper/scripts/test_analysis_queue.py
"""

import ctypes
import json
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ORDER = ("d72_c2r_holm", "d72_report", "d79_report", "d71_report", "d73_report", "d74_report",
         "d74_alarm_holdout")  # fmt: skip
LOG = Path("results/test_analysis_runs.log")
RAM_GB, POLL_S, ATTEMPTS = 16, 300, 3


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


def partial(mode: str, name: str) -> list[Path]:
    out = Path(f"results/analysis_{mode}")
    return [out / name, out / f"{name}.txt", out / f"hashes_{name}.txt",
            *out.glob("audit.log.*")]  # fmt: skip


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


def run(mode: str, name: str) -> bool:
    done = Path(f"results/analysis_{mode}/done_{name}.json")
    if done.exists():
        log(f"analysis {mode} {name}: already done, skipped")
        return True
    for attempt in range(1, ATTEMPTS + 1):
        while (ram := free_ram_gb()) < RAM_GB:
            log(f"analysis {mode} {name}: free RAM {ram:.1f} GB < {RAM_GB}, waiting {POLL_S} s")
            time.sleep(POLL_S)
        log(f"START analysis {mode} {name} attempt {attempt} (free RAM {ram:.1f} GB)")
        Path(f"results/analysis_{mode}").mkdir(parents=True, exist_ok=True)
        con = Path(f"results/analysis_{mode}/console_{name}_{attempt}.log")
        with con.open("w", encoding="utf-8") as fh:
            cmd = [sys.executable, "-u", "paper/scripts/test_analysis.py", mode, name]
            rc = subprocess.run(cmd, stdout=fh, stderr=subprocess.STDOUT).returncode
        if rc == 0:
            peak = json.loads(done.read_text())["peak_mb"]
            w = worker_peaks(mode, name)
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


def main() -> int:
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
