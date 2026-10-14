# STATUS (updated daily)

## 2026-10-15

**On track for 21 October: yes** (Tier 1 done; Tier 2 starting; Tier 3 not expected to fit).

**Done since yesterday (tested, ruff clean, committed; details in CHANGELOG / OPEN_QUESTIONS)**
- Team decision B: verified restore with DP loss matched exactly (D29), hybrid ToH backbone +
  Theorem 2(c) (D30), fleet-pooled benign rate (D31), oracle-ideal work lost, pre-registered
  scenario grid (D32), restore posterior fixes D33/D34, degenerate-rule fix D36 (deviation logged,
  chosen point was visible on DEV), keep-first baseline, trade-off figure, truth-isolation test.
- HEADLINE TEST grid run once with frozen settings: 2400 machines, 1600 cells per policy.

**Headline TEST numbers (mean over all cells; clean recovery / whole-system work lost, h)**
SlowBurn 0.9326 / 1368.8; GFS 0.6438 / 2072.2; ToH 0.5975 / 2379.7; prior-only 0.5750 / 2112.9;
keep-first 0.9997 / 3647.1; oracle 0.9997 / 776.5 (ideal 772.8). Holm-significant cells vs GFS:
recovery better 551 / worse 69; work lost better 800 / worse 620. Against the best of the four
practical fixed schedules per cell (chosen after the fact): recovery better 428 / worse 542,
work lost better 712 / worse 885. SlowBurn improves with detection probability (recovery 0.864
at q = 0 -> 0.971 at q = 1; work lost 1542.5 -> 1254.8 h).

**Contradicts the claim (to narrow):** prior-only does not match the best fixed schedule
(0.575 vs GFS 0.644); at K = 12 prior-only (1.000 / 1036.8 h) beats SlowBurn (0.918 / 1547.4 h)
and SlowBurn is worse at K = 12 than at K = 8 (0.959 / 1295.8 h), which needs diagnosis.

**Next**
1. Tier 2 F: ablations (per-machine null, evidence-only restore posterior, no backbone,
   ungated DP loss, symmetric loss, quantile restore) and sweeps; diagnose the K = 12 drop on DEV.
2. Tier 2 D: real detectors through the same interface (gain vs detector quality).

**Needs you:** decide how to narrow the claim (prior-only half); review docs/theory.md
(Theorems 2(c), 3 extension) by ~19-20 October.

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
