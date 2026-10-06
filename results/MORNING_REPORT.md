# Morning report — 2026-10-08

Unattended session (M0 → M1 → M2; M3 not started, as instructed). Every number below is read
programmatically from the result CSVs (4 decimals; full precision in the CSVs). **All data is
synthetic** (`benign_source=synthetic`, `damage_source=synthetic_random`). No dataset was
downloaded, nothing was pushed, nothing outside the repo was touched.

## TL;DR
- **M0, M1 and M2 are built, tested (91 tests passing, ruff clean) and committed:** `6908197` (M0),
  `f1e0fad` (M1), `232726e` (M2), plus the commit containing this report.
- **The Phase I plot is ready:** `results/detector/auroc_vs_fraction.png` (headline) and
  `results/detector/auroc_by_type.png` (per file type).
- **The premise holds on synthetic data, starkly.** With striped damage, chunk AUROC on high-entropy
  types falls from 0.8693 (100%) to 0.5410 (5%), essentially chance. lzma is at chance at every
  fraction, even for fully random chunks.
- **M2 works but fails in the hard regime, and its numbers are provisional.** The 16-rep re-run was
  stopped by Claude Code because the machine ran low on memory. The M2 numbers here come from an
  earlier 8-rep run made before one methodology fix (see "What failed"). I did not restart it.

## What works
| Milestone | What | Command |
|---|---|---|
| M0 | uv project, ruff/pytest, single-seed RNG, configs, synthetic simulator (10 file types via real encoders), dedup snapshot store, end-to-end `bench` writing tidy CSV + plot | `uv run slowburn bench configs/smoke.yaml` |
| M1 | `features(buf)` (260-d), LightGBM, isotonic probabilities, marginal + Mondrian (per file type) conformal p-values, train/calib/test split by file, hard negatives in every split, AUROC sweep over 2 damage models x 5 fractions x 10 types with file-cluster bootstrap CIs | `uv run slowburn detector configs/detector.yaml` (~95 s) |
| M2 | daily aggregators (exceedance count, trimmed mean, ...), Beta-Binomial and weekday-Gaussian observation models, exact single-changepoint posterior, BOCPD (both brute-force tested), ablations "suspicion only" and "prior only", experiment runner | `uv run slowburn inference configs/inference.yaml` (~25-30 min) |

`configs/*_smoke.yaml` run each pipeline in seconds.

## M1: detector AUROC (the Phase I result)
1500 files (150/type), 142875 labelled chunks, 28521 test
chunks, seed 11. AUROC is computed on the raw LightGBM score (decision D2). Chunk level
unless stated.

### Striped damage within chunk (headline model), per damaged fraction and file type
| file_type | 100% | 50% | 25% | 10% | 5% |
|---|---|---|---|---|---|
| ALL | 0.9069 | 0.8960 | 0.8543 | 0.7808 | 0.7522 |
| HIGH_ENTROPY | 0.8693 | 0.7955 | 0.7198 | 0.5896 | 0.5410 |
| LOW_ENTROPY | 0.9997 | 1.0000 | 0.9999 | 0.9981 | 0.9963 |
| bin | 0.9990 | 1.0000 | 0.9992 | 0.9828 | 0.9668 |
| csv | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| docx | 0.8961 | 0.7341 | 0.6319 | 0.5388 | 0.5223 |
| jpg | 0.9949 | 0.9896 | 0.9521 | 0.7311 | 0.6244 |
| lzma | 0.5510 | 0.5386 | 0.4839 | 0.4975 | 0.4817 |
| mp3 | 0.9919 | 0.9924 | 0.9877 | 0.8430 | 0.6952 |
| png | 0.8734 | 0.7497 | 0.6404 | 0.5451 | 0.5212 |
| txt | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| zip | 0.9191 | 0.7998 | 0.6546 | 0.5577 | 0.5254 |
| zlib | 0.8863 | 0.7582 | 0.6305 | 0.5463 | 0.5240 |

### Whole-chunk damage, per damaged fraction and file type
| file_type | 100% | 50% | 25% | 10% | 5% |
|---|---|---|---|---|---|
| ALL | 0.9070 | 0.9101 | 0.9041 | 0.9095 | 0.9110 |
| HIGH_ENTROPY | 0.8692 | 0.8762 | 0.8666 | 0.8716 | 0.8766 |
| LOW_ENTROPY | 0.9997 | 0.9997 | 0.9997 | 0.9999 | 0.9998 |
| bin | 0.9989 | 0.9992 | 0.9988 | 0.9997 | 0.9997 |
| csv | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| docx | 0.8886 | 0.9039 | 0.9194 | 0.9199 | 0.9101 |
| jpg | 0.9968 | 0.9957 | 0.9953 | 0.9980 | 0.9978 |
| lzma | 0.5171 | 0.5515 | 0.5094 | 0.5253 | 0.5450 |
| mp3 | 0.9917 | 0.9925 | 0.9919 | 0.9920 | 0.9911 |
| png | 0.8688 | 0.8813 | 0.8542 | 0.8650 | 0.8708 |
| txt | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| zip | 0.9254 | 0.9247 | 0.9263 | 0.9075 | 0.9144 |
| zlib | 0.8899 | 0.9027 | 0.8795 | 0.8979 | 0.9105 |

### File level (file score = max over its changed chunks)
| damage_model | file_type | 100% | 50% | 25% | 10% | 5% |
|---|---|---|---|---|---|---|
| striped | ALL | 0.9441 | 0.9182 | 0.8695 | 0.8047 | 0.7751 |
| striped | HIGH_ENTROPY | 0.9391 | 0.8363 | 0.7422 | 0.6240 | 0.5685 |
| whole | ALL | 0.9454 | 0.9200 | 0.8675 | 0.8116 | 0.7680 |
| whole | HIGH_ENTROPY | 0.9438 | 0.9124 | 0.8335 | 0.7509 | 0.6929 |

### Groups with 95% file-cluster bootstrap CIs, and detection rate at a 1% false-alarm level
| damage_model | fraction | file_type | auroc | ci_low | ci_high | tpr_marginal_a0.01 | tpr_mondrian_a0.01 | fpr_mondrian_a0.01 |
|---|---|---|---|---|---|---|---|---|
| whole | 1.0000 | ALL | 0.9070 | 0.8890 | 0.9247 | 0.1178 | 0.4977 | 0.0073 |
| whole | 0.5000 | ALL | 0.9101 | 0.8928 | 0.9281 | 0.1086 | 0.4848 | 0.0073 |
| whole | 0.2500 | ALL | 0.9041 | 0.8843 | 0.9204 | 0.1047 | 0.4364 | 0.0073 |
| whole | 0.1000 | ALL | 0.9095 | 0.8925 | 0.9284 | 0.1224 | 0.4506 | 0.0073 |
| whole | 0.0500 | ALL | 0.9110 | 0.8953 | 0.9306 | 0.1253 | 0.4450 | 0.0073 |
| whole | 1.0000 | HIGH_ENTROPY | 0.8692 | 0.8453 | 0.8908 | 0.1309 | 0.2897 | 0.0082 |
| whole | 0.5000 | HIGH_ENTROPY | 0.8762 | 0.8535 | 0.8981 | 0.1230 | 0.2876 | 0.0082 |
| whole | 0.2500 | HIGH_ENTROPY | 0.8666 | 0.8396 | 0.8921 | 0.1138 | 0.2620 | 0.0082 |
| whole | 0.1000 | HIGH_ENTROPY | 0.8716 | 0.8499 | 0.8968 | 0.1318 | 0.2870 | 0.0082 |
| whole | 0.0500 | HIGH_ENTROPY | 0.8766 | 0.8496 | 0.9045 | 0.1438 | 0.2742 | 0.0082 |
| whole | 1.0000 | LOW_ENTROPY | 0.9997 | 0.9993 | 0.9999 | 0.0869 | 0.9918 | 0.0051 |
| whole | 0.5000 | LOW_ENTROPY | 0.9997 | 0.9995 | 1.0000 | 0.0714 | 0.9946 | 0.0051 |
| whole | 0.2500 | LOW_ENTROPY | 0.9997 | 0.9992 | 0.9999 | 0.0759 | 0.9873 | 0.0051 |
| whole | 0.1000 | LOW_ENTROPY | 0.9999 | 0.9996 | 1.0000 | 0.0909 | 1.0000 | 0.0051 |
| whole | 0.0500 | LOW_ENTROPY | 0.9998 | 0.9992 | 1.0000 | 0.0652 | 1.0000 | 0.0051 |
| striped | 1.0000 | ALL | 0.9069 | 0.8864 | 0.9208 | 0.1191 | 0.5005 | 0.0073 |
| striped | 0.5000 | ALL | 0.8960 | 0.8744 | 0.9132 | 0.3269 | 0.4547 | 0.0073 |
| striped | 0.2500 | ALL | 0.8543 | 0.8309 | 0.8766 | 0.3087 | 0.4220 | 0.0073 |
| striped | 0.1000 | ALL | 0.7808 | 0.7479 | 0.8074 | 0.2675 | 0.3069 | 0.0073 |
| striped | 0.0500 | ALL | 0.7522 | 0.7167 | 0.7850 | 0.2630 | 0.2832 | 0.0073 |
| striped | 1.0000 | HIGH_ENTROPY | 0.8693 | 0.8462 | 0.8911 | 0.1291 | 0.2932 | 0.0082 |
| striped | 0.5000 | HIGH_ENTROPY | 0.7955 | 0.7676 | 0.8266 | 0.0852 | 0.2251 | 0.0082 |
| striped | 0.2500 | HIGH_ENTROPY | 0.7198 | 0.6920 | 0.7489 | 0.0775 | 0.1821 | 0.0082 |
| striped | 0.1000 | HIGH_ENTROPY | 0.5896 | 0.5725 | 0.6106 | 0.0237 | 0.0443 | 0.0082 |
| striped | 0.0500 | HIGH_ENTROPY | 0.5410 | 0.5324 | 0.5508 | 0.0185 | 0.0198 | 0.0082 |
| striped | 1.0000 | LOW_ENTROPY | 0.9997 | 0.9994 | 0.9999 | 0.0951 | 0.9928 | 0.0051 |
| striped | 0.5000 | LOW_ENTROPY | 1.0000 | 1.0000 | 1.0000 | 0.9008 | 1.0000 | 0.0051 |
| striped | 0.2500 | LOW_ENTROPY | 0.9999 | 0.9997 | 1.0000 | 0.8579 | 0.9918 | 0.0051 |
| striped | 0.1000 | LOW_ENTROPY | 0.9981 | 0.9951 | 0.9995 | 0.8466 | 0.9305 | 0.0051 |
| striped | 0.0500 | LOW_ENTROPY | 0.9963 | 0.9922 | 0.9990 | 0.8436 | 0.9090 | 0.0051 |

### Detection rate (TPR) at Mondrian alpha = 0.01, striped damage, per file type
| file_type | 100% | 50% | 25% | 10% | 5% |
|---|---|---|---|---|---|
| bin | 0.9786 | 1.0000 | 0.9755 | 0.7920 | 0.7278 |
| csv | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| docx | 0.1534 | 0.0383 | 0.0147 | 0.0147 | 0.0029 |
| jpg | 0.9026 | 0.7890 | 0.3994 | 0.0779 | 0.0325 |
| lzma | 0.0352 | 0.0293 | 0.0088 | 0.0029 | 0.0000 |
| mp3 | 0.7126 | 0.6916 | 0.8054 | 0.1916 | 0.0719 |
| png | 0.1254 | 0.0370 | 0.0513 | 0.0199 | 0.0228 |
| txt | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| zip | 0.1180 | 0.0311 | 0.0124 | 0.0031 | 0.0062 |
| zlib | 0.0579 | 0.0091 | 0.0030 | 0.0030 | 0.0030 |

### Conformal false-alarm check on benign test chunks (alpha = 0.01)
| file_type | variant | alpha | empirical_fpr | n_benign |
|---|---|---|---|---|
| ALL | marginal | 0.0100 | 0.0151 | 3301 |
| ALL | mondrian | 0.0100 | 0.0073 | 3301 |
| HIGH_ENTROPY | marginal | 0.0100 | 0.0215 | 2323 |
| HIGH_ENTROPY | mondrian | 0.0100 | 0.0082 | 2323 |
| LOW_ENTROPY | marginal | 0.0100 | 0.0000 | 978 |
| LOW_ENTROPY | mondrian | 0.0100 | 0.0051 | 978 |

**Reading, unsoftened**
- Striped 5% on high-entropy types: **0.5410** (CI 0.5324–0.5508). At 5%: docx 0.5223, png 0.5212,
  zip 0.5254, zlib 0.5240, lzma 0.4817. The detector is near-useless there, and that regime is the
  research question.
- **lzma is at chance under every condition** (0.4817–0.5515), including fully random chunks. With
  these features, xz output is indistinguishable from random bytes.
- Even fully overwritten chunks inside compressed containers are hard to flag. At Mondrian alpha
  0.01, TPR for whole-chunk 100% damage is docx 0.1770, png 0.1140, zip 0.1087, zlib 0.0762, lzma
  0.0352.
- Whole-chunk damage gives a flat chunk-level curve (about 0.91 for ALL), as expected: each damaged
  chunk is fully random whatever the file fraction.
- Marginal conformal **breaks its false-alarm level** on high-entropy types (0.0215 at alpha 0.01).
  Mondrian holds it (0.0082) and is far more sensitive, so it became the default (D1).
- Caveat: train and test come from the same synthetic generators. Real NapierOne data is needed
  before any external claim.

## M2: start-day inference (PROVISIONAL: 8 reps, before the day-0 fix)
Figure: `results/inference/start_accuracy_vs_fraction.png`. Example machines:
`results/inference/example_trace_f{5,10,25}_{all,high_entropy}.png`.
Metric: posterior mass on days within ±3 of the true start, at discovery day +14, hazard 0.02.
The prior-only baseline is 0.1014.

### Mass within ±3 days vs damage fraction (exceedance statistic)
| attack_target_types | statistic | model | 1.0 | 0.5 | 0.25 | 0.1 | 0.05 |
|---|---|---|---|---|---|---|---|
| all | exceed | bocpd | 0.4935 | 0.5106 | 0.4410 | 0.2551 | 0.1207 |
| all | exceed | prior_only | 0.1014 | 0.1014 | 0.1014 | 0.1014 | 0.1014 |
| all | exceed | single_cp | 0.5396 | 0.3828 | 0.3939 | 0.4944 | 0.2638 |
| all | exceed | single_cp_uniform | 0.5872 | 0.4345 | 0.4338 | 0.5202 | 0.3517 |
| high_entropy | exceed | bocpd | 0.5485 | 0.3342 | 0.1209 | 0.0863 | 0.1391 |
| high_entropy | exceed | prior_only | 0.1014 | 0.1014 | 0.1014 | 0.1014 | 0.1014 |
| high_entropy | exceed | single_cp | 0.4903 | 0.3120 | 0.2463 | 0.0622 | 0.0919 |
| high_entropy | exceed | single_cp_uniform | 0.5266 | 0.3583 | 0.3503 | 0.1838 | 0.2412 |

### MAP errors at day +14 (exceedance statistic; MAP = "not started" counts as missed)
| attack_target_types | model | median_map_error | missed_rate | mean_p_started |
|---|---|---|---|---|
| all | bocpd | 1.5000 | 0.3000 | 0.8716 |
| all | prior_only |  | 1.0000 | 0.4654 |
| all | single_cp | 2.0000 | 0.2750 | 0.8628 |
| all | single_cp_uniform | 2.0000 | 0.0750 | 0.9888 |
| high_entropy | bocpd | 4.0000 | 0.5750 | 0.7220 |
| high_entropy | prior_only |  | 1.0000 | 0.4654 |
| high_entropy | single_cp | 4.0000 | 0.6250 | 0.6351 |
| high_entropy | single_cp_uniform | 6.0000 | 0.1250 | 0.9691 |

### Clean (attack-free) machines at day +14
| statistic | model | discovery_delay | prior_p_started | mean_p_started | false_alarm_p05 | false_alarm_p09 | n |
|---|---|---|---|---|---|---|---|
| exceed | bocpd | 14 | 0.4654 | 0.4931 | 0.5000 | 0.0000 | 8 |
| exceed | prior_only | 14 | 0.4654 | 0.4654 | 0.0000 | 0.0000 | 8 |
| exceed | single_cp | 14 | 0.4654 | 0.3031 | 0.2500 | 0.0000 | 8 |
| exceed | single_cp_uniform | 14 | 0.9688 | 0.9183 | 1.0000 | 0.7500 | 8 |
| trimmed_mean | bocpd | 14 | 0.4654 | 0.5179 | 0.5000 | 0.2500 | 8 |
| trimmed_mean | prior_only | 14 | 0.4654 | 0.4654 | 0.0000 | 0.0000 | 8 |
| trimmed_mean | single_cp | 14 | 0.4654 | 0.4374 | 0.2500 | 0.2500 | 8 |
| trimmed_mean | single_cp_uniform | 14 | 0.9688 | 0.9337 | 1.0000 | 0.7500 | 8 |

**Reading, unsoftened**
- The pre-registered rule (D16) chose **single-CP + exceedances** as the default. It has the lowest
  clean false-alarm rate (0.25 vs 0.50 for BOCPD). On the "any type" target set its
  fraction-averaged mass within ±3 is 0.4149 vs 0.3642 for BOCPD, a gap within about 1 s.e. So it
  does not lose, but a win is not shown.
- Even when the damage is visible, start recovery is moderate: 0.2638–0.5396 mass within ±3 on
  "any type".
- **Hard regime: failure.** On high-entropy targets at 5% and 10%, the start is missed on 8 of 8
  machines, with mass 0.0919 and 0.0622, *below* the prior-only 0.1014.
- **Errors are late**, almost never early (details in `results/CHANGELOG.md`). For retention that
  is the dangerous direction, so M3 must hedge toward older snapshots.
- The trimmed-mean statistic carries little information: it stays close to the prior baseline.
- On clean machines, single-CP lowers P(started) below the prior on average, but 2 of 8 still
  exceed 0.5 at hazard 0.02 (0 of 8 at hazard 0.005). The placeholder hazard looks too aggressive;
  that's a team decision.

## What failed or was not done
1. **The M2 16-rep re-run was stopped for low memory.** Claude Code stopped it at run 77/176 while
   the session was idle; its instructions say not to restart it, so I didn't. To re-run:
   `uv run slowburn inference configs/inference.yaml`. Partial results are now saved after every
   machine, so an interrupted run keeps its progress.
2. As a result, the M2 numbers come from the 8-rep run made **before** day 0 (the initial full
   backup, n ≈ 840 chunks) was excluded from the benign-model fit. How much that changes the
   numbers is unknown until the re-run.
3. Bugs found and fixed overnight, all with regression tests:
   - non-reproducible zip/docx bytes (zipfile wall-clock timestamps);
   - seed-key collisions for long string keys;
   - plug-in benign parameters causing false alarms on clean series;
   - overdispersion that can't be estimated from 14 warm-up days;
   - a stale hard-coded delay in the summary;
   - object-dtype columns silently dropped from aggregates.
4. Not done:
   - NapierOne benign loading (layout unknown; the damage-source loader exists but is tested only
     on a fake directory);
   - the stripe-length sweep;
   - a file-level daily statistic;
   - features beyond the spec.

   The retention `bench` still uses keep-last-N only, since M3 was not started, as instructed.

## Decisions I made for you
Full text is in `OPEN_QUESTIONS.md` (D1–D16). Short list:
- D1 Mondrian conformal (per declared file type) is the default p-value.
- D2 AUROC on raw scores. D3 isotonic calibrated under a 50/50 prior. D4 file score = max chunk score.
- D5 dataset shape: 150 files/type, 16–128 KiB, 4 KiB chunks, at most 12 chunks per file, 16-byte stripes.
- D6 NapierOne benign loading deferred until the layout is known.
- D7 no features beyond the spec.
- D8 14-day clean warm-up, with day 0 excluded from the fit. D9 the benign rate is estimated, not
  assumed equal to alpha.
- D10 uncertainty grids for the benign parameters. D11 intermittent-attack mixture likelihood,
  upward effects only.
- D12 BOCPD reads the most recent changepoint as the start. D13 hazard 0.02 primary (placeholder),
  0.005 as sensitivity.
- D14 attacker: 0.5 files/day, striped damage, "any type" vs "high-entropy only" targets. D15
  scenarios are in-distribution for the detector.
- D16 default-model rule → single-CP + exceedances (provisional).

## Needs you
- Choose a defensible start hazard (D13); it dominates how clean machines behave.
- Decide how M3 should handle the late bias: shift the posterior earlier, or keep extra old snapshots.
- NapierOne download and layout; the AMOEBA PDF into `docs/`; venue and format.
- Re-run M2 when memory allows.
