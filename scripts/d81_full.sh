cd /c/PROJECTS/ISM
# D81 full DEV run wrapper (exploratory_dev_v3): memory and disk gate before each arm, one heavy job at a time
# gate: napierone sum of process peaks 2623 MiB on the 2-machine pilot, scaled x5/2 = 6.6 GB, + 4 GB
GATE_GB=10.6
for a in napierone synthetic; do
  free=$(powershell -c "[math]::Round((Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory/1MB,1)")
  disk=$(powershell -c "[math]::Round((Get-PSDrive C).Free/1GB,1)")
  echo "$a gate: free RAM $free GB (need $GATE_GB), disk $disk GB (need 45)"
  if ! awk -v f="$free" -v g="$GATE_GB" -v d="$disk" 'BEGIN{exit !(f>=g && d>=45)}'; then
    echo "$a GATE FAILED, stopping"; exit 3
  fi
  uv run --with psutil python scripts/peak_mem.py results/exploratory_dev_v3/d81_${a}/run_peak_mem.json -- \
    uv run python -u -m slowburn.bench.byte_matched run configs/dev_v3_d81_$a.yaml \
    > results/exploratory_dev_v3/d81_${a}_console.log 2>&1
  rc=$?
  echo "$a exit $rc"; tail -3 results/exploratory_dev_v3/d81_${a}_console.log
  if [ $rc -ne 0 ]; then exit $rc; fi
done
