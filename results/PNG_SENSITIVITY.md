# Truncated-png sensitivity row (UNSCORED; OPEN_QUESTIONS "Truncated-png sensitivity row", 2026-10-26)

Run dev_d67_full_napierone_v2notrunc 06:44-08:10 (2026-10-26), exit 0, first attempt: the D67
NapierOne arm on pool v2_notrunc (v2 minus the 9 PNG-FROM-WEB files truncated at 1 MiB), same
seeds, machines, grid and detector. Script paper/scripts/png_sensitivity.py, output
results/dev_png_sensitivity/. Count budgets, w 0.75, verify_snap; paired machine-cluster
bootstrap 95% CIs. **Unscored: the truncated pngs stay in every scored pool and this row changes
no claim by itself (team rule).**

| comparison (SlowBurn vs) | v2 (scored) | v2_notrunc (unscored) |
|---|---|---|
| default GFS, work lost | -14.0% [-18.3, -9.4] | -32.2% [-35.7, -28.2] |
| default Tower of Hanoi, work lost | -19.6% [-23.0, -16.0] | -34.0% [-36.8, -31.0] |
| prior-only (C3'), work lost | -3.8% [-5.3, -2.4] | -9.7% [-11.0, -8.5] |
| default GFS / ToH, recovery | +0.425 / +0.428 | +0.424 / +0.427 |

SlowBurn clean recovery 0.9985 (v2) vs 0.9975 (v2_notrunc).

**What it means.** Nine defective files (13% of the v2 DEV png pool) account for most of the
v1 -> v2 shrinkage in the D75 finding: without them the NapierOne effects are close to the v1
values (C2 vs GFS v1 -34.4%, C3' v1 -11.9%). The mechanism is the benign false flags they cause
(png benign flag rate 0.167; a flagged version in a clean snapshot makes verify_snap reject it).
So the D75 finding is better stated as "a few invalid benign files in a real-data pool change
evidence-based gains by about 2.5x" than as "pool size changes them". Team to decide the
wording of the D75 finding (claims.md and the paper's contribution 4); the scored numbers stay v2.
