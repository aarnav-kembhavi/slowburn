#!/bin/bash
export PATH=/usr/bin:/mingw64/bin:$PATH:/c/Users/kembh/.local/bin
cd /c/PROJECTS/ISM
bash paper/scripts/overnight/job_queue.sh "d78|bash paper/scripts/d78_run.sh"
