#!/bin/bash
export PATH=/usr/bin:/mingw64/bin:$PATH:/c/Users/kembh/.local/bin
cd /c/PROJECTS/ISM
r=$(powershell -NoProfile -c "[int]((Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory/1MB)" | tr -d "
")
if [ "$r" -lt 13 ]; then echo "$(date -Iseconds) SKIP d74_attack_napierone_eqh: free RAM $r GB < 13 GB" >> results/overnight_queue.log; exit 0; fi
echo "$(date -Iseconds) RAM ok for d74_attack_napierone_eqh: $r GB free" >> results/overnight_queue.log
bash paper/scripts/overnight/job_queue.sh "d74_attack_napierone_eqh|uv run python -u paper/scripts/d74_run.py configs/dev_d74_attack_napierone_eqh.yaml"
