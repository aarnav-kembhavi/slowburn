# D79 report: SlowBurn at equal horizon (DEV, 2026-10-26)

Pre-registration: OPEN_QUESTIONS D79 (92789d9), code cd321dd, report e71ad7f
(paper/scripts/d79_report.py; output results/dev_d79_report/, log results/dev_d79_report.txt).
Runs: dev_d79_eqh_napierone 08:10-09:29, dev_d79_eqh_synthetic 09:29-11:03, exit 0, first
attempt. Sanity: every slowburn / gfs_eqh / toh_eqh row reproduces D72 exactly (12,000 of
12,000 per arm). Sign convention: work lost = variant / baseline - 1 (negative = variant loses
less); recovery = variant minus baseline.

## Verdict: NOT a success. Finding: "placement does not help at equal horizon"

Primary, NapierOne v2 (decides), Holm across the two:

| comparison | pairs | work lost | recovery | Holm p | success |
|---|---|---|---|---|---|
| slowburn_age_gfs vs gfs_eqh (K 12, cap 104 d) | 2,400 | -0.9% [-3.2, +1.7] | -0.003 [-0.009, +0.002] | 0.48 | no (CI includes 0) |
| slowburn_age_toh vs toh_eqh (K 8 / 12, cap 127 / 255 d) | 4,800 | **+6.3% [+2.3, +10.6]** | +0.061 [+0.039, +0.085] | 0.004 | no (variant loses more) |

Synthetic bytes (sanity arm): vs gfs_eqh -4.1% [-5.8, -2.2], recovery -0.001 [-0.002, 0.000],
Holm p < 0.001 (would pass); vs toh_eqh +1.8% [-1.6, +5.1], Holm p 0.31 (fails). The arms
disagree on GFS; the NapierOne arm decides, as registered.

## What the cap does (secondary, unadjusted)

- The age cap alone closes most of the equal-horizon gap. SlowBurn vs gfs_eqh goes from +24.9%
  [+19.8, +30.3] (uncapped) to -0.9% (capped); vs toh_eqh from +14.9% [+10.5, +19.8] to +6.3%.
  Capped vs uncapped SlowBurn: -20.7% [-23.9, -17.3] work lost at K 12 (GFS cap; recovery -0.003
  [-0.009, 0.000]) and -7.5% [-9.4, -5.5] (ToH caps; recovery 0.000). Synthetic: -17.4% / -7.6%.
- So the gap in C2 is a horizon effect: uncapped SlowBurn keeps snapshots older than the eqh
  schedules do and pays for it in work lost. At equal reach, SlowBurn's placement ties GFS-eqh
  and loses to ToH-eqh on work lost.
- ToH-eqh has lower recovery than both SlowBurn variants (-0.061), concentrated in the early
  (+0.140) and uniform (+0.095) worlds; the variant's extra work lost vs ToH-eqh is mostly at
  K = 8 (+11.1% [+7.4, +15.0]; K = 12 +2.3% [-3.0, +7.9]) and in the bursty world (+15.7%).

## For the paper

Failure is the registered finding: "placement does not help at equal horizon". The abstract's
equal-horizon caveat stays. New, descriptive: capping SlowBurn's retention age at the eqh
schedule's reach removes most of its work-lost deficit (C2 deficit vs GFS-eqh +24.9% -> -0.9%),
so horizon, not placement, drives it; this is not a pre-registered claim and adopting a capped
SlowBurn would need its own registration and TEST.
