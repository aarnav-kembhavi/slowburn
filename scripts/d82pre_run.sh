# D82 stage 1 precheck runs (exploratory_dev_v3), one at a time, gate rechecked every 10 min.
# Gate: RAM measured peak 6.8 GB + 4 GB = 10.8 GB (unchanged); disk floor 40 GB for these runs only
# (approved, OPEN_QUESTIONS D82 stage 1 precheck)
cd /c/PROJECTS/ISM
GATE_GB=10.8
for job in "napierone 75" "napierone 90" "synthetic 75" "synthetic 90"; do
  set -- $job; a=$1; M=$2
  tries=0
  while :; do
    free=$(powershell -c "[math]::Round((Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory/1MB,1)")
    disk=$(powershell -c "[math]::Round((Get-PSDrive C).Free/1GB,1)")
    echo "$a M=$M gate: free RAM $free GB (need $GATE_GB), disk $disk GB (need 40)"
    if awk -v f="$free" -v g="$GATE_GB" -v d="$disk" 'BEGIN{exit !(f>=g && d>=40)}'; then break; fi
    tries=$((tries + 1))
    if [ $tries -gt 144 ]; then echo "$a M=$M GATE FAILED for 24 h, stopping"; exit 3; fi
    sleep 600
  done
  uv run --with psutil python scripts/peak_mem.py results/exploratory_dev_v3/d81_${a}/d82pre_M${M}_peak_mem.json -- \
    uv run python -u -m slowburn.bench.byte_matched run-m configs/dev_v3_d81_$a.yaml $M \
    > results/exploratory_dev_v3/d82pre_${a}_M${M}_console.log 2>&1
  rc=$?
  echo "$a M=$M exit $rc"; tail -2 results/exploratory_dev_v3/d82pre_${a}_M${M}_console.log
  if [ $rc -ne 0 ]; then exit $rc; fi
done
