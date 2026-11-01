"""D76 (exploratory): snapshot days each restic repository holds after the last day, read from
the repositories with `restic snapshots --json` (snapshot time = T0 + day, set by --time)."""
import json, os, subprocess
from datetime import datetime
T0, LAST, START = datetime(2026, 1, 1, 12), 221, 161
out = {}
for r in ("slowburn_plan", "restic_kd7_kw5", "restic_kd4_kw4"):
    env = {**os.environ, "RESTIC_PASSWORD": "d76-local-only", "RESTIC_REPOSITORY": f"restic/repo_{r}"}
    s = json.loads(subprocess.run([os.path.abspath("tools/restic.exe"), "snapshots", "--json"], env=env,
                                  capture_output=True, text=True, check=True).stdout)
    days = sorted((datetime.fromisoformat(x["time"][:19]) - T0).days for x in s)
    out[r] = {"held_days": days, "oldest_age_days": LAST - days[0],
              "pre_attack_snapshots": sum(d < START for d in days)}
out["note"] = f"last day {LAST}, attack start day {START} (first damaged day)"
open("results/exploratory/d76_restic/final_held_days.json", "w").write(json.dumps(out, indent=1))
print(json.dumps(out))
