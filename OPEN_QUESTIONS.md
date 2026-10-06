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
