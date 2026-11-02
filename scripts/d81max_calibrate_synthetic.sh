# D81 addendum sbmax calibration, synthetic arm (exploratory_dev_v3). Gate approved for this job
# only (OPEN_QUESTIONS D81 addendum): measured peak 6.8 GB + 2 GB = 8.8 GB free RAM; disk >= 45 GB
cd /c/PROJECTS/ISM
GATE_GB=8.8
a=synthetic
tries=0
while :; do
  free=$(powershell -c "[math]::Round((Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory/1MB,1)")
  disk=$(powershell -c "[math]::Round((Get-PSDrive C).Free/1GB,1)")
  echo "$a gate: free RAM $free GB (need $GATE_GB), disk $disk GB (need 45)"
  if awk -v f="$free" -v g="$GATE_GB" -v d="$disk" 'BEGIN{exit !(f>=g && d>=45)}'; then break; fi
  tries=$((tries + 1))
  if [ $tries -gt 72 ]; then echo "$a GATE FAILED for 6 h, stopping"; exit 3; fi
  sleep 300
done
uv run --with psutil python scripts/peak_mem.py results/exploratory_dev_v3/d81_${a}/calibrate_max_peak_mem.json -- \
  uv run python -u -m slowburn.bench.byte_matched calibrate-max configs/dev_v3_d81_$a.yaml \
  > results/exploratory_dev_v3/d81max_${a}_calibrate_console.log 2>&1
rc=$?
echo "$a exit $rc"; tail -4 results/exploratory_dev_v3/d81max_${a}_calibrate_console.log
exit $rc
