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
  (prior-only recovery 0.988281-1.0 beyond the bound vs 0.0) at 4.180-4.539x the work lost when
  the true delay is 7-14 days (2.189-2.213x on the normal grid). Open for the team: whether the paper presents this as a trade-off (hard
  bound: cheap but collapses beyond it; soft tail: safe but restores far back), and whether a
  tail that is cheaper (e.g. smaller weight, or a tail that only opens with detector evidence)
  deserves a separately pre-registered stage.
