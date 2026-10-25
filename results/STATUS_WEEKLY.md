# SlowBurn weekly status, week ending Sunday 2026-10-25 (DEV only)

Target: USENIX Security 2027 cycle 2 (register 2027-01-19, submit 2027-01-26). Single frozen
TEST run planned for the week of 2026-12-15. No test data opened; no tuning on test.

## Results this week (all pre-registered; every failure reported)

| item | outcome | where |
|---|---|---|
| D71b PPMd validator bug | fixed; C2 / C3' NapierOne reversal was the bug | results/D71_REPORT.md s6 |
| D72 per-file restore C | **FAILED** (vs A when detection is imperfect, vs B everywhere); not adopted | results/D72_REPORT.md s1 |
| D72-C2R C2 vs stronger baselines | holds vs default GFS / ToH and narrowly vs Bar-On; **fails vs equal-horizon GFS / ToH** (+16% / +25% more work lost) | results/D72_REPORT.md s2 |
| D73 FLEET | **FAILED** (NapierOne recovery cell criterion, one fleet); effect is the pooled posterior, not reallocation | results/D73_REPORT.md |
| D75 enlarged NapierOne pools | **effect sizes shrank ~2.5x** (C2 vs GFS -34.4% -> -14.0%, C3' -11.9% -> -3.8%); claims still hold, smaller; v1 numbers now sensitivity rows only | results/D75_REPORT.md |

The D75 reversal is the most important finding of the week: the small v1 pools had no benign
files failing validity and easier damage, so they overstated evidence-based gains. It stays in
the paper as an evaluation finding (claims.md, data card). The C2 story also weakened: SlowBurn's
work-lost edge holds only against default schedules and narrowly against Bar-On, not against
equal-horizon schedules.

## In progress

- D74 adaptive attacker: amendment committed (count alarm, disjoint calibration set, fleet false
  alarms per week, threshold-aware attacker as worst-case bound, v2 pools). Alarm calibration
  running; the threshold c is written into OPEN_QUESTIONS before D74 runs.
- Then: D73 NapierOne arm on v2 pools (team order 2026-10-25).

## Open items, need the team

1. D78 detector fix pre-registration (draft in OPEN_QUESTIONS, sent 2026-10-25): approve or
   amend before anything runs. Bug-vs-data check done: all benign failures are real data
   (Windows-1252 csv / txt, gzip files named .txt, NapierOne PNG-FROM-WEB truncated at 1 MiB).
2. Whether the truncated 1 MiB PNG-FROM-WEB files should stay in the pools (a pool-rule
   question, not a detector question).
3. Paper framing of C2 after D72-C2R (reframe toward recovery at equal budget, or keep).
4. Whether the near-oracle-or-collapse behaviour of per-file walk-back (D72 B) becomes a
   pre-registered finding.
5. paper/sections/limitations.tex still says no real file corpus is used; stale since D67.

## Held / not started

- D76 restic prototype: FSL download is complete (767 files verified), so it may start after
  the current queue; its workload rule is still to be written first.
- D77 cloud measurement: not started; needs written approval.
- Freeze (frozen_v2.yaml) and the TEST run: week of 2026-12-15.

Disk: C: 76 GB free (floor 45); data/ 77 GB (cap 100).
