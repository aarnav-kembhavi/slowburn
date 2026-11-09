# Open questions (team decisions)

## Data
- **NapierOne access**: registration / download pending. Once in `data/napierone/`, confirm the
  directory layout (benign originals vs per-family encrypted copies, filename pairing) so the
  loader config can be written.
- **NapierOne splicing**: real encrypted files are fully encrypted by each family's own scheme.
  We plan to splice their bytes into our damage masks (same offset). Confirm this is acceptable
  to describe as "real ciphertext bytes, synthetic placement".
- **RanSAP**: which traces to use for churn/attack-timing realism checks.

## Modelling
- **Dwell / discovery numbers**: fill `configs/discovery.yaml` context sources (Mandiant,
  Sophos) with verified values and years. They only motivate the sweep range.
- **Chunking**: fixed-size 4 KiB chunks for now. Content-defined chunking (as real dedup
  backup tools use) would change which chunks count as "changed" after an edit. Decide
  whether this matters for the paper.
- **Stripe length** for the striped damage model: 16 bytes by default. Real intermittent
  encryptors vary; consider sweeping it.
- **Calibration prior**: isotonic probabilities are calibrated on a class-balanced calibration
  set (i.e. under a 50/50 prior). Conformal p-values are prior-free. Decide which the paper
  reports as "the score".

## Baselines
- **AMOEBA paper**: PDF to be added to `docs/`; check the reimplementation details against it.

## Paper
- Venue / formatting template and page limit.

## Decisions taken unattended (2026-10-07 night) — please review
Conservative choice made, work continued. Each is easy to reverse.

- **D1 Mondrian conformal as the default p-value for M2.** Marginal conformal broke its
  false-alarm level on high-entropy types (FPR 0.0215 at alpha 0.01). Mondrian, conditioned on the
  declared file type (known from the backup manifest), stays at its level per type. Both variants are
  computed and reported.
- **D2 AUROC is computed on the raw LightGBM score**, not the isotonic output. Isotonic is a step
  function, so it creates ties that lower AUROC; the ranking is the classifier's.
- **D3 Isotonic is calibrated under a 50/50 class prior** (balanced calibration weights). Converting
  to a deployment prior is a documented formula; no deployment prior is assumed.
- **D4 File-level score = max over the file's changed chunks.** The simplest aggregator; the mean
  or top-k were not explored.
- **D5 Dataset shape:** 150 files per type, 16-128 KiB, fixed 4 KiB chunks, at most 12 chunks per
  file, tails under 2 KiB dropped, stripe length 16 bytes. The stripe-length sweep is deferred.
- **D6 Benign NapierOne loading is not wired into dataset building** (`NotImplementedError`)
  until the directory layout is known. The damage-source loader exists and is unit-tested on a
  fake directory only.
- **D7 No feature engineering beyond the spec** (histogram, entropy, chi2, printable, magic).
  Possible additions, not done: windowed max-entropy, byte-pair statistics, deflate-stream
  validity checks for zip/png/docx (likely to help most on compressed containers).
- **D8 Warm-up = 14 days assumed clean**, used to fit the benign model. Day 0 (the initial full
  backup) is excluded from that fit. Scenario attacks start on day 30. A real deployment needs
  the same burn-in; an attack already running at install time is out of scope.
- **D9 The benign exceedance rate is estimated from warm-up, not set to the nominal alpha.**
  Conformal validity assumes exchangeable chunks; chunks of one file are correlated.
- **D10 Benign parameters carry uncertainty** (benign rate x overdispersion grid for exceedances;
  a scale grid plus weekday-mean standard errors for the Gaussian model) instead of plug-ins. With
  plug-ins, clean synthetic series raised false alarms (fixed during development; see tests).
- **D11 Attack-regime likelihood = intermittent mixture** (activity rate pi in {0.25, 0.5, 0.75, 1})
  with upward-only effects. Slow attacks have days with no new damage.
- **D12 BOCPD reads the most recent changepoint as the attack start.** Changepoints inside warm-up
  count as "not started". Downward changes are not filtered out.
- **D13 Primary hazard 0.02/day** (placeholder in `configs/discovery.yaml`); 0.005 is reported as a
  sensitivity check. Under h = 0.02 the prior alone gives P(started) = 0.4654 at the day-14
  discovery horizon and 0.6131 at day 30. Clean-machine "false alarms" must be read against that,
  and `prior_p_started` is reported alongside every posterior. **The team should choose a
  defensible hazard**: it dominates clean-machine behaviour.
- **D14 Attacker model in M2:** 0.5 newly damaged files per day (Poisson), striped damage, two
  target sets: any type, or high-entropy types only (the hard case).
- **D15 Scenario files come from the same generators the detector was trained on** (synthetic,
  in-distribution). This is optimistic for the detector.
- **D16 Default model rule:** single-CP + exceedance statistic becomes the default if it has the
  lowest clean false-alarm rate among the data-driven models and does not lose on start
  recovery on the "any type" target set. The outcome is recorded in the CHANGELOG.
  **Outcome (provisional, 8-rep pre-fix run):** single-CP + exceedances is the default. It has the
  lowest clean false-alarm rate (0.25 vs 0.50 for BOCPD at day +14); start recovery vs BOCPD is
  within ~1 s.e. Re-check after the 16-rep re-run.

## Surfaced by M2, for the team
- **Re-run M2** (`uv run slowburn inference configs/inference.yaml`, ~25-30 min). The 16-rep run with
  the day-0 fix was stopped by Claude Code for low memory; current numbers are 8 reps, pre-fix.
- **Hazard choice (D13)** drives clean-machine false alarms more than any model choice.
- **File-level daily statistic**: benign exceedances are bursty because chunks of one rewritten file
  are flagged together. Counting files (not chunks) is the obvious next statistic to try.
- **Late bias**: start estimates are late, never meaningfully early. For M3, should the retention
  objective shift the posterior earlier (e.g. by the detector's blind-spot rate), or simply keep
  extra older snapshots? This is a modelling decision with paper impact.
- **Hard regime**: on high-entropy targets with <=10% damage the detector adds nothing; the paper's
  claim there must rest on the prior/retention layer alone.

## Workstream A decisions (2026-10-08)
- **D17 Weighted averages use uniform type weights** (`eval.type_weights: uniform`) unless the team
  supplies a mix (e.g. from real file-type frequencies once data arrives). No pooled AUROC is reported.
- **D18 Default detector = LightGBM + format validity** (`detector.pkl`); M2 runs both it and the base
  detector so weak-evidence and strong-evidence regimes are both on record.
- **D19 Alarm thresholds:** "ever alarms" means P(started) exceeds the threshold on any monitored day
  (after warm-up, up to day 60). Thresholds are set on 200 attack-free DEV machines, so a 1% target is
  resolved by about 2 machines.
- **D20 Prior reference window = 60 days** for P(attack within window).
- **D21 Format validity covers text:** txt/csv must decode as strict UTF-8; `bin` has no check.
- **D22 Primary prior is chosen after Workstream C**, on dev machines only, by the headline retention
  metric; until then all four values are reported.

## NEEDS DECISION: paper motivation after format validity (Workstream A finding)
On synthetic data, whole-file format validity flags 100% of damaged files at every damage fraction
in every checked type, with 0% false flags on pristine benign files. LightGBM + validity has
weighted-average chunk AUROC 0.9976-1.0000 in every cell. The "compressed types near chance"
blind spot disappears for naive damage. It remains only for (a) types without an integrity check
(`bin` here), (b) the abstract weak-evidence attacker (swept detection probability), and possibly
(c) real data, where benign files can be invalid (unknown until NapierOne/Govdocs1). The
detector-agnostic claim is unaffected, but "detection blind spots are the motivation" needs new
wording, e.g. "detection quality varies by format and attacker, and retention must not depend on it".

## F0 decisions (2026-10-14)
- **D23 File statistic = minimum chunk p-value per changed file, no Bonferroni.** Conformal p-values
  cannot fall below 1/(n_cal + 1) (~0.003 with our per-type calibration sets), so multiplying by a
  file's chunk count would make any file with more than ~3 chunks unflaggable at alpha = 0.01. The
  benign file-flag rate is estimated from warm-up (D9), so alpha is an operating point, not a
  guarantee. Normalisation: flagged files out of changed files (binomial), as requested.
- **D24 Pre-registered tuning rule (set before the run; DEV only).** Candidates: chunk statistic at
  alpha 0.05 (old), file statistic at alpha in {0.05, 0.01, 0.005}. Model: single-CP. Prior
  P(attack within 60 d) = 0.01. Score = mean posterior mass within +-3 days of the true start at day
  +14, averaged over every attack cell (2 detectors x 3 damage fractions x 2 target sets x 3 benign
  failure rates, 16 machines each). Constraint: mean clean-machine rate of P(started) > 0.5 at day
  +14 must not exceed 0.05 (averaged over detectors and benign rates). Pick the highest score among
  candidates meeting the constraint; ties within 0.01 go to the smaller alpha (fewer benign flags).
  The chunk statistic is reported as the ablation, including how much of the late bias it explains.
- **D25 Machines are paired across benign failure rates** (same churn and attack, nested validation
  failures), so rate comparisons are paired.
- **D26 Benign validation failures are drawn per clean changed file per day**, from an auxiliary
  random stream; with rate 0 every earlier result is reproduced exactly.
- **D27 Pre-registered retention tuning rule (DEV only), set before running.** Machines: the
  headline scenario and grid (detection probability {1, 0.9, 0.5, 0.2, 0} x benign failure rate
  {0, 0.001, 0.01, 0.05}), 10 dev machines per cell, all discovery delays {3, 7, 14, 21, 30}.
  Stage 1, shared restore stage: choose (P(attack within 60 d) in {0.005, 0.01, 0.05, 0.2},
  restore quantile in {0.01, 0.05, 0.1, 0.25}) maximising mean clean recovery averaged over ALL
  snapshot baselines except the oracle (keep-last-N, GFS, Tower of Hanoi, threshold vault,
  prior-only, SlowBurn), with penalty 60 and assumed discovery uniform up to 30 days. Stage 2,
  SlowBurn's own knobs: with stage-1 values fixed, choose (penalty in {30, 60, 120} days, assumed
  discovery max in {30, 45, 60} days) maximising SlowBurn's mean clean recovery. Ties within
  0.005 go to lower mean whole-system work lost. Prior-only shares the chosen penalty and
  horizon (it is the same DP without evidence). Budget K = 8 is a scenario choice, swept in F.
- **D28 Retention design choices.** Today's snapshot is always kept (normal practice). The restore
  stage is shared by every policy (same evidence posterior at discovery, same quantile rule), so
  retention is the only variable. AMOEBA-style uses the same shared evidence as its EVID term and
  an equal incremental-bytes budget (keep-last-K's unique history bytes). Unrecovered runs score
  whole-system work lost as everything since day 0 (conservative).
- **D24 v1 outcome set aside (defective candidates), recorded for transparency.** Scoreboard
  (`results/tune_statistic/statistic_scoreboard.csv`, first run): chunk a0.05 score 0.3502, clean FA
  0.07 (ineligible); file a0.005 0.0295; file a0.01 0.0042; file a0.05 0.0014 (missed 98-100%).
  The rule mechanically chose file a0.005. Diagnosis: the file statistic took the minimum of
  chunk-level conformal p-values, and those cannot go below 1/(n_cal + 1), about 0.003. Damaged
  files sat at that floor, and so did many clean files (the minimum over 20+ chunks often reaches
  the top calibration rank), so the two were indistinguishable. Fix: **file-level conformal
  calibration**. A file's score is its maximum raw chunk score, compared with the maximum scores of
  300 benign calibration FILES (marginal over types; per-type sets of ~30 files would floor at
  ~0.03). On the diagnostic machine damaged files now get p = 0.0033 and clean files >= ~0.1.
  The re-run uses rule D24 v2 below. All of this is DEV data; test is untouched.
- **D24 v2 (pre-registered before the re-run).** Same rule as D24, candidates: chunk statistic at
  alpha in {0.05, 0.01} (the lower suspicious level applied to the old statistic too, for
  fairness) and the file-level calibrated statistic at alpha in {0.05, 0.01} (0.005 is below the
  file-level floor plus margin). Ties within 0.01 go to the file statistic, then the smaller alpha.

### 2026-10-14 (evening): changes after the dev result that contradicted the claim (team decision B, extended)

- **D29 Restore-time verification replaces the fixed 10% quantile (team decision).** Rule
  (`slowburn/store/restore.py: verified_restore`): walk kept snapshots newest first, skipping any
  with posterior P(start > j | evidence, attack happened) below a gate tau; verify each candidate
  by running the detector on its file versions written on or after L (the posterior's 0.001
  quantile; versions older than L are treated as clean); restore from the first candidate with no
  flagged version; if none verifies (or none passes the gate) fall back to the oldest kept
  snapshot. Files changed on or after max(j_r + 1, L) are restored to their j_r version.
  Conservative choices made without asking: (a) **the detector is deterministic**, so re-scanning
  a version returns the flag it got when written; a missed damaged version stays missed and a
  benign validation failure stays flagged (no free second look). (b) scan_eps = 0.001 is fixed,
  not tuned. (c) The fallback is the oldest kept snapshot (most likely clean). (d) The gate is
  needed for blind detectors: without it, at detection probability 0 every snapshot "verifies"
  and the newest (dirty) one is restored.
  **The DP's loss equals this rule's expected loss exactly** under the DP's information (its
  planning posterior in place of the discovery posterior) and reliable verification: newest kept
  j < min(s, g + 1), where g is the newest day passing the gate, plus the fallback case where no
  kept snapshot passes the gate. Checked against an independent per-start evaluation of the rule
  and against brute force (`tests/test_retention_dp.py`). Where verification misses or falsely
  rejects, realized restores differ from the DP's model; this is reported per row
  (`restore_matches_dp_model`), with `snapshots_scanned` and `files_scanned`.
- **D30 Hybrid retention and pre-registered tuning rule v3 (DEV only, set before running).**
  SlowBurn = Tower of Hanoi backbone on R = round(f x K) slots + exact DP on the other K - R slots
  (`PosteriorDP(backbone=f)`); its held set always contains the R-media ToH set, so Theorem 2(a)
  holds with K replaced by R (Theorem 2(c), docs/theory.md, NEEDS HUMAN REVIEW). Prior-only is the
  same hybrid without evidence. Tuning on the pre-registered scenario grid (D32), 10 dev machines
  per (attack start, detection probability, benign rate) cell, every K and delay:
  Stage 1 (shared restore + prior), scored on mean clean recovery over ALL snapshot baselines
  except the oracle: P(attack within 60 d) in {0.01, 0.05, 0.2} x gate tau in {0.5, 0.8, 0.95},
  with penalty 90, assumed discovery uniform to 60 d, f = 0.25.
  Stage 2 (SlowBurn's own knobs), stage-1 values fixed, scored on SlowBurn's mean clean recovery:
  penalty in {30, 90, 270} days x assumed discovery max in {30, 60, 90} days x backbone fraction
  f in {0, 0.25, 0.5}. Ties within 0.005 go to lower mean whole-system work lost. This keeps the
  form of D27 (decided before seeing any grid result).
- **D31 Fleet-pooled benign flag rate (team decision).** The benign flag rate gets a Beta prior
  fitted by method of moments on attack-free DEV calibration machines of the same deployment
  (same detector and benign failure rate; the `vault_calib` family, 40 machines), concentration
  capped at 10^4 when the spread is binomial, plus a Jeffreys half count. Each machine's warm-up
  then updates it (hierarchical shrinkage). The per-machine Jeffreys version is kept as the
  ablation (`null_pool: per_machine`). Pooling is per deployment, not across benign rates: a
  fleet runs one detector in one environment.
- **D32 Pre-registered scenario grid (team decision; recorded in configs/frozen.yaml as
  `scenario_grid` before any dev tuning on it).** K in {4, 6, 8, 12} x discovery delay in
  {7, 14, 30, 45, 60} x attack start 112 + o, o in {0, 3, 6, 27} (112 = 4 x 28 is both a weekly
  and a monthly GFS boundary: o = 0 is GFS's best case, o = 6 puts GFS's weekly representative on
  the start day, o = 27 puts the monthly one on it), crossed with detection probability
  {1, 0.9, 0.5, 0.2, 0} x benign failure rate {0, 0.001, 0.01, 0.05}; 30 test machines per cell.
  Report every cell and, per policy, the average and worst cell for clean recovery and
  whole-system work lost, with the oracle-ideal work lost alongside every policy. Conservative
  choices: 112 days of history so Theorem 2's s >= 2d holds up to d = 56; other scenario
  parameters unchanged from the earlier headline.
- **D33 A posterior-DP policy restores with the posterior it plans with (fix found on DEV, before
  any freeze).** In the first D30 run the shared restore gated every policy with the evidence
  posterior, while the prior-only DP planned with the prior. Its DP loss then did not match its
  restore (item 1 of the team decision): at detection probability 0 the evidence posterior still
  differs from the prior (the model reads "no flags" as weak evidence against an early start), so
  the gate often excluded prior-only's planned snapshot. Fixed: prior-only uses the prior for
  both retention and the restore gate; SlowBurn uses the evidence posterior for both; fixed
  schedules (no DP) keep the evidence-gated shared restore. Verification is shared by all.
  Stage 2 was stopped and the whole D30 tuning re-run. **Set-aside first-run stage 1, for
  transparency** (`results/tune_retention_v2_setaside/stage1_scoreboard.csv`, mean clean recovery
  over the six shared baselines): (p, gate) = (0.01, 0.95) 0.4809; (0.05, 0.95) 0.4807;
  (0.01, 0.8) 0.4801; (0.05, 0.8) 0.4799; (0.2, 0.95) 0.4623; (0.2, 0.8) 0.4616; (0.05, 0.5)
  0.4413; (0.01, 0.5) 0.4408; (0.2, 0.5) 0.4332. The rule would have chosen (0.05, 0.8).
  Observation from that run (DEV, kept for the report): at detection probability 0 SlowBurn's
  recovery (e.g. 1.000 at K = 4, b = 0) exceeds prior-only's (0.3) because its evidence model
  treats the absence of flags as information (it assumes the detector has some power). SlowBurn
  at q = 0 is therefore NOT the blind policy; prior-only is.
- **D34 The restore posterior conditions on the discovery day (second fix found on DEV, before
  any freeze).** D33 did not change prior-only's results (stage-1 scoreboard of the re-run was
  identical to the first run; `results/tune_retention_v2_setaside_b/`). Diagnosis: the restore
  gate used the evidence (or prior) posterior over the whole history, ignoring that discovery
  happened on day t, while the DP planned with the posterior conditioned on "not yet discovered"
  under the assumed delay distribution. The prior over [warm-up, t] put the gate's 20% point
  ~100 days back, every kept snapshot failed the gate, and prior-only always fell back to its
  oldest snapshot. Fix: the restore posterior is P(s | evidence) x P(delay = t - s) under the
  same assumed delay distribution the DP uses (`retention.dp.discovery_posterior`), for every
  policy (shared restore). The unconditioned version is kept as an ablation
  (`restore_posterior: evidence`). The full D30 tuning was re-run from scratch after this fix.
  **Correction (2026-10-15):** an earlier version of this entry said D34 raised prior-only's
  recovery on 12 DEV machines to 0.65. That was wrong: on the same 12 machines prior-only was
  already 0.65 before D33/D34, and its restore points are identical in all three runs (mean
  114.4125; per-budget recovery 0.3 / 0.5 / 0.5 / 1.0 for K = 4 / 6 / 8 / 12 in every run). D33
  and D34 change which candidates pass the gate, not where prior-only restores from: its deficit
  comes from its retention, not from the restore. D34 is kept because it makes the restore
  consistent with the DP's model, not because it changed this result.
- **D35 The D30 stage-2 rule chose a degenerate policy (found on DEV after freezing; test run
  stopped during its DEV calibration step, before any test machine was evaluated).** Chosen:
  penalty 270, assumed discovery max 60, backbone 0 (mean clean recovery 0.99875, within the
  0.005 tie of 0.999 at max 90; lower work lost). Its median restore point is day 13 (the last
  warm-up day; 75% quantile 13, mean 13.6) and the oldest retained age is 138.6 days at every K:
  the DP keeps the first post-warm-up snapshot forever. Mean whole-system work lost 3329.9 h vs
  GFS 2076.1 h (oracle-ideal 772.8 h); work lost given recovery 3329.0 h vs GFS 902.9 h. A "keep
  the first backup forever" baseline would match it. Cause: the rule maximises clean recovery and
  uses work lost only to break ties, and a 270-day penalty makes the oldest snapshot optimal.
  frozen.yaml is left frozen (unfreezing is a deliberate manual step); decision asked.
- **D36 DEVIATION from the pre-registered rule D30 stage 2 (team decision, 2026-10-15).** Reason:
  the D30 rule (maximise clean recovery, work lost only as tie-break) admits a degenerate
  keep-oldest-forever solution (D35). The chosen point below was ALREADY VISIBLE on the DEV
  stage-2 scoreboard before this rule was written, so this is a post-hoc rule change on DEV, not
  a pre-registered one; the paper must say so. New rule: maximise SlowBurn's mean clean recovery
  subject to mean whole-system work lost <= the best fixed schedule's on DEV at the stage-1
  choice (lowest of keep-last-N, GFS, ToH, threshold vault: GFS 2076.063 h); ties within 0.005 to
  lower work lost. Applied to the stored D30 stage-2 CSV (no re-run): penalty 90, assumed
  discovery max 60, backbone 0.25 (mean clean recovery 0.929, work lost 1357.842 h). Stage 1
  (p = 0.05, gate = 0.8) unchanged. Also added, per the team: a "keep first backup forever"
  baseline (`keep_first`: day 0 + newest K - 1), so degenerate retention is visible; and a
  recovery-vs-work-lost trade-off figure (SlowBurn as a curve over all 27 stage-2 settings, every
  other policy as a point) on DEV and TEST. The curve on TEST is reporting only; the operating
  point is the DEV choice above.
- **Check requested before test (2026-10-15): SlowBurn is not given cell truth.** SlowBurn and
  prior-only read only the trace (flags, churn, snapshot contents, the discovery DAY) and frozen
  assumed values (hazard, assumed uniform delay to 60 d, penalty, gate, backbone). The true
  detection probability, benign failure rate, start day and delay never enter their code path
  (`oracle_start` is read only by the Oracle; the true start is used only to score outcomes).
  Enforced by `tests/test_retention_experiment.py::test_slowburn_never_sees_cell_truth`
  (relabelling q and b, or changing the evaluated delays, leaves every SlowBurn / prior-only
  output identical). Caveats to state in the paper: (i) the fleet null prior (D31) is fitted on
  40 attack-free DEV machines of the SAME deployment, so it is a data-driven estimate of that
  deployment's benign flag rate, not the true value; the per-machine ablation removes it.
  (ii) Baselines get comparable per-deployment calibration: the threshold vault's line comes
  from the same attack-free machines, and AMOEBA-style is trained with labels on 8 attacked DEV
  machines of the same cell (it therefore sees that cell's detection probability through its
  training data, an advantage to the baseline).
- **D37 BUG FIX after the first test run (team decision, 2026-10-15): K = 12 drop.** Diagnosis on
  DEV (`results/headline_dev`, `python -m slowburn.bench.diag_k12`): SlowBurn and prior-only
  kept 2.0 / 3.0 / 3.0 / 4.0 snapshots at K = 4 / 6 / 8 / 12; without a backbone every K gave
  the same result (0.884 recovery, 1340.7 h), so K acted only through R = round(0.25 K). The DP
  minimised over sets of AT MOST K and broke ties towards the smaller set, so snapshots newer
  than the gate day (zero marginal value that day) were deleted while slots were free; only the
  Tower of Hanoi backbone carried snapshots into the restorable range, and once the old anchor
  was dropped nothing could replace it (K = 12, R = 3: no kept snapshot older than 6 days in the
  replay). The team classified this as a BUG: the specified method (Algorithm 1, problem
  statement) deletes only when the budget is exceeded, and "keep fewer on ties" was never
  specified. Fix, as specified by the team: (1) nothing is deleted while |held + today| <= K;
  otherwise exactly one snapshot is deleted, the one whose removal increases expected loss least
  (DP); (2) ties broken by a rule fixed before the rerun: smallest largest gap between
  consecutive kept snapshots, then delete the newest eligible snapshot (general case: smallest
  sum of kept days). The DP handles the largest-gap key exactly by a threshold search (cap every
  gap at G, minimise (loss, day sum), take the smallest G attaining the minimum loss); the online
  one-deletion case evaluates the K candidate removals directly (same minimiser, tested).
  Property worth stating: the gap rule measures gaps between kept snapshots only, not their span
  back to the oldest, so among exactly tied sets it prefers tight clusters; in the online
  one-deletion setting this deletes the snapshot in the densest region and the replay holds
  evenly spaced sets. Regression tests: `tests/test_retention_fill.py`. No hyperparameter was
  retuned; configs/frozen.yaml unchanged (its values were chosen on DEV with the buggy code,
  which the appendix must say). The full frozen TEST grid is re-run into `results/headline_v2`;
  the first run stays in `results/headline` and both go in the appendix. The myopic one-day
  objective stays and is a stated limitation.
- **D38 Why work lost rose after D37 (DEV, analysis only, 2026-10-16).** SlowBurn DEV whole-system
  work lost 1357.842 h (first run) -> 1760.010 h (rerun); recovery 0.929 -> 0.961. Before the
  fix 5586 of 16000 restores (35%) found no kept snapshot past the restore gate and fell back to
  the oldest kept snapshot, usually a recent backbone copy: recovery 0.820, mean gap
  (s - 1 - restore day) 10.2 days given recovery. After the fix every restore has candidates
  past the gate (4.59 on average, was 0.68) and lands behind it: mean gap 38.0 days given
  recovery (17.2 before), nearly flat in detection probability (41.0 at q = 0, 35.2 at q = 1)
  and LARGEST at short delays (50.6 days at delay 7 vs 26.0 at delay 60). In 74.4% of
  machine-cells recovered in both runs the rerun restores an older snapshot (mean restore day
  82.5 vs 102.9). Cause: the gate (tau = 0.8 under the assumed uniform delay to 60 days) puts
  the newest admissible snapshot about 48 days before discovery unless evidence localises the
  start; the first run's low work lost came partly from the fallback landing on recent
  snapshots. No method change (team decision); recorded as a limitation.
- **Limitations recorded (team, 2026-10-16):** myopic per-day objective; recovery not monotone
  in K (prior-only 1.000 -> 0.957 on DEV, SlowBurn dip at K = 8); verification errors (restore
  accepts a dirty snapshot the detector misses); conservative restore gate (D38).
- **D39 Timing-prior misspecification sweep (DEV, reporting only, 2026-10-16).** The frozen prior
  is NOT the simulator's generating distribution: the simulator starts every attack with
  certainty on day 112 + o, o in {0, 3, 6, 27} (uniform on {112, 115, 118, 139} across the grid);
  the frozen prior is a constant daily hazard after the warm-up with P(start within 60 d) = 0.05.
  Wiring check requested by the team: the frozen variant reproduces `results/headline_dev_v2`
  row for row (64000 rows, every column identical) because it IS the same prior with the same
  seeds; every other prior changes the outcome (e.g. later_60: restore point differs in 100% /
  99.6% of prior-only / SlowBurn rows, oldest kept age in 100%; GFS restore point in 38.7%,
  through the shared gate). Unit test
  `tests/test_retention_experiment.py::test_timing_prior_reaches_dp_and_restore_gate`: on one
  machine, priors centred on day 8 vs day 20 give gate days 9 vs 14 (SlowBurn) and 8 vs 18
  (prior-only), and kept sets [6, 7, 8, 22] vs [9, 13, 14, 22] / [12, 15, 17, 22]. The
  discovery-delay assumption was not swept.
- **D40 Restore-time failures (analysis only, no method change, 2026-10-16).** Every failure with
  a clean snapshot retained is a DAMAGED snapshot that passed verification (616 of 619 SlowBurn
  DEV rows; the other 3 restore a pre-start snapshot that still fails). They concentrate at
  q = 0 and delay 60. At q = 0, on the rows where SlowBurn fails, it restores 22.4 days later
  (median 14) than prior-only on the same machine-cell, with more gate candidates on average
  (4.62 vs 3.92): consistent with "no flags shifts the evidence posterior later, so the gate
  admits newer, damaged snapshots". The gate day itself is not logged, so this is inferred from
  restore points, not measured. Generated: `slowburn fig table-restore-failures`.
- **D41 Scope and framing (team decision, 2026-10-16).** Do: 1a, 1c, core ablations (no
  backbone, no detector, chunk vs file statistic), a light detector-quality comparison. Dropped:
  real-data loaders (NapierOne, Govdocs1), restic integration and the CNN detector; recorded as
  limitations ("simulation study"). All experiments frozen by 20 October; 21-25 October writing.
  Framing: high clean recovery comes from planning for uncertain attack timing and restoring
  conservatively; it beats GFS and Tower of Hanoi on both recovery and work lost, but work lost
  stays well above the oracle (DEV 1760 vs 777 h), and detector evidence moves the restore point
  little under the current gate. No further method changes; the test runs stand.
- **D42 New direction: full systems and measurement paper (team decision, 2026-10-16;
  supersedes D41's deadline, scope and "no further method changes").** No fixed date. Phases:
  P0 consolidate; P1 simulator v2; P2 real data (NapierOne, Govdocs1, FSL Homes churn); P3
  real-product baselines (every rule with a primary vendor source, verified by the team); P4
  method v2 on DEV only; P5 restic system and overhead; P6 fresh pre-registered TEST
  (`configs/frozen_v2.yaml`); P7 IEEE paper. Decisions: (1) the policy's timing assumption is
  fixed (flat, as now) and the GENERATING distribution varies (uniform, early-concentrated,
  late-concentrated, bursty); every world is reported, and the old 60-days-late headline may
  shrink. (2) Budget in bytes (primary for real-product baselines) and in snapshot count; daily
  snapshots for the main grid, Time Machine's hourly rule as a separate fidelity experiment.
  (3) Dataset and restic-workload paths and disk caps to be given by the team; ask before
  exceeding. (4) restic: pinned binary in a gitignored `tools/`, checksum verified, version in
  the README. (5) q = 0 criterion, pre-registered: pooled restore-failure rate at q = 0 must not
  exceed prior-only by more than 1 percentage point (one-sided, Holm-adjusted), and no
  individual cell significantly worse. (6) AMOEBA stays a retention baseline only. (7) Order:
  simulator v2 first, then real data; report FSL Homes availability, format and size, and
  NapierOne partial-encryption coverage before any download; simulated partial damage uses
  blocks from NapierOne's real encrypted files and the data card says so.
- **D43 The v1 TEST split is SPENT (2026-10-16).** `results/headline` and `results/headline_v2`
  were run on it twice (before and after D37). Nothing from it is a headline result in the new
  paper; it may appear only in an appendix as the prototype stage. v2 claims come only from a
  fresh TEST set (new seeds, new machine-to-trace mapping, disjoint file pools), run once per
  method version under `configs/frozen_v2.yaml`. The v1 DEV set has also been used heavily for
  design, so method v2 is designed on a new DEV generated by simulator v2.
- **D44 Restore gate logged per restore (P0, 2026-10-16).** `verified_restore` now records
  `gate_day` (newest day whose clean probability under the restore posterior is at least the
  gate; -1 if none) and `restore_p_clean` (that probability at the chosen restore point; below
  the gate only on the fallback when no candidate verifies). Restore failures are explained from
  these measured values, not from restore points.
- **D45 Simulator v2: generating worlds (P1, decisions made for the team, 2026-10-16).** Each
  machine draws its own attack start from a world on a stream keyed by (seed, split, world, rep),
  so all evidence cells of a world are paired. Window [28, 280] (two weeks after the 14-day
  warm-up to week 40); conservative choice: wide enough that no schedule's block structure lines
  up with it, short enough that traces stay near the v1 length. Worlds: `uniform`; `early` =
  28 + floor(253 * Beta(1, 3)) (mean ~ day 91); `late` = Beta(3, 1) (mean ~ day 217); `bursty` =
  one of three campaign centres plus Normal(0, 3 d) jitter, centres [99, 139, 267] drawn ONCE
  from child_rng(202, "bursty_centres") on [40, 268] (not hand-picked). The policy's timing
  assumption stays the v1 constant-hazard prior (P(start within 60 d) = 0.05 after warm-up),
  which equals none of the worlds. New DEV seed 202 (v1 DEV 101; v1 TEST spent). Evidence grid
  q in {1, .9, .5, .2, 0} x benign rate in {0, .01, .05} (v1's 0.001 level dropped to afford 40
  starts per world); 40 reps per world. Policies in the v2 DEV baseline: prior-only, SlowBurn,
  GFS, Tower of Hanoi, keep last N, keep first, oracle. Threshold vault and AMOEBA-style are left
  out of the v2 DEV baseline for now (not requested for tonight; AMOEBA needs per-cell training
  machines); they return in the P5 grid.
- **D46 Byte budgets (P1, decisions made for the team, 2026-10-16).** Retained storage = unique
  bytes of the kept snapshots (token chunks live on contiguous day intervals, so this is exact
  and O(1) per pair; tested against set unions). A byte budget is enforced with each policy's OWN
  deletion rule, one deletion at a time with a count budget of (held - 1); no policy is
  byte-aware (byte-aware planning would be a method change for P4). Levels: the storage that
  keep-last-N needs for N = 14, 30, 90 days of history, as a multiple of the machine's day-0 size,
  calibrated as the median over 40 attack-free DEV calibration machines and days after warm-up.
  First choice (keep-last-4/8/12 footprints, 1.14x/1.40x/1.62x) was discarded before any
  evaluation run: under the simulator's churn (~5% of bytes new per day; any snapshot a month old
  plus today's ~1.9x the day-0 size) no policy could keep anything older than 2-3 weeks, so the
  grid would only measure that. keep_first is count-only (it cannot meet a byte budget below
  |first U today|). Oracle fixed to always keep today's snapshot (at count budget 1 it kept only
  the pinned day; count budgets >= 2 are unchanged). NOTE: the synthetic churn is high relative
  to real home-directory traces; P2 (FSL Homes) is where realistic churn enters.
- **D47 Worst-case timing grid and assumed-delay sweep (P1, 2026-10-16).** Worst case: starts
  112..143 (every residue mod 7, 28 and 32) x delays {7, 14, 30, 45, 60}, q in {1, .5, 0},
  benign 0.01, 5 reps per start; per policy, budget and q the worst (start, delay) cell of mean
  recovery (and of mean work lost) next to the grid mean (`worst_case_timing.csv`). Simulation
  parameters only. Assumed-delay sweep (reporting only, `configs/dev_v2_delay.yaml`): the
  policy's assumed discovery-delay distribution uniform on 1..{14, 30, 60 (frozen), 90, 120} and
  geometric with mean 30 (truncated at 60), true delays 7-60, all four worlds, q in
  {1, .5, .2, 0}, benign 0.01.
- **D48 Method v2 stage A: uncertain detector sensitivity (DEV only; rule fixed BEFORE the run,
  2026-10-16).** Model: the attack-regime likelihood gets one extra effect component equal to the
  benign likelihood (the detector cannot see this attack) with prior weight w; the v1 effect grid
  shares 1 - w. w = 0 is v1 exactly (tested). Without flags above the benign rate the posterior
  stays close to the timing prior; once flags appear the sensitive components dominate. The
  policy never sees the cell's true q. Candidates w in {0, 0.25, 0.5, 0.75, 0.9}
  (`configs/dev_v2_method_a.yaml`: v2 DEV seed 202, all four worlds, q in {1, .5, .2, 0},
  benign in {0, .01, .05}, 40 reps, count budgets). Selection rule: (1) eligible = in EVERY world,
  SlowBurn's pooled q = 0 restore-time failure rate (clean snapshot retained, recovery failed) is
  at most prior-only's + 0.01 (DEV point estimates; the pre-registered TEST version is the
  one-sided Holm-adjusted test of the team's decision 5); (2) among eligible w, the highest mean
  SlowBurn clean recovery over all worlds, cells, budgets and delays, ties within 0.001 broken by
  lower mean work lost; (3) if none is eligible, the w with the smallest worst-world q = 0 excess,
  reported as NOT meeting the criterion on DEV.
- **D49 Method v2 stage B: adaptive restore gate (DEV only; rule fixed BEFORE the run,
  2026-10-16).** Restore gate = min + (0.8 - min) * (1 - c), c = largest start-posterior mass in
  any 7 consecutive days; applied only to restores that use detector evidence, so the prior-only
  (no-detector) restore keeps the fixed 0.8 gate. The DP keeps planning with the fixed 0.8 gate.
  Variants on the stage-A choice: fixed (control), min 0.5, min 0.65. Adopt an adaptive variant
  only if (a) the D48 q = 0 criterion still holds in every world, (b) mean SlowBurn clean
  recovery is at most 0.005 below the control, and (c) mean work lost is below the control;
  among those, the lowest mean work lost. Otherwise keep the fixed gate. Diagnostic logged per
  restore: `newest_clean_kept` (the best restore the kept set allows) and `restore_gate`, to
  separate work lost caused by the gate from work lost caused by retention spacing.
- **D50 Headline claim (3) not reproduced on v2 DEV (REPORTED, claim unchanged, needs the team;
  2026-10-16).** Under decision 1 (flat assumption fixed, worlds varied) prior-only recovers
  0.97575-0.986 in every world and SlowBurn's recovery differs by -0.004583 to +0.00125; evidence
  still lowers work lost (27.164-133.156 h) and raises byte-budget recovery (+0.021555 to
  +0.055667). The v1
  result needs a concentrated, misplaced assumption. Conservative handling tonight: no claim
  edited; the pre-specified DEV runs continue (they do not depend on the claim); the team decides
  whether claim (3) is restated (e.g. "evidence lowers work lost and helps under tight storage"),
  or tested with a concentrated misplaced assumption as an added "wrong assumption" axis.
- **D51 Incident: duplicate stage-A run (2026-10-17, reported).** Two identical method-v2 stage-A
  runs overlapped for ~95 min (10 workers; cap is 6) because an untracked `nohup` launch did
  start. Data verified (cache files complete and consistent, 6 tasks recomputed identical); the
  CSV was rebuilt from the cache. Process fix: launch long jobs only through tracked background
  tasks, one at a time, and verify with the Windows process list, not `ps` from Git Bash.
- **D48 outcome (2026-10-17):** blind weight 0.5 chosen on DEV by the pre-registered rule (worst-
  world q = 0 excess 0.00625 <= 0.01). It becomes the method-v2 evidence model for stage B and
  for the P5 pre-registration unless the team objects.
- **D49 outcome (2026-10-17):** neither adaptive gate is adopted (both fail the q = 0 criterion;
  recovery falls at every q < 1 for 8.918125-13.395 h less work lost). Method v2 = blind weight 0.5 with the
  fixed 0.8 gate. The gate still accounts for ~440 h of SlowBurn's DEV work lost above the best
  kept snapshot; a gate that loosens only on detector evidence (not on prior concentration) is a
  candidate for a later, separately pre-specified stage.
- **D52 Finding: underestimating the discovery delay collapses every policy; overestimating is
  safe but costs work lost (v2 DEV, 2026-10-17).** `results/dev_v2_delay` (mean of four worlds,
  q in {1, .5, .2, 0}, benign 0.01): with an assumed maximum of 14 days, prior-only recovers
  1.0 / 0.75625 / 0.0 / 0.0 / 0.0 at true delays 7 / 14 / 30 / 45 / 60 (0.35125 overall); 30 days
  -> 1.0 / 1.0 / 0.828516 / 0.0 / 0.0; 60 (frozen) -> 1.0 / 1.0 / 1.0 / 1.0 / 0.866016; 90 and
  120 -> 1.0 at every true delay, at +492.30375 h and +1084.19625 h work lost vs 60. GFS and
  Tower of Hanoi collapse too (assumed 14: 0.3575 and 0.271641), because they share the restore
  gate. Mechanism: the assumed delay distribution gives zero probability to starts more than its
  maximum before discovery, so the gate trusts post-start snapshots and the retention posterior
  treats older snapshots as worthless.
- **D53 Byte budgets are not used in claims until real churn is in (team decision, 2026-10-17).**
  Definition: "N days' worth of storage" = B_N = m_N x S0, with S0 the machine's day-0 snapshot
  size (unique bytes) and m_N the median, over the 40 attack-free DEV calibration machines (seed
  202, family vault_calib) and every day t >= warm-up + N - 1, of unique_bytes(snapshots
  t-N+1..t) / S0, i.e. the storage keep-last-N needs to hold N daily snapshots. m_14 =
  1.7450643130492298, m_30 = 2.66980547090922, m_90 = 6.146835909945129. Simulated churn on the
  same machines (days 14-172, 6360 machine-days): new unique bytes per day / that day's snapshot
  size, mean 0.058170066359578144 (5.8170066%), median 0.0508335648791331, p10 0.0, p90
  0.12204078998321932; by weekday (day mod 7 = 0..6) 0.07264406384897355, 0.07445049219859667,
  0.07333525922917093, 0.07478416944880155, 0.07428770716863084, 0.020494253937146708,
  0.013619456863168457 (`results/dev_v2/daily_change_rate*.csv`). Byte-budget results stay
  design-only until FSL Homes churn replaces the synthetic churn.
- **D54 Method v2 at q = 0 on the worst-case grid is significantly worse than prior-only at
  K = 6 and 8 (DEV, reported, 2026-10-17).** `results/dev_v2_worst_method/
  q0_v2_vs_prior_only_tests.csv`: exact paired McNemar per K (800 pairs = 160 machines x 5
  delays), Holm over K = 4, 6, 8, 12; machine-cluster bootstrap 95% CI. K = 4: 0.93125 vs 0.9375,
  difference -0.00625 [-0.015, 0.00125], discordant 2 / 7, p 0.179688, Holm 0.359375. K = 6:
  0.9725 vs 0.98125, -0.00875 [-0.015, -0.0025], 0 / 7, p 0.015625, Holm 0.046875. K = 8: 0.9225
  vs 0.93875, -0.01625 [-0.02625, -0.00625], 3 / 16, p 0.004425, Holm 0.0177. K = 12: 0.88625 vs
  0.88125, +0.005 [-0.015, 0.025], 36 / 32, p 0.716301, Holm 0.716301. Both policies retain a
  clean snapshot in 1.0 of these rows, so the recovery gap equals the restore-time failure gap
  (the quantity in the pre-registered criterion). Caveat: McNemar treats the
  5 delays of a machine as independent pairs; the cluster CIs agree for K = 6 and 8. The K = 8 gap
  (0.01625) exceeds the pre-registered 1-point non-inferiority margin, so method v2 as chosen
  would likely FAIL the q = 0 criterion on a grid like this one. Not acted on (no method change
  without the team).
- **D55 Claim (3) fails the team's under-estimated-delay test (v2 DEV, 2026-10-17; claim text NOT
  yet changed, awaiting the team).** With true delay > assumed maximum (14 or 30 days), recovery
  is 0.0 for every policy, world and q (including q = 1); evidence cannot help because the
  assumed delay bound enters the evidence posterior, the restore gate and the verification
  window (all measured after the true start in 1.0 of those rows). By the team's rule claim (3)
  is dropped. The fallback wording has a problem: "~7% less work lost at equal recovery" holds
  (6.960729676%, full v2 DEV grid), but "safe when the detector is blind" does not hold on the
  worst-case grid (D54). Possible wording: "reduces work lost by about 7% at equal recovery; with
  a blind detector it is within one point of prior-only on randomly timed attacks, but can be
  significantly worse for specific attack timings." A method that treats the delay bound itself
  as uncertain (heavy-tailed assumed delay) is a separate design question for the team.
- **D55b Finding recorded (team decision, 2026-10-17): claim (3) in its current form is dropped.
  A hard assumed-delay bound overrides all detector evidence: beyond the bound recovery is 0.0
  for every policy, world and q, including q = 1 (v2 DEV, `results/dev_v2_underdelay`). Evidence
  wording for now: "reduces work lost by about 7% at equal recovery"; nothing about blind safety
  until D57 passes.**
- **D57 Blind-weight re-selection with q = 0 non-inferiority as a HARD constraint (DEV only; rule
  fixed BEFORE the runs, 2026-10-17).** Candidates w in {0, 0.25, 0.5, 0.75, 0.9, 0.95}. Data:
  worlds grid = `results/dev_v2_method_a` (w = 0 ... 0.9; same seed, grid and code path, reused)
  plus `results/dev_v2_blind_worlds` (w = 0.95); worst-case grid at q = 0 =
  `results/dev_v2_blind_worst` (starts 112-143 x delays 7-60 x 5 reps, benign 0.01). Count
  budgets. A weight is ELIGIBLE only if, for each of 8 units (4 worlds, pooled over budgets; 4
  budgets K on the worst-case grid), at q = 0: (1) SlowBurn's restore-time failure rate minus
  prior-only's is at most 0.01, and (2) SlowBurn is not significantly worse: one-sided exact
  McNemar on paired restore-time failures (alternative: SlowBurn fails more), Holm-adjusted over
  the 8 units, adjusted p >= 0.05. Among eligible weights: the highest mean SlowBurn clean
  recovery on the worlds grid (all q, benign rates, budgets, delays), ties within 0.001 broken by
  lower work lost. If no weight is eligible, none is chosen and no blind-safety statement is
  made. The same constraint applies to method v3 (D56).
- **D56 Method v3: soft heavy-tailed assumed delay (DEV only; rule fixed BEFORE the runs,
  2026-10-17).** The hard maximum is replaced by: weight 1 - tail uniform on 1..M, weight tail a
  Lomax tail S(k) = (1 + k/M)^-1 that never reaches zero. It enters through the survival function
  S, which is used consistently by the retention posterior (DP), the discovery-conditioned restore
  posterior, the restore gate and the verification window (the window starts at that posterior's
  0.001 quantile). Candidates: tail in {0.05, 0.1, 0.2} x blind weight w in {0, 0.5, 0.9}.
  Grids (`configs/dev_v3_*.yaml`, count budgets): G1 under-estimated, core M in {14, 30}, all four
  worlds, q in {1, .5, .2, 0}, benign 0.01, 40 reps (true delays 7-60); G2 normal, M = 60, q in
  {1, .5, .2, 0} x benign {0, .01, .05}, 40 reps (same machines as stage A); G3 worst-case timing
  grid, M = 60, q = 0. Prior-only uses the same soft assumption as the variant. A variant is
  ELIGIBLE only if (C1) the D57 q = 0 constraint holds against prior-only with the same soft
  assumption (4 worlds on G2, 4 budgets on G3; excess <= 0.01 and not significantly worse,
  one-sided exact McNemar, Holm over the 8 units) and (C2) on G2 SlowBurn's mean recovery is at
  least method v2's on the same machines (0.978646) - 0.005 and its mean work lost at most 1.10 x
  method v2's (1634.5425 h). Among eligible variants: the highest mean SlowBurn recovery on G1
  rows with true delay > M, ties within 0.001 broken by lower G2 work lost. "Clear rescue" (the
  condition for the team's claim wording) is defined now: for the chosen variant, on G1 rows with
  true delay > M, SlowBurn minus prior-only (same soft assumption) recovery >= 0.10 at each
  q in {0.2, 0.5, 1} and each M in {14, 30}, each one-sided exact McNemar significant after Holm
  over those 6 tests. Reported for every variant regardless: (a) prior-only soft vs hard on G1;
  (b) SlowBurn v3 vs prior-only soft at each q and world on G1; (c) the work-lost cost on G2 and
  for short true delays (7, 14 d) on G1.
- **D57 outcome (2026-10-17): blind weight 0.75 chosen; it passes the hard q = 0 constraint.**
  `results/dev_v2_blind_worst/d57_{scoreboard,units}.csv`. Units passing (of 8) / SlowBurn mean
  recovery / work lost (h) on the worlds grid: w = 0: 0 / 0.974922 / 1673.2425; 0.25: 5 /
  0.979323 / 1655.116875; 0.5: 7 / 0.978646 / 1634.5425 (fails worst-case K = 8: excess 0.01625,
  Holm p 0.0177, = D54); 0.75: 8 / 0.97875 / 1644.030625; 0.9: 8 / 0.977135 / 1646.56875; 0.95:
  8 / 0.977266 / 1650.74875. w = 0.75: largest excess 0.00875 (worst-case K = 8, Holm p
  0.261719); worlds excess bursty 0.006667, early -0.002917, late -0.002083, uniform -0.001667.
  Method v2 becomes blind weight 0.75 (was 0.5, D48). Prior-only on the same machines: 0.9762239583
  / 1736.83375 h, so v2's work-lost reduction on this grid is 5.343235931% (0.5 gave 5.889524544%); the "about
  7%" wording came from w = 0.5 on the full grid and must be re-measured for w = 0.75.
- **D56 amendment (2026-10-17, BEFORE any v3 result was seen):** blind-weight candidates for v3
  become {0, 0.5, 0.75, 0.9} so the D57 choice is included; the w = 0.75 variants run as
  `configs/dev_v3_*_w075.yaml` on the same grids and machines. Rule otherwise unchanged.
- **D58 Downloads (team approval 2026-10-17; decisions made for the team logged here).** Location
  `C:\PROJECTS\ISM\data` (gitignored), hard cap 100 GB, at least 45 GB free on C:, checked before
  every archive and extraction, nothing deleted to make room. Done: NapierOne encrypted 100 per
  family (30 archives, 3,914,326,784 bytes, every archive matching its published SHA-256;
  extracted 3,030 files, 4,301,073,838 bytes) and NapierOne benign `NapierOne-tiny.zip`
  (17,737,521,386 bytes; a zip of 100 per-subset zips, extracted as those inner zips,
  17,737,505,702 bytes; contents are read from the inner zips instead of unpacked, to leave room
  under the cap; the APK/DLL/ELF/EXE/POWERSHELL inner zips are excluded from all use). FSL Homes
  `2011-8kb-only`: block fixed at the first planning run = 2011-09-16 to 2011-12-03, 60 snapshot
  days (calendar gap 2011-11-13 to 11-30 inside), all 13 users, 55,954,970,133 bytes of the
  listing's 87,895,854,552 (1,123 archives, 89 days); the block ends where the cap and reserve
  leave no room for the next day. The server serves ~100 KB/s per connection (measured: 3
  parallel 3 MB range requests at 99.4-99.5 KB/s each, alongside a running download); decision:
  4 concurrent connections (modest load on a university server), roughly 1.5 days for the block.
  fs-hasher is not built (WSL timed out on start); a pure-Python reader
  (`slowburn/datasets/hashfile.py`) re-implements the format from the fs-hasher 0.9.5 source and
  reproduces the bundled example exactly, and on the first real archive (user006, 2011-09-16:
  version 7, variable chunking, 48-bit hashes, 8,550 files, 1,690,689 chunks = header, 0 trailing
  bytes; 4,730 of 8,550 files have no extension, so content mapping needs a fallback for them).
- **D56 outcome (2026-10-17): method v3 not adopted; claim (3) not reinstated.** No soft-tail
  variant meets C2 (normal-grid work lost 3784.02375-3956.44375 h vs limit 1797.99675 h); none
  shows a clear rescue (largest evidence gain 0.0109375). The soft tail alone removes the collapse
  (prior-only recovery 0.988281-1.0 beyond the bound vs 0.0) at 4.180368916-4.539579813x the work lost when
  the true delay is 7-14 days (2.189356782-2.213469266x on the normal grid). Open for the team: whether the paper presents this as a trade-off (hard
  bound: cheap but collapses beyond it; soft tail: safe but restores far back), and whether a
  tail that is cheaper (e.g. smaller weight, or a tail that only opens with detector evidence)
  deserves a separately pre-registered stage.
- **D59 Team decisions (2026-10-21).** (1) Blind weight 0.75 is the method-v2 setting for the
  fresh test. Evidence wording = the full-grid number at 0.75: `results/dev_v2_method_full_w075`
  (run 2026-10-17, first read today), count budgets, all worlds, q in {1, .9, .5, .2, 0}, benign
  {0, .01, .05}, 288,000 rows per variant: SlowBurn 0.982729 / 1611.0825 h vs prior-only
  0.980583 / 1721.6945 h, a work-lost reduction of 6.4246008801% (was 6.960729676% at w = 0.5).
  Wording: "reduces work lost by about 6% at equal recovery". (2) The D56 trade-off goes in the
  paper as a finding (hard bound: cheap, collapses beyond it; soft tail: safe, restores far
  back), all v3 numbers kept. (3) Method v4 (D60). (4) restic: repo `C:\PROJECTS\ISM\restic`
  (gitignored), workload = NapierOne benign files on disk with daily changes driven by FSL churn,
  source + repo <= 25 GB, >= 25 GB free on C:, starts only after the FSL download completes,
  nothing outside that folder is backed up or touched. (5) Extensionless FSL files: fallback
  mapping chosen on DEV, then a sensitivity check (fallback A vs B vs excluding them); report
  whether any headline number moves by more than 1 point. Order: D60 rule, D60 DEV runs while FSL
  downloads, restic, then the fresh test set is generated and frozen.
- **D60 Method v4: soft tail in retention only, hard-bound restore that walks back only on
  damage (DEV only; rule fixed 2026-10-21 BEFORE any code change or run; separately
  pre-registered; the 4th method iteration, so v2, v3 and v4 are all reported).**
  Design. (a) Retention: the DP plans with the D56 soft survival S_soft (uniform core 1..M with
  weight 1 - tail, Lomax tail (1 + k/M)^-1 with weight tail), for both its evidence and its
  prior-only posterior. (b) Restore: the discovery posterior, the 0.8 gate and the verification
  window L use the HARD survival (uniform 1..M, the same M), exactly as v2; this gives v2's
  restore point j_v2. (c) Walk-back (new): let j_0 be the oldest kept snapshot. Deep check of a
  snapshot j: scan every file version held in j written after j_0 (what any available restore
  could undo); x = flagged versions, n = versions scanned; damage is found iff the one-sided
  Beta-Binomial tail P(X >= x | n, a0, b0) < 0.05, with (a0, b0) the fleet-pooled benign prior
  the evidence model already uses (D31). If damage is found at j_v2, step to the next older kept
  snapshot and deep-check it; repeat until one passes or j_0 is reached (j_0 is the restore point
  then). If the restore point moved, every file changed after it is restored (s_sel = j + 1);
  otherwise the restore is v2's (s_sel = max(j + 1, L)). The restore goes beyond the hard bound
  only through this walk-back. The walk-back rule (window, test, alpha 0.05) was fixed by
  Claude Code because the team's text left it open: a plain "any flag" trigger on the widened
  window would walk back on benign invalid files (0.01-0.05 per version, ~40 versions per
  snapshot) on most restores. No alternative trigger is run. All policies share the restore
  (as in v2), so the v4 prior-only also walks back; it uses the detector only at restore.
  Candidates: tail in {0.02, 0.05, 0.1}, blind weight 0.75 fixed. Reference variants on the
  same machines (reporting, and the C1 baseline): hard = method v2 (w 0.75); soft = method v3 at
  tail 0.02 (v3 tails 0.05 / 0.1 at w 0.75 already exist on these machines).
  Grids (templates `configs/dev_v3_*_w075.yaml`, same seed 202 and machines, count budgets,
  policies prior-only and SlowBurn): G1 under-estimated (M in {14, 30}, true delays 7-60, four
  worlds, q in {1, .5, .2, 0}, benign 0.01, 40 reps); G2 normal (M = 60, q in {1, .5, .2, 0} x
  benign {0, .01, .05}, 40 reps); G3 worst-case timing (M = 60, starts 112-143, q = 0, benign
  0.01, 5 reps). The hard variant must reproduce v2 w 0.75 on G2 (1644.030625 h) before anything
  is scored; if it does not, stop and report.
  Criteria (pre-registered). C1 blind safety: at q = 0, v4 SlowBurn vs prior-only HARD (v2
  prior-only, same machines), outcome = clean-recovery failure (retention differs between the
  two, so restore-time failure is not the right quantity), 8 units (4 worlds on G2 pooled over
  budgets, benign rates and delays; 4 budgets on G3), each unit: excess failure <= 0.01 and
  one-sided exact McNemar (v4 fails more) Holm-adjusted over the 8 units >= 0.05. C2 cost: mean
  v4 SlowBurn work lost on G2 <= 1.10 x v2 w 0.75 on G2 = 1.10 x 1644.030625 = 1808.4336875 h.
  Selection: among variants passing C1 and C2, the highest mean v4 SlowBurn recovery on G1 rows
  with true delay > M (all q, worlds, both M), ties within 0.001 broken by lower G2 work lost.
  C3 rescue (claim 3), on the chosen variant (reported for every variant): on G1 rows with true
  delay > M, for each q in {0.2, 0.5, 1} and M in {14, 30}, v4 SlowBurn recovery at q minus at
  q = 0 (paired: same machines) >= 0.10 and one-sided exact McNemar (q recovers more)
  significant after Holm over the 6 tests. Rescue holds at q iff it holds at both M; reported
  per q. Decision: v4 goes to the fresh test iff C1 and C2 pass and rescue holds at q = 0.2 or
  q = 0.5 (rescue only at q = 1, a perfect detector, does not count); claim 3 then reads "When an
  attack stays hidden longer than the policy assumed, detector evidence recovers X vs Y without
  it", naming exactly the q where it held. Otherwise claim 3 is dropped for good and the paper
  presents the hard / soft / evidence-gated trade-off. Reported regardless: hard / soft / v4
  recovery and work lost on every grid; restore depth (discovery day minus restore point: mean,
  median, p90), fraction of restores beyond the hard bound, walk-back steps.
- **D60 outcome (2026-10-21): method v4 not adopted; claim (3) is dropped for good (team rule).**
  `results/dev_v4_{normal,worst,under}/` (`d60_scoreboard.csv`, `d60_c1_units.csv`,
  `d60_rescue_tests.csv`, `d60_threeway*.csv`). The hard variant reproduced v2 w 0.75 on G2
  exactly (1644.030625 h). C1: all three tails pass all 8 units (v4 never fails more than
  prior-only hard; excess -0.11875 to -0.033333). C2: all three FAIL. G2 SlowBurn work lost
  3769.360625 / 3768.303125 / 3755.944375 h (tail 0.02 / 0.05 / 0.1) vs limit 1808.4336875 h
  (2.28x v2), recovery 0.997292 / 0.997214 / 0.997292 (v2 0.97875). No variant is eligible, none
  is chosen. C3 (reported anyway), v4 SlowBurn on G1 rows with true delay > M, recovery at q
  minus q = 0: q = 0.2 no rescue for any tail (gain 0.001042-0.004167); q = 0.5 rescue for tail
  0.02 only (M14 0.145833 vs 0.026563, M30 0.129687 vs 0.015625); q = 1 rescue for every tail
  (gain 0.429688-0.496354, recovery 0.446875-0.522917). For comparison on those rows: hard 0.0 at
  every q; soft (tail 0.02, no evidence needed) 0.972917-0.997917. Mechanism (measured, G2,
  SlowBurn): the restore gate is the same (45.15 days back, hard and v4), but the newest clean
  snapshot the soft-tail DP keeps is 155.37 days back vs 49.83 hard (K = 4 / 6 / 8 / 12: 172.8 /
  158.8 / 150.6 / 139.3 vs 55.8 / 52.9 / 48.1 / 42.6), at every tail weight 0.02-0.1. So the D56
  diagnosis ("the tail in the restore gate makes every restore reach far back") was WRONG: the
  cost comes from retention. A never-zero delay tail makes the DP move the whole count budget to
  old snapshots, not add a few insurance copies, and the tail weight barely matters in
  0.02-0.2. Decoupling the restore removes the soft tail's protection (v4 q = 0 beyond-bound
  recovery 0.015625-0.028125) without removing its cost. Walk-back stopped short at q = 1
  (recovery ~0.5 although a clean snapshot was kept): likely cause, NOT verified, is that the
  simulated detector flags only the damaging version, so a damaged file edited again later is
  held unflagged. Paper: claim (3) dropped; the hard / soft / evidence-gated trade-off is
  presented as a finding, with v2, v3 and v4 reported (4 DEV iterations).
- **D61 FSL download robustness (team decision 2026-10-22).** Downloads resume from `.part`
  with HTTP range requests; the server's Content-Range must start at the partial size and name
  the expected total (else restart from 0); SHA-256 covers partial + resumed bytes and a file
  failing its published hash is moved to `.corrupt` (never deleted) so the next attempt
  re-downloads it. Watchdog (`slowburn/datasets/watchdog.py`): checks every 10 min, restarts the
  fetcher after 30 min with neither new bytes under `data/` nor new fetch-log output, logs every
  start / check / restart to `results/fetch_watchdog.log`, one instance at a time (lock file),
  exits at once after the fetch finished (`results/fetch_watchdog.done`). Runs as the Windows
  scheduled task "SlowBurn FSL download watchdog" (pythonw, at logon and every 30 min for 30
  days; extra launches are no-ops). Remove the task with `Unregister-ScheduledTask -TaskName
  "SlowBurn FSL download watchdog"` once the download is done.
- **D62 q = 1 oddity (team item 3; OPEN, needs the team).** Rule (docs/threat_model.md): a
  damaged file stays damaged until restored; the simulator already does this (damaged files are
  never edited) and every damaged version is flagged at q = 1 (test passes). The verification
  test FAILS (committed as strict xfail): a snapshot holding flagged damaged versions verifies
  clean when those versions are older than L (start-posterior 0.001 quantile, D29), because
  verification scans only versions >= L and file selection restores only files changed >=
  max(j + 1, L). Under a hard bound shorter than the true delay, L lies after the true start.
  Traces (6 + 6 rows, q = 1, beyond the bound): v4 restores from a truly clean snapshot (97% of
  its failures) but leaves the flagged files damaged before L unrestored (median 10); hard v2
  keeps no clean snapshot at M = 14 and its damaged point verifies because the damage predates
  L. On the normal grid L is never after the true start (0 of all count-budget rows), so the
  blind spot only acts when the bound is under-estimated. This is the pre-registered D29
  window, not a coding error: fixing it changes method v2's shared restore and may move F1 (at
  assumed 30 days a clean snapshot is retained in 0.947-0.985 of beyond-bound rows). Not fixed;
  diagnostics only (`configs/diag_d62_*.yaml`, option `old_flags`: "select" also restores files
  whose current version is flagged; "verify" also rejects candidates holding any flagged
  version newer than the oldest kept snapshot; default "skip" = D29 unchanged).
- **D63 Assumed vs true delay characterisation (team item 4; DEV, descriptive, nothing
  selected).** `configs/dev_d63_delay_grid.yaml`: prior-only, SlowBurn v2 (w 0.75), GFS, Tower of
  Hanoi; hard M in {7, 14, 30, 60, 90, 120} plus soft tail 0.1 on core M = 60; true delays {7,
  14, 30, 60, 90, 120}; q in {0, 1} (separate panels); benign 0.01; four worlds x 40 reps; all
  four budgets run, figures at K = 8 (the grid has no single main budget; 8 chosen and stated);
  true delay <= M counts as within the bound. `slowburn fig delay-guideline`. Runs with the
  pre-registered (D29) restore; rerun if D62 changes the restore.
- **D62 record (team item 2a, 2026-10-22).** `docs/threat_model.md` (the damage persistence
  rule) was committed in `dcff256` at 2026-10-22 01:10:28 +0530, in the SAME commit as the
  diagnostic restore options and `configs/diag_d62_*.yaml`; the first diagnostic run log was
  created at 01:10:29. So the rule preceded the runs by one second but was not committed
  separately ahead of the diagnostic design. Item 2b: the 3b test FAILS under "skip" and under
  "select" alone (restore point 15 verifies clean holding damaged files a, b), PASSES under
  "verify". Team decision: the fix is chosen by correctness against the threat model, not by
  the stop rules; the stop rules only flag big moves.
- **D64 Faithful restore-time verification "verify_snap" (spec fixed 2026-10-22 BEFORE any code
  or run).**
  Scanner. Per machine, every (file, version day) gets ONE uniform draw u from a dedicated
  random stream keyed by the machine seed key (detect_prob and benign rate excluded, so cells of
  one machine are paired), the file and the version day; independent of the write-time evidence
  flags. The same draw is reused whenever that version is scanned during a restore (a detector
  gives the same answer for the same bytes). A version is damaged iff the file's damage day is
  <= the version day (threat model D62 rule: damage persists until restored). Flag = u < q for a
  damaged version, u < b for a clean one, with q and b the cell's detect_prob and
  benign_invalid_rate (the detector's normal false positive rate).
  Verification. For each gated candidate j (gate, hard-bound posterior, newest-first order and
  the oldest-kept fallback all unchanged from D29), scan EVERY file version contained in snapshot
  j (no L window); any flag rejects j. File selection ("select"): restore every file changed on
  or after max(j_r + 1, L) and also every file whose current version (at discovery) is flagged by
  the same scanner and is newer than j_r. Method v4's deep check uses the same scanner on the
  versions in (j0, j] with its unchanged Beta-Binomial test. Retention and the daily evidence
  stream are unchanged. Expected consequence, stated in advance: a false positive on an old
  version held by every candidate rejects all of them and the restore falls back to the oldest
  kept snapshot, so work lost can rise when b > 0.
  Test: item 3b, re-stated for the scanner, must pass at q = 1 (no snapshot holding a damaged
  version verifies clean).
  Runs (DEV, blind weight 0.75): worst-case grid at q = 0 (hard M 60, prior-only and SlowBurn);
  under-estimated grid (hard M 14 / 30, and v4 tails 0.02 / 0.05 / 0.1 at M 14 / 30 for F3).
  Adoption (team rule, fixed): the restore + verification that passes the 3b test and matches
  the threat model is adopted whatever its cost. After adoption every DEV result that uses
  verification is rerun (v2 w 0.75 full grid, worlds grid, worst case, under-estimated, the D57
  blind-weight table, v4) and reported old vs new. Stop and report if a C1/C2 recovery moves by
  more than 0.01 absolute, a work-lost value by more than 1% relative, the C3' reduction by more
  than 1 percentage point, or w = 0.75 no longer passes all 8 q = 0 units; the new numbers then
  replace the old in docs/claims.md. w is not reselected. F1 is rewritten only from the adopted
  pipeline. The D63 sweep waits for adoption.
- **D64a Amendments to D64 (team, 2026-10-22; committed BEFORE any D64a run).**
  Incident first: the original D64 runs were launched at 02:21:30 before these amendments
  arrived and were stopped at 02:25:38 (worst-case grid finished, under-estimated grid partial).
  Their outputs were renamed `results/aborted_d64_*` UNREAD and are not used.
  (1) Detector determinism: ONE draw per file version, shared by the daily evidence scan and the
  restore-time scan. The simulator already makes exactly one: the daily scan flags each version
  on the day it is written (damaged with probability q from the detector stream, clean when it
  fails validation, rate b, from the aux stream), stored per version in
  `FileHistory.flagged_days`. Verification reads those flags; a version missed at write time is
  missed at restore time. No exception: the abstract detector has no richer restore-time mode
  (no whole-file vs changed-chunk distinction), so no second rate is modelled. D64's separate
  per-version scanner with fresh draws is withdrawn.
  (2) Snapshot accept rule: the existing D29 rule, unchanged: a candidate fails verification
  if ANY scanned version is flagged. No threshold is introduced. (Method v4's deep check keeps
  its own pre-registered D60 Beta-Binomial test, unchanged.)
  So verify_snap (D64a) = for each gated candidate, scan EVERY file version contained in the
  snapshot (no L window) with the shared per-version flags, any flag rejects; gate, order and
  oldest-kept fallback as D29; file selection = files changed on or after max(j_r + 1, L) plus
  every file whose current version is flagged and newer than j_r ("select").
  (3) Work lost: confirmed, no metric change. Whole-system work lost (the headline metric) is
  (discovery - restore point) x 24 h on a clean restore, so rolling back a wrongly flagged clean
  file adds nothing it does not already count; the selective file metric counts that file's
  lost edits explicitly (unit check: a clean file with a false-positive version on day 10, L =
  16, restore point 5: selective 0 h without select, 24 h with select; whole-system 360 h both).
  (4) Old vs new: same seed (202), configs and machines as `results/dev_v2_method_full_w075`;
  pairing is checked on the machine key plus true start, and on retention (kept-set columns must
  be identical, since retention is unchanged); paired deltas with machine-cluster bootstrap CIs.
  (5) The 3b test and the end-to-end q = 1 check are rerun under D64a before the runs; then the
  worst-case (q = 0) and under-estimated grids run as one job. Adoption rule unchanged.
- **D64a outcome (2026-10-22): verify_snap ADOPTED (passes the 3b test, matches the threat
  model); STOP RULE TRIGGERED, downstream reruns held for the team.** Runs: `results/
  dev_d64a_{worst,under}` (same machines as `dev_v4_*`; pairing 6400 / 6400 and 204800 / 204800
  rows; retention columns identical row for row, so only the restore changed).
  Worst-case grid, q = 0, old -> new (paired): prior-only recovery 0.934688 -> 0.945625
  (+0.010938), work lost 1865.1075 -> 2167.335 h (+16.2043%); SlowBurn 0.933438 -> 0.945 (+0.011563),
  1868.895 -> 2179.155 h (+16.6013%). Thresholds crossed: work lost > 1% relative, C1
  worst-case recovery > 0.01. Blind units on this grid still pass (SlowBurn - prior-only
  restore-time failure by K = 4 / 6 / 8 / 12: 0.00375 / 0.00375 / 0.00625 / -0.01125; old
  0.00375 / 0.00375 / 0.00875 / -0.01125). Mechanism: old benign false positives held in every
  candidate now reject them, so restores fall back further (D64 predicted this).
  Under-estimated grid, SlowBurn, true delay > M, recovery at q = 0 / 0.2 / 0.5 / 1 (new): hard
  M 14: 0 / 0 / 0.0026 / 0.1495; hard M 30: 0 / 0 / 0.0062 / 0.8891; v4 (every tail) M 14: 0 / 0 /
  0.0042 / 1.0, M 30: 0 / 0 / 0.0062 / 1.0. Hard q = 1 recovery equals the fraction of rows with a
  clean snapshot retained (0.1495, 0.8891). v4's q = 0.5 rescue (old 0.0977-0.1458) disappears:
  verification now walks the gated candidates down to one whose damaged versions were all
  missed (near the start, few damaged files) and accepts it, so the walk-back never starts.
  Within the bound, hard M 14 q = 0 recovery 0.7844 -> 0.8367 and work lost 1205.3 -> 1055.1 h.
  Not yet rerun under the adopted restore: full grid (C1 worlds, C2, C3'), worlds grid / D57
  table, v4 normal grid. claims.md not yet changed; D63 still on hold.
- **D64b Step 1 reruns under the adopted verify_snap (team decision 2026-10-22, recorded BEFORE
  any run).** Option 1: verify_snap with the inherited D29 accept rule is the adopted pipeline,
  the +16% worst-case work-lost cost accepted. Every policy (prior-only, SlowBurn, GFS, Tower of
  Hanoi, keep-last-N, oracle) restores through the same `verified_restore` call with the run's
  `old_flags`; there is no per-policy restore path (amoeba_style is not a snapshot policy and is
  in no config). Confirmed after each run from the `hp_old_flags` column: every row
  `verify_snap`. Runs (configs copied from the source, only name, output dir and variants
  changed; seed 202, same grid and machines):
  `dev_d64a_blind_worst` (from `dev_v2_blind_worst`, w 0 / 0.25 / 0.5 / 0.75 / 0.9 / 0.95),
  `dev_d64a_blind_worlds` (from `dev_v2_method_a`, same six w; old: `dev_v2_method_a` +
  `dev_v2_blind_worlds`), then, only if w = 0.75 passes all 8 D57 units:
  `dev_d64a_full` (from `dev_v2_method_full_w075`), `dev_d64a_worst_all` (from
  `dev_v2_worst_method`, every policy at w 0.75, old restore `skip` and `verify_snap` side by
  side, since no earlier worst-case run has every policy at w 0.75), `dev_d64a_v4_normal`,
  `dev_d64a_v4_worst` (from `dev_v4_*`). Under-estimated grid: `dev_d64a_under` (done).
  Reporting: per row pairing on PAIR_KEY plus true start, policy, budget kind and detect_prob;
  retention columns must match row for row; paired deltas (new - old) of clean recovery and
  whole-system work lost with 95% cluster bootstrap CIs, clusters = simulated machines (world,
  attack start, rep; shared across q and b), 2000 resamples, seed 0. If w = 0.75 fails any of
  the 8 units: stop and report, no reselection. The new numbers replace C1 / C2 / C3' in
  docs/claims.md whatever they are; F1 and F3 are rewritten from the adopted pipeline (team
  text). The D65 accept-rule iteration is pre-registered only after step 1 lands.
- **D65 Method v2.1: significance-based snapshot accept rule (team, 2026-10-22; committed
  BEFORE any step 1 result is read and before any code or run).** One pre-registered DEV
  iteration on top of the adopted D64a pipeline; no further accept-rule iterations either way.
  Rule. For each gated candidate j (gate, hard-bound posterior, newest-first order, oldest-kept
  fallback, "select" file selection and the v4 walk-back all unchanged from D64a), let n = the
  number of files with a version in j (every version j holds, no L window) and x = how many of
  those versions carry their shared write-time flag. j verifies unless x is significant under
  the D60 walk-back test (`slowburn/store/restore.py:186`, `deep_damage`): one-sided
  Beta-Binomial tail P(X >= x | n, a0, b0) < alpha, with (a0, b0) the cell's fleet-pooled
  benign prior (the same `null_prior` D60 uses) and alpha = 0.05 (D60's value). No new
  parameters. Correction recorded: the team's first wording said "the same binomial test already
  used for daily evidence"; the daily evidence is the Bayesian changepoint model and has no
  alpha-level test, so the test meant is the D60 walk-back test above, not a plain binomial at
  the pooled mean rate.
  Multiplicity. The test is applied per candidate during the walk with no multiplicity
  correction; the per-candidate false reject rate (about alpha on a clean snapshot) is accepted
  as part of the rule. alpha is not changed after results.
  Runs (DEV, w 0.75, paired against the step 1 / D64b runs on the same machines): worst-case
  grid at q = 0 (from `dev_d64a_blind_worst`, w 0.75), full grid (from `dev_d64a_full`), the
  D57 worlds grid at w 0.75 (from `dev_d64a_blind_worlds`) for the blind units; under-estimated
  grid and worst case with every policy for reporting.
  Adoption: ALL must hold, on the worst case q = 0 and the full grid, paired vs step 1:
  (a) clean recovery not lower by more than 0.01 on any grid or world (full grid per world,
  count budgets; worst case pooled);
  (b) whole-system work lost lower (point estimate) on the worst case and on the full grid;
  (c) all 8 D57 blind units at w = 0.75 still pass;
  (d) the 3b test, restated: with q = 1 a snapshot whose damaged-version flag count is
  significant under the test must not verify (unit test before any run).
  If any fails, v2.1 is rejected and the step 1 numbers stand. v2.1 is reported either way.
- **D64b outcome (2026-10-22): step 1 complete; w = 0.75 passes all 8 blind units; claims.md
  updated.** Every row of every rerun restored with verify_snap (checked from `hp_old_flags`);
  every pairing complete with retention identical row for row. D57 units at w 0.75 (worlds
  bursty / early / late / uniform; worst K 4 / 6 / 8 / 12): excess 0.0058 / -0.0008 / -0.0021 /
  -0.0021; 0.0038 / 0.0038 / 0.0063 / -0.0113, all Holm p >= 0.39: 8 / 8 pass (w 0.5: 7 / 8;
  w 0: 0 / 8; reporting only, no reselection). Full grid, count, old -> new pooled: prior-only
  0.9806 -> 0.9845, 1721.7 -> 2148.5 h (+24.8% [22.6, 27.0]); SlowBurn 0.9827 -> 0.9864,
  1611.1 -> 2047.1 h (+27.1% [24.7, 29.4]); GFS +0.03%, Tower of Hanoi +2.9%, keep-last-N and
  oracle unchanged. C3' -6.42% -> -4.72% [-5.46, -3.93]. At q = 0 SlowBurn now loses +0.85%
  [+0.03, +1.65] more work than prior-only (recovery equal). C2 against GFS in the early world
  no longer significant: SlowBurn -3.0% [-9.5, +3.9], prior-only +1.7% [-5.1, +8.6] (flagged
  in claims.md for the team). Worst case, every policy (old restore run alongside): prior-only
  +18.3%, SlowBurn +18.6% work lost; recovery +0.004. v4 normal grid: 3911.8-3918.1 h vs hard
  2078.2 h (1.88x), still fails C2 (limit 2286.1); C1 8 / 8; rescue only at q = 1. Tables:
  `results/dev_d64a_{blind_worst,full,worst_all,v4_normal,v4_worst}/`.
- **D65 scoring note (team, recorded 2026-10-22 20:20:13 +0530, BEFORE any D65 result is read).** Criteria (a)-(c)
  are scored on SlowBurn (the method). Prior-only, GFS and Tower of Hanoi are printed for
  reference only and do not enter the verdict. No criteria are added after the fact (in
  particular not the early-world C2 check); (a)-(d) as committed in D65 are the whole rule.
- **D65 outcome (2026-10-22): v2.1 REJECTED (criterion a fails); step 1 (D64a verify_snap)
  numbers stand; no further accept-rule iterations.** Scored on SlowBurn as recorded before
  the results were read; pairing complete, retention identical row for row.
  (a) FAIL. Worst case q = 0: recovery 0.9450 -> 0.9262 (-0.0188 [-0.0238, -0.0144]). Full grid,
  count, per world bursty / early / late / uniform: -0.0122 / -0.0170 / -0.0196 / -0.0155 (every
  world beyond -0.01; CIs exclude it in every world but bursty, [-0.0146, -0.0099]).
  (b) pass. Work lost worst case 2179.2 -> 1852.5 h (-15.0%), full grid 2047.1 -> 1593.8 h
  (-22.1% [-23.6, -20.6]).
  (c) pass. 8 / 8 units at w 0.75 (largest excess 0.0087, K = 8 worst case, Holm p 0.262).
  (d) pass (unit test, d48f681).
  Reference only (not in the verdict): prior-only fails (a) too (full grid -0.0266 pooled),
  GFS / Tower of Hanoi pass (a) and (b). Beyond the bound, SlowBurn q = 1 recovery 0.1495 ->
  0.1062 (M 14), 0.8891 -> 0.6852 (M 30). Worst case, every policy: SlowBurn 0.9793 -> 0.9705,
  -17.9% work lost. Mechanism, as the rule implies: a single flagged damaged version (not
  significant against the benign prior) no longer rejects a candidate, so lightly damaged
  snapshots verify; v2.1 recovers the D64a work-lost cost by giving back recovery.
  Tables: `results/dev_d65_{worst,full,worst_all,under}/`.
- **D63 run amendment (2026-10-22, before the run): restore = the final adopted pipeline (D64a
  verify_snap, D65 rejected) for every policy.** `configs/dev_d63_delay_grid.yaml` predates the
  adoption; every variant now sets `old_flags: verify_snap`. Nothing else in D63 changes.
- **D63 outcome (2026-10-22; descriptive, nothing selected; adopted verify_snap restore).**
  `results/dev_d63_delay_grid` (exit 0), figure `fig_delay_guideline_{recovery,work_lost_h,
  scatter}` and CSVs (generated; not kept in this repository) (K = 8; all budgets in
  `delay_grid_cells_all_budgets.csv`). Pre-registered question, under-estimated rows (hard M,
  true delay > M), paired, one-sided McNemar, Holm over 30 rows: at q = 0 no policy recovers
  anything (all 0; ties). At q = 1 a fixed schedule DOES beat SlowBurn where the bound is short:
  Tower of Hanoi at M 7 / 14 / 30 (0.708 / 0.634 / 0.525 vs SlowBurn 0 / 0.230 / 0.142), GFS at
  M 7 (0.348 vs 0); SlowBurn beats both at M 60 / 90 (0.972 / 1.0 vs GFS 0, ToH 0.366 / 0.100).
  Prior-only beats SlowBurn at q = 1 for M 14 / 30 / 60 (0.250 / 0.333 / 1.0 vs 0.230 / 0.142 /
  0.972). Pooled under-estimated rows, q = 1: ToH 0.565, prior-only 0.333, SlowBurn 0.286, GFS
  0.165; q = 0: 0 for all. Edge effect (not a bug, reported): at true delay = M the uniform 1..M
  prior gives the start day only 1/M mass, so the DP may keep no snapshot before it; the
  diagonal is below 1 (SlowBurn 0.76 / 0.66 / 0.71 at M 14 / 30 / 60) and at K = 8, M = 7 the
  DP keeps exactly days d-7..d (recovery 0 at delay 7 for both DP policies; K 4 / 6 / 12 keep
  older snapshots and recover 0.78-1.0).
- **D66 Retention audit of product defaults (team request 2026-10-23; DEV only, descriptive,
  nothing selected, claims.md unchanged; recorded BEFORE any audit code or run).** Rules, sources
  and the simulation mapping are fixed in `docs/baselines.md` (Dropbox 30/180/365 d, Google Drive
  30 d or 100 newer versions, OneDrive personal 25 versions (+ 30 d variant), OneDrive for
  Business 500 versions, restic documented forget presets, NetApp ARP/AI 12 h / locked until
  response / 7 d). Grid = D63 attack grid, q in {0, 1}, benign 0.01, delays 1..400 days; adopted
  restore (D64a verify_snap, M = 60) for every product, per-file products through a point-in-time
  analogue of verify_snap. Per-file churn from FSL Homes, the 48 complete verified days only
  (2011-09-16..2011-11-03; the per-file rewrite process is replayed circularly, so the missing 12
  days are not needed). Output: recovery and "clean point held" vs true delay, first grid delay
  with recovery < 0.5 and < 0.1. Stated before the run: with this attack model (one damaging write
  per file) no count limit >= 2 can drop a file's last clean version.
- **D66 amendment (team, 2026-10-23; recorded BEFORE any D66 result is read, before the run):
  rewrites per damaged file, r.** Simulation parameter only (no code rewrites real files):
  r = damaged versions per damaged file (r = 1 is the main rule, the simulator's single damaging
  write; r - 1 extra damaged versions are added). Timing, fixed now: all r damaged versions carry
  the damage day (written that day, before the next daily snapshot), so time windows and daily
  snapshots are unaffected and only per-file COUNT limits see them. r in {1, 2, 5, 25, 100},
  reported as labelled variants `<product>_r<r>` for the count-limit products
  (gdrive_30d_100v, gdrive_30d_100v_created, onedrive_personal_25v, onedrive_personal_25v_30d,
  onedrive_business_500v); every other product and every headline row stays at r = 1.
  Expected mechanics, stated before the run: a count limit N loses a file's last clean version
  once r >= N (OneDrive personal at r = 25 and 100, Google at r = 100, OneDrive for Business never
  in this range).
- **D67 NapierOne integration rule (team decision 2026-10-23; recorded BEFORE any code or run;
  DEV only; no reselection of w, gate, alpha, M or any threshold).**
  *Why the design looks like this:* retention runs use abstract tokens and an abstract detector
  (q), where file content has no effect, so swapping the data there would change nothing. Real
  data enters through a real detector on real bytes: both arms below run the retention
  simulator in byte mode with the trained LightGBM chunk detector, and the detector's flags
  replace the abstract q.
  *Benign files.* NapierOne-tiny subsets mapped to the simulator's types (lzma has no NapierOne
  counterpart and is dropped from BOTH arms; 9 types): txt <- TXT; csv <- CSV; bin <- BIN;
  docx <- DOCX; zip <- ZIP-DEFLATE, ZIP-BZIP2, ZIP-LZMA, ZIP-PPMD, ZIP-HIGH-COMPRESSION;
  png <- PNG-c0/c3/c5/c7/c9, PNG-FROM-WEB; jpg <- JPG-q001/q025/q050/q075/q100, JPG-from-web;
  mp3 <- MP3; zlib <- ZLIB. Excluded: *-PASSWORD, *-NOMAGIC, *-ENCRYPTED (deliberately unusual;
  reported as a later robustness check, not used now), RANSOMWARE-* and RANDOM-* (not benign
  documents), executables (never extracted). Files are read from the inner zips in memory.
  *Encrypted files.* All 30 NapierOne families (100 files each), spliced offset-aligned into
  the damage masks (`NapierOneDamageSource`), exactly as the synthetic arm uses random bytes.
  *Splits, seed 202, stream "napierone_split".* Per type, the pooled files are permuted and
  capped at 100: 50% detector train, 20% detector calibration, 30% held out (detector AUROC
  test). The held-out 30% is the only content for simulated machines: DEV machines take its
  first half, the later fresh TEST set the second half (TEST files are not read now). Families
  are permuted the same way: 18 train, 6 calibration, 6 held out (3 DEV, 3 TEST); DEV damage
  bytes come from the 3 DEV families only.
  *Machines.* Unchanged grid and seeds (dev_d64a_full, dev_d64a_blind_worlds settings; 40 files
  per machine, types cycled as now). File i of a machine takes a file drawn (seeded by the
  machine key and "napierone_content") from the DEV pool of its type, at most 1 MiB. Benign edits
  replace chunks with chunks of another DEV-pool file of the same type (whole-file types: the
  whole file). This edit model on real content is simulated and labelled so.
  *Detector.* The NapierOne arm trains with configs/detector.yaml unchanged (same model, same
  variants, default variant `validity`) on the NapierOne train/calibration splits. The synthetic
  arm uses the existing synthetic detector (`results/detector/detector.pkl`, seed 11). A file is
  flagged when its file-level p-value is <= 0.01, the frozen daily-statistic alpha. These flags
  feed both the daily evidence and the verify_snap restore, as the abstract flags do now.
  *Runs.* (1) Detector AUROC table with NapierOne benign and NapierOne damage, next to the
  existing synthetic table. (2) The C1/C2/C3' full grid (dev_d64a_full: worlds x benign rate
  {0, 0.01, 0.05} x 40 reps, all policies and budgets) and the worlds grid, in two paired arms
  with the same machines and attack timing: synthetic bytes + synthetic detector, and NapierOne
  bytes + NapierOne detector. The q axis does not exist with a real detector. The C3' blind
  half (q = 0) is the absence of a detector, so it is unaffected by the data and stays as
  reported (abstract). Reported side by side: synthetic (abstract q, current claims),
  synthetic-bytes/real-detector, NapierOne-bytes/real-detector.
- **D68 Equal-horizon fairness diagnostic (team overnight queue 2026-10-23, JOB 1; the team
  labelled it "D67", but D67 is already the NapierOne rule, so it is D68; recorded BEFORE any code
  or run; DEV only, report only, nothing selected).**
  *Horizon.* H(policy, K) = the largest D <= 400 such that for every delay d = 0..D and every
  discovery day t < 800 with attack start s = t - d >= max(1, 2d), the policy's held set at t
  (replayed alone, one snapshot per day, K counting today's) contains a day j < s. This is the
  G1 / Theorem 2(a) check (`theory_checks.toh_guarantee_table`), maximised over D.
  *Tower of Hanoi family (base b).* Day n = t + 1 goes to level min(v_b(n), K - 1), where v_b(n)
  is the largest k with b^k dividing n; each level keeps its newest day, plus today. b = 2 is the
  current Tower of Hanoi. Rule: the smallest integer b in 2..64 with H >= M.
  *GFS family.* Tiers daily (1), weekly (7-day blocks), monthly (28-day blocks), quarterly
  (91-day blocks), with the current GFS block semantics (newest snapshot of each of the most
  recent completed blocks). Counts n1 >= 1, n7, n28, n91 >= 0, summing to K. Rule: among
  configurations with H >= M, the lexicographically largest (n1, n7, n28), i.e. the finest
  tiers. No configuration with H >= M at that K: the cell is infeasible and is reported as such.
  *Cells.* K in {4, 6, 8, 12} x M in {7, 14, 30, 45, 60, 90, 120} (the D63 bounds plus 45): table
  of chosen configurations, H and feasibility.
  *Runs.* The full grid (dev_d64a_full machines: worlds x q {1, .9, .5, .2, 0} x benign
  {0, .01, .05} x 40 reps, count budgets) with the adopted restore (D64a verify_snap, w 0.75,
  M = 60), policies SlowBurn, prior-only, Tower of Hanoi, GFS, `toh_eqh` and `gfs_eqh`
  (configured for M = 60 at each K). The worlds grid (dev_d64a_blind_worlds) uses the SAME
  machines with q in {1, .5, .2, 0}, so it is reported as that subset of the same run rather
  than re-simulated.
  *Report.* toh_eqh and gfs_eqh against SlowBurn and against prior-only, paired by row:
  recovery difference and relative work-lost difference, 95% machine-cluster bootstrap CIs
  (clusters (world, start, rep), 2000 resamples, seed 0). Pooled, per world and per K; full
  grid, plus the worlds subset at q = 0 and q = 1. Question: at equal budget and equal horizon,
  does SlowBurn still win on recovery, on work lost, or neither? Report only.
- **D69 Worst-case-optimal online checkpointing baselines (Bar-On, Dinur, Dunkelman, Hod,
  Keller, Ronen, Shamir, "Tight Bounds on Online Checkpointing Algorithms", arXiv 1704.02659v2;
  team JOB 2, labelled "D68" by the team; recorded BEFORE any code or run; DEV only).**
  *Mapping.* The paper keeps k checkpoints in [0, T], with 0 and the present T as free virtual
  checkpoints. Our budget K counts today's snapshot, which plays the role of T, so k = K - 1.
  *Algorithms implemented* (paper notation, update times t_i, pattern p_i = freshness index):
  (a) exact optimal schedules the paper gives in closed form: k = 3 Round-Robin with G = golden
  ratio (Prop. 3.2, q3 = 1.5278641); k = 4 the (2, gamma)-cyclic algorithm, gamma the largest
  root of x^3 - x^2 - 2x + 1, pattern (3, 1), S4 = (1, g, g^3 - g^2, g^2) (Prop. 3.4,
  q4 = 1.5398927); k = 5 the (2, G)-geometric algorithm, G = 1/(1 - r5), pattern (3, 1),
  S5 = (1, G^2, G^3, G^4, G^5) (Prop. 3.3, q5 = 1.4707341). In our grid these apply at
  K = 4 (k = 3) and K = 6 (k = 5); k = 4 (K = 5) is implemented and tested but not in the grid.
  (b) best single-ratio geometric family: Round-Robin with G = 1/(1 - r), r the smallest root
  of x = (1 - x)^(k - 1) (Prop. 3.1); the paper's rule, not tuned (k = 4: 5 r~4 = 1.58836, the
  best geometric 4-checkpoint efficiency).
  (c) Recursive(G*, K*) (Section 4): K* = {k_j = floor(2^-j k), j = 0..m; 0}, m = floor(log2 k)
  - 1, pattern p_{k+i} = 1 + k_{mu(i)+1}, update times G^i; G* = the G > 1 minimising
  r(G, K*) = max of (1a), (1b), (1c) (equivalently the paper's "smallest root" rule).
  The paper specifies (c) fully. The optimal k = 6..10 schedules of Table 1 are NOT used: the
  table gives patterns and gamma, but the update times come from an LP that is not printed.
  So K = 8 (k = 7) and K = 12 (k = 11) use (b) and (c) only.
  *Daily discrete time.* The continuous algorithm runs with time unit s days, s the smallest
  integer for which the initial checkpoints fall on distinct days. At the end of day d the held
  set is today's snapshot plus floor(T_j) for the algorithm's checkpoints after every update with
  t_i < d + 1. An update at t_i stores day floor(t_i), which is today's snapshot when it happens,
  so the policy never needs a snapshot it has dropped.
  *Unit tests.* Continuous efficiency of each sequence, measured at update times, equals the
  paper's q_k (above, plus the Recursive values of Tables 3 and 4 where k matches) within 1e-6.
  Discrete efficiency (max over days 2,000..200,000 of the longest gap / (d / (k + 1))) is
  reported. Normalisation note: the team's targets (c3 ~ 1.1459, c5 ~ 1.2256, geometric
  c4 ~ 1.2707) equal q_k * k / (k + 1), i.e. the ideal gap taken as T/k instead of the paper's
  T/(k + 1). Both are reported. The paper's own definition (T/(k + 1)) is the primary one.
  *Runs.* Count budgets K in {4, 6, 8, 12}. Grids: the full grid (dev_d64a_full machines;
  the worlds grid is its q in {1, .5, .2, 0} subset, same machines), the worst case
  (dev_d64a_worst_all machines, q in {0, .5, 1}), and the D63 delay grid (q in {0, 1}, every
  assumed-bound variant). Policies: SlowBurn, prior-only, Tower of Hanoi, GFS,
  shamir_exact (K 4, 6), shamir_rr, shamir_recursive.
  *Restores, for EVERY policy.* (i) The adopted D64a verify_snap. (ii) An oracle restore: the
  newest kept snapshot older than the true start (the oldest kept if none), with every file
  changed after it restored. (ii) separates retention quality from restore quality; the paper's
  model assumes the rollback point is known. (ii) is computed on the same rows as extra columns,
  with no second simulation.
  *Report.* Every Shamir scheme against SlowBurn, prior-only, Tower of Hanoi and GFS, paired, with
  cluster bootstrap CIs, under both restores. Report only.
- **D68 amendment (2026-10-23, BEFORE any D68 run; configuration only, no result read).**
  The configuration table (`results/dev_d68_equal_horizon/eqh_configs.csv`) shows the
  pre-registered base-b Tower of Hanoi family never extends the horizon beyond base 2. Base 2
  gives H = 3 / 15 / 63 / >= 400 at K = 4 / 6 / 8 / 12, i.e. 2^(K-2) - 1, tight. Larger bases are
  worse: with "newest per level", m and m - b^j can share a level. A stride-p rotation (checked,
  not adopted) fails at d = 0, since it does not hold yesterday. GFS tiers cannot reach the bound
  at K = 4 or 6 for any M: blocks of 7, 28 and 91 days align, so on a quarter boundary every tier
  holds yesterday. No family is added. At the run's M = 60: toh_eqh is feasible at K = 8 and
  K = 12 (base 2, i.e. the existing Tower of Hanoi) and infeasible at K = 4 and 6; gfs_eqh is
  feasible only at K = 12, with (7 daily, 2 weekly, 3 monthly, 0 quarterly), H = 76. Infeasible
  cells are reported as such and get no rows. Noted for the report: H has no work-lost bound, so
  keep-first (day 0 plus today) has an unbounded horizon with 2 slots; equal horizon alone is a
  weak fairness criterion.
- **D70 Pareto summary (team overnight queue 2026-10-23, JOB 5, labelled "D69" by the team;
  recorded BEFORE any code or run; DEV, descriptive, nothing selected).** Panels: each start-time
  world (uniform, early, late, bursty) x each count budget K in {4, 6, 8, 12}. Points: mean clean
  recovery and mean whole-system work lost per policy over the panel's rows of the full grid
  (dev_d64a_full machines: q in {1, .9, .5, .2, 0}, benign {0, .01, .05}, delays 7-60, 40 reps),
  under (i) the adopted verify_snap restore and (ii) the oracle restore. Policies on these machines:
  SlowBurn, prior-only, Tower of Hanoi, GFS (from D69's run), shamir_exact/rr/recursive (D69),
  toh_eqh/gfs_eqh (D68; verify_snap only, since D68 has no oracle columns; cells as feasible).
  Pareto optimal = no other policy in the same panel and restore has recovery >= and work lost
  <= with one strict. The D66 product defaults run on DIFFERENT machines (FSL churn, delays
  1-400, no budget K), so they are drawn on every panel as separately marked reference points
  from their own grid (restricted to delays 7-60, verify_snap and their "held" curve). They are
  NOT included in the Pareto comparison: mixing machine sets would be invalid. Also written: the
  q = 0 and q = 1 panels separately. CSVs and figures (generated; not kept in this repository)
  (`pareto_points.csv`, `fig_pareto_<restore>.png`).

## Team decisions after the overnight run (2026-10-23)

- C2 and C3' as stated do not hold on NapierOne bytes (D67); recorded in docs/claims.md with the
  JOB 3 numbers. Recovery claims (C1) stand.
- Bar-On et al. online checkpointing (D69: shamir_exact / shamir_rr / shamir_recursive) replaces
  GFS / Tower of Hanoi as the main retention baseline. GFS and Tower of Hanoi stay as secondary.
- No method changes to SlowBurn retention. No new restore method until the team has seen the
  D71 gap table.

- **D71 restore diagnostics (team list 2026-10-23, items 1-3; recorded BEFORE any code or run;
  DEV, descriptive, report only, nothing selected or tuned).**
  Machines: exactly the D69 full grid (dev_d69_full: seed 202, the four worlds, reps 40, delays
  7-60, q in {1, .9, .5, .2, 0}, benign {0, .01, .05}, count budgets K in {4, 6, 8, 12}, w 0.75,
  hard M 60). Policies: prior-only, SlowBurn, GFS, Tower of Hanoi, shamir_exact / rr / recursive,
  toh_eqh, gfs_eqh (equal horizon only where D68 found a configuration; others at every
  supported K). One new run, `configs/dev_d71_oracle_gap.yaml`, adds to every row:
  1. **Oracle gap.** (a) the adopted verify_snap restore (unchanged), (b) the D69 oracle
     SNAPSHOT restore (newest kept snapshot older than the true start; every file changed after it
     restored). Reported per policy x q in {0, .2, .5, 1} x K, on the full grid (pooled over
     worlds) and the worlds grid (by world): recovery and whole-system work lost under (a) and (b)
     and the paired gap (a) - (b), recovery as a difference, work lost as a ratio, 95%
     machine-cluster bootstrap CIs (2000 resamples, seed 0). q = .9 is run (same machines) but not
     tabled.
     Restore-choice diagnosis, rows where a clean snapshot was retained (some kept j < true
     start; j* = the newest such), verify_snap's restore point j_r classified as:
     - `picked_clean_point`: j_r = j*;
     - `missed_damage`: j_r >= true start (a dirty snapshot verified because its damaged
       versions were not flagged);
     - `false_flag`: j_r < j*, j* passed the gate and was rejected by a flag; every flagged
       version in j* is benign by construction. Sub-label whether a flagged version was the
       file's day-0 (creation) version;
     - `gated_out`: j_r < j* and j* failed the 0.8 gate;
     - and separately `residual_outside_scope`: j_r clean but damaged files remain (damaged files
       outside the restore set, i.e. unflagged and changed only before L).
     Reported: share of all rows with j_r != j* and with failed recovery despite a held clean
     snapshot, and the shares by cause, per policy x q (pooled K), with cluster bootstrap CIs.
  2. **Per-file oracle ceiling.** (c) every damaged file restored from the newest version held
     in any kept snapshot that is truly clean (version day < its damage day); undamaged files
     untouched. Recovery = every damaged file has such a version. Work lost = benign versions
     discarded (file-days x 24 h, the `work_lost_selective_file_hours` accounting of (a) and
     (b)). Reported for (a), (b), (c) on the same rows; (c) is the upper bound of any per-file
     restore over that retention. Whole-system work lost is not defined for (c).
  3. **NapierOne false-flag rate.** Re-simulate exactly the D67 eval machines of both arms
     (dev_d67_full_synthetic / dev_d67_full_napierone, same tasks and seeds) and count, for every
     clean file version written (day 0 creation and later benign rewrites separately), whether
     the detector flagged it (file p <= 0.01). Report the benign flag rate per arm x file type x
     benign_invalid_rate, the per-machine distribution (median, 90th percentile, share of
     machines with >= 1 flagged day-0 version), and the share of clean snapshots (j < true
     start, j >= 14) holding >= 1 flagged version, which is what verify_snap rejects. This tests
     the JOB 3 explanation (more false flags on real bytes); it is not tuned on.
  Outputs: results/dev_d71_*; tables in results/D71_REPORT.md.

### D71b: zip ground truth check and validator fix (rule fixed by the team 2026-10-23, before code)

Team rule (verbatim intent): test every benign NapierOne zip version the detector flags with
external standard tools (python zipfile.testzip, 7z t). If the tool says valid and our validator
says invalid, it is a validator bug: fix the validator to agree with the tool, add a test, log in
results/CHANGELOG.md, rerun the D67 NapierOne arm and D71 item 3, report old vs new. If the tool
also says invalid, or the flag comes from the learned model, it is a detector property: report,
change nothing. Thresholds are not touched either way.

Check done before this entry (read only, no code in the repo changed):
- Benign zip versions in the D67 NapierOne arm are whole-file rewrites drawn from the DEV pool
  files <= 1 MiB: 5 files (deflate, high compression, bzip2, and 2 PPMd). Both PPMd files
  (0001-zip-ppmd, 0039-zip-ppmd) are the flagged ones; 2 of 5 matches the 0.397 flag rate.
- python zipfile.testzip: NotImplementedError ("compression method is not supported") on both
  PPMd files, which `file_validity` maps to INVALID. 7z t: "Everything is Ok" on all 5.
  Decoding the PPMd members (method 98) with pyppmd 1.3.1 (Ppmd8, variant I, parameters from
  the 2-byte header): all 6 members' CRC-32 match.
- Flag source: the validity bit. Detector file p = 0.006 with validity 0, 0.244 with validity
  forced to 1 (deflate / bzip2 files: 0.23 to 0.32). The learned model alone does not flag them.
- Verdict under the rule: validator bug.

Fix (spec):
- `_zip_ok` / `_docx_ok`: members with compression method 98 (PPMd) are decoded with pyppmd
  (new dependency) and their CRC-32 checked; a decode error or CRC mismatch is INVALID, as for
  other methods. Every other method is unchanged. A test builds a PPMd zip in memory (valid ->
  1.0; one flipped byte in the member data -> 0.0) and, when data/napierone is present, checks
  that both DEV PPMd files are valid.
- The validator is a detector input, so the NapierOne detector is rebuilt with the fixed
  validator from the unchanged config (configs/detector_napierone.yaml, seed 11, same splits,
  same calibration procedure); flag alpha stays 0.01 (frozen). The old detector and outputs are
  kept as results/*_v1. Reported old vs new: detector AUROC (per type and overall), D67
  NapierOne arm (C1, C2, C3' rows of the D67 comparison, count and byte budgets), D71 item 3
  (NapierOne flag rates). The synthetic arm is unaffected (synthetic zips are deflate) and is
  not rerun.
- One job at a time; disk floor rules as before. D72 is not run until this is reported.

### D72: per-file restore under noisy detection (team spec 2026-10-23; registered before code; not run until D71b is reported)

DEV only, no test set, no reselection of w, gate, M, budgets or flag alpha. Retention is
unchanged (no method change to SlowBurn retention).

Restore methods, all on the same retained snapshots and the same write-time detector draws
(D64a: each version is flagged or not once, when written), for every retention policy:
SlowBurn, prior-only, Bar-On recursive, Bar-On round robin, GFS, Tower of Hanoi.
- A. verify_snap snapshot restore (current, D64a).
- B. Independent per-file walk-back (industry baseline, as in Druva US 11755420): each file is
  restored from its newest retained version that is unflagged; a file whose live version is
  unflagged is left as is; if no retained version is unflagged, the oldest retained version.
- C. Monotone per-file restore. Per file, the versions are clean ... clean, damaged ... damaged
  (threat model: a damaged file is never benignly rewritten). Bayesian changepoint over the
  file's versions (retained versions plus the live version, oldest first, v_1 < ... < v_n),
  changepoint tau in {1, ..., n} (first damaged version) or none:
  - P(flag | damaged) = q, q ~ Beta(1, 1), integrated out (Beta-Binomial over the damaged
    segment);
  - P(flag | clean) = b_f, b_f ~ Beta(a_t, b_t) for the file's type t, integrated out over
    the clean segment. (a_t, b_t): the D31 fleet-pooled prior (`fit_pooled_null_prior`, same
    attack-free calibration machines, same method of moments and cap) fitted per type from the
    per-type flagged and changed file counts. Mean = the pooled per-type benign rate, strength
    = the pooled concentration of that fit. No new tuned parameter.
  - onset prior: the existing restore-time attack-start posterior p(S) (the one the gate and
    verify_snap already use; "not started" included). Given S, tau is uniform over the file's
    versions written on or after S plus "none" (onset cannot precede the start); p(tau) is this
    mixed over p(S).
  - P(v_j clean) = P(tau > j | flags). The file is restored from its newest version with
    P(clean) >= 0.95 (alpha 0.05, as in D60); the live version counts, so a file whose live
    version passes is left as is. If none passes, the oldest retained version.
- D. Oracle per file (ceiling, D71 (c)). E. Oracle snapshot (D71 (b)).

Metrics (fixed now): clean recovery (every file clean after the restore); residual damaged
files; per-file work lost in file-hours, headline (benign versions discarded, the
`work_lost_selective_file_hours` accounting: file-days between the restored version and the
newest clean version x 24 h); whole-system work lost, secondary (for A and E as now; for B, C,
D: (discovery day - oldest restored version day) x 24 h over the restored files, 0 if none).

Grids (same machines as before, count budgets): full (dev_d69_full machines), worlds
(dev_d64a_blind_worlds machines), worst case (dev_d69_worst machines); q in {0, 0.2, 0.5, 1}; K in
{4, 6, 8, 12}. Bytes: the D67 synthetic-bytes and NapierOne-bytes arms (trained detectors, after
D71b), every policy above.

Adoption criteria for C. All must hold against A and against B, paired, machine-cluster
bootstrap 95% CIs (world x true start x rep, 2000 resamples, seed 0), in each scored unit:
abstract-detector grids at q in {0.2, 0.5, 1} (each q separately) and the two byte arms (no q;
the trained detector):
  a. recovery not lower by more than 0.01 in any world (lower CI bound >= -0.01);
  b. residual damaged files not higher (upper CI bound of the mean difference <= 0);
  c. per-file work lost lower (point estimate) pooled and in at least 3 of 4 worlds.
q = 0 is reported, not scored. Also reported: the share of the oracle gap (A minus D) closed by
B and by C, for per-file work lost and for recovery, overall and separately for zip and non-zip
files. If C fails, it is reported as failed; no second iteration without a new
pre-registration.

Points Claude Code fixed where the team text left them open (team to confirm before the run):
1. Onset prior: uniform over admissible versions given S, mixed over p(S). The alternative
   (onset at the file's first version after S) would make every post-start version near
   certainly dirty and reduce C to a snapshot restore.
2. Evidence: flags of the retained and live versions only (as written: "all retained versions");
   flags of versions no snapshot kept are not used.
3. Per-type prior: no per-type pooled count exists in the code; the D31 fit is per machine and
   pooled over types. It is refitted per type on the same calibration machines.
4. Scoring units "on synthetic and on NapierOne, q in {0.2, 0.5, 1}": the byte arms have no q, so
   they are scored as one unit each; the abstract grids carry the q split.
5. Whole-system work lost for per-file methods as defined above.

### D71b amendment (team, 2026-10-23)

Accepted as a validator bug (PPMd; the external tool decides). The NapierOne detector rebuild
from the unchanged config and seed (configs/detector_napierone.yaml, seed 11, flag alpha 0.01
unchanged) is part of D71b. Old detector: results/detector_napierone_v1. After the reruns:
old vs new for the D67 NapierOne arm and D71 item 3, then the C2 / C3' NapierOne verdict in
docs/claims.md is updated with the new numbers whichever way they go, and the zip-cause
paragraph is reworded or removed.

Known limitations recorded (no change now): NapierOne DEV content pools are small (files
<= 1 MiB per type: txt 15, csv 15, bin 15, docx 13, zip 5, png 5, jpg 14, mp3 15, zlib 5);
before the fresh test set is generated the pools are enlarged per type under a seeded,
stratified rule written here first. CSV / TXT strict UTF-8 failures (0.158 / 0.042 of benign
detector-data files) are not changed; they produce no benign flags at injected rate 0
(D71 item 3); rechecked after the pools are enlarged.

### D72 amendment (team confirmation 2026-10-23, before any D72 code or run)

The five open points are confirmed, with point 1 stated exactly:
1. Onset prior. For a given attack start S, let n_S be the number of the file's versions
   (retained plus live) written on or after day S. The changepoint has n_S + 1 outcomes: the
   first damaged version is one of those n_S versions, or "no damage"; each outcome has mass
   1 / (n_S + 1). Versions written before S cannot be damaged. The prior is this mixed over the
   restore-time attack-start posterior p(S); "not started" gives "no damage" mass 1.
2. Evidence: flags of the retained versions plus the live version only.
3. Per-type benign prior refit on the attack-free calibration machines. Checked in the code:
   these are RetentionTask family "vault_calib" with attack_start None, and the machine seed key
   (registry.machine_key) includes the family, so they share no random stream with the "eval"
   machines that are scored. They do draw file contents from the same NapierOne DEV content pool
   (byte arms) as the eval machines; the machines are disjoint, the pool is not.
4. Each real-byte arm is scored as one unit (no q).
5. Whole-system work lost for per-file restores = (discovery day - oldest restored version day)
   x 24 h, secondary.
D72 runs after the D71b old vs new report, on the post-fix detector.

### D72 amendment 2 (team decision 2026-10-23, before any D72 run)

1. Scoring scope, option (iii): adoption criteria a, b and c (C vs A and C vs B) must pass on
   BOTH SlowBurn and Bar-On recursive (shamir_recursive) retention. Prior-only, Bar-On round
   robin, GFS and Tower of Hanoi are reported only. The pooled all-policies row is reported only.
   C is adopted only if every criterion passes under both required policies.
2. The two byte-arm configs (dev_d72_bytes_synthetic, dev_d72_bytes_napierone) also run the
   equal-horizon variants gfs_eqh and toh_eqh (D68 definition, horizon >= M = 60). Retention
   only; they are reported, not scored for D72. The full and worst grids are unchanged.

### D72-C2R: C2 restated against stronger baselines (reporting job, registered 2026-10-23, runs right after D72)

Question: does C2 (SlowBurn loses less work than fixed schedules) hold against Bar-On recursive,
Bar-On round robin and the equal-horizon GFS / Tower of Hanoi configurations, not only the
default GFS / Tower of Hanoi?
- Data: the D72 byte-arm outputs (results/dev_d72_bytes_synthetic, results/dev_d72_bytes_napierone),
  post-D71b detector, count budgets K in {4, 6, 8, 12}, w 0.75, verify_snap restore (the adopted
  restore, column clean_recovery / work_lost_whole_system_hours). No new simulation.
- Comparisons: SlowBurn vs each of gfs, tower_of_hanoi, shamir_recursive, shamir_rr, gfs_eqh,
  toh_eqh; paired on the same machine rows (method_v2.policy_vs_policy); recovery difference and
  relative whole-system work lost; 95% machine-cluster bootstrap CIs (2000 resamples, seed 0);
  pooled, by world, by budget; each arm separately.
- Sanity check: the SlowBurn / GFS / ToH rows reproduce the D67 post-fix numbers (same seed and
  machines); any mismatch is reported.
- Reporting rule: C2 is stated per baseline, per arm, with CIs, whichever way it goes. "Holds"
  against a baseline means the pooled work-lost CI is below 0 and recovery is not lower (CI of
  the difference includes or exceeds 0). No reselection of w, gate or thresholds.
- Until this report exists, claims.md states C2 only "vs default GFS / Tower of Hanoi
  configurations".
- Output: results/dev_d72_c2r/, script paper/scripts/d72_c2r_report.py.

## Ambitious scope (team, 2026-10-23): D73 to D77, USENIX Security 2027 cycle 2

Target: register 2027-01-19, submit 2027-01-26. Rules for D73 to D77: each D entry is written
here and committed before its code; DEV only until the single frozen test run (week of
2026-12-15; frozen_v2.yaml covering every adopted method and every baseline goes to the team
before any test run); no tuning on test; every result reported, failures included; defensive
only (the attacker exists only as simulation parameters and public dataset files; no
encryptors, no evasion code, nothing touching systems we do not own); one heavy job at a time,
disk floors as before, failed twice = log and move on; results/STATUS_WEEKLY.md every Sunday.
Order: D72 and D72-C2R first; D73 code may be written while D72 runs; D73 runs after the D72
reports.

### D73: fleet-aware retention (registered 2026-10-23, before any D73 code)

Question: when N machines share one snapshot budget, does reallocating slots across machines by
a fleet-pooled start posterior (FLEET) lose less per-file work than fixed per-machine splits,
without losing recovery?

**Fleet model (simulation parameters only).**
- Fleet of N machines, N in {20, 100}. Shared budget B = N * K_avg snapshots, K_avg in {4, 6, 8}.
- Machines: the D72 scenario (40 files, 9 types, striped 10% damage, same detectors), each with
  its own seeded content and churn. Churn heterogeneity (so that a churn-proportional split
  differs from an equal split): each machine's edits_per_day = 4.0 * exp(0.75 * z), z ~ N(0, 1)
  from child_rng(seed, "fleet_churn", rep, i), fixed now.
- Attack: fleet start S0 drawn from the four D72 worlds (uniform, early, late, bursty; window
  [28, 280]). Infected set: exactly max(1, round(f * N)) machines, f in {0.05, 0.2, 0.5}, chosen
  uniformly (seeded). One infected machine (patient zero) starts at S0; every other infected
  machine starts at S0 + L_i, L_i ~ Geometric on {0, 1, ...} with mean m in {0, 2, 7} days
  (m = 0: all at S0). Per-machine damage and evidence as in D72 from its own start.
- One discovery day for the fleet: td = S0 + d, d in {7, 14, 30, 45, 60}. A machine whose start
  is after td is uninfected at discovery.
- Arms: synthetic bytes with the synthetic detector, and NapierOne bytes with the post-D71b
  NapierOne detector (as D67 / D72); benign_invalid_rate 0.01 (the middle D67 value) only.

**Methods (each machine always holds today's snapshot; budget sum <= B every day).**
- (a) equal split: K_avg slots per machine, Bar-On recursive (shamir_recursive) per machine.
- (b) churn-proportional split: k_i = k_min + extra slots split over machines proportionally to
  machine i's mean daily changed files over warm-up days 0..13 (largest remainder rounding,
  sum = B), fixed for the whole run, Bar-On recursive per machine at k_i. The 14 warm-up days
  are benign by construction (starts >= day 28); using them from day 0 is a 14-day benign
  lookahead, stated as such.
- (c) FLEET: every machine keeps a floor of k_min = max(3, K_avg / 2) slots (3 / 3 / 4; Bar-On
  recursive is undefined at budget 2, measured) under the Bar-On recursive schedule at budget k_min (forced set, never deleted, so the Bar-On guarantee at
  k_min is preserved per machine). The other E = B - N * k_min slots are reallocated daily.
  Each day, each machine's candidates are its held snapshots plus today's. Machine i's value of
  holding k_i slots is V_i(k_i) = -c_i * L_i(k_i), where L_i(k) is the minimum expected loss (in
  days, the SlowBurn DP loss: penalty 90, gate 0.8, the frozen operating point) over subsets of
  size k of its candidates containing its floor set and today's snapshot, under machine i's
  fleet retention posterior pi_i (below), and c_i is machine i's mean daily changed files over
  warm-up (so c_i * days approximates per-file work lost). pi_i carries the not-started /
  not-infected mass, so L_i already equals P(machine i infected and started) times the expected
  loss given infection: the spec's "expected per-file work lost saved times P(machine
  infected)". Allocation: start from keep-all (k_i = number of candidates); while the total
  exceeds B, remove one slot from the machine whose next removal increases c_i * L_i least
  (ties: larger k_i, then lower machine index); never below the floor. This is greedy marginal
  gain run from the top: snapshots are deleted only when the budget forces it (D37), and only
  losses at the next one or two removals are ever needed. Machine i then keeps the D37 DP
  selection (dp_select) of size k_i with the floor forced.
  - Fleet posterior (hierarchical, fixed now): fleet start a has the frozen geometric timing
    prior (p_attack_within_window 0.05 per 60 days, warm-up 14); each machine is infected
    independently with probability rho and starts at a + L, L ~ Geometric with mean mu,
    truncated at 45 days; rho and mu are integrated over fixed grids, rho in {0.02, 0.05, 0.1,
    0.2, 0.35, 0.5} (weights proportional to Beta(1, 3) density) and mu in {0.5, 2, 5, 10}
    (equal weights). Machine likelihoods L_i(s) are each machine's single-changepoint
    likelihoods from its own daily statistic (the D72 evidence model, method v2 w 0.75, the
    fleet-pooled benign null prior from attack-free calibration machines), so the per-machine
    model is unchanged; only the prior over starts is coupled. pi_i(s) is the exact marginal of
    s_i (leave-one-out product over the other machines), conditioned on "fleet not discovered by
    day t" under the frozen assumed discovery distribution (uniform, max 60) applied to the
    fleet start a. Patient zero (L = 0 for one machine) is not modelled: a stated mismatch.
  - Correctness check (fixed now): on small cases (N in {2, 3, 4}, E <= 6, random posteriors and
    candidate sets, 500 cases) compare the greedy allocation's total c_i * L_i with the exact
    optimum by brute force over all allocations; report the share of cases where greedy is
    optimal and the largest relative excess. A unit test asserts greedy equals brute force on
    concave cases. The check is reported; greedy is not replaced if it is suboptimal.
- Reported-only references (not adoption criteria): (d) SlowBurn per machine at K_avg each
  (no sharing; separates the fleet effect from the SlowBurn DP); (e) FLEET-indep: the same
  reallocation with each machine's own SlowBurn posterior (no hierarchical pooling).

**Restore at discovery, per infected machine** (rows for every method): verify_snap (D64a)
with the machine's fleet posterior at discovery (conditioned on discovery at td through a)
for (c) and (e), its own posterior for (a), (b), (d); D72 method C if D72 adopts it, otherwise
D72 method B is reported; oracle snapshot and oracle per file.

**Metrics.** Primary: fleet clean recovery (1 iff every machine infected by td recovers clean);
per-file work lost summed over infected machines (hours, file level); residual damaged files
summed. Secondary: per-machine clean recovery share, whole-system work lost, slots used by
infected machines at td, and, if every machine in the fleet were restored with the same method,
the work lost on uninfected machines (false restores).

**Grid.** N {20, 100} x K_avg {4, 6, 8} x f {0.05, 0.2, 0.5} x m {0, 2, 7} x 4 worlds x
d {7, 14, 30, 45, 60} x 2 arms. Delays and K_avg share a fleet (one simulation, every K and d
read from it). 8 fleets (reps) per (N, world, arm); within a rep every (f, m) cell uses the same machines
(the same benign traces, the same fleet start S0), so cells are paired. The N = 20 fleet is the
first 20 machines of the N = 100 fleet; its infected set is drawn separately. Seed 202, DEV.
Timing basis (2026-10-23, measured with D72 running): a byte-mode machine costs about 0.13 s per
simulated day, dominated by content generation (not scoring); full DP re-selection 8 to 70 ms,
single deletion 0.3 ms.
Implementation (exactness, not method): the scenario and trace builder become a forkable
stepper; a benign trace is forked at day S0 + L_i to produce the infected trace, which is exact
because benign and attack draws share one stream that is identical before the start. A test
asserts the stepper reproduces simulate() exactly (every day's files, flags and daily
statistic) on abstract, synthetic-byte and NapierOne-byte machines, and that a fork equals a
fresh simulation with that start. Retention state before S0 is shared across the (f, m) cells
of a rep (identical evidence), then branched.

Reps chosen for compute, not power; no rep is added or removed after results are seen.

**Adoption criteria (fixed now), FLEET (c) vs (a) and vs (b), each arm separately:**
1. Recovery: fleet clean recovery not lower by more than 0.01 in ANY (N, K_avg, f, m) cell
   (point estimate; the CI is reported).
2. Per-file work lost lower pooled (95% fleet-cluster bootstrap CI of the relative difference
   below 0).
3. Per-file work lost lower (point estimate) in at least 2/3 of the 9 (f, m) cells, pooled over
   N, K_avg, worlds and delays.
FLEET is adopted only if 1 to 3 pass vs both (a) and (b) on both synthetic and NapierOne bytes.
Everything reported either way. No reselection of k_min, grids, priors or penalty.

### D74: adaptive attacker, best response per defence (registered 2026-10-23, before any D74 code)

Security evaluation only: no defence parameter, threshold, prior or grid changes in response to
anything D74 finds. The attacker exists only as simulation parameters (rate, damage fraction,
target types, delay) applied to public dataset bytes and synthetic bytes in the simulator.

**Attacker strategy** = (daily damage rate, damage fraction, target types, discovery delay d).
Discovery = ransom note, so the attacker chooses d. Grid (fixed now):
- rate (files damaged per day, Poisson mean): {0.25, 0.5, 1, 2, 4}
- damage fraction (striped damage, the D67 model): {0.01, 0.05, 0.1, 0.5, 1.0}
- targets: all types; weak4 = {csv, bin, txt, jpg} (the four lowest NapierOne post-D71b damage
  detection rates, D71 item 3: 0.83, 0.88, 0.94, 0.94); csv only (the lowest). Same sets on
  both arms (the synthetic detector detects every type at 1.000, so targeting is a NapierOne
  question; reported for both).
- d (days from start to discovery): {7, 14, 30, 45, 60, 90, 120}; 90 and 120 lie beyond the
  retention's assumed bound M = 60, on purpose.
75 damage strategies x 7 delays = 525 strategies. One simulation per (machine, damage
strategy) covers every d (forked at the start, run to start + 120; D73 stepper).

**Stealth constraint.** The existing daily evidence alarm is the threshold vault's line: the
95% quantile of the largest daily flagged-file fraction after warm-up on attack-free DEV
calibration machines (per-machine false alarm rate 5% over a run; D31 calibration, unchanged).
Primary analysis: a strategy is feasible at delay d if the alarm fires on some day in
[start, start + d - 1] on at most 5% of the selection machines (below); infeasible strategies
are excluded. Secondary: every strategy, with discovery at min(start + d, first alarm day + 1)
(the alarm caught it), reported.

**Defences** (each with the frozen operating point; count budgets K in {4, 8}): Bar-On
recursive, GFS, Tower of Hanoi, prior-only, SlowBurn; each restored with verify_snap (A) and with
the per-file restore (D72 method C if D72 adopts it, else method B). FLEET (D73): fleet of
N = 20, K_avg = 6, f = 0.2, m = 2, the strategy applied to every infected machine, on a reduced
grid (rate {0.5, 2} x fraction {0.01, 0.1, 1.0} x targets {all, weak4} x the 7 delays = 84
strategies) because a fleet costs ~20 machines per strategy; stated as a limitation.

**Machines.** Both byte arms (synthetic bytes + synthetic detector; NapierOne bytes + post-D71b
NapierOne detector), benign_invalid_rate 0.01, the D72 scenario otherwise; 4 worlds x 10 reps
per arm; seed 202, family "d74_attack" (disjoint from eval, calibration and fleet machines).
Reps 0-4 are the selection half, reps 5-9 the evaluation half.

**Best response.** For each defence, restore and arm, two attacker objectives: (i) minimise
clean recovery, (ii) maximise per-file work lost (ties: lower clean recovery). The best
strategy is chosen on the selection half and its value reported on the evaluation half (no
winner's curse); the selection-half value is reported alongside. Also reported: the full
strategy surface, the worst case per d, and results under the realistic delay distribution
(uniform over the D72 delays {7, 14, 30, 45, 60}, rate 0.5, fraction 0.1, all types: the D72
attacker). Brackets: machine-cluster bootstrap CIs on the evaluation half.

**No adoption criteria** (evaluation only). Every defence's worst case is reported, including
SlowBurn's and FLEET's, whichever way it goes.

### D73 amendment (team decision 2026-10-23, before any D73 run)

K_avg = 4 cells are reported as "no reallocation room (floor 3 of 4)", not as a result for or
against FLEET. (Measured fact for the record: at K_avg = 4 the floor is 3, leaving N extra slots
in the whole fleet, one per machine on average.) The pre-registered adoption criteria apply to
the K_avg in {6, 8} cells only: criterion 1 in every (N, K_avg in {6, 8}, f, m) cell; criterion 2
pooled over K_avg in {6, 8}; criterion 3 over the 9 (f, m) cells pooled over N and K_avg in
{6, 8}. Primary restore: A (verify_snap), unless the D72 report adopts method C, in which case C.

### D75 pool enlargement rule (team decision 2026-10-23, before any download)

Purpose: enlarge the NapierOne simulation content pools (DEV and the fresh TEST pool) before the
fresh test set. The detector stays exactly as it is.
- Types short of unused files: txt, csv, bin, docx, mp3, zlib (NapierOne-tiny has exactly 100
  files each, all already in the detector train / calibration / held-out sets). Source: the next
  larger official NapierOne release, the per-subset "small" archives (1,000 files per subset) on
  the NapierOne S3 bucket (s3://napierone.com, https://s3.eu-north-1.amazonaws.com/napierone.com,
  registry.opendata.aws/napierone), keys NapierOne/Data/<T>/<T>-small.zip with the published
  NapierOne/Data/<T>/<T>-small_zip_hashes.txt, for T in TXT, CSV, BIN, DOCX, MP3, ZLIB (the same
  subsets the simulator maps today, D67 TYPE_SUBSETS). Listed sizes on 2026-10-23: TXT 1.018 GB,
  CSV 0.046, BIN 0.200, DOCX 0.343, MP3 0.879, ZLIB 4.074 GB. The combined NapierOne-small.zip
  (152.5 GB) is not used. The exact key, byte count, published SHA-256 and our SHA-256 of every
  archive are recorded in data/manifest and the data card.
- zip, png, jpg: no download; their existing unused NapierOne-tiny files (not in any detector
  split) are the source.
- Per type: from the candidate files of size <= 1 MiB (the simulator's limit), drop every file
  whose content SHA-256 equals that of any file already in the detector training, calibration or
  held-out sets (all 100 per type of the tiny set, all subsets of the type), and drop exact
  duplicates within the candidates (keep the lexicographically first member name); then draw a
  seeded random sample of up to 200 files (permutation from child_rng(202, "d75_pool", type),
  first 200 in that order). The sample is split in half by that order: first half added to the
  simulation DEV pool, second half to the simulation TEST pool (rounded so DEV gets the extra
  file). Files per type, before and after, are reported.
- New files go only to the simulation evaluation pools, never to detector training or
  calibration. The old pools stay reproducible: configs name the pool version (v1 = the D67
  pools, v2 = enlarged).
- Disk: one archive at a time: check free space and the data cap first, download, verify bytes
  and the published SHA-256, extract only the sampled members (untrusted-archive rules of the
  data card), delete the archive before the next one. 45 GB floor and 100 GB data cap at all
  times. If a single archive cannot fit within floor and cap, stop and report sizes; the rule is
  not changed.
- Afterwards: rerun the NapierOne arms of D67 and D72 on the v2 pools (same seeds, configs
  otherwise unchanged) and report v1 pools vs v2 pools side by side.
- Order: after the D72 report, D72-C2R and D73; the download may overlap D73 only if disk and the
  one-heavy-job rule allow (a download is not a heavy compute job; the extraction and hashing are
  short).

### D74 amendment (team decision 2026-10-25, before any D74 run)

1. Pools: the NapierOne arm uses the D75 v2 pools (napierone_pool: v2).
2. Alarm, replacing the degenerate threshold-vault line (it is 1.0 at benign rate 0.01): a
   daily flagged-file COUNT alarm. On day t the alarm fires iff k_t >= c, where k_t is the
   number of changed files flagged that day (file p <= 0.01, the D72 evidence). c is the
   smallest integer such that at most 5% of calibration runs have max k_t >= c, a run being the
   120 days after warm-up (days 14 to 133; 120 = the largest attacker delay).
   Calibration set (never used in the attack evaluation): 100 attack-free machines per arm,
   family "d74_alarm_calib" (seed key disjoint from "d74_attack", "vault_calib", "eval" and
   "fleet"), the D74 scenario (benign_invalid_rate 0.01; v2 pools on NapierOne), seed 202.
   Per arm: c, the achieved per-run false-alarm rate, the per-machine-day rate p_day, and the
   expected fleet false alarms per week 7 * N * p_day for N in {20, 100} are reported. The
   value of c is written here and committed before D74 runs.
3. Threshold-aware attacker (worst-case bound): in addition to the grid, strategies that damage
   exactly c - 1 files on every day from the start (deterministic, not Poisson), the most the
   attacker can do while staying under the alarm if every damaged file were flagged, crossed
   with the 5 damage fractions, 3 target sets and 7 delays (105 strategies). Benign flags can
   still push a day over c; the achieved alarm rate is reported. These are reported as the
   worst-case bound per defence, separately from the stealth-filtered grid best response. If
   c = 1 the bound is "no damage possible without risking an alarm" and is reported as such.
4. Everything else in D74 unchanged (grid, split halves, defences, no defence tuning).

### D78 (DRAFT, sent to the team 2026-10-25; nothing runs until approved): one fix attempt for the NapierOne detector weaknesses

**Step a, done before any criterion (2026-10-25), bug or real data:**
- csv, 55 of 100 new DEV files fail strict UTF-8: all 55 decode as Windows-1252 (en dash 0x96,
  pound 0xA3): real non-UTF-8 text, not a validator bug. Benign csv is never flagged anyway
  (0.000), so csv needs no fix.
- txt, 33 of 100: 27 are Windows-1252 text; 6 are gzip streams (magic 1F 8B) named .txt inside
  NapierOne: real data (mislabelled in the dataset), not a validator bug.
- png, 9 of 54: all are PNG-FROM-WEB files of exactly 1,048,576 bytes; PIL also fails them
  ("Truncated File Read"). 13 of the 100 PNG-FROM-WEB tiny files are exactly 1 MiB and none is
  larger: NapierOne truncated web downloads at 1 MiB. Real (defective) data, not a validator bug.
- bin has no format check; its damage detection drop (0.88 -> 0.66) and txt's (0.94 -> 0.59)
  come from the content features on more varied files.

**Split (seeded, before any tuning):** the v2 DEV additions per type (benign_v2/<type>/dev) are
permuted with child_rng(202, "d78_split", type) over sorted names; the first half is the FIX
half, the second the CHECK half. Pool versions "v2fix" / "v2check" = the v1 DEV pool plus that
half. The TEST pool (v1 sim_test and benign_v2/<type>/test) is never opened.

**Allowed changes (calibration or feature only; the validator is not loosened; detector
training data, model hyperparameters and the file p <= 0.01 flag rule unchanged):**
- F1 calibration: refit the type-conditional conformal calibration on the detector calib split
  plus the FIX-half benign files (benign rows only).
- F2 feature: replace the absolute validity bit by a validity-transition bit (previous version
  valid and this version invalid); a file already invalid before (Windows-1252 text, truncated
  png, gzip-as-txt) no longer looks damaged by validity alone. Model retrained on the same train
  split with the same hyperparameters.
- F3: F1 and F2 together.
No other candidate. Accepting Windows-1252 as valid text is excluded: striped random damage
decodes as Windows-1252 almost everywhere, so it would stop catching real damage (rule f).

**Selection on the FIX half only:** each of F1 to F3 and the unchanged detector are scored by a
D71-style recount on the D67 NapierOne grid with pool "v2fix" (same seeds); the candidate that
meets the criteria with the lowest benign flag rate is selected (none meeting them: the closest
is still scored once on CHECK and reported, but cannot be adopted).

**Acceptance criteria, scored once on the CHECK half (pool "v2check"), paired with the unchanged
detector on the same machines:**
1. benign false-flag rate of rewrite versions at injected rate 0: <= 0.005 overall (point), with
   the upper 95% machine-cluster CI <= 0.008;
2. damage detection on every type not lower than the unchanged detector by more than 0.02
   (lower 95% CI of the paired difference >= -0.02); ~500 damaged versions per type give a
   standard error near 0.015, so "no worse at all" would fail on noise;
3. detector file-level AUROC (striped 10%, uniform type mean) on the CHECK files not lower than
   the unchanged detector's by more than 0.01.
Pass: lock as detector v2 (results/detector_napierone_v2/) for the frozen run, and rerun the
NapierOne arms that use it. Fail: the unchanged detector ships and png / txt / bin are listed as
limitations. Either way the unchanged and the candidate detectors are reported side by side.

### D74 alarm threshold (calibrated 2026-10-25 16:19-16:32, before any D74 run)

results/dev_d74_alarm_calib/threshold.json, 100 disjoint benign runs of 120 days per arm:

| arm | c | per-run false alarm at c | at c - 1 | p_day at c | fleet false alarms / week, N = 20 / 100 |
|---|---|---|---|---|---|
| synthetic bytes | 3 | 0.00 (0 of 100) | 0.08 | 0 of 12,000 machine-days (95% upper bound 2.5e-4) | 0 / 0 (upper bounds 0.035 / 0.17) |
| NapierOne bytes, v2 pools | 3 | 0.01 | 0.31 | 8.3e-5 | 0.012 / 0.058 |

The count is discrete: c = 2 would exceed 5% per run, so c = 3 and the achieved rate is below
the 5% target. The threshold-aware attacker therefore damages exactly 2 files per day.

### D74 held-out alarm check (team decision 2026-10-25; registered before it runs)

The false-alarm rates reported with c = 3 (synthetic 0 / 100 runs, NapierOne 1 / 100) are IN
SAMPLE: they come from the same 100 runs per arm that chose c (family "d74_alarm_calib", seed
202, reps 0-99, setting {data_source}). A held-out set scores c = 3 once:
- 100 new attack-free runs per arm, family "d74_alarm_holdout" (seed key disjoint from
  "d74_alarm_calib", "d74_attack", "vault_calib", "eval", "fleet"), reps 0-99, the same D74
  scenario (benign_invalid_rate 0.01; NapierOne on the v2 DEV pools), same 120-day window.
- Reported per arm: per-run false-alarm rate at c = 3 with an exact (Clopper-Pearson) 95% CI,
  p_day with its exact 95% upper bound, fleet false alarms per week for N = 20 / 100 (point and
  upper bound). c stays 3 whatever the result.
- Runs after D73 NapierOne v2 (queue), not before.

### D74 boundary-straddling attacker (registered 2026-10-25, before the D74 report)

The alarm counter is per calendar day (one simulated day = one daily snapshot; k_t counts the
files flagged among that day's changes). A boundary-straddling attacker (c - 1 files just before
midnight, c - 1 just after) is, in this daily model, c - 1 files on day t and c - 1 on day t + 1,
which the threshold-aware attacker (c - 1 = 2 files on every day) already does. The straddling
variant is therefore reported as identical to the threshold-aware rows; no new simulation. A
sub-day (rolling 24 h) counter would need an hourly model, which the simulator does not have;
stated as a limitation.
Correction (2026-10-25): the synthetic p_day upper bound above (2.5e-4) was a rule-of-three
approximation; the exact Clopper-Pearson 95% bound for 0 of 12,000 is 3.1e-4 (fleet false
alarms per week upper bounds 0.043 / 0.22 for N = 20 / 100). The D74 report uses exact bounds.

### Truncated-png sensitivity row (team decision 2026-10-25)

The 9 truncated NapierOne pngs (exactly 1 MiB, fail PNG check and PIL) stay in every scored pool.
One unscored sensitivity row: the D67 NapierOne arm on pool v2_notrunc (v2 minus those 9),
same seeds, run after the primary arms (queue: after D73 NapierOne v2 and the held-out alarm
check), reported next to v2 and labelled unscored. It changes no claim by itself.

### D78 amendment 1 (power check, 2026-10-26, before any D78 fix code; team approves or rejects)

**Scope.** D78 targets benign false flags (png validity failures, txt). It is not expected to
raise txt (0.59) or bin (0.66) damage detection; if those stay unchanged they stay as
limitations.

**Power check** (paper/scripts/d78_power.py, results/dev_d78_power/). Source: the D71 v2-pool
recount at injected rate 0, the same D67 NapierOne grid and seeds as the D78 recount, so the
CHECK version counts are these (the pool changes content, not the number of versions). No
detector was changed and nothing was simulated.
- Sizes per type, benign rewrite versions / damaged versions: bin 13,316 / 626, csv 13,418 /
  603, docx 13,456 / 610, jpg 10,941 / 501, mp3 11,010 / 471, png 10,808 / 501, txt 13,681 /
  599, zip 10,686 / 485, zlib 10,614 / 503; overall 107,930 benign rewrite versions on 160
  machines.
- Criterion 1 is passable: exact 95% upper bounds for 0 / 1 / 2 flags out of 107,930 are
  2.8e-5 / 5.2e-5 / 6.7e-5 (per type, n ~ 10,600: 2.8e-4 / 5.3e-4 / 6.8e-4). The point limit
  0.005 allows up to 539 flags. The unchanged detector has 1,804 (0.0167; png 1,625).
  Criterion 1 is unchanged.
- Criterion 2 as written (per type) is not reliably passable. The unchanged detector against
  itself passes trivially (difference exactly 0). A candidate with the same true detection that
  changes a fraction d of damaged-version decisions fails it by noise alone (200 simulations):
  at d = 0.10 per-type fail rate txt 0.39, bin 0.34, csv 0.25, others 0; expected failing types
  0.24 / 0.97 / 1.86 at d = 0.05 / 0.10 / 0.20. F2 changes decisions on exactly the weak types.

**Amended criterion 2 (replaces criterion 2):**
- (a) primary: the uniform type mean of the paired detection difference (candidate minus
  unchanged, same damaged versions), with one machine-cluster bootstrap shared across types
  (2000 resamples), has a lower 95% CI >= -0.02;
- (b) guard: no type's point difference is below -0.05;
- (c) per-type paired CIs are reported as secondary and are not scored.
Null false-fail rate of (a) and of (b) at d up to 0.20: 0 of 200 simulations each
(results/dev_d78_power/criterion2_pooled_null.csv). Criteria 1 and 3, the split, the candidates
and the selection rule are unchanged. D78 still does not run until the team approves.

**False-pass check (team rule 2026-10-26, conditional approval; run before any fix code).**
Rule fixed by the team before the run: tighten 2(a) from -0.02 to -0.01 if candidates with a
true uniform detection drop of 0.03 on every type pass 2(a) more than 20% of the time; tighten
2(b) from -0.05 to -0.03 if candidates with a true drop of 0.08 on one type only (txt, bin, csv
separately) pass 2(b) more than 20% of the time for any of them. 200 simulations each, same
shared machine-cluster bootstrap; drops applied on top of discordance d = 0 and d = 0.10 (the
larger rate decides). paper/scripts/d78_power.py false_pass(),
results/dev_d78_power/criterion2_false_pass.csv.

| case | d = 0 | d = 0.10 |
|---|---|---|
| uniform drop 0.03, pass rate of 2(a) | 0.000 | 0.000 |
| drop 0.08 on txt only, pass rate of 2(b) | 0.000 | 0.005 |
| drop 0.08 on bin only, pass rate of 2(b) | 0.005 | 0.010 |
| drop 0.08 on csv only, pass rate of 2(b) | 0.000 | 0.015 |

No rate exceeds 0.20, so neither threshold is tightened. **Final thresholds: 2(a) lower 95% CI
>= -0.02; 2(b) every type's point difference >= -0.05.** The null false-fail check above stands
at these values (0 of 200 for each). With this commit D78 is approved to run, after the held-out
alarm check and the png row finish, one heavy job at a time. TEST stays closed.

### D79: SlowBurn at equal horizon (team spec 2026-10-26; registered before any D79 code)

Question: is SlowBurn's loss to the equal-horizon schedules (C2) a horizon effect or a placement
effect? Give SlowBurn the same reach as the matching eqh baseline and compare again.

**Variant (exactly one configuration per run, no tuning).** SlowBurn DP (the frozen operating
point: penalty 90, gate 0.8, backbone 0.25, w 0.75, same DP objective, same posterior, same
R-media Tower of Hanoi backbone rule, same budget K) with one added constraint: a maximum
retention age A(K). Each day, before the DP chooses, held snapshots older than A(K) days are
deleted (never the backbone's own set; with R = round(0.25 K) <= 3 media the backbone never
holds a snapshot older than 8 days, so this exception never applies at these K). Nothing else
changes.
- Run 1 (`slowburn_age_gfs`): A(K) = the maximum age held by gfs_eqh at K in a steady-state
  replay (days 200 to 399 of a 400-day replay, retention.horizon, D68 configuration). gfs_eqh
  exists only at K = 12 (tiers 7 daily / 2 weekly / 3 monthly / 0 quarterly): A(12) = 104.
- Run 2 (`slowburn_age_toh`): A(K) = the same quantity for toh_eqh, which exists at K = 8
  (base 2) and K = 12 (base 2): A(8) = 127, A(12) = 255.
- Why the held age, not the guaranteed horizon H: H(toh_eqh, 12) reaches the computation cap
  (400 days), so a cap at H would not constrain anything; the held age is the reach the baseline
  actually uses. H is reported next to A: H(gfs_eqh, 12) = 76, H(toh_eqh, 8) = 63,
  H(toh_eqh, 12) >= 400. Computed before this entry with the existing D68 code; recomputed by
  the D79 code and any mismatch reported.

**Data.** NapierOne v2 DEV pools primary, synthetic bytes as the sanity arm. Same seed (202),
worlds, reps (40), benign rates, discovery delays, detector, restore (verify_snap) and metrics
as dev_d72_bytes_*; count budgets K = 8 and 12 only (where an eqh baseline exists). Each run
config also re-runs slowburn, gfs_eqh and toh_eqh on the same machines; the slowburn / eqh rows
must reproduce the D72 rows exactly (sanity check, reported). TEST stays closed.

**Statistics.** Paired on the same machine rows, machine-cluster bootstrap 95% CIs (2000
resamples, seed 0), as in the C2 restatement (method_v2.policy_vs_policy, d72_c2r_holm). Holm
across the two primary comparisons (run 1 vs gfs_eqh at K 12, run 2 vs toh_eqh at K 8 and 12
pooled), per arm.

**Success (per comparison, NapierOne arm decides; synthetic reported):** work lost (variant
relative to baseline, sum variant / sum baseline - 1) has an upper 95% CI < 0, the comparison
is Holm significant at 0.05, and recovery (variant minus baseline) has a lower 95% CI >= -0.02.
Recovery and work lost are reported both ways (variant vs baseline and baseline vs variant)
and for the unconstrained SlowBurn, whatever happens. Per-world and per-K rows are secondary and
unadjusted.

**Failure is a finding:** "placement does not help at equal horizon", reported in claims.md and
the paper. A success replaces the equal-horizon caveat sentence in the abstract.

**Order.** Implement, smoke test on 2 machines, then run after the held-out alarm check and the
png row, before D78; one heavy job at a time; memory gate: measured peak + 4 GB (13 GB default).

### D78 implementation notes (2026-10-26, before any D78 code runs; no criterion changes)

- Pools: "v2fix" / "v2check" = the v1 DEV pool plus the FIX / CHECK half of the v2 DEV additions
  (benign_v2/<type>/dev, sorted names permuted with child_rng(202, "d78_split", type); FIX = the
  first floor(n / 2), CHECK = the rest). The 9 truncated pngs stay wherever the split puts them.
- Recount: the D71 recount on the D67 NapierOne grid (configs/dev_d67_full_napierone_v2pool.yaml
  with the pool and detector swapped), injected benign rate 0 only (all three criteria are at
  rate 0; amendment 1's power check used the same rows), 160 machines per pool and detector.
  Each version row carries (world, rep, true start, file id, day) so candidate and unchanged
  detector are paired on identical versions (detection does not change file histories).
- Unchanged detector: results/detector_napierone/detector.pkl (post-D71b), not retrained.
- F1: the unchanged classifier, calibration refit on the detector calib split plus every
  FIX-half benign file (benign rows only; same chunking and file-level calibration as the
  detector build). F2: the same LightGBM, hyperparameters, seed and train split, with the file
  validity column replaced by a validity-transition column (0 = previous version valid and this
  version invalid; -1 = no check for the type; 1 otherwise; training: benign rows compare a file
  with itself, damaged rows with their original); calibrated on the calib split. At simulation
  time the previous version's validity is kept per file and machine (first version: no
  transition). Injected benign invalid versions count as invalid. F3: F2's classifier with F1's
  calibration.
- Criterion 3 on FIX uses the FIX files (selection), on CHECK the CHECK files (scoring): file
  level, striped 10%, uniform type mean (WAVG_ALL), the D75 AUROC code.
- Selection on FIX: candidates meeting criteria 1, 2 (amended) and 3 on FIX; among them the
  lowest benign flag rate. If none meets them, the "closest" is the candidate with the lowest
  benign flag rate among those meeting criteria 2 and 3, else the lowest benign flag rate
  overall; it is scored once on CHECK and reported but cannot be adopted.

### D80: C2 with the D78 detector (team decision 2026-10-26; registered before D78 runs)

Runs only if D78 accepts a candidate on CHECK.
- Rerun the C2 comparisons (SlowBurn vs all six baselines: GFS, Tower of Hanoi, Bar-On recursive
  and round robin, GFS-eqh, ToH-eqh) on NapierOne v2 pools with the 9 truncated pngs kept,
  the D72 byte-arm configuration with only the detector swapped; same seeds, machines, paired
  machine-cluster bootstrap (2000 resamples, seed 0) and Holm across the six per arm
  (d72_c2r_holm). Reported alongside the scored v2 rows; no change to pools.
- Alarm: c stays 3; held-out false alarms at c = 3 with the new detector on the D74 held-out
  machines (family d74_alarm_holdout, NapierOne arm) as a secondary row; no recalibration.
- If D78 rejects every candidate, D80 does not run; the png effect is reported as a limitation
  with the mechanism table (results/dev_png_mechanism.md).

### D74 eqh arm (team decision 2026-10-26; registered before any code; last experiment before TEST)

Descriptive, no success criterion; goes in the paper either way.
- Rerun the D74 best-response and realistic-attacker evaluations on NapierOne v2 with the
  equal-horizon schedules added (D68 rule, M = 60, `EqualHorizon`), restore A, K 4 and 8, same
  seed (202), machines (family d74_attack, 4 worlds x 10 reps), attacker grid, alarm c = 3,
  selection / evaluation halves and calibration (results/dev_d74_attack_napierone/calibration.pkl
  is copied, not recomputed; it is deterministic).
- Coverage, stated before the run: under the D68 rule GFS-eqh exists only at K = 12 and ToH-eqh
  at K = 8 and 12, so at K 4 / 8 the arm adds ToH-eqh at K = 8 only; GFS-eqh and ToH-eqh at K = 4
  are reported as "no configuration reaches M" (the policies are skipped by the existing
  infeasible-K rule, not changed).
- Only the eqh policies are simulated (config dev_d74_attack_napierone_eqh.yaml); the other
  policies' rows come from the existing D74 NapierOne run on the same machines and seeds.
  Report: recovery vs delay (best response, recovery-minimising and work-lost-maximising
  attacker, evaluation half) and the realistic attacker, all policies side by side.
- Synthetic arm only if time remains, same rule. Memory gate 13 GB.

### TEST content path (team request 2026-10-27; registered before any code; nothing on TEST runs)

Code only. No TEST file is opened, counted or simulated until configs/frozen_v2.yaml has
`approved: true` (team and Aarnav, in writing).
- Gate: the TEST content pool (`ContentPool(pool="sim_test", version="v2test")`) and the TEST
  damage families load only when configs/frozen.yaml has `frozen: true` AND
  configs/frozen_v2.yaml has `approved: true`; otherwise a ValueError naming TEST. Pool
  version `v2test` = the v1 `sim_test` files plus `benign_v2/<type>/test`; damage =
  NapierOne `sim_test` families. `v2test` is refused on the DEV pool and the DEV versions are
  refused on the TEST pool.
- Split comes from the machine key: test-keyed machines read TEST content. Calibration
  machines (dev keys: vault / null-prior calibration, amoeba, the D74 count alarm c = 3 from
  results/dev_d74_alarm_calib/threshold.json) keep DEV content (`v2`) in a TEST config, so no
  defender quantity is fitted on TEST files. Detector unchanged (results/detector_napierone).
- Random streams that do not carry the split today (D74 starts "d74_start"; D73 "d73_fleet_start",
  "d73_infect", "d73_lag", "d73_fleet_churn") get the split appended for test only, so TEST
  starts and infections differ from DEV and every DEV stream is unchanged byte for byte.
- D74 and D73 entrypoints accept split test through the existing registry gate
  (check_split_allowed) and the TEST content gate; the alarm hold-out script uses family
  "d74_alarm_test" on test configs. D74 best-response selection on reps 0 to 4 is the
  attacker's selection step, identical to DEV, not tuning of any defender parameter.
- test_*.yaml are generated mechanically from the DEV configs listed in frozen_v2.yaml; only
  `split` (dev -> test), `napierone_pool` (v2 -> v2test), `experiment` and `output_dir`
  (dev_ -> test_) may differ; a script checks this by parsing both and reruns the registry
  gate on each (reads configs only).
- Inventory (before any TEST experiment, after approval): counts only (files per type,
  validity failures per type, truncated png count), committed before any experiment. Inventory
  changes nothing; no file is removed or added; it is used only to interpret results. No
  detector or experiment runs during inventory.
- Dry run (after inventory): each test_*.yaml for 1 machine and 1 simulated day into a scratch
  dir that no analysis script reads; checked: exit code, files load from TEST paths, config
  diff output. Scratch output deleted unread and the deletion logged.

### TEST gate by grid hash, failure rule, queue order (team decisions 2026-10-27; registered before code)

- Registry gate (not loosened): configs/frozen_v2.yaml gets `scenario_grids`, one entry per test
  experiment whose run has a scenario grid (C2/D72 x2, D79 x2, D71): the canonical serialization
  of the grid computed from the DEV config (`scenario_grid_of`, JSON with sorted keys, no
  whitespace, `scenario.napierone_pool` left out because it is the one registered DEV -> TEST
  change, checked by test_configs.py) and its SHA-256. On test, check_split_allowed passes a run
  with a scenario grid only if its hash equals the entry of its experiment exactly (missing
  entry = refuse); frozen.yaml's v1 scenario_grid is no longer compared on test. Every other
  hyperparameter stays an exact match against configs/frozen.yaml. Tests: a modified grid fails.
- Calibration content stays DEV (a63fc54); stated in the paper's limitations.
- Failure rule: a crashed TEST job's partial output is not read; only the crash cause is fixed,
  committed with the traceback in the message, and the item rerun from scratch with identical
  seeds; both attempts logged in results/test_queue.log. A fix may not change any config, grid,
  hyperparameter, metric or analysis script; if it would, stop and report. No rerun for any
  other reason.
- Queue after approval: inventory, dry run, ALARM, C2/D72 NapierOne, D79 NapierOne, D71, D74
  NapierOne, C2/D72 synthetic, D79 synthetic, D74 synthetic, D73 NapierOne, D73 synthetic; one
  heavy job at a time, memory gate as before; analysis scripts only after all items finish.
- Approval: approved stays false until Aarnav writes in the chat "APPROVED frozen_v2.yaml at
  commit <hash>"; then code_commit is re-pinned, approved: true committed, and the queue starts.

### TEST sweep entrypoint fix, output handling, prediction (team decisions 2026-10-28; registered before code)

- Gap found after approval (77b3253): run_dev_sweep (the DEV entrypoint of C2/D72, D79, D71)
  refused split test and built DEV tasks only. Fix: on test it passes the same gates as the other
  entrypoints (check_split_allowed with the run's scenario grid hash and experiment name; the TEST
  content gate in the pool) and builds tasks with build_tasks(cfg, split) (calibration stays on
  DEV machines, as registered in a63fc54). No config, grid, hyperparameter, metric or analysis
  script changes. Test: the sweep entrypoint on a tiny token-mode test-split config with
  temporary frozen / frozen_v2 files (no real TEST file opened); a missing grid entry is refused.
  The dry run additionally calls each entrypoint's gate check for all 9 test configs.
- Output handling: each runner writes stdout to results/test_<item>_run.log and stderr to
  results/test_<item>_err.log; nothing in either is read until every item has finished, except
  the stderr traceback of a crash, as the failure rule needs. No counts-only mode for ALARM.
- results/test_prediction.md (the team's text, verbatim) is committed before the queue starts.
- The queue starts only after a new approval line naming the new commit.

### TEST analysis by path override (Aarnav 2026-10-29, "APPROVED test_analysis.py path override"; registered before code)

- Why: the analysis scripts listed in configs/frozen_v2.yaml hard-code DEV run folders
  (results/dev_*), so run unchanged they re-analyse DEV or crash on arms without a TEST run.
  They are not edited. paper/scripts/test_analysis.py imports each one unchanged and replaces
  only its path constants, then calls its main() once.
- Hash check first: before any analysis, the SHA-256 of every analysis script listed in
  frozen_v2.yaml (d72_c2r_holm, d72_report, d79_report, d74_report, d74_alarm_holdout,
  d73_report, d71_report) and of the scripts they import from paper/scripts (d74_alarm_calib)
  is compared with `git show 51fe9db:<path>`; any mismatch aborts. `git diff 51fe9db -- slowburn`
  must also be empty (library code the scripts import), else abort.
- Two runs of the same wrapper, mode dev then mode test, after QUEUE DONE. The report's DEV
  column comes from the dev run, not from older DEV outputs. Outputs: results/analysis_dev/<script>/
  and results/analysis_test/<script>/, stdout of each main() in <script>.txt there.
- Path overrides (mode dev uses the dev_ folder, mode test the test_ folder of the same name):
  d72_c2r_holm ARMS = {napierone_bytes: d72_bytes_napierone_v2pool, synthetic_bytes:
  d72_bytes_synthetic}; d72_report UNITS = {bytes_synthetic: d72_bytes_synthetic,
  bytes_napierone_v2pool: d72_bytes_napierone_v2pool} (qs None, as the byte units);
  d79_report ARMS = {napierone_bytes: (d79_eqh_napierone, d72_bytes_napierone_v2pool),
  synthetic_bytes: (d79_eqh_synthetic, d72_bytes_synthetic)}; d74_report arms =
  {synthetic_bytes: d74_attack_synthetic, napierone_bytes: d74_attack_napierone} (passed as
  arguments); d73_report ARMS = {synthetic_bytes: d73_fleet_synthetic, napierone_bytes:
  d73_fleet_napierone_v2pool}; d71_report R = results/analysis_<mode>/d71_report holding a hard
  link to <folder>/d71_oracle_gap/tuning_sweep.csv (d71_report writes its CSVs into R, so this
  keeps the run folders unwritten; the link source is logged). OUT of every script goes to
  results/analysis_<mode>/<script>. d74_report CALIB stays results/dev_d74_alarm_calib
  (calibration is DEV, a63fc54).
- Arms dropped (no TEST run): d72_c2r_holm napierone_bytes_v1pool; d72_report full, worst,
  bytes_napierone (v1 pool); d73_report napierone_bytes_v1pool. Numbers from these stay labelled
  DEV only wherever claims.md or the paper use them.
- ALARM: d74_alarm_holdout is both the TEST run and its analysis and already ran in the queue
  (results/test_d74_alarm); it is not run again in mode test (no rerun except for a crash). The
  wrapper copies results/test_d74_alarm/holdout.json into results/analysis_test/d74_alarm_holdout.
  In mode dev it runs main() on the two DEV configs with --out=results/analysis_dev/d74_alarm_holdout
  (DEV family d74_alarm_holdout, the same 100 runs per arm).
- File access audit: a Python audit hook (sys.addaudithook; also installed in worker processes
  through a sitecustomize on PYTHONPATH) logs every file open with its mode, listdir/scandir,
  mkdir, link and remove under the repo (not .venv, not __pycache__) during each main(), to
  results/analysis_<mode>/audit.log (committed). Abort rules: mode test aborts on any read under
  results/dev_* except the allow list; mode dev aborts on any read under results/test_*, and on
  a read under results/dev_* outside that script's dev run folders and the allow list; both
  modes abort on a write under results/ outside results/analysis_<mode>/. Allow list (DEV
  calibration, read in both modes): results/dev_d74_alarm_calib/threshold.json,
  results/dev_d74_alarm_calib/daily_counts_napierone_bytes.csv.gz,
  results/dev_d74_alarm_calib/daily_counts_synthetic_bytes.csv.gz. Reads outside results/
  (data/, configs/, detector pickles under results/detector*) are logged, not restricted.
- No metric, test, threshold or analysis logic changes. Outputs and audit logs are committed
  (results/ is git-ignored; force-added, except the hard-linked tuning_sweep.csv).
- Amendment (Aarnav 2026-10-29, after the DEV attempt killed for low memory; before code): one
  process per script, one at a time, order d72_c2r_holm, d72_report, d79_report, d71_report,
  d73_report, d74_report, then d74_alarm_holdout (registered above, not in the team's list of
  six: on test a copy, on dev the 100 DEV holdout runs per arm); DEV mode first, then TEST mode
  in the same order (paper/scripts/test_analysis_queue.py). Before each script free RAM >= 16 GB,
  else wait and poll every 5 minutes. Logged per script: free RAM at start and the peak working
  set of the script process and of each worker process. If a script process is killed or
  crashes in either mode: its partial output (its folder, its .txt, its audit parts) is deleted
  unread, the cause fixed only if it is in the wrapper, logged, and that script rerun; analysis
  of fixed run outputs is deterministic, so this applies to analysis only; TEST simulation
  outputs are never rerun. An audit DENY or a hash mismatch is not a crash: it stops the queue.
  Hash and audit checks run in every script process.
- Amendment 2 (Aarnav 2026-10-29, "resume at 22 GB"; before code): the remaining analysis (TEST
  d74_report, then the TEST ALARM copy) waits for free RAM >= 22 GB (DEV d74_report peak 17.6 GB
  + 4 GB), polling every 5 minutes, never stopping. Fallback if free RAM stays below 22 GB for
  30 minutes: d74_report is called once per arm (napierone_bytes, then synthetic_bytes) through
  its existing arms and out arguments, the script unchanged. Validation first on DEV: per-arm
  runs into results/analysis_dev/d74_report_per_arm_check/<arm>, then per output file the two
  arms' rows concatenated (NapierOne first, as ordered() writes them; false_alarms.csv is built
  from the DEV calibration for both arms in every call, so the NapierOne call's copy is used)
  and compared with the combined DEV output results/analysis_dev/d74_report: byte identical
  (.csv.gz compared after decompression, since the gzip header holds a timestamp), else
  identical after sorting rows; the result per file is logged. The per-arm mode is used on TEST
  only if every file is identical by one of the two; else stop and report. Per-arm runs use the
  earlier 16 GB gate (one arm at a time; their peaks logged). The TEST per-arm outputs stay in
  results/analysis_test/d74_report_per_arm/<arm> and are merged the same way into
  results/analysis_test/d74_report. Hash and audit checks in every process.
- Amendment 3 (Aarnav 2026-10-30, "copy at 16 GB"): the TEST ALARM copy step only (copies
  results/test_d74_alarm/holdout.json, about 120 MB) uses the 16 GB gate; it had waited at the
  22 GB gate from 2026-10-30 00:28 to 08:13 (free RAM about 18 GB). The waiting loop was stopped
  by process tree before the copy started.

### Paper expansion analyses (Aarnav 2026-11-01; registered before code; all EXPLORATORY in the paper)

TEST is closed: nothing below reruns a TEST item or opens a TEST content pool. Every result here
is labelled exploratory in the paper; none changes a confirmatory claim, and a breakdown that
contradicts a headline is reported as such.
- E1 Overhead (no data). SlowBurn's decision (PosteriorDP, frozen hyperparameters: penalty 90,
  gate 0.8, backbone 0.25) replayed online for 400 days with a uniform start prior conditioned on
  "not discovered yet" (the DP's input, built with the code's own discovery_posterior), for K in
  {4, 6, 8, 12, 16, 24} and assumed discovery bound M in {30, 60, 120, 365} days; GFS and Tower of
  Hanoi replayed at the same K for reference. Measured: wall time per daily decision (median and
  95th percentile over days 30 to 399, after the budget is full), peak traced Python memory
  (tracemalloc) per replay. One machine, single process, nothing else heavy running; machine
  spec reported. Script paper/scripts/overhead.py, output results/exploratory/overhead/.
  Cross-check (descriptive): dp_ms_per_decision recorded in the TEST C2 run.
- E2 Post hoc breakdowns of TEST (no rerun). results/analysis_test holds pooled tables only
  (plus d79_report/by_world_budget.csv), so the breakdowns read the TEST run outputs those
  tables were computed from, read only: results/test_d72_bytes_{napierone_v2pool,synthetic}/
  tuning_sweep.csv (C2: SlowBurn vs each of the six baselines; filter variant
  method_v2_w075_vsnap, count budgets, as d72_c2r_holm), results/test_d79_eqh_*/tuning_sweep.csv
  (D79 primary pairs), results/test_d74_attack_*/attack_rows.csv.gz (D74). Splits: world, K,
  benign invalid rate (C2, D79); world (D74: realistic attacker recovery per policy and K; the
  best-response strategy chosen in analysis_test/d74_report/best_response.csv scored on the
  evaluation half per world). Statistic: the same paired machine-cluster bootstrap as the
  confirmatory scripts (method_v2.policy_vs_policy with by=, 2000 resamples, seed 0); point
  estimates and 95% CIs, no Holm, labelled "exploratory, post hoc". The same splits are computed
  on the DEV v2 run outputs for comparison. Script paper/scripts/posthoc_breakdowns.py, output
  results/exploratory/posthoc/.
- E3 Storage. The TEST C2 outputs record snapshots_retained, retained_unique_bytes and
  storage_vs_keep_last_n per row: mean per policy and K on both arms, descriptive, from the same
  files as E2 (read only). Output results/exploratory/storage/.
- E4 D76 restic prototype (DEV synthetic only; after E1 to E3; one heavy job at a time, RAM gate
  16 GB and 45 GB disk floor as before). restic pinned binary (official GitHub release, SHA-256
  checked against the release's SHA256SUMS) in gitignored tools/. Workload: one simulated DEV
  synthetic machine (synthetic bytes, family of a new key "d76_restic", DEV split, a fixed seed),
  materialised as a file tree in gitignored restic/ (tree + repository <= 5 GB); each simulated
  day the tree is updated to that day's file versions (benign edits from the simulator; damaged
  versions are the simulator's existing synthetic damaged bytes, no encryptor), `restic backup`
  takes the day's snapshot, and SlowBurn's held set for that day (from the same simulator
  replay) is applied by `restic forget <snapshot ids>` for every snapshot the plan drops. Check
  every day: the set of restic snapshots equals the plan (mismatches counted and reported).
  Measured: forget time, prune time (prune every 7 days and at the end), repository size; the
  same tree and backups under restic's own `--keep-daily 7 --keep-weekly 5` (plus a count-matched
  variant) for comparison. Nothing outside restic/ is read or written except the repo's own
  code and the synthetic generator. Script paper/scripts/d76_restic.py, output
  results/exploratory/d76_restic/.

### 2026-11-02 amendment to E4 (D76), registered before the change and the run
- RAM gate for E4 only lowered from 16 GB to 8 GB free (user instruction 2026-11-02; free RAM
  stayed at 15.4 to 15.9 GB for hours). The 45 GB free disk gate on C: is unchanged. All other
  jobs keep their gates. Nothing else about E4 changes (machine, policies, measurements, outputs).
- Added measurement: peak memory of the run, logged in run.json, as the Python process's peak
  working set and the largest peak working set of any restic subprocess (Windows
  GetProcessMemoryInfo).
- Fix already committed in 300bc7e: the day-by-day consistency check now compares the
  scenario's own chunks with the trace (the earlier re-chunking check aborted on day 16; bytes
  backed up are unchanged).

## Protocol v3 (team, 2026-11-02): development on DEV, then a fresh held-out pool TEST2

TEST is spent: nothing in v3 reads or runs anything on TEST. The paper v1 state is tagged
`paper-v1-ieee-access-candidate`. Every v3 output is labelled exploratory_dev_v3 until a TEST2
pre-registration says otherwise. One heavy job at a time. D81 is specified by the team; for D82 to
D88 the hypotheses and criteria below were drafted by Claude Code from the team's one-line spec
and are NOT final: the team confirms or changes each before any code for that item.

### D81: byte-budget arm (team spec and decisions 2026-11-02; registered before any D81 code)
- Hypothesis: the C2 and equal-horizon comparisons at matched snapshot count change when every
  policy is held to the same repository bytes.
- Data: DEV v2 only, both arms: NapierOne bytes (configs/dev_d72_bytes_napierone_v2pool.yaml
  machines: seed 202, 4 worlds x 40 reps, benign invalid rate {0, 0.01, 0.05}, delays
  {7, 14, 30, 45, 60}) and synthetic bytes (configs/dev_d72_bytes_synthetic.yaml, same grid).
  Restore A (verify_snap). Policies: those of C2 and the equal-horizon comparisons, i.e.
  SlowBurn, prior-only, Bar-On recursive, Bar-On round robin, GFS, Tower of Hanoi, GFS-eqh and
  ToH-eqh (the D79 age-capped variants are not part of D81).
- Bytes: unique bytes of the held snapshots' contents in the simulator (ByteIndex, exact union
  of chunks in byte mode).
- Primary budget levels, one per K in {4, 6, 8, 12}: the median unique bytes SlowBurn retains at
  count K on the attack-free DEV calibration machines (40 per arm, calibration family), over days
  after warm-up. Following the D46 convention, the median is taken of retained bytes divided by
  the machine's day-0 snapshot size, and each evaluation machine's budget is that multiplier
  times its own day-0 size. Computed per arm and per benign invalid rate (SlowBurn's footprint
  depends on its flags). The values are committed to this entry BEFORE any D81 evaluation run.
- Secondary level (policy independent, reported separately): the D46 keep-last 30-day footprint
  (multiplier of day-0 size, calibrated as in D46 on the same calibration machines).
- Enforcement, identical for every policy including SlowBurn (team rule; replaces native
  eviction): for each machine, policy and level, K' = the largest count in the supported range
  2..24 whose retained unique bytes stay within the budget on EVERY day of the run, found by
  simulating the policy at each count. K' is fixed per machine for the whole run (no mid-run
  switching). The machine's work lost and recovery at that level are its rows at count K'. No
  byte-aware planning (a byte-aware SlowBurn DP would be a new method; logged as a possible later
  D entry).
- Infeasible: no count in 2..24 fits, or the policy supports no fitting count (for example an
  eqh schedule whose count cannot reach its horizon). Infeasible cells are recorded and reported
  per policy and level, never dropped silently. K' = 24 (top of range) is reported as censored.
- Metrics: per policy, work lost (whole-system hours) and clean recovery at matched bytes and at
  matched count (count-K rows of the same machines); SlowBurn against each other policy, relative
  work lost and recovery difference with the paired machine-cluster bootstrap (2000 resamples,
  seed 0; pairs only where both are feasible; pairs lost to infeasibility reported). Also:
  repository bytes per policy (mean retained unique bytes), the distribution of K' per policy
  and level, and per machine the days on which the selected count is at the cap (retained bytes
  >= 0.95 x budget).
- Success / kill: none. D81 is a reporting arm (exploratory_dev_v3): no claim, no adoption, no
  Holm. Kill only on a broken invariant: any selected run exceeding its budget on any day, or
  count-K rows that do not reproduce the existing DEV v2 rows for the same machines.
- Memory gate: a pilot (2 machines per arm) measures the peak working set of the run's process
  tree; the full run starts only with free RAM >= that peak (scaled to the run's worker count)
  + 4 GB, and C: >= 45 GB free. One heavy job at a time.
- Outputs: results/exploratory_dev_v3/d81_*. Report numbers only, no interpretation.

### D82: adaptive-horizon SlowBurn (DRAFT criteria, team to confirm)
- Hypothesis: choosing the assumed discovery bound (retention horizon) from the benign flag rate
  measured during calibration lowers work lost against fixed-horizon SlowBurn without lowering
  recovery. Rule developed on DEV only and fixed before TEST2.
- Metric: work lost and clean recovery against fixed-horizon SlowBurn (M = 60) and against the
  equal-horizon rotations, by injected benign invalid rate and world.
- Baselines (team review 2026-11-03): adaptive-horizon GFS and adaptive-horizon ToH, with the
  horizon chosen by the same rule as adaptive SlowBurn.
- Split (team review 2026-11-03): DEV machines are split at machine level into fit and check
  halves; the rule is fixed on the fit half and judged on the check half only.
- Success (team review 2026-11-03, replaces the earlier draft): at benign invalid rates 0.01 and
  0.05, adaptive SlowBurn work lost below equal-horizon GFS and equal-horizon ToH (upper CI < 0);
  at rate 0, non-inferiority only (upper CI of the relative work lost difference < +2%); recovery
  within 0.01 in every world; all evaluated under both count budgets and sbmax byte budgets.
- Kill (team review 2026-11-03): the rule needs more than two free parameters, fails the success
  criterion on the check half, needs test-time quantities, or does not beat the adaptive-horizon
  GFS and ToH baselines.

### D83: format-aware png truncation validator (DRAFT criteria, team to confirm)
- Hypothesis: a png structure check (signature, chunk lengths and CRCs, IEND) marks benign files
  truncated at a size cap as truncated-benign rather than damaged, removing their benign flags.
- Metric (DEV pools): share of the benign flags from the 9 truncated DEV pngs removed; damaged
  png detection; benign flag rate.
- Added (team review 2026-11-03): synthetic truncation of DEV pngs at several cut points, with
  the removed share reported per cut point; damaged png detection reported per damage family.
- Success: at least 90% of those flags removed and damaged png detection lower by at most 0.01.
  Kill: the check cannot tell truncated benign files from damaged ones (damaged detection drops
  by more than 0.01).

### D84: detector baselines (DRAFT criteria, team to confirm)
- Baselines: an entropy threshold; entropy plus magic bytes; both reported per file type.
- Metric (DEV): per-type detection at matched benign flag rate, AUROC; SlowBurn's downstream
  work lost and recovery with each detector.
- Success / kill: reporting item. If a baseline is within 0.01 AUROC of the trained detector
  pooled, the trained detector is not claimed as necessary.

### D85: FSL Homes benign replay with in-place edits (DRAFT criteria, team to confirm)
- Hypothesis: replaying FSL Homes per-file rewrite days with in-place edits of each file's own
  bytes (instead of redrawing content from the pool) lowers benign validity transitions and
  benign flags relative to the Poisson model.
- Metric (DEV): benign flag rate, benign validity transitions, C2 and equal-horizon deltas.
- Pre-registered (team review 2026-11-03): reduced benign flags may shrink the gap between
  SlowBurn and the equal-horizon rotations; that change is reported whatever its direction.
- Success: the replay runs on DEV with both rates measured. Machine histories may resample user
  days with repeats; the number of repeated days per machine is reported. Kill: the trace cannot
  supply machine histories even with resampled days (team review 2026-11-03, replaces "without
  repeating days more than once per machine").

### D86: hourly model with a rolling-window alarm (DRAFT criteria, team to confirm)
- Hypothesis: an hourly simulation with a rolling 24-hour flagged-file count alarm keeps the
  held-out false alarm rate of the daily alarm while detecting within-day bursts.
- Metric (DEV): false alarms per run (Clopper-Pearson), detection delay, threshold-aware attacker
  detection. Success: upper 95% bound of false alarms per run <= 0.05 on held-out DEV runs.
  Kill: a false alarm rate above the daily alarm's at the same threshold, or a simulation cost
  above 10 times the daily model's.

### D87: calibration shift (DRAFT criteria, team to confirm)
- Hypothesis: calibrating on one content mix and evaluating on another raises benign flags and
  false alarms. Design: calibrate on the v1 DEV pool and evaluate on the v2 additions, and the
  reverse; a type-mix shift as a second axis.
- Metric: benign flag rate, false alarms, work lost against matched calibration.
- Success / kill: reporting item; any degradation is reported with its interval.

### D88: TEST2 construction (DRAFT, team to confirm before any file is drawn)
- TEST2 = NapierOne benign files and encrypted samples disjoint from the DEV and TEST pools (by
  SHA-256), stratified per type as before, with three ransomware families used in neither DEV
  nor TEST. The TEST2 inventory (names, hashes, per-type counts, validity failures) is committed
  before any experiment touches TEST2.
- Open point for the team: disjointness from TEST needs the committed TEST manifest (names and
  hashes only, no file contents). Confirm that reading the manifest is allowed under "nothing
  reads TEST".
- Team decision (2026-11-02): reading the TEST manifest is allowed for hashes only, to enforce
  disjointness. No TEST file contents, labels or result files are read.
- Kill: a type without enough unused files is reported and reduced or dropped, decided before
  drawing.

### D81 budget values (calibrated 2026-11-02 16:40-18:16, committed before any D81 evaluation run)
Multipliers of each machine's day-0 snapshot size (D46 convention), from 40 attack-free DEV
calibration machines per arm and benign invalid rate (`slowburn.bench.byte_matched calibrate`;
files results/exploratory_dev_v3/d81_{napierone,synthetic}/levels.json). Primary sb_K{K}: median
of SlowBurn's retained unique bytes at count K / day-0 size over days after warm-up. Secondary
keep30: the D46 keep-last 30-day footprint (does not depend on the benign rate).

| arm | benign invalid rate | sb_K4 | sb_K6 | sb_K8 | sb_K12 | keep30 |
|---|---|---|---|---|---|---|
| napierone | 0.0 | 2.3728 | 3.0490 | 3.4664 | 3.9480 | 2.7675 |
| napierone | 0.01 | 2.3744 | 3.0215 | 3.4527 | 3.9423 | 2.7675 |
| napierone | 0.05 | 2.3911 | 3.0625 | 3.4497 | 3.9841 | 2.7675 |
| synthetic | 0.0 | 2.4976 | 3.2134 | 3.5386 | 4.0233 | 2.7602 |
| synthetic | 0.01 | 2.5134 | 3.2000 | 3.5568 | 4.0458 | 2.7602 |
| synthetic | 0.05 | 2.5285 | 3.2217 | 3.5382 | 4.0635 | 2.7602 |

Unsupported counts found while writing the code (reported, part of the infeasible rule):
Bar-On recursive and round robin at count 2 (no schedule for one checkpoint); GFS-eqh at
counts below 11 and ToH-eqh below 8 (horizon not reachable).

### D81 addendum (team review 2026-11-02, exploratory_dev_v3, DEV only)
- Level names: the first run's `sb_K{K}` is renamed `sbdaymed_K{K}` in all reports. It is the
  median over all pooled calibration machine-days after warm-up (40 attack-free DEV machines x
  days; not a median over machines) of SlowBurn's daily retained unique bytes at count K / that
  machine's day-0 size.
- New level `sbmax_K{K}`, K in {4, 6, 8, 12}: the median over the 40 calibration machines of each
  machine's MAX daily retained unique bytes at count K over every day of the run / day-0 size,
  so that SlowBurn's own K' is at least K on about half the machines. Same K' rule, same report.
  Values below are committed before any sbmax evaluation run.
- Memory gate change, approved by Aarnav on 2026-11-03 for the sbmax calibration job only:
  headroom reduced from measured peak + 4 GB to measured peak + 2 GB. Reason: the PROMPT
  project's job holds about 5 GB, so free RAM sat between 9.2 and 9.9 GB, below the 10.6 GB
  gate; the calibration is DEV only and exploratory_dev_v3, with no confirmatory impact.
  Measured peak used: 6945 MiB (6.8 GB), the sum of per-process peaks of the full D81 napierone
  run, which includes the same in-run calibration; gate = 6.8 + 2 = 8.8 GB free RAM. NapierOne
  calibration had already passed the unchanged gate and finished before the change; the change
  applies to the synthetic calibration. Every other gate is unchanged (the sbmax evaluation runs
  keep peak + 4 GB; disk >= 45 GB); frozen_v2.yaml is unchanged.

#### D81 addendum: sbmax budget values (calibrated 2026-11-02/03, committed before any sbmax run)
Multipliers of each machine's day-0 snapshot size; median over the 40 attack-free DEV
calibration machines of SlowBurn's per machine max daily retained unique bytes at count K over
every day (files results/exploratory_dev_v3/d81_{napierone,synthetic}/levels_sbmax.json). The
same runs recomputed sb_K (sbdaymed) and matched levels.json exactly on every cell.

| arm | benign invalid rate | sbmax_K4 | sbmax_K6 | sbmax_K8 | sbmax_K12 |
|---|---|---|---|---|---|
| napierone | 0.0 | 3.5263 | 4.2135 | 4.8892 | 5.6782 |
| napierone | 0.01 | 3.5263 | 4.2135 | 4.8892 | 5.7789 |
| napierone | 0.05 | 3.5263 | 4.2135 | 4.7926 | 5.6074 |
| synthetic | 0.0 | 3.5370 | 4.2639 | 4.9800 | 5.8304 |
| synthetic | 0.01 | 3.5370 | 4.2500 | 4.9733 | 6.1350 |
| synthetic | 0.05 | 3.5370 | 4.2639 | 4.9800 | 6.1132 |

#### D81 addendum: disk floor change for the synthetic sbmax run (approved by Aarnav 2026-11-03)
- The disk floor is lowered from 45 GB to 40 GB free on C: for the synthetic sbmax evaluation run
  only. Reason: C: stayed at 41.7-42.0 GB free (space taken by the PROMPT project's job; nothing
  was deleted), below the 45 GB floor for more than 6 h; this run writes about 105 MB (measured on
  the napierone sbmax run: 97 MB per machine cache, 5.6 MB rows, 76 KB tasks, logs). DEV only,
  exploratory_dev_v3, no confirmatory impact. The RAM gate (measured peak 6.8 GB + 4 GB = 10.8 GB)
  is unchanged. The 45 GB floor is unchanged for every other job.

### D82 rule (pre-registered 2026-11-04, team decision; before any D82 code)
- Rule (G_q; the r_hat variant is not pre-registered). On the 40 attack-free DEV calibration
  machines per benign setting (the machines attack_free_calibration already simulates), for each
  day t after warm-up, G_t = days from t back to the newest snapshot that holds no flagged
  version (the depth restore A walks back past benign flags on a clean machine). G_q = the
  q-quantile of G_t pooled over machines and days. Output, per benign setting:
  M = 60 + ceil(lambda * G_q) days, used as SlowBurn's assumed discovery bound (uniform, max M)
  and as EqualHorizon("gfs", M) and EqualHorizon("toh", M) for the adaptive GFS and ToH
  baselines. lambda = 0 gives frozen SlowBurn and the existing eqh baselines.
- Free parameters and grid: q in {0.5, 0.9, 0.99}; lambda in {0, 0.5, 1, 2}. Selected on the fit
  half by pooled work lost subject to recovery within 0.01 in every world; judged once on the
  check half under the committed D82 criteria.
- Fit and check split: unit = DEV machine (world, true start, rep), shared across benign rates
  and both data arms (160 machines per arm). Sort the machines by (world, rep), permute with
  numpy.random.default_rng(82082).permutation; the first 80 are the fit half, the rest the check
  half. The split is fixed before any D82 number is computed.
- Written prediction: adaptive SlowBurn will likely fail D82, because lengthening M raised work
  lost in D52 (assumed 90 / 120 vs 60 days: +492.3 / +1084.2 h, old restore) and the same M is
  given to the adaptive GFS and ToH baselines.
- Limitation: the DEV discovery-delay grid stops at 60 days, and recovery beyond the assumed
  bound is about 0 (F1). M below 60 therefore cannot be evaluated on this grid; the rule only
  lengthens M.

### D82 stage 1 precheck (pre-registered 2026-11-04, team approval; before any precheck code)
- Question: does lengthening SlowBurn's assumed discovery bound M beyond 60 lower its work lost
  at any benign rate? SlowBurn only (frozen v1 operating point, variant method_v2_w075_vsnap),
  M in {60, 75, 90}. M is the uniform assumed discovery bound; with no separate
  restore_discovery in the config, restore A uses the same M. Nothing else changes.
- Grid: DEV v2 (seed 202), both arms (napierone, synthetic), benign invalid rates 0, 0.01, 0.05,
  all worlds and delays; budgets count K8, K12 and sbmax K8, K12 with the committed
  levels_sbmax.json multipliers (fixed at the M = 60 SlowBurn footprint) and the unchanged D81
  K' rule. M = 60 rows are the existing D81 rows (count from d81_machines_rows, sbmax from
  d81max_machines_rows; same code, same frozen parameters); M = 75 and 90 are new runs.
- Halves: the D82 fit and check halves by machine (ed3f273: machines (world, true start, rep)
  sorted by (world, rep), numpy.random.default_rng(82082).permutation, first 80 fit). Fit and
  check reported separately.
- Statistics: per half, arm, rate and budget cell, SlowBurn mean work lost and recovery per M;
  M = 75 and M = 90 against M = 60 with the existing paired machine-cluster bootstrap
  (method_v2.policy_vs_policy, 2000 resamples, seed 0); K' distribution and infeasible counts per
  M at the sbmax cells.
- Kill rule (fit half, as committed): per benign rate, mean SlowBurn work lost pooled over both
  arms and the four budget cells (point estimate). If M = 60 has the lowest value at every rate,
  D82 is killed by precheck: commit and stop. Otherwise stop and show the table; stage 2 (GFS-eqh
  and ToH-eqh at the same M) does not start without team approval.
- Stated before any number: the DEV delay grid stops at 60 days, so M above 60 cannot gain
  recovery on this grid and any work lost increase is a pure cost. Under sbmax, the byte cap is
  fixed, so a larger M changes K' (a policy holding older snapshots can fit fewer of them).
- Disk floor (approved by Aarnav 2026-11-04, these precheck runs only): lowered from 45 GB to
  40 GB free on C:. Reason: C: is held at about 41.7 GB free by another project's job, nothing is
  deleted, and each run writes about 100 MB (measured on the D81 sbmax runs). DEV only,
  exploratory_dev_v3, no confirmatory impact. RAM gate unchanged (measured peak 6.8 GB + 4 GB =
  10.8 GB); one heavy job at a time; the 45 GB floor is unchanged for every other job.
- Code change limited to letting byte_matched accept an M override; no D82 rule code.
- Addendum (team, 2026-11-04, committed before any precheck run started): the kill rule's primary
  version uses the common rows (machine, delay and cell rows feasible at all three M). The
  all-feasible-rows version is reported alongside, with infeasible counts per M. D82 is killed by
  precheck only if both versions show M = 60 lowest at every rate on the fit half. If they
  disagree, D82 is not killed: show the table and stop.

### D82 killed by precheck (2026-11-04, exploratory_dev_v3, DEV only)
- Outcome: D82 killed by stage 1 precheck under the committed rule (8c9fa56). On the fit half,
  mean SlowBurn work lost pooled over both arms and the four cells (hours, M = 60 / 75 / 90):
  rate 0: 1582 / 1633 / 1891; rate 0.01: 1809 / 1885 / 2145; rate 0.05: 2676 / 2817 / 3243.
  M = 60 is lowest at every rate in both versions. They are identical (28,800 rows each) because
  0 fit-half machines are infeasible at any M, arm or cell. Recovery is 0.997 to 1.000 at every M.
- Not hidden by the pooled rule: synthetic count_K8 has lower work lost at M = 75 than at M = 60
  on both halves (fit -0.027, -0.004, -0.072 relative at rates 0, 0.01, 0.05; only check rate 0.05
  excludes 0: -0.103 [-0.171, -0.033]). No other cell or arm shows it. It is not a D82 result and
  supports no claim.
- The written prediction (ed3f273) held. Stage 2 not run; no D82 rule code written.
- Source: results/exploratory_dev_v3/d82_precheck/precheck_kill.json, precheck_cells.csv,
  precheck_vs_M60.csv, precheck_kprime_distribution.csv.

### D89 benign-flag tolerance in verify_snap (pre-registered 2026-11-04, team; before any code or run; exploratory_dev_v3, DEV only)
- D65's "no further accept-rule iterations" is lifted for D89 only (team, 2026-11-04). The D65
  result stands and is cited as prior evidence. D65 and D89 are both reported in the paper
  whatever D89 shows; neither is a headline method claim; any confirmatory claim needs TEST2
  under a new freeze.
- Hypothesis: the work lost penalty from benign false flags comes from verify_snap rejecting a
  candidate on any single flagged version (`slowburn/store/restore.py:156`). A tolerance reduces
  work lost for every policy.
- Definitions, per gated candidate j: x = held versions carrying their write-time flag; c = held
  versions written after day 0 (changed files).
- Rules (only these two): N(n): j dirty iff x >= n. T(t): j dirty iff x / c >= t (c = 0 means
  clean). Untuned = N(1), exactly verify_snap. Gate, candidate order, oldest-kept fallback, file
  selection and retention unchanged.
- Grid (fixed now): n in {2, 3, 5, 10}; t in {0.001, 0.002, 0.005, 0.01, 0.02}. 9 points plus
  untuned.
- Free parameters: two, the rule family and its value, shared by all policies (no per-policy
  choice, no joint (n, t) rule).
- Halves: fit and check by machine, the ed3f273 split (machines sorted by (world, rep),
  numpy.random.default_rng(82082).permutation, first half fit).
- Selection on the fit half: the grid point with the lowest pooled work lost such that EVERY
  policy's recovery (pooled over cells, rates and arms) is no more than 0.01 below untuned. Ties
  go to the smaller tolerance. If no point qualifies, D89 is killed.
- Scope: SlowBurn, GFS, ToH, GFS-eqh, ToH-eqh, Bar-On recursive; count K8, count K12, sbmax K8,
  sbmax K12; benign rates 0, 0.01, 0.05; both arms; DEV v2 grid.
- Metrics: work lost and recovery, and the change against untuned per policy, paired
  machine-cluster bootstrap CIs (method_v2.policy_vs_policy, 2000 resamples).
- Success (check half, selected point): pooled work lost lower than untuned and no kill. Reported
  separately: whether SlowBurn benefits more than each baseline (difference in relative work
  lost change, paired CI).
- Kill (check half): any policy's pooled recovery drops by more than 0.01 below untuned, or more
  than two parameters are used. Pooled recovery is also reported. Per-cell changes are reported
  and do not enter the verdict.
- Caveat: under T(t) the effective tolerance depends on what each policy retains, so the
  SlowBurn versus baseline comparison is primary for N(n) and secondary for T(t).
- Checks: N(1) must reproduce the existing rows exactly, and retention must be identical row for
  row. If either fails, stop and report.
- Written prediction: it will help all policies, and probably help the equal horizon policies at
  least as much as SlowBurn, because the penalty comes from long retained history. D65 suggests
  the recovery kill is the likely outcome (a slow attack's early snapshots hold few flagged
  versions, so any n >= 2 or t > 0 can accept lightly damaged snapshots).
- Gates: RAM measured peak + 4 GB, disk floor 45 GB, one heavy job at a time. Time box: done by
  2026-11-06. TEST untouched.

### D89 outcome (2026-11-04, exploratory_dev_v3, DEV only): success, not killed
- Checks passed: N1 reproduces the existing D81 rows (55,200 per arm, 80 to 81 columns, 0
  differing) and retention is identical across all 10 rules row for row.
- Fit half: qualifying points N2, N3 and T0.001 to T0.02; N5 and N10 fail (GFS-eqh recovery
  -0.0104). Selected N3 (pooled work lost 1904.1 -> 1554.3 h). Every T(t) point is identical to
  N1 on every row: on this grid one flagged version already gives x / c >= 0.02, so the
  committed T grid has no effect. Reported as found; not re-gridded.
- Check half at N3, recovery change [95% CI] and relative work lost change:
  SlowBurn -0.0018 [-0.0034, -0.0004], -29.2% [-31.4, -26.9]; GFS -0.0025 [-0.0063, -0.0001],
  -4.3%; ToH 0.0000, -16.1%; GFS-eqh -0.0003, -14.7%; ToH-eqh 0.0000, -16.7%; Bar-On recursive
  -0.0019 [-0.0035, -0.0005], -33.0%. Pooled: -0.0011 [-0.0021, -0.0004], -19.8%
  [-21.6, -18.0]. No policy drops by more than 0.01: not killed. Pooled work lost lower:
  success. Parameters: two (family N, n = 3).
- SlowBurn minus baseline, relative work lost change (primary, N family): vs GFS -0.249
  [-0.271, -0.226]; ToH -0.131 [-0.159, -0.102]; GFS-eqh -0.145 [-0.166, -0.125]; ToH-eqh -0.125
  [-0.153, -0.096]; Bar-On recursive +0.038 [+0.021, +0.055] (Bar-On benefits more).
- Per cell (reported, not in the verdict): 2 of 138 check-half cells drop recovery by more than
  0.01, both GFS, napierone sbmax_K12 (-0.0125 at rates 0.01 and 0.05, CIs include 0).
- Written prediction: "helps all policies" held. "Equal horizon policies at least as much as
  SlowBurn" failed: SlowBurn gains more than GFS-eqh and ToH-eqh. The recovery kill D65 suggested
  did not happen at N3; it is near on the fit half at N5 and N10.
- Status: exploratory DEV result; not a headline method claim; any confirmatory claim needs
  TEST2 under a new freeze. Reported in the paper alongside D65.
- Resource note: napierone sum of process peaks 10.0 GB (tree peak 7.3 GB), above the 6.8 GB
  the gate assumed; a rerun of this job should gate on 10.0 + 4 = 14.0 GB.
- Source: results/exploratory_dev_v3/d89_report/.

### D90 limitation test: threshold-aware attacker against the N3 restore (pre-registered 2026-11-04, team; before any code or run; exploratory_dev_v3, DEV only)
- Label: LIMITATION TEST. No success or kill criterion; whatever comes out is reported. The
  experimental phase closes after D90 (team, 2026-11-04). No N3 runs at count K4 / K6; no TEST2.
- Attacker (a simulation parameter, `d90_attacker_flag_cap` = 2; no attack technique is
  modelled): an upper bound on an attacker that knows the N3 rule. Attacker versions = versions
  of a damaged file written on or after its damage day. Processing attacker versions carrying a
  detector flag in write-day order (ties by file id), a flag is kept only if every snapshot that
  holds the version (end of its write day up to the day before the file's next change, or the end
  of the run) still holds fewer than 2 flagged attacker versions; otherwise the flag is removed,
  i.e. that damaged version goes undetected. The cap is applied consistently: the history flags
  used by verify_snap, the daily evidence (k and k / n of that day's DailyObs) used by the
  posterior, and the write-time evidence of the same version. Damage itself is unchanged, so
  every file the honest attacker damages is still damaged. Benign flags are untouched, so a
  snapshot can still hold 3 or more flagged versions through benign flags.
- What it means: worst case for N3 (dirty iff x >= 3). It also weakens the daily evidence for
  every policy that uses it (SlowBurn's retention and the posterior gate), so retention is not
  identical to D89; N1 and N3 are paired on the same D90 runs, so retention is identical between
  them (checked row for row; if not, stop and report).
- Scope: SlowBurn, GFS-eqh, ToH-eqh, Bar-On recursive; sbmax K8 and K12 (the D81 sbmax levels,
  unchanged); benign rates 0 and 0.01; both arms; DEV v2 grid; check half only (ed3f273 split);
  restores N1 (untuned) and N3 (the D89 selection, fixed).
- Metrics: recovery and work lost per policy, N3 vs N1, per cell (arm x level x rate) and pooled,
  paired machine-cluster bootstrap CIs (2000 resamples). Reported alongside for reference: the
  D89 honest-attacker check-half rows for the same cells; and per machine the count of attacker
  flags removed and kept.
- Free parameters: unchanged (N3 from D89; the cap 2 is fixed by the N3 rule, not fitted).
- Gates: RAM 14 GB free (D89 NapierOne sum of process peaks 10.0 GB + 4 GB), disk floor 45 GB,
  one heavy job at a time. TEST untouched.
- D90 run setup change (approved by Aarnav 2026-11-05; run setup only, no change to the
  experiment): workers reduced from 5 to 2 for the D90 runs. Reason: the D89 NapierOne run peaked
  at 10.0 GB (sum of process peaks; tree peak 7.3 GB) with 5 workers, the PROMPT jobs hold about
  9 GB, and the first D90 attempt (2026-11-04) was stopped by Claude Code for critically low
  memory before any machine finished (no results lost; leftover process tree killed and
  verified). Expected peak with 2 workers: about 0.6 + 2 x 1.9 = 4.4 GB (D89 per-worker upper
  bound; D90 runs 4 of the 6 policies and no count cells), target at most 6 GB. Checks before
  the full run: one NapierOne batch at 2 workers with its measured peak; and rows at 2 workers
  must be byte identical to rows of the same machines from the original 5-worker runs (the D89
  N1 / N3 rows, via the same code with the cap off). If either fails, stop and report. Gate:
  free RAM >= measured peak + 4 GB, rechecked every 10 min; a watchdog stops the run tree if free
  RAM falls below 3 GB (finished machines stay cached).

### D90 outcome (2026-11-05, exploratory_dev_v3, DEV only, LIMITATION TEST; no criterion)
- Checks: all 80 machines per arm in the check half; retention identical N1 vs N3 row for row;
  25,600 rows. Attacker flags per machine: 2 kept, 24.1 (napierone) / 28.4 (synthetic) removed
  on average (max 35 / 38). Runs at 2 workers; peaks 3.3 / 1.4 GB (sum of process peaks).
- Pooled, N3 vs N1 under the capped attacker, recovery change [95% CI], relative work lost:
  SlowBurn -0.0575 [-0.0675, -0.0481], -10.9%; GFS-eqh -0.0589 [-0.0727, -0.0448], +2.3%
  [-1.4, +5.9]; ToH-eqh -0.0311 [-0.0428, -0.0211], -8.6%; Bar-On recursive -0.0466
  [-0.0575, -0.0366], -19.6%. N1 recovery under the same attacker: 0.995 / 0.998 / 0.940 /
  0.997, near the honest D89 values.
- Honest attacker reference (D89 rows, same machines and cells): recovery change -0.0022 to
  0.0000, work lost -12.1% to -26.4%.
- Per cell: every policy loses 0.021 to 0.088 recovery at N3 in every cell; recovery CIs exclude
  0 in all 32 cells. Under the cap at benign rate 0 on the synthetic arm, N3 also raises work lost
  for SlowBurn, GFS-eqh, ToH-eqh (CIs exclude 0) and Bar-On at sbmax K12.
- Reading, no claim beyond the table: an attacker that keeps its detected versions under the
  N3 threshold removes the D89 gain in recovery terms (3 to 6 points lost against N1), for every
  policy; N1 (verify_snap, any flag) is not affected the same way. N3 is not robust to a
  threshold-aware attacker. Reported as a limitation alongside D65 and D89.
- Source: results/exploratory_dev_v3/d90_report/. The experimental phase is closed.
