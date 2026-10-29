"""TEST analysis by path override (OPEN_QUESTIONS 2026-10-29, registered in a51b5f1).

Imports each analysis script listed in configs/frozen_v2.yaml unchanged, replaces only its path
constants with the run folders of one mode (dev_* or test_*), and calls its main() once under
the file access audit (paper/scripts/audit). Before any analysis: SHA-256 of every analysis
script (and d74_alarm_calib, which d74_alarm_holdout imports) against 51fe9db, and no change
under slowburn/ since 51fe9db; any mismatch aborts. Outputs and audit.log go to
results/analysis_<mode>/. One script per process (amendment fe42e5f); run from the repo root
after QUEUE DONE through paper/scripts/test_analysis_queue.py, or for one script:

    uv run python -u paper/scripts/test_analysis.py dev d72_c2r_holm
"""

import contextlib
import hashlib
import importlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "audit"))
import analysis_audit as audit  # noqa: E402

BASE = "51fe9db"
FROZEN_V2 = Path("configs/frozen_v2.yaml")
QUEUE_LOG = Path("results/test_queue.log")
DEPS = ("paper/scripts/d74_alarm_calib.py",)
ALARM_CFGS = ("configs/dev_d74_attack_napierone.yaml", "configs/dev_d74_attack_synthetic.yaml")


def analysis_scripts() -> list[str]:
    items = yaml.safe_load(FROZEN_V2.read_text(encoding="utf-8"))["items"]
    return list(dict.fromkeys(it["analysis"] for it in items if "analysis" in it))


def hash_check(scripts: list[str], out: Path, name: str) -> bool:
    rows, ok = [], True
    for p in [*scripts, *DEPS]:
        cur = hashlib.sha256(Path(p).read_bytes()).hexdigest()
        blob = subprocess.run(["git", "show", f"{BASE}:{p}"], capture_output=True, check=True)
        ref = hashlib.sha256(blob.stdout).hexdigest()
        ok &= cur == ref
        rows.append(f"{p}\t{cur}\t{ref}\t{'match' if cur == ref else 'MISMATCH'}")
    lib = subprocess.run(["git", "diff", "--name-only", BASE, "--", "slowburn"],
                         capture_output=True, text=True, check=True).stdout.split()  # fmt: skip
    ok &= not lib
    rows.append(f"git diff {BASE} -- slowburn: {'empty' if not lib else ' '.join(lib)}")
    (out / f"hashes_{name}.txt").write_text("path\tsha256 now\tsha256 at " + BASE + "\tresult\n"
                                    + "\n".join(rows) + "\n")  # fmt: skip
    print("\n".join(rows))
    return ok


def plan(mode: str) -> dict:
    """script -> (constants to replace, DEV run folders it may read in mode dev, call)."""
    f = lambda name: f"results/{mode}_{name}"  # noqa: E731
    o = lambda s: Path(f"results/analysis_{mode}/{s}")  # noqa: E731
    d72 = {"napierone_bytes": f("d72_bytes_napierone_v2pool"),
           "synthetic_bytes": f("d72_bytes_synthetic")}  # fmt: skip
    d74 = {"synthetic_bytes": f("d74_attack_synthetic"),
           "napierone_bytes": f("d74_attack_napierone")}  # fmt: skip
    d73 = {"synthetic_bytes": f("d73_fleet_synthetic"),
           "napierone_bytes": f("d73_fleet_napierone_v2pool")}  # fmt: skip
    d79 = {"napierone_bytes": (f("d79_eqh_napierone"), d72["napierone_bytes"]),
           "synthetic_bytes": (f("d79_eqh_synthetic"), d72["synthetic_bytes"])}  # fmt: skip
    return {
        "d72_c2r_holm": ({"OUT": o("d72_c2r_holm"), "ARMS": d72}, list(d72.values()),
                         lambda m: m.main()),
        "d72_report": ({"OUT": o("d72_report"),
                        "UNITS": {"bytes_synthetic": (d72["synthetic_bytes"], None),
                                  "bytes_napierone_v2pool": (d72["napierone_bytes"], None)}},
                       list(d72.values()), lambda m: m.main()),
        "d79_report": ({"OUT": o("d79_report"), "ARMS": d79},
                       [p for pair in d79.values() for p in pair], lambda m: m.main()),
        "d74_report": ({"OUT": o("d74_report"), "ARMS": d74}, list(d74.values()),
                       lambda m: m.main(d74, o("d74_report"))),
        "d74_alarm_holdout": ({}, [], lambda m: alarm(m, mode, o("d74_alarm_holdout"))),
        "d73_report": ({"OUT": o("d73_report"), "ARMS": d73}, list(d73.values()),
                       lambda m: m.main()),
        "d71_report": ({"R": o("d71_report")}, [f("d71_oracle_gap")],
                       lambda m: d71(m, f("d71_oracle_gap"), o("d71_report"))),
    }  # fmt: skip


def alarm(m, mode: str, out: Path) -> None:
    """mode test: the queue's ALARM output is copied, not rerun; mode dev: main() on the DEV
    configs (family d74_alarm_holdout)."""
    out.mkdir(parents=True, exist_ok=True)
    if mode == "test":
        shutil.copyfile("results/test_d74_alarm/holdout.json", out / "holdout.json")
        print((out / "holdout.json").read_text())
    else:
        m.main([f"--out={out}", *ALARM_CFGS])


def d71(m, run: str, r: Path) -> None:
    """d71_report writes its CSVs into R: R is the analysis folder with a hard link to the run's
    tuning_sweep.csv, removed afterwards; the run folder is not written."""
    r.mkdir(parents=True, exist_ok=True)
    link = r / "tuning_sweep.csv"
    os.link(Path(run) / "tuning_sweep.csv", link)
    print(f"tuning_sweep.csv: hard link to {run}/tuning_sweep.csv")
    try:
        m.main()
    finally:
        os.remove(link)


def merge_parts(log: Path, name: str) -> list[str]:
    lines = []
    for part in sorted(log.parent.glob(log.name + ".*")):
        lines += part.read_text(encoding="utf-8").splitlines()
        part.unlink()
    with log.open("a", encoding="utf-8") as fh:
        fh.write(f"== {name}: {len(lines)} accesses\n")
        fh.writelines(line + "\n" for line in lines)
    return [x for x in lines if "\tDENY: " in x]


def main(mode: str, name: str) -> int:
    """One script in this process (amendment fe42e5f); test_analysis_queue.py runs them in
    order, one process each. Exit 0 ok, 1 abort (hash mismatch, audit DENY, error in main)."""
    if mode not in ("dev", "test"):
        raise SystemExit("mode: dev or test")
    if "QUEUE DONE" not in QUEUE_LOG.read_text().strip().splitlines()[-1]:
        raise SystemExit("the TEST queue has not finished (no QUEUE DONE)")
    scripts = {Path(p).stem: p for p in analysis_scripts()}
    if name not in scripts:
        raise SystemExit(f"script: one of {', '.join(scripts)}")
    out = Path(f"results/analysis_{mode}")
    if mode == "test" and not Path(f"results/analysis_dev/done_{name}.json").exists():
        raise SystemExit(f"run {name} in mode dev first")
    if (out / f"done_{name}.json").exists():
        raise SystemExit(f"{name} already done in mode {mode}; each script runs once per mode")
    out.mkdir(parents=True, exist_ok=True)
    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True,
                          text=True, check=True).stdout.strip()  # fmt: skip
    print(f"mode {mode}, script {name}, commit {head}")
    if not hash_check(list(scripts.values()), out, name):
        print("ABORT: analysis script hash or library mismatch vs " + BASE)
        return 1
    os.environ["PYTHONPATH"] = os.pathsep.join(
        [str(HERE / "audit"), str(HERE), *filter(None, [os.environ.get("PYTHONPATH")])]
    )
    log = out / "audit.log"
    consts, runs, call = plan(mode)[name]
    m = importlib.import_module(name)
    for k, v in consts.items():
        setattr(m, k, v)
        if k == "OUT":  # d72_c2r_holm writes into OUT without creating it
            v.mkdir(parents=True, exist_ok=True)
    print(f"== {name}: {', '.join(f'{k}={v}' for k, v in consts.items()) or 'no override'}",
          flush=True)  # fmt: skip
    err = None
    with (out / f"{name}.txt").open("w", encoding="utf-8") as fh:
        audit.start({"mode": mode, "runs": runs, "log": str(log.resolve())})
        try:
            with contextlib.redirect_stdout(fh):
                call(m)
        except Exception as e:  # noqa: BLE001
            err = repr(e)
        finally:
            audit.stop()
    peak = audit.peak_mb()
    denied = merge_parts(log, name)
    if err or denied:
        print(f"ABORT in {name}: {err or ''} {denied[:5]}")
        return 1
    (out / f"done_{name}.json").write_text(json.dumps(
        {"mode": mode, "script": name, "commit": head, "peak_mb": round(peak),
         "constants": {k: str(v) for k, v in consts.items()}, "dev_runs": runs},
        indent=1))  # fmt: skip
    print(f"   ok ({name}.txt), peak working set {peak:.0f} MB", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(*(sys.argv[1:3] + ["", ""])[:2]))
