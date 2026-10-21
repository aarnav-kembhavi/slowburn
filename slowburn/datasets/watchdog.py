"""Download watchdog (D61): run the fetcher, check progress every ``check_s`` seconds and restart
it when no bytes were written under the data root for ``stall_s`` seconds, or when it exits
without finishing. Every start, check and restart is logged with a timestamp.

The fetcher ends its log with ``DONE`` (finished) or ``STOP: ...`` (cap or free-space reserve
reached); either ends the watchdog, as does reaching ``max_restarts``.
"""

from __future__ import annotations

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


def _finished(fetch_log: Path) -> str | None:
    lines = [s.strip() for s in fetch_log.read_text(errors="replace").splitlines() if s.strip()]
    last = lines[-1] if lines else ""
    return last if last == "DONE" or last.startswith("STOP:") else None


def run(root: str = "data", fetch_log: str = "results/fetch_run3.log",
        log_path: str = "results/fetch_watchdog.log", check_s: float = 600,
        stall_s: float = 1800, max_restarts: int = 50, cmd=FETCH_CMD) -> int:  # fmt: skip
    """Returns the number of restarts."""
    root_p, flog, wlog = Path(root), Path(fetch_log), Path(log_path)

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
    last_b, last_t = tree_bytes(root_p), time.monotonic()
    log(f"start pid {proc.pid}, {last_b} bytes under {root_p}")
    while True:
        time.sleep(check_s)
        b, now = tree_bytes(root_p), time.monotonic()
        code = proc.poll()
        if b > last_b:
            last_b, last_t = b, now
        log(f"check: {b} bytes, {'running' if code is None else f'exited {code}'}")
        reason = None
        if code is not None:
            done = _finished(flog)
            if done:
                log(f"fetcher finished: {done}")
                return restarts
            reason = f"fetcher exited with code {code} before finishing"
        elif now - last_t >= stall_s:
            reason = f"no bytes written for {now - last_t:.0f} s"
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
