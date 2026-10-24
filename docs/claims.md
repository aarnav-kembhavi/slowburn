# Claims (DRAFT wording, team to confirm; numbers from the adopted pipeline, 2026-10-22)

**Data (correction 2026-10-23): every number below uses synthetic benign files and synthetic
damage** (abstract chunk tokens, random-token damage, abstract detector with detection
probability q), unless marked NapierOne. See docs/data_card.md.

**NapierOne check (D67, post-D71b, on the D75 enlarged pools v2, 2026-10-24, DEV): C1, C2 (vs
default GFS / Tower of Hanoi configurations) and C3' hold on NapierOne bytes, with much smaller
effects than on the small v1 pools.** The v1 numbers (pools of 5 to 15 files per type, marked
provisional) are superseded; results/D75_REPORT.md has both side by side. Arms on the same
machines, w 0.75, verify_snap: the abstract q grid (the numbers below), synthetic bytes with the
synthetic detector, NapierOne benign bytes (v2 pools, 59 to 115 DEV files per type) with
NapierOne damage and the detector trained on NapierOne (file flag p <= 0.01, unchanged).
**Caveats on every NapierOne number (D75, v2 pools):** (1) the detector flags 0.875 of truly
damaged NapierOne versions (txt 0.59, bin 0.66, csv 0.79, every other type >= 0.97; synthetic
1.000); missed damage is the only recovery failure mode when a clean snapshot is held (D71 item
1). (2) Benign false flags are higher than on synthetic bytes at injected rate 0 (0.017 vs
0.002; png 0.167, from 9 of 54 png files failing validity), so half of all clean snapshots hold
a flagged version; injected benign invalid csv/txt versions are still never flagged (so the
false flag stress axis is weaker there). (3) zip and png v2 DEV pools stay below 100 files (69,
59): not enough unused NapierOne files. (4) Strict UTF-8 fails on 55% of the new benign csv and
33% of the new txt files; this does not raise benign csv flags (0.000) but txt benign flags are
0.010 (known limitation, validator unchanged).

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

**C2. ... with less work lost than the default GFS / Tower of Hanoi configurations.** Scope
(team decision 2026-10-23): C2 is stated against the default GFS / Tower of Hanoi configurations.
**Restated against stronger baselines (D72-C2R, 2026-10-24, synthetic / NapierOne bytes, count
budgets; results/D72_REPORT.md section 2):** against Bar-On recursive -4.4% [-7.5, -1.1] /
-3.4% [-6.3, -0.3] and Bar-On round robin -6.8% / -5.1% (recovery equal): holds pooled but
small and not uniform (early world +10% to +11%, SlowBurn worse, CI above 0). Against the
equal-horizon configurations (horizon >= M; GFS-eqh exists only at K = 12, ToH-eqh at K 8 and
12) **C2 fails**: SlowBurn loses more work, vs GFS-eqh +16.1% [+12.1, +20.1] / +6.9% [+3.6,
+10.5] at equal recovery, vs ToH-eqh +10.1% [+6.3, +13.9] / +3.0% [-0.5, +6.4] with recovery
+0.059. The +0.43 recovery advantage over default GFS / ToH does not survive any stronger
baseline. NapierOne numbers carry the caveats in the header.
Lower work lost than default GFS / Tower of Hanoi pooled (-23.4% vs GFS,
-26.7% vs Tower of Hanoi) and in 3 of 4 attack worlds; in the early world SlowBurn vs GFS is
-3.0% [-9.5, +3.9], not significant. Whole-system work lost (h) bursty / early / late /
uniform: prior-only 2325.4 / 1813.1 / 2394.0 / 2061.7, SlowBurn 2189.2 / 1729.4 / 2301.2 /
1968.6, GFS 2939.1 / 1783.0 / 3480.2 / 2489.5, Tower of Hanoi 3111.0 / 1990.6 / 3493.5 / 2580.3.
Paired SlowBurn vs GFS: -25.5% [-31.2, -18.8] / -3.0% [-9.5, +3.9] / -33.9% [-38.8, -28.7] /
-20.9% [-27.1, -12.8], pooled -23.4% [-26.8, -19.8]; vs Tower of Hanoi pooled -26.7% [-29.1,
-24.2], every world significant (`results/dev_d64a_full/c2_vs_fixed_schedules.csv`). Reported
as is (team decision 2026-10-22, no post hoc rescue).
NapierOne bytes (D67 on the D75 v2 pools, count budgets): recovery vs GFS +0.425 [+0.407,
+0.444], vs Tower of Hanoi +0.428 [+0.416, +0.440]; work lost vs GFS **-14.0% [-18.3, -9.4]**,
vs Tower of Hanoi **-19.6% [-23.0, -16.0]**; by world vs GFS bursty -13.8%, **early +4.2%
[-2.9, +11.7] (not significant)**, late -25.4%, uniform -11.3%; vs Tower of Hanoi every world
significant. Synthetic bytes: -27.6% [-31.0, -24.0] / -30.2% [-32.8, -27.5]. **C2 (vs default
GFS / Tower of Hanoi configurations) holds on NapierOne bytes, with a smaller effect than on
synthetic bytes and not in the early world vs GFS.** NapierOne caveats: see the header. (v1
pools, superseded: -34.4% / -35.7%; pre-D71b, withdrawn: +7.9% / -2.3%.)

**C3'. Evidence reduces work lost by 4.7% [3.9, 5.5] at equal recovery. With a blind detector
(q = 0), recovery is non-inferior (pre-registered, 8 of 8 units) but work lost is 0.85% [0.03,
1.65] higher than prior-only.** Both halves go in the paper. Full grid: SlowBurn 0.9864 /
2047.1 h vs prior-only 0.9845 / 2148.5 h, -4.72% [-5.46, -3.93] (old restore -6.42%), recovery
+0.0019 [0.0004, 0.0034]. By q 0 / 0.2 / 0.5 / 0.9 / 1: +0.85% [+0.03, +1.65] / -1.45% / -5.60%
/ -8.59% / -9.26%; by benign rate 0 / 0.01 / 0.05: -11.96% / -6.71% / +1.12% [-0.18, +2.40].
Blind units (4 worlds, 4 budgets on the worst-case grid, D57): all within 1 point of prior-only
and not significantly worse after Holm (largest excess 0.00625, K = 8 worst case, Holm p 0.629;
worlds 0.00583 bursty, Holm p 0.392; `results/dev_d64a_blind_worst/d57_units.csv`). Worst case
q = 0 work lost: +0.55% [-0.38, +1.47].
NapierOne bytes (D67 on the D75 v2 pools), SlowBurn vs prior-only: count budgets recovery
-0.000 [-0.001, 0.000], work lost **-3.8% [-5.3, -2.4]** (synthetic bytes -9.0% [-10.1, -7.9]);
every world significant (bursty -5.0%, early -3.3%, late -4.1%, uniform -2.5%); by benign rate
0 / 0.01 / 0.05: -7.3% / -5.2% / +0.1% [-1.3, +1.6]. Byte budgets: recovery +0.077 [+0.064,
+0.091], work lost -11.7% [-13.8, -9.5]. **C3' holds on NapierOne bytes, smaller than on
synthetic bytes, and vanishes at the highest injected benign rate.** NapierOne caveats: see the
header. (v1 pools, superseded: -11.9%; pre-D71b, withdrawn: +1.5%, the PPMd validator bug.)

## Guarantee (theory, docs/theory.md, NEEDS HUMAN REVIEW)

**G1. Tower of Hanoi with K snapshots holds a clean snapshot at discovery for every delay
d <= 2^(K-2) - 1 days, provided the attack started at least 2d days into the history, with
whole-system work lost <= 3d (Theorem 2(a)).** Numerical check: 48,686 (K, discovery day,
delay) cases, K in {4, 5, 6, 8} (2,381 / 4,715 / 9,239 / 32,351), 600 days, every d from 0 to
2^(K-2) - 1 inclusive (3 / 7 / 15 / 63) with s >= 2d, 0 failures (`tests/test_theory.py`).
Scope, stated wherever G1 is cited:
- It is about what is HELD, not what is restored. D63 (K = 8, delay 7, q = 0): Tower of Hanoi
  holds a clean snapshot in every row but the restore recovers 0.80.
- Its range is the rotation's own horizon 2^(K-2) - 1, not the assumed bound M. It says nothing
  about any policy at d = M.
- It does not cover the DP policies. SlowBurn's backbone is R = round(0.25 K) slots, so the
  inherited guarantee (Theorem 2(c)) covers d = 0 at K = 8 and d <= 1 at K = 12, nothing at
  K = 4 (R = 1). Prior-only and SlowBurn have no worst-case guarantee: at K = 8, M = 7, true
  delay 7, both hold no clean snapshot (D63 edge effect), while Tower of Hanoi does.
SlowBurn's fixed-rotation backbone is round(0.25 K) slots (backbone size unchanged), so its
inherited guarantee covers only delay 0 at K = 8. Its recovery comes from the timing prior in
the DP, not from the backbone: 0.98 pooled over q (C1); with a blind detector (q = 0) 0.953 /
0.959 / 0.953 / 0.962 bursty / early / late / uniform (D57 blind grid,
`results/dev_d64a_blind_worst/d57_units.csv`) and 0.9450 on the worst-case grid.
The shorthand "the fixed rotation keeps a clean copy for any discovery delay within its range"
is true only with these three qualifiers (horizon 2^(K-2) - 1, history s >= 2d, held not
restored); do not use it without them.

## Findings

**F1. Beyond the assumed bound, recovery is ~0 unless the detector is near perfect, and even
then it is capped by the fraction of rows where retention kept a clean snapshot.** True delay >
assumed hard bound, recovery at q = 0 / 0.2 / 0.5: 0 / 0 / 0.0026 (M = 14) and 0 / 0 / 0.0062
(M = 30), SlowBurn and prior-only alike. At q = 1, SlowBurn / prior-only: M = 14: 0.1495 /
0.1568; M = 30: 0.8891 / 0.9852, each equal to the policy's clean-retained fraction
(`results/dev_d64a_under`). Evidence-driven retention trades beyond-bound coverage for lower
work lost inside the bound. Fixed schedules (D63, K = 8, benign 0.01, all
under-estimated rows pooled): q = 0: 0 for every policy; q = 1: Tower of Hanoi 0.565,
prior-only 0.333, SlowBurn 0.286, GFS 0.165. With a short bound (M 7 / 14 / 30) Tower of Hanoi
recovers more than SlowBurn at q = 1 (0.708 / 0.634 / 0.525 vs 0 / 0.230 / 0.142, Holm p <
0.05); SlowBurn recovers more at M 60 / 90 (`paper/generated/delay_grid_under_vs_fixed_K8.csv`). The earlier
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

- D65 (v2.1, significance-based snapshot accept rule): REJECTED; step 1 numbers stand, no
  further accept-rule iterations. Reported as a trade-off (team decision 2026-10-22): v2.1 cuts
  SlowBurn work lost by 15.0% [12.5, 17.3] (worst case, q = 0) / 22.1% [20.6, 23.6] (full grid)
  but lowers recovery in every world (bursty / early / late / uniform -0.0122 / -0.0170 /
  -0.0196 / -0.0155; worst case -0.0188 [-0.0238, -0.0144]), failing pre-registered criterion
  (a) (drop <= 0.01). `results/dev_d65_*/v21_vs_step1*.csv`.
- Guideline figure: done (D63, `paper/generated/fig_delay_guideline_*`); caption must state
  the edge effect at true delay = M (D63 outcome).
- Fresh TEST confirmation of C1, C2, C3' and F1 (under-estimated rows included).
