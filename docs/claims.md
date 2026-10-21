# Claims (DRAFT wording, team to confirm; decided 2026-10-22)

All numbers are DEV (seed 202), count budgets K in {4, 6, 8, 12}, method v2 = blind weight 0.75
with the fixed 0.8 gate, unless stated. The fresh TEST set (P5) decides; nothing here is a test
result. Numbers that depend on restore-time verification may change after the q = 1
verification check (D62); this file is updated if they do. Decisions: D59, D60, team list of
2026-10-22.

## Thesis

"Against slow ransomware, retention outcomes are governed by the assumed discovery delay, not by
detector quality."

FLAG (team to decide): "governed by ... not by" may be too strong given C3' (evidence does buy
about 6% less work lost). Alternative: "are dominated by the assumed discovery delay rather than
by detector quality".

## Claims

**C1. Timing-aware budgeted retention beats fixed schedules on recovery, even with a blind
detector.** Worlds grid (`results/dev_v2_method_full_w075`, all q and benign rates), clean
recovery bursty / early / late / uniform: prior-only 0.9860 / 0.9815 / 0.9758 / 0.9791,
SlowBurn 0.9863 / 0.9828 / 0.9790 / 0.9828, GFS 0.5760 / 0.6146 / 0.5356 / 0.5664, Tower of
Hanoi 0.6003 / 0.5252 / 0.5928 / 0.5492. Worst-case timing grid (starts 112-143 x delays 7-60):
prior-only 0.9741, SlowBurn 0.9731, GFS 0.6020, Tower of Hanoi 0.5885
(`results/dev_v2_worst_method`, blind weight 0.5 run; to be regenerated at 0.75); at q = 0,
v2 w 0.75 SlowBurn 0.933438 vs prior-only 0.934688 (`results/dev_v4_worst`, hard variant).
Not circular: the policy's timing prior is near flat and differs from every simulator world.

**C2. ... with less work lost.** Same grid, whole-system work lost (h) bursty / early / late /
uniform: prior-only 1794.4 / 1544.4 / 1860.8 / 1687.2, SlowBurn 1654.2 / 1464.0 / 1732.7 /
1593.4, GFS 2938.8 / 1781.8 / 3480.0 / 2488.0, Tower of Hanoi 2992.7 / 1980.0 / 3367.9 / 2525.2.

**C3'. Detector evidence reduces work lost by about 6% at equal recovery, and is non-inferior
when the detector is blind.** Full grid: SlowBurn 0.982729 / 1611.0825 h vs prior-only 0.980583
/ 1721.6945 h, -6.42% (D59). Blind: at q = 0 all 8 units (4 worlds, 4 budgets on the worst-case
grid) within 1 point of prior-only and not significantly worse after Holm (largest excess
0.00875, Holm p 0.261719; D57).

## Findings

**F1. Under-estimating the discovery delay collapses every policy to 0, even with a perfect
detector.** True delay > assumed hard bound (14 or 30 days): recovery 0.0 for prior-only,
SlowBurn, GFS and Tower of Hanoi in every world and at every q including q = 1 (D50, D55,
`results/dev_v2_underdelay`; at w 0.75: `results/dev_v4_under`, hard variants). WORDING PENDING: (a) the D63 baselines sweep (GFS and
Tower of Hanoi against assumed vs true delay); (b) D62: part of the q = 1 collapse comes from
verification and file selection skipping versions older than L (the start-posterior 0.001
quantile, which the bound pushes after the true start); at assumed 30 days a clean snapshot is
retained in ~0.95-0.99 of rows, so F1 at that bound may not survive a restore that uses those
flags. Over-estimating
is safe but costs work lost (D52: assumed 90 / 120 vs 60 days, +492.3 / +1084.2 h).

**F2. A never-zero delay tail restores recovery but moves the whole budget to old snapshots.**
Soft tail (D56): recovery beyond the bound 0.988-1.0 vs 0.0 hard, at 2.19-2.21x the work lost on
the normal grid and 4.18-4.54x when the true delay is 7-14 days; insensitive to tail weight in
0.02-0.2 (D56, D60). Mechanism (corrected in D60): retention, not the restore gate. With the same
gate (45 days back), the newest clean snapshot the soft-tail DP keeps is 155.4 days back vs 49.8
with the hard bound (K = 12: 139.3 vs 42.6).

**F3. Evidence-gated restore cannot substitute for the tail.** Method v4 (hard-bound restore
that walks back on detected damage, soft tail only in retention; D60): rescue beyond the bound
only at q >= 0.5 (q = 0.5: 0.146 / 0.130 at M = 14 / 30 vs 0.027 / 0.016 at q = 0), at most
~0.5 recovery at q = 1 (PROVISIONAL, D62: the q = 1 failures restore from a clean snapshot but
leave flagged files damaged before L unrestored), against 0.97-1.0 for the soft tail with no detector; and it keeps the
soft tail's retention cost (2.28x v2 work lost). Method iterations v2 (D48, D57), v3 (D56) and
v4 (D60) are all reported; claim "(3) evidence rescues mis-specified delays" was tested three
times and dropped (D55b, D56, D60).

## Pending for the paper

- Guideline figure (assumed vs true delay heatmaps, recovery vs work-lost scatter): D63 sweep.
- Worst-case GFS / Tower of Hanoi at blind weight 0.75.
- Fresh TEST confirmation of C1, C2, C3' and F1 (under-estimated rows included).
