# D81 addendum sbmax evaluation, synthetic arm only (exploratory_dev_v3); gate rechecked every 10 min
# peak 6.8 GB (full D81 napierone run, sum of process peaks) + 4 GB = 10.8 GB free RAM; disk >= 45 GB
cd /c/PROJECTS/ISM
GATE_GB=10.8
for a in synthetic; do
  tries=0
  while :; do
    free=$(powershell -c "[math]::Round((Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory/1MB,1)")
    disk=$(powershell -c "[math]::Round((Get-PSDrive C).Free/1GB,1)")
    echo "$a gate: free RAM $free GB (need $GATE_GB), disk $disk GB (need 45)"
    if awk -v f="$free" -v g="$GATE_GB" -v d="$disk" 'BEGIN{exit !(f>=g && d>=45)}'; then break; fi
    tries=$((tries + 1))
    if [ $tries -gt 144 ]; then echo "$a GATE FAILED for 24 h, stopping"; exit 3; fi
    sleep 600
  done
  uv run --with psutil python scripts/peak_mem.py results/exploratory_dev_v3/d81_${a}/run_max_peak_mem.json -- \
    uv run python -u -m slowburn.bench.byte_matched run-max configs/dev_v3_d81_$a.yaml \
    > results/exploratory_dev_v3/d81max_${a}_console.log 2>&1
  rc=$?
  echo "$a exit $rc"; tail -3 results/exploratory_dev_v3/d81max_${a}_console.log
  if [ $rc -ne 0 ]; then exit $rc; fi
done
