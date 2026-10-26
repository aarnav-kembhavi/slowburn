# D73 report: fleet-aware retention (DEV, 2026-10-24)

**Update 2026-10-26: NapierOne v2 rerun (the primary NapierOne arm; the v1 numbers further down
are now a sensitivity row).** Run d73_fleet_napierone_v2pool 01:32-06:31, exit 0, first attempt,
5,760 pairs per comparison; report paper/scripts/d73_report.py (results/dev_d73_report/,
log results/dev_d73_report.txt). **FLEET is still NOT adopted, and on v2 it fails more clearly:**

| criterion (restore A, K_avg 6 / 8), NapierOne v2 | vs a (equal split) | vs b (churn split) |
|---|---|---|
| 1. recovery not lower by > 0.01 in any cell | **fail (worst cell -0.213)** | **fail (-0.206)** |
| pooled recovery difference | **-0.029 [-0.049, -0.012]** | **-0.030 [-0.050, -0.012]** |
| 2. per-file work lost pooled | -16.6% [-20.3, -12.6] | -7.3% [-10.8, -3.5] |
| 3. lower in >= 6 of 9 (f, m) cells | 9 / 9 | 6 / 9 |

On v1 pooled recovery was not lower (0.000 [-0.012, +0.011]); on v2 FLEET recovers
significantly less than both splits, so the work-lost gain is bought with recovery. Synthetic
unchanged (passes every criterion). K_avg = 4 (descriptive): fleet recovery 0.911 vs 0.944 equal
split. With per-file restores B / D the recovery loss vanishes (0.000) and C gains recovery
(+0.079 [+0.048, +0.110]); none of these is the pre-registered primary restore. Greedy check
unchanged (optimal 0.990). Reported as a failure; no rescue, no rerun.

**Original report (v1 pools; NapierOne numbers below are the sensitivity row):**

Pre-registration: OPEN_QUESTIONS D73 (0bae5bb) and amendment (0ac3331: K_avg = 4 is "no
reallocation room (floor 3 of 4)", criteria on K_avg 6 and 8; primary restore A since D72 did not
adopt C). Code 91314a6. Runs: d73_fleet_synthetic 01:03-06:53, d73_fleet_napierone 06:53-11:26
(2026-10-24), exit 0, first attempt; 8 reps x 4 worlds x N {20, 100}, 43,200 fleet rows per
arm. Outputs: results/dev_d73_fleet_{synthetic,napierone}/fleet_rows.csv.gz,
results/dev_d73_report/{criteria,summary,greedy_check,k4_no_reallocation_room}.csv, log
results/dev_d73_report.txt. Clusters for CIs: (rep, world), because the N = 20 and N = 100
fleets of a rep share machines.

## Verdict: FLEET is NOT adopted

| criterion (restore A, K_avg 6 / 8) | synthetic vs a | synthetic vs b | NapierOne vs a | NapierOne vs b |
|---|---|---|---|---|
| 1. fleet recovery not lower by > 0.01 in any cell | pass (worst 0.000) | pass (0.000) | **fail (worst -0.025)** | **fail (-0.025)** |
| 2. per-file work lost lower pooled (CI) | -16.2% [-20.3, -12.1] | -9.4% [-13.0, -5.8] | -17.9% [-23.0, -12.7] | -10.3% [-14.3, -6.2] |
| 3. lower in >= 6 of 9 (f, m) cells | 9 / 9 | 9 / 9 | 9 / 9 | 6 / 9 |

FLEET passes every criterion on synthetic bytes and fails criterion 1 on NapierOne bytes against
both splits, so it fails the pre-registered rule (both arms required). Pooled fleet recovery is
not lower (NapierOne vs a: 0.000 [-0.012, +0.011]); the failing cells are 10 of 36 vs a and 6 of
36 vs b, all N = 20 but one, and 52 of the 54 losing rows come from a single fleet (rep 6, late
world, N = 20, both K_avg). Reported as a failure; no rescue, no rerun.

## What FLEET actually does (descriptive)

- It barely reallocates. The share of the fleet budget held by infected machines at discovery is
  0.193 for FLEET vs 0.192 equal split at f = 0.2 (0.482 vs 0.480 at f = 0.5): slots do not
  move toward infected machines in any meaningful amount.
- Its gain comes from which snapshots each machine keeps under the fleet posterior. Same
  reallocation with each machine's own posterior (e, reported only) loses 12% to 14% more
  per-file work than FLEET (synthetic -12.2% [-14.4, -10.0], NapierOne -14.4% [-16.9, -12.0]
  for c vs e); SlowBurn per machine without sharing (d) is no better than the equal Bar-On split
  (+0.3% [-5.3, +5.7] synthetic, -0.1% NapierOne). So the effect is the hierarchical (pooled)
  start posterior, not the budget sharing the method was named for.
- With the per-file oracle restore (D) or per-file walk-back (B) the advantage over the churn
  split vanishes (-0.9% to -1.3%, CIs include 0): the gain is in snapshot-level restores.
- K_avg = 4 (no reallocation room, floor 3 of 4; descriptive only): FLEET has the lowest per-file
  work lost there too (NapierOne 81,814 h vs 109,423 h equal split) and the lowest fleet recovery
  on NapierOne (0.972 vs 0.979).

## Greedy vs exact allocation (pre-registered check)

500 random small cases (2 to 4 machines, up to 6 removals): greedy optimal in 99.0%; largest
relative excess 24.1% (greedy_check.csv). Greedy is not replaced (pre-registered). Given that
FLEET hardly moves slots, the allocation rule is not where its effect comes from.

## For the paper

FLEET as pre-registered fails on recovery in one arm. The positive, robust finding is narrower:
pooling the start posterior across machines that share an attacker cuts per-file work lost by
10% to 18% at equal pooled recovery on both byte arms, with the recovery losses concentrated in
one N = 20 fleet. Claiming that would need a new pre-registration, e.g. FLEET's posterior without
reallocation, tested on fresh DEV fleets.
