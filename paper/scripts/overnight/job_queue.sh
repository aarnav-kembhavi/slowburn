#!/bin/bash
# usage: job_queue.sh "<name>|<command>" ... ; one job at a time, 45 GB floor (2 GB margin),
# retry once, everything logged to results/overnight_queue.log and results/<name>_run.log.
cd /c/PROJECTS/ISM
LOG=results/overnight_queue.log
for job in "$@"; do
  name=${job%%|*}; cmd=${job#*|}
  free=$(python -c "import shutil;print(int(shutil.disk_usage('C:/').free/1e9))")
  if [ $((free - 2)) -lt 45 ]; then echo "$(date -Iseconds) SKIP $name: free $free GB" >> $LOG; continue; fi
  for attempt in 1 2; do
    echo "$(date -Iseconds) START $name attempt $attempt (free $free GB)" >> $LOG
    bash -c "$cmd" >> "results/${name}_run.log" 2>&1
    rc=$?; echo "$(date -Iseconds) END $name attempt $attempt exit $rc" >> $LOG
    [ $rc -eq 0 ] && break
    [ $attempt -eq 2 ] && echo "$(date -Iseconds) FAILED TWICE $name, moving on" >> $LOG
  done
done
