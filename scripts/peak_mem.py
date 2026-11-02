"""Run a command and record the peak memory of its whole process tree (D81 memory gate).

Samples every second: the summed working set of the process and all its descendants (the tree's
peak) and the sum of each process's own peak working set (an upper bound). Writes both, in MiB,
to the JSON file given first. Usage:

    uv run --with psutil python scripts/peak_mem.py OUT.json -- CMD ARGS...
"""

import json
import subprocess
import sys
import time

import psutil


def main() -> None:
    out, cmd = sys.argv[1], sys.argv[sys.argv.index("--") + 1:]
    t0 = time.time()
    proc = subprocess.Popen(cmd)
    root = psutil.Process(proc.pid)
    tree_peak, own_peaks = 0, {}
    while proc.poll() is None:
        try:
            procs = [root, *root.children(recursive=True)]
        except psutil.NoSuchProcess:
            break
        total = 0
        for p in procs:
            try:
                m = p.memory_info()
            except psutil.Error:
                continue
            total += m.rss
            own_peaks[p.pid] = max(own_peaks.get(p.pid, 0), getattr(m, "peak_wset", m.rss))
        tree_peak = max(tree_peak, total)
        time.sleep(1)
    res = {"cmd": cmd, "exit": proc.wait(), "wall_s": round(time.time() - t0, 1),
           "tree_peak_mib": tree_peak / 2**20,
           "sum_of_process_peaks_mib": sum(own_peaks.values()) / 2**20,
           "processes": len(own_peaks)}  # fmt: skip
    with open(out, "w") as f:
        json.dump(res, f, indent=1)
    print(json.dumps(res))
    sys.exit(res["exit"])


if __name__ == "__main__":
    main()
