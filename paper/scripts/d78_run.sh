#!/bin/bash
# D78: recount on FIX (unchanged, F1-F3) -> criteria and selection on FIX -> recount on CHECK
# (unchanged + selected) -> criteria once on CHECK. TEST is never read.
set -e
cd /c/PROJECTS/ISM
uv run python -u paper/scripts/d78_recount.py v2fix unchanged F1 F2 F3
uv run python -u paper/scripts/d78_score.py v2fix F1 F2 F3
sel=$(uv run python -c "import json; print(json.load(open('results/dev_d78/selection.json'))['selected'])")
echo "selected on FIX: $sel"
uv run python -u paper/scripts/d78_recount.py v2check unchanged "$sel"
uv run python -u paper/scripts/d78_score.py v2check "$sel"
