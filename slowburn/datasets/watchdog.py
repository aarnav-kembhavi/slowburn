"""Download watchdog (D61): run the fetcher, check progress every ``check_s`` seconds and restart
it when for ``stall_s`` seconds neither the data root grew nor the fetcher logged anything
(re-hashing files already on disk writes no data, only log lines), or when it exits without
finishing. Downloads resume from their partial files with HTTP range requests (fetch.py).
One instance at a time (a lock file); once the fetcher has finished, later starts exit at once,
so the scheduled task (D61) can relaunch the watchdog freely. Every start, check and restart
is logged with a timestamp.

The fetcher ends its log with ``DONE`` (finished) or ``STOP: ...`` (cap or free-space reserve
reached); either ends the watchdog, as does reaching ``max_restarts``.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

FETCH_CMD = (sys.executable, "-u", "-m", "slowburn.datasets.fetch")


def tree_bytes(root: Path) -> int:
    """Bytes in every file under ``root``, partial downloads included."""
    total = 0
    for p in root.rglob("*"):
        try:
            if p.is_file():
                total += p.stat().st_size
        except OSError:  # a .part renamed between listing and stat
            pass
    return total


def _progress(root: Path, fetch_log: Path) -> int:
    """Bytes under the data root plus the fetch log's size: grows while anything happens."""
    return tree_bytes(root) + (fetch_log.stat().st_size if fetch_log.exists() else 0)


def _lock(path: Path):
    """Exclusive lock held for the life of the process (released by the OS if it dies)."""
    fh = path.open("a+")
    try:
        if os.name == "nt":
            import msvcrt

            fh.seek(0)
            msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        fh.close()
        return None
    return fh


def _finished(fetch_log: Path) -> str | None:
    lines = [s.strip() for s in fetch_log.read_text(errors="replace").splitlines() if s.strip()]
    last = lines[-1] if lines else ""
    return last if last == "DONE" or last.startswith("STOP:") else None


def run(root: str = "data", fetch_log: str = "results/fetch_run3.log",
        log_path: str = "results/fetch_watchdog.log", check_s: float = 600,
        stall_s: float = 1800, max_restarts: int = 50, cmd=FETCH_CMD) -> int:  # fmt: skip
    """Returns the number of restarts (-1: another instance runs, or the fetch already ended)."""
    root_p, flog, wlog = Path(root), Path(fetch_log), Path(log_path)
    done_marker = wlog.with_suffix(".done")
    if done_marker.exists():
        return -1
    lock = _lock(wlog.with_suffix(".lock"))
    if lock is None:
        return -1

    def log(msg: str) -> None:
        with wlog.open("a") as fh:
            fh.write(f"{datetime.now().isoformat(timespec='seconds')} {msg}\n")

    def start() -> subprocess.Popen:
        with flog.open("a") as fh:
            fh.write(f"--- fetcher started by watchdog {datetime.now().isoformat()}\n")
        with flog.open("a") as fh:  # the child keeps its own copy of the handle
            return subprocess.Popen(cmd, stdout=fh, stderr=subprocess.STDOUT)

    restarts = 0
    proc = start()
    last_b, last_t = _progress(root_p, flog), time.monotonic()
    log(f"start pid {proc.pid}, {last_b} bytes under {root_p}")
    while True:
        time.sleep(check_s)
        b, now = _progress(root_p, flog), time.monotonic()
        code = proc.poll()
        if b > last_b:
            last_b, last_t = b, now
        log(f"check: {b} bytes, {'running' if code is None else f'exited {code}'}")
        reason = None
        if code is not None:
            done = _finished(flog)
            if done:
                log(f"fetcher finished: {done}")
                done_marker.write_text(f"{done}\n")
                return restarts
            reason = f"fetcher exited with code {code} before finishing"
        elif now - last_t >= stall_s:
            reason = f"no bytes written and no log output for {now - last_t:.0f} s"
            proc.kill()
            proc.wait()
        if reason:
            if restarts >= max_restarts:
                log(f"giving up after {restarts} restarts: {reason}")
                return restarts
            restarts += 1
            proc = start()
            last_t = time.monotonic()
            log(f"RESTART {restarts}: {reason}; new pid {proc.pid}")


if __name__ == "__main__":
    run()
