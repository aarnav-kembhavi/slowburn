#!/bin/bash
# usage: run_queue.sh <min_free_GB_after_estimate> <config>:<estimated_GB> ...
# One job at a time; skip a job whose estimated output would leave < floor GB free; retry once.
cd /c/PROJECTS/ISM
LOG=results/overnight_queue.log
floor=$1; shift
for job in "$@"; do
  cfg=${job%%:*}; est=${job##*:}; name=$(basename "$cfg" .yaml)
  free=$(python -c "import shutil;print(int(shutil.disk_usage('C:/').free/1e9))")
  if [ $((free - est)) -lt "$floor" ]; then
    echo "$(date -Iseconds) SKIP $name: free $free GB - est $est GB < floor $floor GB" >> $LOG; continue
  fi
  for attempt in $(seq ${FIRST_ATTEMPT:-1} 2); do
    echo "$(date -Iseconds) START $name attempt $attempt (free $free GB)" >> $LOG
    uv run python -u -m slowburn.cli dev-sweep "$cfg" > "results/${name}_run.log" 2>&1
    rc=$?; echo "exit $rc" >> "results/${name}_run.log"
    echo "$(date -Iseconds) END $name attempt $attempt exit $rc" >> $LOG
    [ $rc -eq 0 ] && break
    [ $attempt -eq 2 ] && echo "$(date -Iseconds) FAILED TWICE $name, moving on" >> $LOG
  done
done
