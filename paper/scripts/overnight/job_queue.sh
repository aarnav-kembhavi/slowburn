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
# One-off follow-up (team decision 2026-10-26), runs only while results/.followup_after_d73 exists:
# after D73 NapierOne v2 exits 0, held-out alarm check then png sensitivity row, each only if free
# RAM >= FOLLOWUP_MIN_GB (proxy: D73 peak private memory 9 GB + 4 GB headroom).
if [ -f results/.followup_after_d73 ]; then
  rm -f results/.followup_after_d73; MIN=13
  ram() { powershell -NoProfile -c "[int]((Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory/1MB)" | tr -d '\r'; }
  if ! tail -3 $LOG | grep -qE "END d73_fleet_napierone_v2pool attempt [12] exit 0"; then
    echo "$(date -Iseconds) SKIP follow-up: D73 NapierOne v2 did not exit 0" >> $LOG
  else
    for job in "d74_alarm_holdout|uv run python -u paper/scripts/d74_alarm_holdout.py configs/dev_d74_attack_napierone.yaml configs/dev_d74_attack_synthetic.yaml" \
               "dev_d67_full_napierone_v2notrunc|uv run python -u -m slowburn.cli dev-sweep configs/dev_d67_full_napierone_v2notrunc.yaml"; do
      r=$(ram)
      if [ "$r" -lt $MIN ]; then echo "$(date -Iseconds) SKIP ${job%%|*}: free RAM $r GB < $MIN GB" >> $LOG; break; fi
      echo "$(date -Iseconds) RAM ok for ${job%%|*}: $r GB free" >> $LOG
      bash "$0" "$job"
    done
  fi
fi
# One-off follow-up 2 (team decision 2026-10-26): D79 NapierOne v2 then D79 synthetic, after the
# png row has ended (or a follow-up was skipped), while results/.followup_d79 exists (created
# only after the D79 smoke test passed); each only if free RAM >= 13 GB. D78 is added here only
# once its fix code exists.
if [ -f results/.followup_d79 ] && grep -qE "END dev_d67_full_napierone_v2notrunc attempt|FAILED TWICE dev_d67_full_napierone_v2notrunc|SKIP (follow-up|d74_alarm_holdout|dev_d67_full_napierone_v2notrunc)" $LOG; then
  rm -f results/.followup_d79; MIN=13
  ram() { powershell -NoProfile -c "[int]((Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory/1MB)" | tr -d '\r'; }
  for job in "dev_d79_eqh_napierone|uv run python -u -m slowburn.cli dev-sweep configs/dev_d79_eqh_napierone.yaml" \
             "dev_d79_eqh_synthetic|uv run python -u -m slowburn.cli dev-sweep configs/dev_d79_eqh_synthetic.yaml"; do
    r=$(ram)
    if [ "$r" -lt $MIN ]; then echo "$(date -Iseconds) SKIP ${job%%|*}: free RAM $r GB < $MIN GB" >> $LOG; break; fi
    echo "$(date -Iseconds) RAM ok for ${job%%|*}: $r GB free" >> $LOG
    bash "$0" "$job"
  done
fi
