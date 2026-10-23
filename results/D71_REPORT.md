# D71 report: restore diagnostics (DEV, descriptive, report only)

Spec: OPEN_QUESTIONS D71 (committed 6fa7744 before the code, bcd61d2, and the run). Machines: the
D69 full grid (seed 202, 4 worlds x 40 reps, delays 7-60, benign rates 0 / .01 / .05, count
budgets K 4 / 6 / 8 / 12, w 0.75, assumed M 60), every D68/D69 policy. Run:
results/dev_d71_oracle_gap (12:06 to 12:36, exit 0). Script: paper/scripts/d71_report.py. Tables:
results/dev_d71_oracle_gap/{gap,diag}_*.csv. Brackets: 95% machine-cluster bootstrap CIs
(clusters = world x true start x rep, 2000 resamples, seed 0).

Restores compared on the same rows:
- (a) verify_snap: the adopted restore.
- (b) oracle snapshot: newest kept snapshot older than the true start.
- (c) oracle per file: every damaged file from its newest truly clean held version.

Work lost: whole-system hours for (a) and (b); file-hours (benign versions discarded) for
(a), (b) and (c).

## 1. Oracle gap, full grid, pooled over K

| policy | q | rec (a) | rec (b) | gap a-b [95% CI] | work lost (a) h | (b) h | (a) vs (b) [95% CI] |
|---|---|---|---|---|---|---|---|
| SlowBurn | 0 | 0.959 | 1.000 | -0.041 [-0.047, -0.036] | 2248 | 1195 | +88% [+82, +94] |
| SlowBurn | 0.2 | 0.980 | 1.000 | -0.020 [-0.026, -0.015] | 2147 | 1196 | +79% [+74, +85] |
| SlowBurn | 0.5 | 0.995 | 1.000 | -0.005 [-0.007, -0.003] | 2012 | 1196 | +68% [+63, +73] |
| SlowBurn | 1 | 1.000 | 1.000 | 0.000 [0, 0] | 1906 | 1197 | +59% [+54, +64] |
| prior-only | 0 | 0.959 | 1.000 | -0.041 [-0.046, -0.037] | 2229 | 1178 | +89% [+83, +95] |
| prior-only | 0.2 | 0.974 | 1.000 | -0.026 [-0.031, -0.021] | 2178 | 1178 | +85% [+79, +91] |
| prior-only | 0.5 | 0.991 | 1.000 | -0.009 [-0.012, -0.006] | 2131 | 1178 | +81% [+75, +86] |
| prior-only | 1 | 1.000 | 1.000 | 0.000 | 2101 | 1178 | +78% [+73, +84] |
| Bar-On exact (K 4, 6) | 0 | 0.965 | 0.999 | -0.035 [-0.042, -0.028] | 2334 | 1281 | +82% [+76, +88] |
| Bar-On exact | 1 | 0.999 | 0.999 | 0.000 | 2050 | 1281 | +60% [+54, +66] |
| Bar-On round-robin | 0 | 0.949 | 1.000 | -0.051 [-0.057, -0.045] | 2319 | 1287 | +80% [+76, +84] |
| Bar-On round-robin | 1 | 1.000 | 1.000 | 0.000 | 2033 | 1287 | +58% [+54, +62] |
| Bar-On recursive | 0 | 0.957 | 0.999 | -0.043 [-0.049, -0.037] | 2265 | 1213 | +87% [+82, +91] |
| Bar-On recursive | 0.2 | 0.980 | 0.999 | -0.019 [-0.025, -0.014] | 2189 | 1213 | +80% [+76, +85] |
| Bar-On recursive | 0.5 | 0.994 | 0.999 | -0.005 [-0.009, -0.002] | 2083 | 1213 | +72% [+67, +77] |
| Bar-On recursive | 1 | 0.999 | 0.999 | 0.000 | 1980 | 1213 | +63% [+58, +68] |
| GFS | 0 | 0.574 | 0.574 | 0.000 | 2706 | 2512 | +7.7% [+7.2, +8.3] |
| GFS | 1 | 0.574 | 0.574 | 0.000 | 2635 | 2512 | +4.9% [+4.5, +5.4] |
| Tower of Hanoi | 0 | 0.556 | 0.573 | -0.017 [-0.022, -0.012] | 2891 | 2456 | +18% [+17, +19] |
| Tower of Hanoi | 1 | 0.573 | 0.573 | 0.000 | 2716 | 2456 | +11% [+10, +11] |
| ToH equal horizon (K 8, 12) | 0 | 0.908 | 0.941 | -0.034 [-0.044, -0.025] | 1968 | 1131 | +74% [+67, +81] |
| ToH equal horizon | 1 | 0.941 | 0.941 | 0.000 | 1624 | 1131 | +44% [+38, +49] |
| GFS equal horizon (K 12) | 0 | 0.947 | 1.000 | -0.053 [-0.063, -0.043] | 1881 | 1006 | +87% [+81, +93] |
| GFS equal horizon | 1 | 1.000 | 1.000 | 0.000 | 1477 | 1006 | +47% [+42, +51] |

All q rows (0, .2, .5, 1) for every policy: gap_full_by_q.csv. By K: gap_full_by_q_K.csv. By
world (worlds grid): gap_worlds_by_q.csv and gap_worlds_by_q_K.csv. The recovery gap grows with
K at q = 0. For SlowBurn by K 4 / 6 / 8 / 12:
- recovery gap: -0.015 / -0.033 / -0.050 / -0.068
- work lost: +72% / +74% / +98% / +115%

### Restore-choice diagnosis (rows holding a clean snapshot; shares of all rows)

| policy | q | verify_snap did not pick j* [95% CI] | failed despite clean held | missed damage | false flag on clean j* | j* gated out | false flag on a day-0 version |
|---|---|---|---|---|---|---|---|
| SlowBurn | 0 | 0.717 [0.702, 0.731] | 0.041 | 0.041 | 0.190 | 0.485 | 0.011 |
| SlowBurn | 0.2 | 0.665 [0.648, 0.682] | 0.020 | 0.020 | 0.195 | 0.450 | 0.011 |
| SlowBurn | 0.5 | 0.571 [0.550, 0.592] | 0.005 | 0.005 | 0.211 | 0.355 | 0.012 |
| SlowBurn | 1 | 0.479 [0.455, 0.503] | 0.000 | 0.000 | 0.256 | 0.223 | 0.014 |
| prior-only | 0 | 0.732 [0.718, 0.746] | 0.041 | 0.041 | 0.188 | 0.503 | 0.011 |
| prior-only | 1 | 0.697 [0.682, 0.713] | 0.000 | 0.000 | 0.194 | 0.503 | 0.011 |
| Bar-On recursive | 0 | 0.716 [0.696, 0.735] | 0.043 | 0.043 | 0.179 | 0.494 | 0.005 |
| Bar-On recursive | 1 | 0.498 [0.472, 0.523] | 0.000 | 0.000 | 0.230 | 0.268 | 0.007 |

`residual_outside_scope` and `other` are 0 in every cell. Every policy and q is in
diag_full_by_q.csv (CIs on every share), by K and by world in the other diag_*.csv files.

Findings:
- **Every recovery failure with a clean snapshot held is missed damage.** In every policy x q
  cell, `failed despite clean held` = `missed damage`. False flags and the gate never cause a
  recovery failure; they cost work lost by sending the restore to an older clean point.
- **The work-lost gap is mostly false flags and the gate.**
  - At q = 1, verify_snap still skips j* in 48% of SlowBurn rows (false flag 26%, gated out 22%)
    and loses 59% more whole-system work than the oracle snapshot.
  - By benign rate (SlowBurn, q = 1): at rate 0 it picks j* in 90% of rows and loses only 6.6%
    more than the oracle; at rate 0.01 it is 57% and +38%; at rate 0.05 it is 9% and +134%.
  - At q = 0 and rate 0 the gate alone keeps it at 46% picked, +53%.
  - The false flags in this grid come from `benign_invalid_rate` (abstract detector). On real
    bytes they come from the detector itself (item 3).
- prior-only's gate never uses evidence, so its gated-out share is the same 50% at every q.
- GFS and Tower of Hanoi have small gaps (+5% to +18%) because they hold so few clean points
  that the restore rarely has a choice.

## 2. Per-file oracle ceiling (c)

| policy | q | rec (a) | rec (b) | rec (c) | file-hours lost (a) | (b) | (c) |
|---|---|---|---|---|---|---|---|
| SlowBurn | 0 | 0.959 | 1.000 | 1.000 | 6513 | 3708 | 736 |
| SlowBurn | 1 | 1.000 | 1.000 | 1.000 | 5944 | 3712 | 741 |
| prior-only | 0 | 0.959 | 1.000 | 1.000 | 6464 | 3650 | 708 |
| prior-only | 1 | 1.000 | 1.000 | 1.000 | 6564 | 3650 | 708 |
| Bar-On recursive | 0 | 0.957 | 0.999 | 0.999 | 6721 | 3759 | 907 |
| Bar-On recursive | 1 | 0.999 | 0.999 | 0.999 | 6164 | 3759 | 907 |
| GFS | 0 / 1 | 0.574 | 0.574 | 0.574 | 2712 / 2485 | 2097 | 201 |
| GFS equal horizon | 1 | 1.000 | 1.000 | 1.000 | 4653 | 3164 | 339 |

(c) never recovers more than (b), in every cell. The first damaged file is damaged on the start
day, so it needs a snapshot older than the start, which is exactly what (b) needs. The per-file
ceiling therefore buys only work lost: about 5x less than the oracle snapshot and 8x less than
verify_snap, in file-hours.

(File-hours are larger than whole-system hours for (a) and (b) because they sum over every
restored file. Low file-hours for GFS reflect its failed recoveries, which the file-hour
accounting does not penalise.)

## 3. NapierOne false-flag rate (PRE-FIX; superseded by section 6, D71b)

The NapierOne numbers in this section were produced with the validator bug found in D71b (PPMd
zips marked invalid). Kept for the record; the post-fix numbers are in section 6. Synthetic
numbers are unaffected.

Re-simulation of exactly the D67 eval machines of both arms (same tasks and seeds; 480 machines
per arm, 160 per benign rate). Run 12:36 to 14:04, exit 0. Scripts:
paper/scripts/d71_false_flags.py (counting), paper/scripts/d71_false_flag_report.py (tables).
Tables: results/dev_d71_false_flags/*.csv. A version counts as flagged if the detector flags it
(file p <= 0.01) on the day it is written. Descriptive shares, no CIs.

Benign flag rate per version (pooled over benign rates; damaged = true damage, i.e. detection):

| arm | day 0 | rewrite | damaged (detected) |
|---|---|---|---|
| synthetic | 0.033 | 0.021 | 1.000 |
| NapierOne | 0.057 | 0.045 | 0.746 |

By injected benign invalid rate (day 0 and rewrites together):

| arm | rate 0 | rate .01 | rate .05 |
|---|---|---|---|
| synthetic, all types | 0.003 | 0.013 | 0.049 |
| NapierOne, all types | 0.036 | 0.041 | 0.060 |
| NapierOne, zip | 0.397 | 0.405 | 0.428 |
| NapierOne, all types except zip | 0.0004 | 0.005 | 0.025 |

Per file type, NapierOne at rate 0: zip 0.397, bin 0.003, every other type 0. Zip versions are
99% of NapierOne benign flags at rate 0, 88% at .01 and 63% at .05. Injected benign invalid
versions are never flagged on NapierOne csv, txt or bin (rate stays 0 / 0 / 0.003 at .05), while
on synthetic bytes every type tracks the injected rate (about .05 at .05).

Per machine (benign versions):

| arm | rate | median flag rate | p90 | median flagged versions | share with any day-0 flag |
|---|---|---|---|---|---|
| synthetic | 0 | 0.002 | 0.006 | 2 | 0.38 |
| synthetic | .01 | 0.013 | 0.018 | 9 | 0.61 |
| synthetic | .05 | 0.049 | 0.061 | 34 | 0.94 |
| NapierOne | 0 | 0.036 | 0.045 | 23 | 0.91 |
| NapierOne | .01 | 0.041 | 0.052 | 26 | 0.93 |
| NapierOne | .05 | 0.061 | 0.074 | 38 | 0.98 |

Clean snapshots (day 14 to start - 1) holding at least one flagged benign version:

| arm | rate 0 | rate .01 | rate .05 |
|---|---|---|---|
| synthetic | 0.09 | 0.36 | 0.84 |
| NapierOne | 0.87 | 0.90 | 0.96 |

Reading:
- The JOB 3 explanation holds in direction and size: at rate 0, 87% of clean NapierOne snapshots
  hold a flagged benign version against 9% on synthetic bytes. Section 1 shows that a clean
  snapshot with a flagged version is skipped by verify_snap and costs work lost, not recovery.
  NapierOne at every rate sits above synthetic at rate .05 on this measure, the cell where
  section 1 found verify_snap 134% behind the oracle.
- The cause is one file type, not real bytes in general. Benign NapierOne zip files are flagged
  40% of the time; every other NapierOne type is flagged at or below its synthetic rate
  (largest excess: mp3 at rate .05, 0.052 vs 0.047). This is a detector property on real zip files (high entropy containers) and is
  reported, not fixed (no detector or threshold change on DEV per the D71 spec).
- Second difference: true damage is detected in 75% of NapierOne damaged versions against 100%
  on synthetic (bin 0.40, csv 0.69, jpg 0.61, txt 0.72). That raises missed damage, which section
  1 identifies as the only recovery failure mode with a clean snapshot held. It did not show up
  as a recovery loss in JOB 3 under count budgets, but it is a caveat on any NapierOne recovery
  number.
- The injected benign rate is a weaker knob on NapierOne than on synthetic bytes, because its
  invalid versions on text-like types are not detected. The benign-rate axis therefore does not
  mean the same thing in the two arms.

## 4. JOB 3 byte-budget comparison in the report script

Done (cdbbc81). paper/scripts/overnight/d67_report.py now writes
results/dev_d67_compare/bytes_c1_pooled.csv and bytes_slowburn_vs.csv. The regenerated numbers
equal the ad hoc ones (NapierOne vs prior-only +0.0385, -4.68%; synthetic +0.0857, -16.16%).
The ad hoc entry in OVERNIGHT_REPORT.md is marked superseded.
Post-D71b regeneration: NapierOne +0.045, -9.67% (section 6); synthetic unchanged.

## 5. Bar-On Table 3 discrepancy

What differs: Table 3 ("Recursive(G*, K*) for k = 2^(m+1)") gives for m <= 6 the G* as the
smallest root of x^(k/2) - x - 1. The paper defines G* as the minimiser of r(G, K*), the max of
(1a), (1b), (1c). For m = 1 to 4 that root is not the minimiser:

| k | G (Table 3) | G (argmin r, ours) | Table efficiency | k r at our G | (k+1) r, Table G | (k+1) r, our G | sim. efficiency, Table G | sim., our G |
|---|---|---|---|---|---|---|---|---|
| 4 | 1.6180340 | 1.3247180 | 1.5278640 | 1.2988718 | 1.9098301 | 1.6235898 | 1.9098301 | 1.6235898 |
| 8 | 1.2207441 | 1.1938591 | 1.4466199 | 1.4028768 | 1.6274474 | 1.5782365 | 1.6274474 | 1.5782365 |
| 16 | 1.0969816 | 1.0918177 | 1.4145223 | 1.3938594 | 1.5029300 | 1.4809757 | 1.5029300 | 1.4809757 |
| 32 | 1.0457510 | 1.0447091 | 1.3999822 | 1.3907721 | 1.4437316 | 1.4342337 | 1.4437316 | 1.4342337 |

- **Size of the difference**, at our G vs the Table's G: 15.0% lower at k = 4, 3.0% at k = 8,
  1.5% at k = 16 and 0.7% at k = 32.
- **Not an implementation error.** Our r(G, K*) evaluated at the Table's own G reproduces the
  Table's efficiency column to 1e-9: Table efficiency = k r(G), i.e. the q k/(k+1)
  normalisation. Table 4 rows k = 3, 7, 15 match the same way (1.145898034, 1.31843376,
  1.408092224).
- **Not discretisation.** Every number above is continuous time. The simulated efficiency
  (`checkpointing.efficiency`: schedule played out, the max gap measured at every update) equals
  (k+1) r at both G values. So the schedule really is more efficient at our G, independent of
  the r formula.
- **Why:** at the Table's G, (1a) and (1b) are tight (for k = 4, both equal 0.381966 at the
  golden ratio). But (1b) = G^-1 - G^-3 is not monotone, and the max over (1a)-(1c) is lower
  where (1b) and (1c) meet (k = 4: plastic number 1.3247, (1b) = (1c) = 0.324718, (1a) = 0.245).
  The Table's closed form appears to assume (1a) and (1b) bind for every m; for m <= 4 that is
  not where the minimum is.
- **Effect on our runs: none.** Table 3 covers k = 2^(m+1) (k = 4, 8, 16, ...). Our budgets use
  k = K - 1 = 3, 5, 7, 11, where the minimiser is the one used.
  - Daily-discretised efficiency at those k: 1.52898 / 1.47201 / 1.50902 / 1.47591, against
    continuous 1.52786 / 1.47073 / 1.50678 / 1.47400 (at most +0.15%).
  - The k = 3 and 7 rows match Table 4 exactly.
- **Caveat:** this rests on our reading of (1a)-(1c) and of the Recursive update pattern. The
  simulation check rules out an error in the r formula but not a misreading of the construction.
  Table 4 matching at k = 3, 7, 15 is the evidence that the construction is read correctly.

## 6. D71b: zip ground truth, validator fix, old vs new

Rule, check and fix: OPEN_QUESTIONS D71b (5cc9e04, amendment 133868f); fix e44df6e. The flagged
benign zip versions were the 2 PPMd zips of the 5-file DEV zip pool; Python zipfile raises
NotImplementedError on PPMd, 7z t reads all 5, the flag came from the validity bit (file p 0.006,
0.244 with validity forced to 1). Verdict: validator bug. PPMd members are now decoded (pyppmd)
and CRC-checked; the NapierOne detector was rebuilt from the unchanged config and seed (flag
alpha 0.01 unchanged; old detector results/detector_napierone_v1). Reruns 15:37 to 17:46, exit 0.

Detector, file-level AUROC (lgbm_validity; results/detector_napierone/auroc_d71b_old_vs_new.csv):
zip 0.884 -> 1.000 (striped 10%), all 9 types uniform mean 0.985 -> 0.997; other types move by at
most 0.016 (bin 0.979 -> 0.969). Benign zip invalid rate in the detector test split 0.233 -> 0.

D67 NapierOne arm, count budgets (results/dev_d67_compare vs results/dev_d67_compare_v1):

| quantity | pre-fix | post-fix |
|---|---|---|
| SlowBurn recovery / work lost (h) | 0.9999 / 2915 | 0.9999 / 1724 |
| prior-only recovery / work lost (h) | 0.9998 / 2873 | 0.9998 / 1957 |
| C3' SlowBurn vs prior-only, work lost | +1.5% [+0.2, +2.8] | -11.9% [-13.4, -10.5] |
| C2 SlowBurn vs GFS, work lost | +7.9% [+3.8, +12.2] | -34.4% [-37.7, -30.8] |
| C2 SlowBurn vs Tower of Hanoi, work lost | -2.3% [-5.3, +0.9] | -35.7% [-38.3, -32.9] |
| C2 recovery vs GFS / ToH | +0.426 / +0.427 | +0.426 / +0.427 |
| byte budgets, SlowBurn vs prior-only | +0.039 rec, -4.7% | +0.045 rec, -9.7% |

Post-fix, C3' holds in every world (-10.5% to -13.5%) and C2 in every world against both fixed
schedules. Synthetic bytes for comparison: C3' -9.0%, C2 -27.6% / -30.2%.

D71 item 3, NapierOne arm (results/dev_d71_false_flags vs results/dev_d71_false_flags_v1):

| quantity | pre-fix | post-fix | synthetic |
|---|---|---|---|
| benign flag rate, rate 0 / .01 / .05 | 0.036 / 0.041 / 0.061 | 0.0004 / 0.007 / 0.030 | 0.003 / 0.013 / 0.049 |
| benign zip flag rate, rate 0 | 0.397 | 0 | 0 |
| clean snapshots holding a flagged version, rate 0 / .01 / .05 | 0.88 / 0.90 / 0.96 | 0.005 / 0.24 / 0.71 | 0.09 / 0.36 / 0.84 |
| damaged versions detected | 0.746 | 0.947 | 1.000 |

Damage detection per type post-fix: bin 0.88, csv 0.83, jpg 0.94, txt 0.94, mp3 0.97, docx,
png, zip, zlib 1.00. The rise is not a threshold change: the raw score needed for file p <= 0.01
is 0.99996 before and 0.99997 after. It comes from the retrained model's scores; the likely
reason (not tested separately) is that the 5 benign PPMd training zips no longer carry
validity 0, so the model no longer learns that an invalid file can be benign.

Still true post-fix: injected benign invalid versions of NapierOne csv and txt are never flagged
(0 at rate .05; bin 0.003), so the benign-rate axis is weaker on NapierOne than on synthetic
bytes for those types. At rate 0 NapierOne now has fewer benign flags than synthetic bytes
(synthetic bin is flagged at 0.022).

### 6a. Caveats on every NapierOne C2 / C3' number above (team, 2026-10-23)

- Injected benign invalid csv/txt versions are never flagged on NapierOne, so the benign-rate
  stress axis is weaker there than on synthetic bytes. The larger NapierOne effects (C3' -11.9%
  vs synthetic -9.0%; C2 -34.4% / -35.7% vs -27.6% / -30.2%) may partly reflect a lower effective
  false-flag rate, not only real-byte behaviour.
- The NapierOne DEV pools are small (zip = 5 files, png 5, zlib 5, docx 13, others 14 to 15).
  All NapierOne numbers are provisional until the pools are enlarged under the D75 rule.
- C2 here is against the default GFS / Tower of Hanoi configurations only. It is restated against
  Bar-On recursive, Bar-On round robin and the equal-horizon GFS / Tower of Hanoi variants on
  both byte arms by D72-C2R (OPEN_QUESTIONS), right after D72.
