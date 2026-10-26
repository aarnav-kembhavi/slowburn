# Truncated-png mechanism check (team request 2026-10-26; existing outputs only)

Sources: D67 NapierOne arm on v2 (scored) and v2_notrunc (unscored, 9 truncated pngs removed),
same seeds and machines, count budgets, w 0.75, verify_snap
(paper/scripts/png_mechanism.py -> results/dev_png_sensitivity/mechanism_by_world.csv); benign
flags from the D71 v2 recount at injected rate 0 (results/dev_d71_false_flags/versions.csv.gz).
Means per row; 40 machines per world and pool.

## Work lost (whole-system hours) and SlowBurn's start estimate and restore

| world | pool | SlowBurn | GFS | ToH | start error (est - true, days) | est. before true start | restore depth (days) | snapshots scanned | restored point before start (days) |
|---|---|---|---|---|---|---|---|---|---|
| bursty | v2 | 2,545 | 2,953 | 3,222 | -27.7 | 0.80 | 106.0 | 2.44 | 73.8 |
| bursty | no trunc | 1,882 | 2,908 | 3,035 | -26.0 | 0.80 | 78.4 | 1.66 | 46.2 |
| early | v2 | 1,859 | 1,784 | 2,013 | -24.1 | 0.80 | 77.4 | 2.38 | 45.2 |
| early | no trunc | 1,592 | 1,754 | 1,950 | -23.2 | 0.80 | 66.2 | 1.79 | 34.1 |
| late | v2 | 2,606 | 3,494 | 3,640 | -28.3 | 0.80 | 108.5 | 2.44 | 76.3 |
| late | no trunc | 1,896 | 3,451 | 3,362 | -26.8 | 0.80 | 78.9 | 1.59 | 46.7 |
| uniform | v2 | 2,213 | 2,496 | 2,596 | -26.3 | 0.80 | 92.2 | 2.45 | 60.0 |
| uniform | no trunc | 1,798 | 2,459 | 2,511 | -24.8 | 0.80 | 74.6 | 1.77 | 42.5 |

GFS scans 0.35 to 0.45 snapshots on both pools (its restored point is 13 to 21 days before the
start on both).

## Benign false flags (v2, injected rate 0, D71 recount)

| world | machines | benign versions | flagged | flag rate | share of flags from png |
|---|---|---|---|---|---|
| bursty | 40 | 32,651 | 588 | 0.018 | 0.88 |
| early | 40 | 19,717 | 354 | 0.018 | 0.87 |
| late | 40 | 35,938 | 596 | 0.017 | 0.87 |
| uniform | 40 | 26,024 | 443 | 0.017 | 0.87 |

Not available from existing outputs: benign flags on v2_notrunc (no recount was run on that
pool) and flags per calendar day (the recount stores versions, not days). Getting them needs a
D71-style recount on v2_notrunc (heavy, not run).

## Answer

**The C2 loss runs through benign false flags at restore time, not through changepoint error.**
- The change is almost entirely in SlowBurn's own work lost (bursty 2,545 -> 1,882 h); GFS and
  ToH move by 1% to 7%. So C2 shrinks because SlowBurn gets worse with the pngs, not because the
  baselines get better.
- The start estimate barely moves (mean error -27.7 vs -26.0 days in bursty; 80% of estimates
  fall before the true start on both pools): the changepoint is not the channel.
- The restore is: with the pngs, SlowBurn scans more snapshots (2.44 vs 1.66) and restores 28
  days further back (restored point 73.8 vs 46.2 days before the start). verify_snap rejects any
  snapshot holding a flagged version, and 87% to 88% of benign flags come from png, where the 9
  truncated files fail validity in every version. GFS keeps fewer old candidates, so it scans
  fewer snapshots and is barely affected.
- Caveat: the flag counts on v2_notrunc were not measured, so "the removed pngs account for most
  png flags" is inferred (their every version fails validity), not counted.
