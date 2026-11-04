# D90 limitation-test runs (exploratory_dev_v3), one arm at a time, 2 workers (D90 setup change).
# Gate: free RAM >= measured pilot peak + 4 GB (first argument, GB), rechecked every 10 min; disk
# floor 45 GB. Watchdog: every 30 s, if free RAM < 3 GB, the run's process tree is killed (finished
# machines stay cached) and the script exits 4 before the system reaches critical memory.
cd /c/PROJECTS/ISM
GATE_GB=${1:?gate GB}
FLOOR_GB=3
free_gb() { powershell -c "[math]::Round((Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory/1MB,1)"; }
for a in napierone synthetic; do
  tries=0
  while :; do
    free=$(free_gb)
    disk=$(powershell -c "[math]::Round((Get-PSDrive C).Free/1GB,1)")
    echo "$a gate: free RAM $free GB (need $GATE_GB), disk $disk GB (need 45)"
    if awk -v f="$free" -v g="$GATE_GB" -v d="$disk" 'BEGIN{exit !(f>=g && d>=45)}'; then break; fi
    tries=$((tries + 1))
    if [ $tries -gt 144 ]; then echo "$a GATE FAILED for 24 h, stopping"; exit 3; fi
    sleep 600
  done
  uv run --with psutil python scripts/peak_mem.py results/exploratory_dev_v3/d81_${a}/d90_peak_mem.json -- \
    uv run python -u -m slowburn.bench.byte_matched run-d90 configs/dev_v3_d81_$a.yaml --workers 2 \
    > results/exploratory_dev_v3/d90_${a}_console.log 2>&1 &
  pid=$!
  winpid=$(cat /proc/$pid/winpid)
  while kill -0 $pid 2>/dev/null; do
    free=$(free_gb)
    if awk -v f="$free" -v g="$FLOOR_GB" 'BEGIN{exit !(f<g)}'; then
      echo "$a WATCHDOG: free RAM $free GB < $FLOOR_GB GB, killing run tree (winpid $winpid)"
      taskkill //F //T //PID $winpid
      exit 4
    fi
    sleep 30
  done
  wait $pid
  rc=$?
  echo "$a exit $rc"; tail -2 results/exploratory_dev_v3/d90_${a}_console.log
  if [ $rc -ne 0 ]; then exit $rc; fi
done
