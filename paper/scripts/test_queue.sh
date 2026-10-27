#!/bin/bash
# frozen_v2.yaml TEST queue (OPEN_QUESTIONS 2026-10-27 / 2026-10-28). Starts only after the approval
# line; inventory and dry run are done before it. One heavy job at a time, in the approved order.
# Items: name|output dir|command. Per item: stdout -> results/test_<item>_run.log, stderr ->
# results/test_<item>_err.log; neither is read until every item has finished (on a crash, only the stderr traceback). Gates before each
# item: free RAM >= 13 GB (measured peak + 4 GB) and C: >= 45 GB free (2 GB margin). No retry:
# a crash or a failed gate stops the queue (failure rule: fix the crash cause only, commit with the
# traceback, rerun that item from scratch). No analysis script runs here.
cd /c/PROJECTS/ISM
export PATH
LOG=results/test_queue.log
ITEMS=(
  "alarm|results/test_d74_alarm|uv run python -u paper/scripts/d74_alarm_holdout.py configs/test_d74_attack_napierone.yaml configs/test_d74_attack_synthetic.yaml"
  "c2_d72_napierone|results/test_d72_bytes_napierone_v2pool|uv run python -u -m slowburn.cli dev-sweep configs/test_d72_bytes_napierone_v2pool.yaml"
  "d79_napierone|results/test_d79_eqh_napierone|uv run python -u -m slowburn.cli dev-sweep configs/test_d79_eqh_napierone.yaml"
  "d71|results/test_d71_oracle_gap|uv run python -u -m slowburn.cli dev-sweep configs/test_d71_oracle_gap.yaml"
  "d74_napierone|results/test_d74_attack_napierone|uv run python -u paper/scripts/d74_run.py configs/test_d74_attack_napierone.yaml"
  "c2_d72_synthetic|results/test_d72_bytes_synthetic|uv run python -u -m slowburn.cli dev-sweep configs/test_d72_bytes_synthetic.yaml"
  "d79_synthetic|results/test_d79_eqh_synthetic|uv run python -u -m slowburn.cli dev-sweep configs/test_d79_eqh_synthetic.yaml"
  "d74_synthetic|results/test_d74_attack_synthetic|uv run python -u paper/scripts/d74_run.py configs/test_d74_attack_synthetic.yaml"
  "d73_napierone|results/test_d73_fleet_napierone_v2pool|uv run python -u paper/scripts/d73_run.py configs/test_d73_fleet_napierone_v2pool.yaml"
  "d73_synthetic|results/test_d73_fleet_synthetic|uv run python -u paper/scripts/d73_run.py configs/test_d73_fleet_synthetic.yaml"
)
START_AT=${1:-alarm}   # resume point after a crash fix (that item reruns from scratch)
ram() { powershell -NoProfile -c "[int]((Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory/1MB)" | tr -d '\r'; }
disk() { python -c "import shutil;print(int(shutil.disk_usage('C:/').free/1e9))"; }
started=0
echo "$(date -Iseconds) QUEUE start at $START_AT, commit $(git rev-parse --short HEAD)" >> $LOG
for item in "${ITEMS[@]}"; do
  name=${item%%|*}; rest=${item#*|}; out=${rest%%|*}; cmd=${rest#*|}
  [ "$name" = "$START_AT" ] && started=1
  [ $started -eq 0 ] && continue
  r=$(ram); f=$(disk)
  if [ "$r" -lt 13 ] || [ $((f - 2)) -lt 45 ]; then
    echo "$(date -Iseconds) QUEUE STOPPED before $name: free RAM $r GB, disk $f GB (gate 13 / 45)" >> $LOG
    exit 2
  fi
  if [ -e "$out" ]; then  # from scratch: a crashed attempt's output is removed unread
    rm -rf "$out"; echo "$(date -Iseconds) removed $out unread (previous attempt)" >> $LOG
  fi
  echo "$(date -Iseconds) START $name (RAM $r GB, disk $f GB): $cmd" >> $LOG
  bash -c "$cmd" > "results/test_${name}_run.log" 2> "results/test_${name}_err.log"
  rc=$?
  echo "$(date -Iseconds) END $name exit $rc" >> $LOG
  if [ $rc -ne 0 ]; then
    echo "$(date -Iseconds) QUEUE STOPPED: $name crashed (failure rule)" >> $LOG
    exit 1
  fi
done
echo "$(date -Iseconds) QUEUE DONE: all items finished; analysis may start" >> $LOG
