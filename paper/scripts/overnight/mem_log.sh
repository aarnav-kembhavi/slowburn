#!/bin/bash
# usage: mem_log.sh <queue_windows_pid> [interval_s]; every interval logs free RAM and the summed
# private memory of this repo's python processes to results/overnight_queue.log until the queue
# exits.
export PATH=/usr/bin:$PATH
cd /c/PROJECTS/ISM
LOG=results/overnight_queue.log; Q=$1; I=${2:-900}
while tasklist //FI "PID eq $Q" //NH | grep -qw "$Q"; do
  m=$(powershell -NoProfile -c "\$o=Get-CimInstance Win32_OperatingSystem; \$p=(Get-CimInstance Win32_Process -Filter \"name='python.exe'\" | ? { \$_.CommandLine -match 'PROJECTS.ISM|paper/scripts|slowburn|multiprocessing' } | % { (Get-Process -Id \$_.ProcessId -EA SilentlyContinue).PrivateMemorySize64 } | Measure-Object -Sum).Sum; '{0:N1} GB free, ISM python private {1:N1} GB' -f (\$o.FreePhysicalMemory/1MB), (\$p/1GB)" | tr -d '\r')
  echo "$(date -Iseconds) MEM $m" >> $LOG
  sleep "$I"
done
