# D89 tolerance runs (exploratory_dev_v3), one arm at a time, gate rechecked every 10 min.
# Gate: RAM measured peak 6.8 GB + 4 GB = 10.8 GB; disk floor 45 GB (normal gates, OPEN_QUESTIONS D89)
cd /c/PROJECTS/ISM
GATE_GB=10.8
for a in napierone synthetic; do
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
  uv run --with psutil python scripts/peak_mem.py results/exploratory_dev_v3/d81_${a}/d89_peak_mem.json -- \
    uv run python -u -m slowburn.bench.byte_matched run-tol configs/dev_v3_d81_$a.yaml \
    > results/exploratory_dev_v3/d89_${a}_console.log 2>&1
  rc=$?
  echo "$a exit $rc"; tail -2 results/exploratory_dev_v3/d89_${a}_console.log
  if [ $rc -ne 0 ]; then exit $rc; fi
done
