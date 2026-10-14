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
