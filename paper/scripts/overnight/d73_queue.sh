#!/bin/bash
# D73: both arms one at a time (stage 1 machines, stage 2 fleets), then the report. Skips an arm
# if free space minus 2 GB would cross the 45 GB floor.
cd /c/PROJECTS/ISM
LOG=results/overnight_queue.log
for arm in synthetic napierone; do
  free=$(python -c "import shutil;print(int(shutil.disk_usage('C:/').free/1e9))")
  if [ $((free - 2)) -lt 45 ]; then echo "$(date -Iseconds) SKIP d73_$arm: free $free GB" >> $LOG; continue; fi
  for attempt in 1 2; do
    echo "$(date -Iseconds) START d73_fleet_$arm attempt $attempt (free $free GB)" >> $LOG
    uv run python -u paper/scripts/d73_run.py configs/dev_d73_fleet_$arm.yaml >> results/dev_d73_fleet_${arm}_run.log 2>&1
    rc=$?; echo "$(date -Iseconds) END d73_fleet_$arm attempt $attempt exit $rc" >> $LOG
    [ $rc -eq 0 ] && break
    [ $attempt -eq 2 ] && echo "$(date -Iseconds) FAILED TWICE d73_fleet_$arm, moving on" >> $LOG
  done
done
uv run python paper/scripts/d73_report.py A > results/dev_d73_report.txt 2>&1
echo "$(date -Iseconds) d73_report exit $?" >> $LOG
