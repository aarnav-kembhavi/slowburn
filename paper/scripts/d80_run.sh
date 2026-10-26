#!/bin/bash
# D80: runs only if D78 accepted a candidate on CHECK (selection adoptable and every criterion
# met on CHECK); otherwise logs that D80 does not run.
set -e
cd /c/PROJECTS/ISM
acc=$(uv run python -c "
import json, pandas as pd
s = json.load(open('results/dev_d78/selection.json'))
c = pd.read_csv('results/dev_d78/criteria_v2check.csv')
ok = s['adoptable'] and bool(c[c.candidate == s['selected']]['all'].iloc[0])
print(s['selected'] if ok else '')")
if [ -z "$acc" ]; then echo "D78 accepted no candidate: D80 does not run"; exit 0; fi
echo "D78 accepted $acc: running D80"
uv run python paper/scripts/d80_configs.py "$acc"
uv run python -u -m slowburn.cli dev-sweep configs/dev_d80_c2_napierone.yaml
uv run python -u paper/scripts/d74_alarm_holdout.py --out=results/dev_d80_alarm_holdout configs/dev_d80_alarm_napierone.yaml
uv run python -u paper/scripts/d80_report.py
