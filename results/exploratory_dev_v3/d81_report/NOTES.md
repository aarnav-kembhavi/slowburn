# D81 report notes (exploratory_dev_v3, DEV only; team review 2026-11-03)

1. sbdaymed budgets are well below SlowBurn's real footprint: 0.67 to 0.72 of the sbmax budget,
   and under sbdaymed SlowBurn holds 0.54 to 0.63 of its count-K footprint (napierone). Detail:
   - sbdaymed budget / sbmax budget (napierone): 0.67 (K4), 0.72 (K6), 0.71 (K8), 0.70 (K12).
   - sbdaymed budget / SlowBurn's mean retained unique bytes at count K on the discovery day:
     napierone 0.75, 0.79, 0.73, 0.69; synthetic 0.81, 0.85, 0.76, 0.71 (K4, K6, K8, K12).
   - What SlowBurn holds under sbdaymed against what it holds at count K: napierone mean
     retained 20.6 / 32.7, 23.9 / 40.1, 27.2 / 49.0, 32.1 / 59.6 MiB (0.63, 0.60, 0.56, 0.54);
     K' is below K on most machines (SlowBurn K' >= K on 7 to 31 of 480).
   The sbdaymed budget is a median over pooled machine-days, so most machines exceed it on some
   day and the every-day K' rule pushes K' down. sbmax (median over machines of each machine's max
   daily bytes) is the level at which SlowBurn's own K' is about K.

2. sbdaymed and sbmax results differ in sign against GFS and ToH on work lost (napierone; synthetic
   sbmax pending). SlowBurn minus policy, relative work lost [95% CI]:

   | vs | K | sbdaymed | sbmax |
   |---|---|---|---|
   | GFS | 8 | -0.345 [-0.400, -0.283] | +0.227 [+0.158, +0.308] |
   | GFS | 12 | -0.163 [-0.226, -0.096] | +0.354 [+0.286, +0.421] |
   | ToH | 8 | -0.359 [-0.416, -0.298] | +0.179 [+0.115, +0.246] |
   | ToH | 12 | -0.129 [-0.201, -0.053] | +0.060 [+0.001, +0.122] |

   At K4 both levels are negative; at K6 sbmax is -0.053 [-0.124, +0.023] (GFS) and
   -0.000 [-0.073, +0.074] (ToH). Recovery differences are positive at every level. Source:
   slowburn_vs_policy.csv and review2_t1_gfs_toh_by_level.csv.

3. Not claimable: review3_t2_smallest_level_matching_slowburn.csv ("smallest budget level at which
   each policy matches SlowBurn's mean recovery"). Its matches rest on selected feasible subsets
   (Bar-On and eqh rows average only over machines where the policy is feasible), one row rests on
   n = 3 machines (GFS-eqh at sbdaymed_K6), and several "not reached" or "reached" outcomes turn on
   the third decimal of mean recovery. Kept in the CSV for the record; excluded from every paper
   table.

4. Horizon share table (review3_t1_horizon60_sbmax.csv): ToH and ToH-eqh rows are identical
   because ToH's own horizon already reaches the 60-day target at these budgets. At M = 60, ToH-eqh
   is ToH with base 2, plain ToH, at every K' >= 8 (ToH horizon >= 63 days); below K' = 8 no ToH
   base reaches 60 days, so ToH-eqh is infeasible there and plain ToH's horizon is under 60 (31 at
   K' = 7), and neither counts toward the share.
