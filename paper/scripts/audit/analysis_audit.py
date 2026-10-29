"""File access audit for paper/scripts/test_analysis.py (OPEN_QUESTIONS 2026-10-29, a51b5f1).

A sys.addaudithook hook logs every file open (with read / write), listdir / scandir, mkdir,
remove, rename, link and copy under the repo (not .venv, not __pycache__) while rules are set,
one line per access to <log>.<pid>. The rules come from start() in the wrapper process and from
the SLOWBURN_AUDIT environment variable in worker processes (sitecustomize.py in this folder,
on PYTHONPATH). A forbidden access is logged as DENY and raises PermissionError.
"""

import json
import os

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")).replace("\\", "/")
ENV = "SLOWBURN_AUDIT"
ALLOW = frozenset(
    {  # DEV calibration, read in both modes (a63fc54)
        "results/dev_d74_alarm_calib/threshold.json",
        "results/dev_d74_alarm_calib/daily_counts_napierone_bytes.csv.gz",
        "results/dev_d74_alarm_calib/daily_counts_synthetic_bytes.csv.gz",
    }
)
WRITE_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_APPEND | os.O_CREAT | os.O_TRUNC
_state = {"rules": None, "log": None, "installed": False}


def rel(path) -> str | None:
    """Repo-relative posix path, or None outside the repo / in .venv / __pycache__."""
    if path is None or isinstance(path, int):
        return None
    try:
        p = os.path.abspath(os.fsdecode(path)).replace("\\", "/")
    except (TypeError, ValueError):
        return None
    if not p.lower().startswith(ROOT.lower() + "/"):
        return None
    r = p[len(ROOT) + 1 :]
    if r.startswith(".venv/") or "__pycache__" in r:
        return None
    return r


def _under(r: str, folder: str) -> bool:
    return r == folder or r.startswith(folder + "/")


def verdict(r: str, kind: str, rules: dict) -> str | None:
    """None if allowed, else the reason. kind is read or write."""
    mode = rules["mode"]
    if kind == "read":
        if r in ALLOW:
            return None
        if mode == "test" and r.startswith("results/dev_"):
            return "results/dev_* read in mode test"
        if mode == "dev" and r.startswith("results/test_"):
            return "results/test_* read in mode dev"
        if (
            mode == "dev"
            and r.startswith("results/dev_")
            and not any(_under(r, f) for f in rules["runs"])
        ):
            return "results/dev_* read outside this script's DEV run folders"
        return None
    if r.startswith("results/") and not _under(r, f"results/analysis_{mode}"):
        return f"write under results/ outside results/analysis_{mode}"
    return None


def _accesses(event: str, args: tuple) -> list:
    if event == "open":
        path, mode, flags = args
        if mode is not None:
            write = any(c in str(mode) for c in "wax+")
        else:
            write = bool(flags & WRITE_FLAGS)
        return [(path, "write" if write else "read")]
    if event in ("os.listdir", "os.scandir"):
        return [(args[0] if args and args[0] is not None else ".", "read")]
    if event in ("os.mkdir", "os.remove", "os.rmdir", "shutil.rmtree"):
        return [(args[0], "write")]
    if event in ("os.rename", "os.replace"):
        return [(args[0], "write"), (args[1], "write")]
    if event in ("os.link", "shutil.copyfile"):
        return [(args[0], "read"), (args[1], "write")]
    return []


def _hook(event: str, args: tuple) -> None:
    rules, log = _state["rules"], _state["log"]
    if rules is None or log is None:
        return
    for path, kind in _accesses(event, args):
        r = rel(path)
        if r is None:
            continue
        why = verdict(r, kind, rules)
        log.write(f"{os.getpid()}\t{kind}\t{event}\t{r}\t{'DENY: ' + why if why else 'ok'}\n")
        log.flush()
        if why:
            raise PermissionError(f"audit: {why}: {r}")


def start(rules: dict) -> None:
    """Set the rules for this process and the workers it starts (environment)."""
    stop()
    os.environ[ENV] = json.dumps(rules)
    _state["log"] = open(f"{rules['log']}.{os.getpid()}", "a", encoding="utf-8")  # noqa: SIM115
    _state["rules"] = rules
    if not _state["installed"]:
        import sys

        sys.addaudithook(_hook)
        _state["installed"] = True


def stop() -> None:
    _state["rules"] = None
    if _state["log"] is not None:
        _state["log"].close()
        _state["log"] = None
    os.environ.pop(ENV, None)


def peak_mb() -> float:
    """Peak working set of this process (Windows GetProcessMemoryInfo), MB."""
    import ctypes
    from ctypes import wintypes

    class PMC(ctypes.Structure):
        _fields_ = [
            ("cb", wintypes.DWORD),
            ("PageFaultCount", wintypes.DWORD),
            *[
                (n, ctypes.c_size_t)
                for n in (
                    "PeakWorkingSetSize",
                    "WorkingSetSize",
                    "QuotaPeakPagedPoolUsage",
                    "QuotaPagedPoolUsage",
                    "QuotaPeakNonPagedPoolUsage",
                    "QuotaNonPagedPoolUsage",
                    "PagefileUsage",
                    "PeakPagefileUsage",
                )
            ],
        ]

    c = PMC()
    c.cb = ctypes.sizeof(c)
    k32, psapi = ctypes.windll.kernel32, ctypes.windll.psapi
    k32.GetCurrentProcess.restype = wintypes.HANDLE
    psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(PMC), wintypes.DWORD]
    psapi.GetProcessMemoryInfo(k32.GetCurrentProcess(), ctypes.byref(c), c.cb)
    return c.PeakWorkingSetSize / 2**20


def _log_peak() -> None:
    if _state["log"] is not None:
        _state["log"].write(f"{os.getpid()}\tpeak\t-\t-\t{peak_mb():.0f} MB\n")
        _state["log"].flush()


def from_env() -> None:
    """Worker processes: start with the rules the wrapper put in the environment; log the
    process peak working set at exit."""
    s = os.environ.get(ENV)
    if s:
        import atexit

        start(json.loads(s))
        atexit.register(_log_peak)
