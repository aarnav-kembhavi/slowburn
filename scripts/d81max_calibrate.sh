# D81 addendum sbmax calibration (exploratory_dev_v3), one arm at a time, gate before each
cd /c/PROJECTS/ISM
GATE_GB=10.6
for a in napierone synthetic; do
  free=$(powershell -c "[math]::Round((Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory/1MB,1)")
  disk=$(powershell -c "[math]::Round((Get-PSDrive C).Free/1GB,1)")
  echo "$a gate: free RAM $free GB (need $GATE_GB), disk $disk GB (need 45)"
  tries=0  # wait for the gate (other projects may hold RAM), at most 6 h
  until awk -v f="$free" -v g="$GATE_GB" -v d="$disk" 'BEGIN{exit !(f>=g && d>=45)}'; do
    tries=$((tries + 1))
    if [ $tries -gt 72 ]; then echo "$a GATE FAILED for 6 h, stopping"; exit 3; fi
    sleep 300
    free=$(powershell -c "[math]::Round((Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory/1MB,1)")
    disk=$(powershell -c "[math]::Round((Get-PSDrive C).Free/1GB,1)")
    echo "$a gate retry $tries: free RAM $free GB, disk $disk GB"
  done
  uv run python -u -m slowburn.bench.byte_matched calibrate-max configs/dev_v3_d81_$a.yaml \
    > results/exploratory_dev_v3/d81max_${a}_calibrate_console.log 2>&1
  rc=$?
  echo "$a exit $rc"; tail -4 results/exploratory_dev_v3/d81max_${a}_calibrate_console.log
  if [ $rc -ne 0 ]; then exit $rc; fi
done
