# Overnight report, 2026-10-23

DEV only. No test set, no frozen_v2, no reselection of w or thresholds. Every run below was
pre-registered in OPEN_QUESTIONS.md and committed before its code or run. CIs are 95%
machine-cluster bootstrap (clusters = world x true start x rep, 2000 resamples, seed 0),
paired on identical machines. "Work lost" is whole-system hours; a failed recovery is charged
everything since day 0, so lower is better and failures are not rewarded.
`work_lost_rel` = (sum A - sum B) / sum B.

## D-number mapping (deviation)

D67 was already the NapierOne integration rule, so the team's numbering shifted by one:

| team job | team label | registered as |
|---|---|---|
| JOB 1 equal-horizon fairness | "D67" | D68 (+ amendment) |
| JOB 2 Bar-On/Shamir checkpointing | "D68" | D69 |
| JOB 3 NapierOne integration | D67 | D67 |
| JOB 4 read D66 | D66 | D66 (+ r amendment) |
| JOB 5 Pareto summary | "D69" | D70 |

## Queue log

From results/overnight_queue.log (one job at a time, floor 45 GB):

```
2026-10-23T01:10:04+05:30 overnight queue armed: waiting for JOB 3 (D67 arms) before D68
2026-10-23T02:34:12+05:30 JOB 3 arms done: exit 1 / exit 1
2026-10-23T02:34:12+05:30 START dev_d68_equal_horizon attempt 1 (free 82 GB)
2026-10-23T02:54:56+05:30 END dev_d68_equal_horizon attempt 1 exit 0
2026-10-23T02:55:46+05:30 START dev_d69_full attempt 1 (free 80 GB)
2026-10-23T03:23:25+05:30 END dev_d69_full attempt 1 exit 0
2026-10-23T03:23:25+05:30 START dev_d69_worst attempt 1 (free 67 GB)
2026-10-23T03:28:45+05:30 END dev_d69_worst attempt 1 exit 0
2026-10-23T03:28:45+05:30 START dev_d69_delay_grid attempt 1 (free 67 GB)
2026-10-23T03:44:19+05:30 END dev_d69_delay_grid attempt 1 exit 0
2026-10-23T03:44:19+05:30 START dev_d67_full_synthetic attempt 2 (free 66 GB)
2026-10-23T05:14:40+05:30 END dev_d67_full_synthetic attempt 2 exit 0
2026-10-23T05:14:40+05:30 START dev_d67_full_napierone attempt 2 (free 75 GB)
2026-10-23T06:15:15+05:30 END dev_d67_full_napierone attempt 2 exit 0
2026-10-23T06:15:15+05:30 queue drained
```

No job was skipped for disk. Free space stayed between 63 and 82 GB (floor 45).

## JOB 1: equal-horizon fairness (D68)

Status: done, exit 0 (02:34 to 02:55). Outputs: results/dev_d68_equal_horizon/
(eqh_configs.csv, eqh_vs_slowburn_prior.csv, report.txt).

Feasibility (D68 amendment, recorded before the run): at the grid's assumed bound M = 60, an
equal-horizon configuration exists only for
- `toh_eqh` at K = 8 and 12. It is base 2 at both, so it is identical to the existing Tower of
  Hanoi (H = 63 and 400).
- `gfs_eqh` at K = 12 only, configured as 7 daily, 2 weekly, 3 monthly (H = 76).

K = 4 and 6 are infeasible for both families. Base b > 2 never extends the Tower of Hanoi horizon.

Paired results, all q, verify_snap restore:

| A vs B | pairs | recovery A / B | diff [95% CI] | work lost rel [95% CI] |
|---|---|---|---|---|
| toh_eqh vs slowburn | 24000 | 0.931 / 0.982 | -0.051 [-0.074, -0.029] | -11.1% [-13.4, -8.7] |
| toh_eqh vs prior_only | 24000 | 0.931 / 0.977 | -0.046 [-0.069, -0.025] | -14.1% [-16.3, -11.8] |
| gfs_eqh vs slowburn (K 12) | 12000 | 0.980 / 0.980 | +0.000 [-0.005, +0.005] | -14.4% [-16.6, -12.1] |
| gfs_eqh vs prior_only (K 12) | 12000 | 0.980 / 0.971 | +0.009 [+0.004, +0.015] | -13.9% [-15.7, -11.9] |

By world, toh_eqh vs slowburn:
- early: -0.133 [-0.194, -0.077]
- uniform: -0.090 [-0.148, -0.038]
- late: +0.001 [-0.009, +0.010]
- bursty: +0.019 [+0.013, +0.025]

The guarantee needs the attack to start at least 2d into the trace. Early-world starts violate it.

Surprises:
- At K = 12, a fixed GFS schedule tuned to an equal horizon (7/2/3/0) ties SlowBurn on
  recovery and loses 14% less work. This holds at q = 0 (recovery +0.015 [+0.001, +0.029])
  and at q = 1 (both 1.0; work lost -15.4% [-18.0, -12.8]).
  - So once the fixed baseline is given the right horizon, SlowBurn's advantage at K = 12 is
    gone. Its advantage remains at K = 4 to 8, where no equal-horizon fixed schedule exists.
  - Paper consequence: the "beats GFS / ToH" claim must be scoped to the budgets where the fixed
    schedules cannot reach the bound, or reported against gfs_eqh at K = 12 as a loss on work lost.
- Equal horizon has no work-lost bound, so it is a weak fairness criterion. Keep-first reaches an
  infinite horizon with 2 slots. Recorded in the D68 amendment before the run.

## JOB 2: Bar-On et al. online checkpointing (D69)

Status: done, all three runs exit 0 (dev_d69_full 02:55 to 03:23, dev_d69_worst to 03:28,
dev_d69_delay_grid to 03:44). Outputs: results/dev_d69_compare/{means,paired}.csv and
results/dev_d69_compare_report.txt.

Reproduction (unit tests, before the runs): the closed-form efficiencies match the paper to
1e-6 (q3 = 1.527864, q4 = 1.5398926, q5 = 1.470734; best geometric k = 4 at 1.588361), as do the
two Table 4 rows tested (k = 7, 15). Daily discretisation adds at most 0.15%. The family used at
each budget (k = K - 1):
- `shamir_exact` (closed form) only at K = 4 and 6.
- `shamir_rr` (Round-Robin) and `shamir_recursive` (Recursive(G*, K*)) at all K.

Paired vs SlowBurn, pooled over K:

| grid | restore | policy | recovery diff [95% CI] | work lost rel [95% CI] |
|---|---|---|---|---|
| full (M = 60, all q) | verify_snap | shamir_exact | -0.001 [-0.005, +0.002] | +3.5% [+0.3, +6.9] |
| full | verify_snap | shamir_rr | -0.002 [-0.005, +0.001] | +5.0% [+1.9, +8.1] |
| full | verify_snap | shamir_recursive | -0.001 [-0.004, +0.002] | +2.7% [+0.1, +5.4] |
| full | oracle | shamir_recursive | -0.001 [-0.002, 0.000] | +1.4% [-1.8, +4.5] |
| full, q = 0 | verify_snap | shamir_exact | -0.011 [-0.021, -0.002] | +3.3% [+0.4, +6.5] |
| full, q = 0 | verify_snap | shamir_recursive | -0.002 [-0.010, +0.005] | +0.8% [-1.2, +2.9] |
| worst | verify_snap | shamir_recursive | -0.004 [-0.007, -0.001] | -11.4% [-13.1, -9.7] |
| worst | verify_snap | shamir_exact | +0.001 [-0.004, +0.005] | -11.5% [-14.6, -8.1] |

Delay grid (assumed bound M varied, q = 1, verify_snap), shamir_recursive vs SlowBurn. Bar-On
recovery is 0.991 in every row because it does not use M.

| assumed M | SlowBurn recovery | diff [95% CI] | work lost rel |
|---|---|---|---|
| 7 | 0.134 | +0.857 [+0.852, +0.862] | -55% |
| 14 | 0.408 | +0.583 [+0.575, +0.590] | -43% |
| 30 | 0.642 | +0.349 [+0.341, +0.357] | -29% |
| 60 | 0.991 | +0.000 [-0.006, +0.006] | -0.3% |
| 90 | 0.998 | -0.007 [-0.012, -0.003] | -12% |
| 120 | 0.999 | -0.009 [-0.014, -0.004] | -18% |
| soft 60, tail 0.1 | 1.000 | -0.009 [-0.014, -0.005] | -51% |

Restricted to trials whose true delay exceeds the assumed M, Bar-On beats SlowBurn by +0.61
[+0.60, +0.62] (recursive, q = 1). The oracle restore gives the same numbers, so this is
retention, not restore choice. At q = 0 under verify_snap the Bar-On advantage disappears
(-0.024 [-0.030, -0.018]): without flags the restore falls back on the assumed-delay rule and
cannot use the old checkpoints Bar-On holds. The oracle restore shows they were held
(+0.25 [+0.25, +0.26]).

Surprises:
- A detector-free, horizon-free worst-case schedule ties SlowBurn within 0.002 recovery when M
  is right. It costs 3 to 5% more work lost on the full grid and 11% less on the worst grid.
- Even with perfect detection (q = 1), SlowBurn at assumed M = 7 recovers only 0.134. It has
  already discarded the clean point, so no detector can save it. This is the D65 trade-off in its
  sharpest form, and Bar-On removes it.
- Paper consequence: Bar-On et al. is the baseline to beat, not GFS or ToH. The honest framing is
  that SlowBurn buys up to 5% work lost and a hard dependence on M, against a schedule that is
  M-free.

Deviations:
- The paper's Table 3 rows at k = 4, 8, 16 disagree with its own rule for G*. I follow the rule.
- The efficiency targets in the request are in the q k / (k + 1) normalisation (Tables 3 and 4).
  Both normalisations are tested.
- The exact optimal schedule exists only for k = 3, 4, 5 (K = 4 and 6 here).

## JOB 3: NapierOne integration (D67)

Status: done on attempt 2. Attempt 1 failed for both arms (exit 1 at 02:34, after about 80
minutes in the tuning stage) on a byte-accounting bug.
- Cause: `ByteIndex` refused traces where a chunk disappears and later reappears. Real and
  synthetic file bytes repeat chunks; token mode never does.
- Fix (f0b39f7, no spec change): such traces use the exact union of chunk sets. Token-mode
  results are bit-identical.
- Attempt 2: synthetic 03:44 to 05:14, NapierOne 05:14 to 06:15, both exit 0.
- Outputs: results/dev_d67_compare/ (c1_by_world, c1_pooled, c2_slowburn_vs_fixed,
  c3_evidence_reduction) and results/dev_d67_report.txt.
- Attempt-1 logs: results/dev_d67_full_*_run_attempt1.log.

Arms, all at the same seed, worlds, reps, policies and budgets, with w = 0.75 and verify_snap:
- abstract q: dev_d64a_full, the current claims.
- synthetic bytes with the synthetic detector.
- NapierOne benign bytes (sim_dev half) with NapierOne damage (sim_dev families
  LORENZ/WANNACRY/MAZE) and the detector trained on NapierOne.

The flag rule is file p <= 0.01, the frozen alpha.

Detector AUROC (run earlier in this session, 9 types, NapierOne vs synthetic training data):
- chunk level: 0.985 to 0.988 vs 0.997 to 1.0
- file level: 0.978 to 0.986 vs 1.0
- weakest NapierOne types at file level (striped 10%): zip 0.884, bin 0.979

C1, recovery, count budgets, pooled:

| policy | abstract q | synthetic bytes | NapierOne bytes |
|---|---|---|---|
| slowburn | 0.986 | 1.000 | 1.000 |
| prior_only | 0.984 | 1.000 | 1.000 |
| gfs | 0.573 | 0.574 | 0.574 |
| tower_of_hanoi | 0.568 | 0.573 | 0.573 |

C1, recovery, byte budgets (14/30/90-day multipliers), pooled:

| policy | abstract q | synthetic bytes | NapierOne bytes |
|---|---|---|---|
| slowburn | 0.671 | 0.749 | 0.513 |
| prior_only | 0.629 | 0.663 | 0.475 |
| oracle | 0.774 | 0.811 | 0.567 |
| gfs | 0.536 | 0.552 | 0.353 |

C2, SlowBurn vs fixed schedules, count budgets:

| arm | vs | recovery diff [95% CI] | work lost rel [95% CI] |
|---|---|---|---|
| abstract q | gfs | +0.413 [+0.395, +0.433] | -23.4% [-26.8, -19.8] |
| synthetic bytes | gfs | +0.426 [+0.408, +0.445] | -27.6% [-31.0, -24.0] |
| NapierOne bytes | gfs | +0.426 [+0.408, +0.446] | **+7.9% [+3.8, +12.2]** |
| abstract q | ToH | +0.418 [+0.408, +0.430] | -26.7% [-29.1, -24.2] |
| synthetic bytes | ToH | +0.427 [+0.416, +0.439] | -30.2% [-32.8, -27.5] |
| NapierOne bytes | ToH | +0.427 [+0.416, +0.439] | -2.3% [-5.3, +0.9] |

C3', SlowBurn vs prior-only (the evidence effect):

| arm | budgets | recovery diff [95% CI] | work lost rel [95% CI] |
|---|---|---|---|
| abstract q | count | +0.002 [+0.000, +0.003] | -4.7% [-5.5, -3.9] |
| synthetic bytes | count | -0.000 [-0.000, +0.000] | -9.0% [-10.1, -7.9] |
| NapierOne bytes | count | +0.000 [+0.000, +0.000] | **+1.5% [+0.2, +2.8]** |
| abstract q | bytes | +0.042 [+0.033, +0.052] | -7.6% [-9.1, -6.0] |
| synthetic bytes | bytes | +0.086 [+0.074, +0.098] | -16.2% [-17.9, -14.3] |
| NapierOne bytes | bytes | +0.039 [+0.027, +0.050] | -4.7% [-6.2, -3.2] |

Worlds grid: the per-world rows (same machines, subsets of the full grid) are in
c1_by_world.csv, c2_slowburn_vs_fixed.csv and c3_evidence_reduction.csv. C3' on NapierOne
count budgets by world:
- bursty: +2.4% [+0.1, +4.8]
- early: +0.3% [-1.3, +1.9]
- late: +0.8% [-2.2, +3.6]
- uniform: +2.2% [-0.2, +4.8]

Findings:
- Recovery claims (C1, the C2 recovery gap) carry over to real benign bytes unchanged under
  count budgets.
- The work-lost claims do not:
  - On NapierOne bytes, SlowBurn loses 1.5% MORE work than prior-only under count budgets, where
    it lost 4.7% (abstract) and 9.0% (synthetic) less.
  - It loses 7.9% more than GFS.
  - prior_only's work lost rises from 2102 h (synthetic) to 2873 h (NapierOne), and SlowBurn's
    from 1912 h to 2915 h, at identical recovery.
  - Most likely cause: more false flags on real benign files (file AUROC 0.98 vs 1.0), which push
    the verified restore point earlier. Benign flag rates per arm were not extracted tonight.
    That is the next diagnostic, not a conclusion.
- Under byte budgets the evidence effect survives on NapierOne (+0.039 recovery, -4.7% work
  lost), but every policy recovers much less (SlowBurn 0.749 to 0.513, oracle 0.811 to 0.567).
  Real files are larger and less compressible, so the same multiplier holds fewer snapshots.
- Paper consequence: C3' (evidence reduces work lost) must be stated as holding under byte
  budgets and on synthetic data. On real benign bytes with count budgets it is reversed (small
  but significant).

Deviations:
- JOB 3 ran after JOBs 1 and 2 because attempt 1 failed. Attempt 1 actually started before
  JOB 1, against the requested order.
- The worlds grids are reported as subsets of the full grid's machines, not separate runs.
- zip, png and zlib have only 5 DEV NapierOne files of at most 1 MiB each, so the content
  pool repeats files for those types.
- The byte-budget paired comparison was computed ad hoc after d67_report.py; the numbers above
  come from method_v2.policy_vs_policy on the byte rows.

## JOB 4: D66 product retention audit (read after D68, as required)

Status: run earlier (exit 0); read at 03:00 after D68 results existed. Outputs:
results/dev_d66_retention_audit/ (audit_rows.csv.gz, audit_curves.csv, audit_thresholds.csv,
report.txt). 160 machines, 33 product rules (main rules plus r in {2, 5, 25, 100}), FSL churn,
48 days of FSL replayed circularly.

First grid delay where the clean point is no longer held (held < 0.5; identical at < 0.1):

| product | held drops at | recovery q = 1 drops at |
|---|---|---|
| dropbox_30d, gdrive_30d_100v, onedrive_personal_25v_30d | 30 d | 30 d |
| dropbox_180d | 180 d | 180 d |
| dropbox_365d | 365 d | 365 d |
| onedrive_personal_25v, onedrive_business_500v | never (to 400 d) | never |
| restic_docs_dwmy / within | 0.67 held at 365 d | same |
| restic_keep_within_7d | 7 d | 7 d |
| restic_keep_last_1 | always 0 | always 0 |
| gdrive_30d_100v_created | 1 d (held 0.019 at d = 1) | 1 d |
| netapp_arpai | q = 0: always 0; q = 1: never | follows detection |

r amendment (extra damaged versions per file, parameter only):
- A count-limited product loses the clean version at every delay once r reaches its version
  limit: onedrive_personal_25v and 25v_30d at r = 25 and 100; gdrive_30d_100v at r = 100.
- Below the limit (r = 2, 5) nothing changes.
- onedrive_business_500v is unaffected up to r = 100.

Surprises and caveats:
- Recovery at q = 0 drops to 0.194 at a 60-day delay for every product that still holds the clean
  point (restic 0.75), and to 0 beyond. That is our restore rule (assumed delay 60 days, no
  flags), not the product. The `held` columns are the retention measure to cite.
- Google Drive with the 30 days counted from version creation retains almost nothing. FSL
  churn is so low that the clean version is usually already older than 30 days when it gets
  replaced. Which reading Google uses is not settled by its docs, so both are reported.
- FSL churn is very low (0 to 9% of long-lived files ever rewritten in 48 days), which makes
  count-limited products look stronger than they would on a busy machine.

## JOB 5: Pareto summary (D70)

Status: done, committed (93c376d). Outputs in paper/generated/:
- pareto_points.csv
- pareto_reference_products_d66.csv
- fig_pareto_{verify_snap,oracle}[_q0|_q1].png

Data: D69 full and D68 count budgets, mean recovery vs mean work lost per world x K x policy, 16
panels per figure. D66 products are plotted as grey references (different machines; not in the
Pareto computation).

Pareto memberships out of 16 panels, all q:

| restore | slowburn | prior_only | shamir_exact | shamir_rr | shamir_recursive | tower_of_hanoi | toh_eqh | gfs_eqh |
|---|---|---|---|---|---|---|---|---|
| verify_snap | 11 | 5 | 6 | 7 | 7 | 6 | 6 | 4 |
| oracle | 2 | 5 | 5 | 3 | 6 | 2 | 0 | 0 |

- SlowBurn is on the frontier most often under its own restore (11/16), but only 2/16 under the
  oracle restore. Part of SlowBurn's frontier position comes from its restore, not its retention.
- toh_eqh equals tower_of_hanoi at K = 8 and 12 (both base 2), so ties are counted twice.
- GFS (unadjusted) is on the frontier once (q = 0, verify_snap); plain ToH at K = 4 and 6 never is.

## Still queued or held

- FSL download continues: through 2011-12-01 at 06:11 (data/ at 78.9 GB of the 100 GB cap).
- Restic, the extensionless check and the fresh test set with frozen_v2.yaml are held for approval.
