# STATUS (updated daily)

## 2026-10-14

**On track for 21 October: yes**, with Tier 3 (G restic, CNN detector) not expected to fit.

**Done today (all tested, ruff clean, committed)**
- F0: shared parallel runner (<= 6 workers, one thread each, resume), seed/split registry,
  `configs/frozen.yaml` gate (test runs refused unless frozen), stats (McNemar, risk difference,
  Wilcoxon, rank-biserial, Holm), LaTeX tables, benign validation-failure rate, token-mode
  simulator, file-level statistic, abstract detector.
- File-level statistic redesign: file-level conformal calibration after D24 v1 showed the
  chunk-min version was blind (recorded in OPEN_QUESTIONS.md).
- C: exact retention DP (asymmetric/symmetric), keep-last-N, GFS, Tower of Hanoi, threshold
  vault, prior-only, SlowBurn, oracle, AMOEBA-style (equal unique bytes), shared selective
  restore with residual damaged files, retention experiment + DEV tuning runner.
- B1-B3: docs/theory.md (NEEDS HUMAN REVIEW). Checks: Prop. 1 holds in every tested case;
  Theorem 2(a) zero violations in 48,686 cases, bound attained (max W/3d = 1.000); Theorem 2(b)
  within 1 of the exhaustive minimum; Theorem 3 DP = brute force on 120 random instances.
- H: paper/ skeleton (IEEE), threat-model draft, `slowburn fig <name>`.

**Current headline numbers:** none yet (headline run pending DEV tuning and freeze).

**Next**
1. D24 v2 statistic tuning (running) -> D27 retention tuning on DEV -> freeze -> headline TEST
   run (30 seeds) -> figures/tables -> report.
2. Tier 2: D (real detectors through the same interface), F sweeps and ablations.

**Needs you:** review docs/theory.md proofs by ~19-20 October.
