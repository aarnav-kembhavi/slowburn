# SlowBurn weekly status, week ending Sunday 2026-10-25 (DEV only)

Target: USENIX Security 2027 cycle 2 (register 2027-01-19, submit 2027-01-26). Single frozen
TEST run planned for the week of 2026-12-15. No test data opened; no tuning on test.

## Done this week

- D71b: PPMd validator bug found and fixed; the pre-fix NapierOne C2 / C3' reversal withdrawn.
- D72-C2R: C2 restated against Bar-On and equal-horizon schedules (NapierOne on v2 pools).
- D75: NapierOne pools enlarged (v1 5-15 -> v2 59-115 DEV files per type), archives verified and
  deleted; D67 / D72 NapierOne arms, detector AUROC and false-flag recount rerun on v2; v2 is now
  the only source for NapierOne numbers (v1 = labelled sensitivity rows).
- D74 count alarm calibrated (c = 3 both arms); amendment, held-out check and
  boundary-straddling note pre-registered; report script extended (exact bounds, detection
  probability of the threshold-aware attacker, NapierOne first).
- Bug-vs-data check for benign validity failures: all real data (Windows-1252 csv / txt, gzip
  files named .txt, NapierOne PNG-FROM-WEB truncated at 1 MiB); truncated pngs counted and kept.

## Failed this week (reported as failures)

- **D72**: per-file restore C not adopted (loses recovery to verify_snap when detection is
  imperfect, loses per-file work to walk-back everywhere).
- **D72-C2R**: C2 fails against the equal-horizon GFS / ToH configurations (SlowBurn loses
  +16% / +10% more work on synthetic, +25% / +15% on NapierOne v2); vs Bar-On only -4% to -7%.
- **D73**: FLEET not adopted (NapierOne recovery cell criterion, one fleet); its gain is the
  pooled posterior, not reallocation.
- **D75 reversal of effect sizes**: on representative pools the NapierOne effects shrink about
  2.5x (C2 vs default GFS -34.4% -> -14.0%; C3' -11.9% -> -3.8%; C3' gone at benign rate 0.05).
  Kept in the paper as an evaluation finding.
- First D74 start aborted by me (variable-shadowing bug caught on a smoke run, before any
  result); fixed and restarted.

## Running now (one heavy job at a time)

D74 synthetic arm (started 16:37) -> D74 NapierOne v2 arm -> D74 report -> D73 NapierOne v2 ->
held-out alarm check -> truncated-png sensitivity row (unscored).

## Blocked on the team

1. D78 detector fix pre-registration (draft in OPEN_QUESTIONS): approve or amend.
2. C2 wording (draft sent 2026-10-25).
3. Whether per-file walk-back's near-oracle-or-collapse behaviour becomes a pre-registered
   finding.
4. paper/sections/limitations.tex line 36 still says no real corpus is used (stale since D67).
5. D76 restic workload rule (FSL is complete); D77 needs written approval (not started).

## Next week plan

Report D74 (worst case per defence, threshold-aware bound, realistic attacker) and D73 on v2;
held-out alarm check; D78 if approved; write the D76 rule; start freezing the method list for
frozen_v2.yaml (to the team before any test run).

## Disk and data

- C: 60 GB free (floor 45). It fell from 80 GB during the D74 run; our outputs are small, so the
  cause is being checked (a watch alerts below 50 GB).
- data/: 77 GB of the 100 GB cap.
- FSL Homes download: complete, 767 of 767 files verified against the published SHA-256
  (2011-09-16 to 2011-12-03, 60 days, 13 users, 56 GB, kept compressed).
