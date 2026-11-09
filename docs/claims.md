# Claims (TEST numbers primary since 2026-10-30; DEV v2 in parentheses)

**TEST (frozen_v2, single frozen run, queue done 2026-10-29; analysis by path override,
results/analysis_test; DEV v2 rerun of the same scripts in results/analysis_dev).** Claims C2,
D79, D72 (F6), D73 (F7), ALARM (F4) and D74 (F8) give the TEST number first and the DEV v2
number in parentheses. Every other number in this file is DEV and is labelled "DEV only, not
covered by TEST". Numbers from the v1 pools appear only as "DEV, v1 pools, sensitivity".

**Data (correction 2026-10-23): every DEV-only number below uses synthetic benign files and synthetic
damage** (abstract chunk tokens, random-token damage, abstract detector with detection
probability q), unless marked NapierOne. See docs/data_card.md.

**NapierOne check (D67, post-D71b, on the D75 enlarged pools v2, 2026-10-24; DEV only, not
covered by TEST except C2): C1, C2 (vs default GFS / Tower of Hanoi configurations) and C3' hold
on NapierOne bytes, with much smaller effects than on the small v1 pools.** Numbers from the v1
pools (5 to 15 files per type) are DEV, v1 pools, sensitivity only; results/D75_REPORT.md has both side by side. Arms on the same
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

**Evaluation finding (D75, reworded 2026-10-26 after the png mechanism check; DEV only, not
covered by TEST): a handful of invalid benign files can halve measured retention gains.**
Pre-registered prediction (results/test_prediction.md, committed before any TEST result): with
4 truncated pngs of 57 on TEST vs 9 of 54 on DEV, C2 vs default GFS and ToH on TEST would fall
between the scored DEV value and the no-png DEV value. It held: TEST -19.0% [-22.8, -15.2] vs
GFS (DEV -14.0%, no-png DEV -32.2%) and -23.0% [-26.3, -19.7] vs ToH (DEV -19.6%, no-png DEV
-34.0%); both TEST intervals overlap the scored DEV intervals. The 9 truncated NapierOne pngs (13%
of the v2 DEV png pool) cause 87% to 88% of benign flags; without them (unscored sensitivity
row) SlowBurn vs default GFS is -32.2% [-35.7, -28.2] instead of -14.0%, C3' -9.7% [-11.0,
-8.5] instead of -3.8%, recovery unchanged. The channel is the restore, not the start
estimate: with the pngs SlowBurn scans 2.44 vs 1.66 snapshots and restores 28 days deeper,
while its start estimate error barely moves (-27.7 vs -26.0 days, bursty); GFS / ToH move by
1% to 7% (`results/dev_png_mechanism.md`, `results/PNG_SENSITIVITY.md`). Benign flags on the
no-png pool were not recounted. Original wording, kept for the record (DEV, v1 pools, sensitivity): content
pool size changed the NapierOne effect sizes by about 2.5x. Same machines, seeds, detector and grid; only the benign pool grew from 5 to 15
(v1) to 59 to 115 files per type (v2). C2 vs default GFS -34.4% -> -14.0% (2.5x), vs default
Tower of Hanoi -35.7% -> -19.6% (1.8x); C3' -11.9% -> -3.8% (3.1x). Cause: the small pools had
no benign files failing validity and easier-to-detect damage (benign false flags at injected
rate 0: 0.000 -> 0.017; damage detection 0.947 -> 0.875). Real-data evaluations with a few
files per type can overstate evidence-based gains; results/D75_REPORT.md.

Numbers not marked TEST are DEV (seed 202), count budgets K in {4, 6, 8, 12}, method v2 = blind weight 0.75
with the fixed 0.8 gate, restored with the ADOPTED restore (D64a verify_snap: every version in a
candidate snapshot is checked against its shared write-time flag, D29 any-flag rule, select),
for EVERY policy (D64b). Brackets: 95% machine-cluster bootstrap CIs. The fresh TEST set (P5)
decided; TEST numbers are marked TEST. Old-vs-new tables: `results/dev_d64a_*/old_vs_new*.csv`.
Decisions: D59, D60, D64a, D64b, team list of 2026-10-22.

## Thesis

"Against slow ransomware, retention outcomes are governed by the assumed discovery delay, not by
detector quality."

FLAG (team to decide): "governed by ... not by" may be too strong given C3' (evidence does buy
about 5% less work lost). Alternative: "are dominated by the assumed discovery delay rather than
by detector quality".

## Claims

**C1 (DEV only, not covered by TEST). Timing-aware budgeted retention beats fixed schedules on
recovery, even with a blind detector.** Worlds grid (`results/dev_d64a_full`, all q and benign rates), clean recovery
bursty / early / late / uniform: prior-only 0.9888 / 0.9858 / 0.9810 / 0.9822, SlowBurn
0.9892 / 0.9865 / 0.9838 / 0.9860, GFS 0.5760 / 0.6146 / 0.5356 / 0.5666, Tower of Hanoi
0.6003 / 0.5274 / 0.5941 / 0.5498. Worst-case timing grid (starts 112-143 x delays 7-60, q in
{0, 0.5, 1}, `results/dev_d64a_worst_all`, every policy at w 0.75): prior-only 0.9785,
SlowBurn 0.9793, GFS 0.6025, Tower of Hanoi 0.5926; at q = 0 prior-only 0.9456, SlowBurn
0.9450. Not circular: the policy's timing prior is near flat and differs from every simulator
world.

**C2. Against the default GFS and Tower of Hanoi configurations SlowBurn loses less work at
much higher recovery; no significant difference from Bar-On (no equivalence margin was
tested); it loses to GFS and Tower of Hanoi configured to the
same horizon.** TEST, NapierOne bytes on the v2 pools, count budgets, w 0.75, verify_snap;
paired machine-cluster bootstrap 95% CIs (2000 resamples, seed 0); Holm across the six
baselines per arm (`results/analysis_test/d72_c2r_holm/c2_holm.csv`; DEV v2 in parentheses from
`results/analysis_dev/d72_c2r_holm/c2_holm.csv`).
Sign convention: every work-lost delta is SlowBurn relative to the baseline (sum SlowBurn / sum
baseline - 1; positive = SlowBurn loses more) and every recovery delta is SlowBurn minus
baseline. The Holm family is the six pooled comparisons per arm.
- Default configurations: work lost -19.0% [-22.8, -15.2] vs GFS and -23.0% [-26.3, -19.7] vs
  Tower of Hanoi, recovery +0.428 [+0.411, +0.445] / +0.411 [+0.404, +0.421]; Holm p < 0.001
  both (DEV -14.0% [-18.3, -9.4] / -19.6% [-23.0, -16.0], recovery +0.425 / +0.428). The
  pre-registered png prediction (results/test_prediction.md) held (see the D75 paragraph).
  Synthetic bytes: -22.8% [-26.0, -19.4] / -26.0% [-28.6, -23.4] (DEV -27.6% / -30.2%).
- Bar-On: **no significant difference from Bar-On; no equivalence margin was tested** (TEST +0.2% [-3.1, +3.8] vs recursive, Holm p 0.865;
  -2.1% [-5.5, +1.5] vs round robin, Holm p 0.450; not significant); the small DEV advantage
  (-5.3% / -6.7%, Holm p < 0.001) did not replicate. Synthetic: -0.5% [-3.6, +2.3] / -2.3%
  [-5.3, +0.7], not significant (DEV -4.4% / -6.8%).
- Equal horizon (horizon >= M; GFS-eqh exists only at K = 12, ToH-eqh at K 8 and 12): uncapped
  SlowBurn loses +15.6% [+11.3, +20.3] more work than GFS-eqh (recovery +0.000 [-0.003,
  +0.004]) and +14.9% [+10.6, +19.3] more than ToH-eqh (recovery +0.031 [+0.016, +0.049]);
  Holm p < 0.001 both (DEV +24.9% / +14.9%). Synthetic +17.4% [+13.3, +21.6] / +14.0% [+10.1,
  +17.8] (DEV +16.1% / +10.1%).
- DEV, v1 pools, sensitivity: equal-horizon gap +6.9% [+3.6, +10.5] / +3.0% [-0.5, +6.4] on
  the v1 pools vs +24.9% / +14.9% on DEV v2.

**D79 (pre-registered test). Retention horizon dominates.** Uncapped SlowBurn loses to
equal-horizon GFS and ToH (TEST +15.6% / +14.9% work lost). With the same age cap, SlowBurn
beats GFS-eqh (TEST -4.6% [-7.1, -2.0] NapierOne, -4.0% [-6.1, -1.8] synthetic, Holm p 0.001
and < 0.001, recovery unchanged: -0.003 [-0.008, +0.001] / -0.002 [-0.005, 0.000]) but loses
to ToH-eqh on work lost (+7.7% [+4.1, +11.4] / +7.1% [+3.7, +10.6], Holm p < 0.001) while
recovering 0.03 more (+0.030 [+0.015, +0.048] both arms). On DEV the NapierOne GFS-eqh
comparison was a tie (-0.9% [-3.2, +1.7], Holm p 0.48); TEST is the confirmatory run (DEV
ToH-eqh +6.3% NapierOne; synthetic +1.8% [-1.6, +5.1], not significant). The age cap is taken
from each baseline's own held age (104 days for GFS-eqh at K 12; 127 / 255 days for ToH-eqh at
K 8 / 12), so this is a controlled comparison, not a standalone method
(`results/analysis_test/d79_report/primary.csv`).
NapierOne numbers carry the caveats in the header.
Supporting detail, default configurations (DEV only, abstract grid, not covered by TEST):
lower work lost than default GFS / Tower of Hanoi pooled (-23.4% vs GFS, -26.7% vs Tower of
Hanoi) and in 3 of 4 attack worlds; in the early world SlowBurn vs GFS is -3.0% [-9.5, +3.9],
not significant (`results/dev_d64a_full/c2_vs_fixed_schedules.csv`).
(DEV, v1 pools, sensitivity: -34.4% / -35.7% vs default GFS / ToH; pre-D71b, withdrawn: +7.9%
/ -2.3%.)

**C3' (DEV only, not covered by TEST). Evidence reduces work lost by 4.7% [3.9, 5.5] at equal recovery. With a blind detector
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
header. (DEV, v1 pools, sensitivity: -11.9%; pre-D71b, withdrawn: +1.5%, the PPMd validator bug.)

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

**F1 (DEV only, not covered by TEST). Beyond the assumed bound, recovery is ~0 unless the detector is near perfect, and even
then it is capped by the fraction of rows where retention kept a clean snapshot.** True delay >
assumed hard bound, recovery at q = 0 / 0.2 / 0.5: 0 / 0 / 0.0026 (M = 14) and 0 / 0 / 0.0062
(M = 30), SlowBurn and prior-only alike. At q = 1, SlowBurn / prior-only: M = 14: 0.1495 /
0.1568; M = 30: 0.8891 / 0.9852, each equal to the policy's clean-retained fraction
(`results/dev_d64a_under`). Evidence-driven retention trades beyond-bound coverage for lower
work lost inside the bound. Fixed schedules (D63, K = 8, benign 0.01, all
under-estimated rows pooled): q = 0: 0 for every policy; q = 1: Tower of Hanoi 0.565,
prior-only 0.333, SlowBurn 0.286, GFS 0.165. With a short bound (M 7 / 14 / 30) Tower of Hanoi
recovers more than SlowBurn at q = 1 (0.708 / 0.634 / 0.525 vs 0 / 0.230 / 0.142, Holm p <
0.05); SlowBurn recovers more at M 60 / 90 (`delay_grid_under_vs_fixed_K8.csv`, a generated table not kept in this repository). The earlier
"collapses to 0 even with a perfect detector" was an artifact of the old restore's scan window
(CHANGELOG 2026-10-22). Over-estimating is safe but costs work lost (D52: assumed 90 / 120 vs
60 days, +492.3 / +1084.2 h; old restore, not rerun).

**F2 (DEV only, not covered by TEST). A never-zero delay tail restores recovery but moves the whole budget to old snapshots.**
Soft tail (D56) under the adopted restore: recovery 0.9980 on the normal grid at 3918.0 h vs
2078.2 h for the hard bound (1.89x; old restore 2.30x) and 1.0 on the worst case (3123.3 vs
2179.2 h). Insensitive to tail weight in 0.02-0.2 (D56, D60). Mechanism (D60): retention, not
the restore gate; the newest clean snapshot the soft-tail DP keeps is 155.4 days back vs 49.8
with the hard bound (K = 12: 139.3 vs 42.6; retention is unchanged by the restore).

**F3 (DEV only, not covered by TEST). Evidence-gated restore rescues only with a near-perfect detector.** Method v4 (D60:
hard-bound restore that walks back on detected damage, soft tail only in retention) beyond the
bound: q = 1: 1.0 at M = 14 and 30; q <= 0.5: <= 0.006 (q = 0.5: 0.0042 / 0.0062 at M = 14 /
30; q = 0.2 and 0: 0). v4 FAILED on cost: normal-grid work lost 3911.8-3918.1 h vs limit 2286.1
(1.10 x the hard bound's 2078.2; 1.88x; `results/dev_d64a_v4_normal/
d60_scoreboard_vsnap.csv`). Claim "(3) evidence rescues mis-specified delays" was tested
three times and dropped (D55b, D56, D60).

**F4. The daily flagged-file count alarm (D74) at c = 3 rarely fires on benign machines.**
Threshold c = 3 chosen on 100 attack-free 120-day calibration runs per arm (DEV; smallest c with
at most 5% of runs alarming; in sample 0 / 100 synthetic, 1 / 100 NapierOne; at c = 2: 8% /
31%). TEST held out (100 new attack-free runs per arm on TEST machines and content, c fixed):
NapierOne 0 / 100, exact 95% upper bound 0.036 per run, 0 of 12,000 machine-days (upper
3.1e-4), fleet false alarms per week upper 0.043 (N = 20) / 0.22 (N = 100); synthetic 1 / 100
= 0.010 [0.0003, 0.054], 1 of 12,000 machine-days (8.3e-5, upper 4.6e-4), fleet false alarms
per week 0.012 (upper 0.065) at N = 20 and 0.058 (upper 0.32) at N = 100
(`results/analysis_test/d74_alarm_holdout/holdout.json`). DEV held out: 0 / 100 on both arms.
The alarm gives no guarantee against a threshold-aware attacker (F8).

**F5 (DEV only, not covered by TEST). Product retention defaults (D66 audit, FSL Homes churn, delays 1 to 400 days, 160
machines; descriptive).** Rules checked against vendor pages on 2026-10-27 (Dropbox version
history overview; Google Drive "Check activity & file versions"; Microsoft Learn "Set default
organization version limits"; restic forget docs, stable). With a blind detector (q = 0)
recovery falls below 0.5 at 30 days for the 30-day products (Dropbox 30 d, Google Drive 30 d /
100 versions) and at 60 days for the longer-retention products (Dropbox 180 / 365 d, OneDrive
for work or school 500 versions: 0.194 at 60 days, below 0.1 at 90), although those products
still hold a clean version far longer: the restore, not retention, limits them. restic's two
documented example forget policies fall below 0.5 at 90 days (0.750 at 60). With a perfect
detector (q = 1) recovery follows the retention window. Count limits fail once the damaged
versions per file reach the limit: Google Drive 100 versions at r = 100
(`results/dev_d66_retention_audit/audit_thresholds.csv`). Dropped from the claims (rule not
stated on the vendor page): OneDrive personal 25 versions and its 30-day variant, NetApp ARP/AI
periodic retention; keep-within-7d and keep-last-1 are restic flags, not documented defaults,
and stay as reference rows only.

**F6. Per-file restore under imperfect detection (D72; method C not adopted).** TEST, SlowBurn
retention, NapierOne bytes v2, recovery / per-file work lost (h), DEV v2 in parentheses:
verify_snap 0.998 / 6,448 (0.999 / 7,130), walk-back 0.199 / 709 (0.230 / 715), changepoint
0.964 / 3,757 (0.969 / 3,848), per-file oracle 1.000 / 747 (1.000 / 712), snapshot oracle 0.998
/ 3,676 (1.000 / 3,640). Changepoint vs verify_snap: recovery -0.033 [-0.051, -0.018] (DEV
-0.030 [-0.045, -0.017]), per-file work lost -41.7% [-43.7, -39.7] (DEV -46.0%). Synthetic
bytes: changepoint keeps recovery (difference 0) at -39.6% [-41.1, -37.9] work lost (DEV
-37.7%). Walk-back is near the per-file oracle on work lost but recovers 0.199 on NapierOne.
The adoption verdict is unchanged: NapierOne fails, so method C is not adopted
(`results/analysis_test/d72_report/`). DEV only, not covered by TEST: full grid q 0.2
verify_snap 0.980 / 6,452, walk-back 0.001 / 175, changepoint 0.801 / 3,914, per-file oracle
1.000 / 736; changepoint loses 0.12 to 0.19 recovery at q 0.2 / 0.5 (`results/D72_REPORT.md`).

**F7. Fleet-aware retention (D73; not adopted, negative finding).** TEST, NapierOne v2, restore
A, K_avg 6 / 8: FLEET vs equal budget split per-file work lost -18.7% [-22.4, -15.2] (DEV -16.6%
[-20.3, -12.6]), but pooled fleet recovery -0.035 [-0.055, -0.017] (DEV -0.028) and the worst
(f, m, K, N) cell -0.19 (DEV -0.21); vs churn split -14.5% [-18.4, -10.8] (DEV -7.3%), recovery
-0.033 [-0.059, -0.011] (DEV -0.030), worst cell -0.21. Synthetic bytes pass every criterion on
TEST and DEV. FLEET is not adopted on TEST (`results/analysis_test/d73_report/criteria.csv`).
DEV only, point estimates: of FLEET's per-file gain over per-machine SlowBurn, pooling the
start posterior accounts for more (-8.6% file-hours, FLEET vs FLEET-indep) than moving slots
(-5.0%, FLEET-indep vs per-machine SlowBurn) (`results/analysis_dev/d73_report.txt`).

**F8. Adaptive attacker under the alarm (D74, c = 3).** TEST, threshold-aware attacker (exactly
2 damaged files per day, 40 runs per strategy, exact 95% CIs, caught within 120 days; median
days to alarm over caught runs), DEV in parentheses. NapierOne: all types, fraction 0.01: 13 /
40 = 0.325 [0.186, 0.491], median 10 (DEV 0.40, 7.5); all types, 0.1: 19 / 40 = 0.475 [0.315,
0.639], median 8 (DEV 0.65 [0.48, 0.79], 5.5); four weakest types, 0.01: 3 / 40 = 0.075
[0.016, 0.204], median 7 (DEV 0.075, 13); four weakest, 0.1: 10 / 40 = 0.25 [0.127, 0.412],
median 5 (DEV 0.45, 6.5); csv only, 0.1: 2 / 40 = 0.05 [0.006, 0.169], median 1.5 (DEV 0.10,
1). Synthetic: all types 0.1: 23 / 40 = 0.575 [0.409, 0.730] (DEV 0.45); csv only 5 / 40 =
0.125 [0.042, 0.268] (DEV 0.05). **The alarm gives no guarantee against this attacker.** By
construction the attacker writes exactly 2 new damaging versions per day, below c = 3, so every
alarm day needed at least one further flagged version that day: a benign flag or a benign
re-edit of an already damaged file. DEV only: attack-free NapierOne runs have at least one
benign flag on 7.0% of days.
Best response under the stealth constraint (TEST; chosen on the selection half, scored on the
evaluation half; NapierOne, restore A, recovery-minimising attacker; 20 machines per point;
delays 7 / 14 / 30 / 45 / 60 / 90 / 120): K = 4: SlowBurn 1.00 / 1.00 / 0.90 / 0.60 / 0.30 / 0
/ 0, prior-only identical, Bar-On recursive 1.00 / 1.00 / 0.80 / 0.65 / 0.30 / 0 / 0, GFS 0.75
/ 0.55 / 0.10 / 0 / 0 / 0 / 0, Tower of Hanoi 0 at every delay. K = 8: SlowBurn 1.00 / 1.00 /
0.90 / 0.50 / 0.30 / 0 / 0, Tower of Hanoi 1.00 / 1.00 / 0.80 / 0.60 / 0.15 / 0 / 0.05, GFS
0.95 / 0.70 / 0.55 / 0.05 / 0 / 0 / 0. At K = 8 Tower of Hanoi (its own equal-horizon
configuration) is within 0.15 of SlowBurn's recovery at every delay and loses 7% to 28% less
per-file work up to 90 days (36% at 120). Against the attacker that maximises per-file work
lost (same file, objective wl), Tower of Hanoi loses 3% to 33% less per-file work up to 90 days
(41% at 120) but its recovery falls behind from 45 days: 0.85 vs 0.95 (45), 0.85 vs 1.00 (60),
0.10 vs 0.70 (90), 0.05 vs 0.65 (120); "within 0.15" holds only against the recovery-minimising
attacker (`results/analysis_test/d74_report_per_arm/napierone_bytes/best_response.csv`). DEV: K = 8 SlowBurn 1.00 / 0.85 / 0.90 / 0.85 / 0.30
/ 0.05 / 0.05, Tower of Hanoi 1.00 / 1.00 / 0.90 / 0.65 / 0.30 / 0.05 / 0.00 (13% to 27% less
work up to 90 days). Every defence is at most 0.05 beyond the assumed bound on TEST. Synthetic
recovery vs delay: TEST only; DEV produced no scored best-response rows
(`results/analysis_test/d74_report/best_response.csv`). Realistic D72 attacker (delays 7 to
60, rate 0.5, fraction 0.1; mean recovery): TEST SlowBurn 0.99 (K 4 and 8) vs GFS 0.41 / 0.615
and Tower of Hanoi 0.0 / 0.93 (DEV 1.0 vs 0.395 / 0.6 and 0.0 / 0.99).

## Limitations

- Restore A (verify_snap) rejects any snapshot that holds a flagged version. The 9 truncated
  benign pngs therefore push SlowBurn's restore about 28 days deeper (restored point 73.8 vs
  46.2 days before the start, bursty world; results/dev_png_mechanism.md).
- The simulator draws each benign rewrite from a new pool file, so consecutive versions of a
  file are unrelated real files; this creates benign validity transitions (a valid version
  followed by an invalid one) that real edits of one file rarely produce.
- D78: no recalibration separates truncated benign pngs from damaged files; both fail the same
  validity check with the same score (results/D78_REPORT.md).

- Detector on NapierOne (D78, 2026-10-26): the one registered fix attempt (F1 recalibration, F2
  validity transition, F3 both) was rejected on CHECK; the unchanged detector ships. Benign
  flags come from 9 truncated pngs that score like damaged files; the png effect on C2 / C3'
  stays a limitation (results/D78_REPORT.md, results/dev_png_mechanism.md). Damage detection
  txt 0.59 / bin 0.66 unchanged.

- Alarm window (D74): the count alarm counts flagged files per calendar day, because the
  simulator has daily granularity (one simulated day = one daily snapshot). A deployed counter
  should use a rolling window. Burst behaviour inside a day (for example c - 1 files just before
  and after midnight) is not modelled; in the daily model it reduces to the threshold-aware
  attacker (c - 1 files on consecutive days).

## Pending for the paper

- D65 (v2.1, significance-based snapshot accept rule): REJECTED; step 1 numbers stand, no
  further accept-rule iterations. Reported as a trade-off (team decision 2026-10-22): v2.1 cuts
  SlowBurn work lost by 15.0% [12.5, 17.3] (worst case, q = 0) / 22.1% [20.6, 23.6] (full grid)
  but lowers recovery in every world (bursty / early / late / uniform -0.0122 / -0.0170 /
  -0.0196 / -0.0155; worst case -0.0188 [-0.0238, -0.0144]), failing pre-registered criterion
  (a) (drop <= 0.01). `results/dev_d65_*/v21_vs_step1*.csv`.
- Guideline figure: done (D63, `fig_delay_guideline_*`, generated figures not kept in this repository); caption must state
  the edge effect at true delay = M (D63 outcome).
- TEST done 2026-10-29 for C2, D79, D72, D71, D73, ALARM and D74 (frozen_v2). C1, C3', F1 to
  F3 and F5 are DEV only and not covered by TEST.
