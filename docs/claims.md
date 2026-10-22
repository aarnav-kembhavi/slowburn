# Claims (DRAFT wording, team to confirm; numbers from the adopted pipeline, 2026-10-22)

All numbers are DEV (seed 202), count budgets K in {4, 6, 8, 12}, method v2 = blind weight 0.75
with the fixed 0.8 gate, restored with the ADOPTED restore (D64a verify_snap: every version in a
candidate snapshot is checked against its shared write-time flag, D29 any-flag rule, select),
for EVERY policy (D64b). Brackets: 95% machine-cluster bootstrap CIs. The fresh TEST set (P5)
decides; nothing here is a test result. Old-vs-new tables: `results/dev_d64a_*/old_vs_new*.csv`.
Decisions: D59, D60, D64a, D64b, team list of 2026-10-22.

## Thesis

"Against slow ransomware, retention outcomes are governed by the assumed discovery delay, not by
detector quality."

FLAG (team to decide): "governed by ... not by" may be too strong given C3' (evidence does buy
about 5% less work lost). Alternative: "are dominated by the assumed discovery delay rather than
by detector quality".

## Claims

**C1. Timing-aware budgeted retention beats fixed schedules on recovery, even with a blind
detector.** Worlds grid (`results/dev_d64a_full`, all q and benign rates), clean recovery
bursty / early / late / uniform: prior-only 0.9888 / 0.9858 / 0.9810 / 0.9822, SlowBurn
0.9892 / 0.9865 / 0.9838 / 0.9860, GFS 0.5760 / 0.6146 / 0.5356 / 0.5666, Tower of Hanoi
0.6003 / 0.5274 / 0.5941 / 0.5498. Worst-case timing grid (starts 112-143 x delays 7-60, q in
{0, 0.5, 1}, `results/dev_d64a_worst_all`, every policy at w 0.75): prior-only 0.9785,
SlowBurn 0.9793, GFS 0.6025, Tower of Hanoi 0.5926; at q = 0 prior-only 0.9456, SlowBurn
0.9450. Not circular: the policy's timing prior is near flat and differs from every simulator
world.

**C2. ... with less work lost.** Same grid, whole-system work lost (h) bursty / early / late /
uniform: prior-only 2325.4 / 1813.1 / 2394.0 / 2061.7, SlowBurn 2189.2 / 1729.4 / 2301.2 /
1968.6, GFS 2939.1 / 1783.0 / 3480.2 / 2489.5, Tower of Hanoi 3111.0 / 1990.6 / 3493.5 / 2580.3.
Paired, SlowBurn vs GFS: -25.5% [-31.2, -18.8] / -3.0% [-9.5, +3.9] / -33.9% [-38.8, -28.7] /
-20.9% [-27.1, -12.8], pooled -23.4% [-26.8, -19.8]; vs Tower of Hanoi pooled -26.7% [-29.1,
-24.2] (every world significant). Prior-only vs GFS, early world: +1.7% [-5.1, +8.6]
(`results/dev_d64a_full/c2_vs_fixed_schedules.csv`).
FLAG (team to decide): under the adopted restore C2 does NOT hold in the early world against
GFS (SlowBurn not significantly lower; prior-only point estimate higher). Old restore: SlowBurn
1464.0 vs GFS 1781.8 there. The adopted restore raised prior-only / SlowBurn work lost by
24.8% / 27.1% on this grid and GFS by 0.03%, because GFS rarely has a gated clean candidate to
lose.

**C3'. Detector evidence reduces work lost by about 5% at equal recovery, and is non-inferior
on recovery when the detector is blind.** Full grid: SlowBurn 0.9864 / 2047.1 h vs prior-only
0.9845 / 2148.5 h, -4.72% [-5.46, -3.93] (old restore -6.42%; change +1.70 points), recovery
+0.0019 [0.0004, 0.0034]. By q: 0 / 0.2 / 0.5 / 0.9 / 1: +0.85% [+0.03, +1.65] / -1.45% /
-5.60% / -8.59% / -9.26%; by benign rate 0 / 0.01 / 0.05: -11.96% / -6.71% / +1.12% [-0.18,
+2.40]. Blind: at q = 0 all 8 units (4 worlds, 4 budgets on the worst-case grid) within 1 point
of prior-only and not significantly worse after Holm (largest excess 0.00625, K = 8 worst case,
Holm p 0.629; worlds: 0.00583 bursty, Holm p 0.392; `results/dev_d64a_blind_worst/
d57_units.csv`). NOTE: with a blind detector SlowBurn now loses slightly MORE work than
prior-only on the full grid (+0.85%, CI excludes 0; worst case q = 0: +0.55% [-0.38, +1.47]).

## Findings

**F1. Beyond the assumed bound, recovery is ~0 unless the detector is near perfect, and even
then it is capped by the fraction of rows where retention kept a clean snapshot.** True delay >
assumed hard bound, SlowBurn recovery at q = 0 / 0.2 / 0.5 / 1: M = 14: 0 / 0 / 0.0026 /
0.1495; M = 30: 0 / 0 / 0.0062 / 0.8891; the q = 1 values equal the clean-retained fraction
(0.1495, 0.8891). Prior-only: M = 14: 0 / 0 / 0.0026 / 0.1568, M = 30: 0 / 0 / 0.0062 / 0.9852,
again equal to its clean-retained fraction (`results/dev_d64a_under`). Measured for prior-only
and SlowBurn only; GFS / Tower of Hanoi beyond the bound wait for the D63 sweep. The earlier
"collapses to 0 even with a perfect detector" was an artifact of the old restore's scan window
(CHANGELOG 2026-10-22). Over-estimating is safe but costs work lost (D52: assumed 90 / 120 vs
60 days, +492.3 / +1084.2 h; old restore, not rerun).

**F2. A never-zero delay tail restores recovery but moves the whole budget to old snapshots.**
Soft tail (D56) under the adopted restore: recovery 0.9980 on the normal grid at 3918.0 h vs
2078.2 h for the hard bound (1.89x; old restore 2.30x) and 1.0 on the worst case (3123.3 vs
2179.2 h). Insensitive to tail weight in 0.02-0.2 (D56, D60). Mechanism (D60): retention, not
the restore gate; the newest clean snapshot the soft-tail DP keeps is 155.4 days back vs 49.8
with the hard bound (K = 12: 139.3 vs 42.6; retention is unchanged by the restore).

**F3. Evidence-gated restore rescues only with a near-perfect detector.** Method v4 (D60:
hard-bound restore that walks back on detected damage, soft tail only in retention) beyond the
bound: q = 1: 1.0 at M = 14 and 30; q <= 0.5: <= 0.006 (q = 0.5: 0.0042 / 0.0062 at M = 14 /
30; q = 0.2 and 0: 0). v4 FAILED on cost: normal-grid work lost 3911.8-3918.1 h vs limit 2286.1
(1.10 x the hard bound's 2078.2; 1.88x; `results/dev_d64a_v4_normal/
d60_scoreboard_vsnap.csv`). Claim "(3) evidence rescues mis-specified delays" was tested
three times and dropped (D55b, D56, D60).

## Pending for the paper

- D65 (v2.1, significance-based snapshot accept rule): one pre-registered iteration; these
  numbers stand unless it is adopted.
- Guideline figure (assumed vs true delay heatmaps, recovery vs work-lost scatter): D63 sweep.
- Fresh TEST confirmation of C1, C2, C3' and F1 (under-estimated rows included).
