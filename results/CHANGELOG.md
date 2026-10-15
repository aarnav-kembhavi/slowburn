# Results changelog

Numbers here are copied from generated CSVs at the stated commit/config; nothing is hand-entered.

## M0 — scaffold (2026-10-07)

**Works**
- `uv run slowburn bench configs/smoke.yaml` runs end to end (simulate -> features -> placeholder
  detector -> trimmed-mean daily statistic -> placeholder posterior -> keep-last-N -> metrics),
  ~11 s wall clock, writes `results/smoke/results.csv` (12 rows) and `recovery_vs_fraction.png`.
- 49 unit tests pass; ruff clean.
- Synthetic benign generators for txt, csv, bin, docx, zip, png, jpg, mp3, zlib, lzma (real
  encoders on synthetic source material). Damage models `whole` and `striped`, seeded.

**Numbers (smoke, synthetic only: benign_source=synthetic, damage_source=synthetic_random)**
- keep-last-N with N=7: clean recovery 1.0 at discovery delay 3 days, 0.0 at 14 days, at every
  damage fraction (2 reps each). This is the expected failure of fixed retention: it only depends
  on delay > N, not on the detector.
- Runtime per backup ~2 ms (16 files, 8–32 KiB each).

**Placeholders (not results)**
- Detector = entropy/8; start-day posterior = crude mean-shift score. The posterior's argmax is
  the "not started" entry in every smoke run, so the start-estimate error column is meaningless
  until M2.

## M1 - detector (2026-10-07)

Config `configs/detector.yaml` (seed 11). **All data synthetic**: benign_source=synthetic,
damage_source=synthetic_random. 1500 files (150 per type, 10 types), 142875 labelled
chunks, 28521 test chunks. Split 60/20/20 train/calib/test **by file**, stratified by type.
Dataset build 83.642 s, LightGBM train + calibration 6.509 s, scoring
12.25 us/chunk (features excluded).

**Works**: `features()` (260-d), LightGBM, isotonic probabilities (balanced prior), marginal and
Mondrian (per file type) split-conformal p-values, AUROC sweep over 2 damage models x 5 fractions x
file types with 95% file-cluster bootstrap CIs, TPR/FPR at conformal alpha, file-level AUROC.
Figures: `results/detector/auroc_vs_fraction.png` (Phase I headline), `results/detector/auroc_by_type.png`.

### Chunk-level AUROC, striped damage (headline)
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

### Chunk-level AUROC, whole-chunk damage
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

### File-level AUROC (file score = max changed-chunk score)
| damage_model | file_type | 100% | 50% | 25% | 10% | 5% |
|---|---|---|---|---|---|---|
| striped | ALL | 0.9441 | 0.9182 | 0.8695 | 0.8047 | 0.7751 |
| striped | HIGH_ENTROPY | 0.9391 | 0.8363 | 0.7422 | 0.6240 | 0.5685 |
| whole | ALL | 0.9454 | 0.9200 | 0.8675 | 0.8116 | 0.7680 |
| whole | HIGH_ENTROPY | 0.9438 | 0.9124 | 0.8335 | 0.7509 | 0.6929 |

### Conformal false-alarm check on benign test chunks
| file_type | variant | alpha | empirical_fpr | n_benign |
|---|---|---|---|---|
| ALL | marginal | 0.0100 | 0.0151 | 3301 |
| ALL | marginal | 0.0500 | 0.0451 | 3301 |
| ALL | marginal | 0.1000 | 0.1030 | 3301 |
| ALL | mondrian | 0.0100 | 0.0073 | 3301 |
| ALL | mondrian | 0.0500 | 0.0494 | 3301 |
| ALL | mondrian | 0.1000 | 0.1072 | 3301 |
| HIGH_ENTROPY | marginal | 0.0100 | 0.0215 | 2323 |
| HIGH_ENTROPY | marginal | 0.0500 | 0.0641 | 2323 |
| HIGH_ENTROPY | marginal | 0.1000 | 0.1464 | 2323 |
| HIGH_ENTROPY | mondrian | 0.0100 | 0.0082 | 2323 |
| HIGH_ENTROPY | mondrian | 0.0500 | 0.0538 | 2323 |
| HIGH_ENTROPY | mondrian | 0.1000 | 0.1076 | 2323 |
| LOW_ENTROPY | marginal | 0.0100 | 0.0000 | 978 |
| LOW_ENTROPY | marginal | 0.0500 | 0.0000 | 978 |
| LOW_ENTROPY | marginal | 0.1000 | 0.0000 | 978 |
| LOW_ENTROPY | mondrian | 0.0100 | 0.0051 | 978 |
| LOW_ENTROPY | mondrian | 0.0500 | 0.0389 | 978 |
| LOW_ENTROPY | mondrian | 0.1000 | 0.1063 | 978 |

**Honest reading**
- Striped damage at 5% on high-entropy types: AUROC 0.5410 (CI 0.5324-0.5508), essentially chance.
  docx/png/zip/zlib are 0.52-0.53 at 5%. lzma is at chance (0.48-0.55) at **every** fraction and
  under both models, including fully random chunks: xz output is indistinguishable from random bytes
  with byte-histogram features. This is the regime the retention layer must handle via the prior.
- Whole-chunk damage gives a flat chunk-level curve (~0.91 ALL, ~0.87 high-entropy) because each
  damaged chunk is fully random regardless of the file fraction; the fraction only matters at file
  level. As predicted, (b) striped is the informative model.
- Marginal conformal is not valid per type: high-entropy benign FPR 0.0215 at alpha 0.01. Mondrian
  conformal fixes this (0.0082) and raises TPR (striped 100% ALL: 0.1191 -> 0.5005 at alpha 0.01),
  because a pooled threshold is set by lzma benign chunks that look random.
- Even with Mondrian, TPR at alpha 0.01 for fully random whole chunks (whole, 100%) is low for
  compressed containers: docx 0.1770, png 0.1140, zip 0.1087, zlib 0.0762, lzma 0.0352 (jpg 0.9026,
  mp3 0.6677). Compressed-container chunks are hard negatives even at 100% damage.
- Caveat: train and test share the same synthetic generators; real NapierOne data is needed before
  any external-validity claim.


## M2 - daily statistic + changepoint inference (2026-10-07/08)

**Provenance warning.** The numbers below come from the first full run of `configs/inference.yaml`
with **8 reps** (+8 clean machines), produced *before* two later changes: (1) day 0 (the initial
full backup) was excluded from the benign-model fit, and (2) reps were raised to 16. The re-run
with both changes was **stopped by Claude Code at run 77/176 because the machine was low on
memory** and produced no output. Treat these numbers as provisional; re-run with
`uv run slowburn inference configs/inference.yaml` (~25-30 min; partial results are now saved
after every machine to `results/inference/inference_results.partial.csv`).

All data synthetic (benign_source=synthetic, damage_source=synthetic_random); detector from M1.
Scenario: 40 files, 10 types, 4 benign edits/day with weekend dip, striped damage, attack starts
day 30, 0.5 newly damaged files/day, warm-up 14 days, Mondrian conformal alpha 0.05.
"Mass within +-3" = posterior probability on start days within 3 days of the truth (higher is
better; the timing prior alone gives 0.1014 at h = 0.02).

**Works**: pluggable daily aggregators (exceedance count, trimmed mean, mean, frac_above), Beta-Binomial
exceedance model and weekday Gaussian model with benign-parameter uncertainty, exact single-changepoint
posterior (brute-force tested, incl. null grid), BOCPD (brute-force tested against enumeration of all
segmentations), ablations "suspicion only" (uniform prior) and "prior only" (no data), experiment
runner, figures `results/inference/start_accuracy_vs_fraction.png` and
`results/inference/example_trace_f{5,10,25}_{all,high_entropy}.png`.

**Default model (decision D16): single-CP + exceedance statistic.** Lowest clean false-alarm rate among the
data-driven models; on the "any type" target set its fraction-averaged mass within +-3 is 0.4149 vs 0.3642
for BOCPD, a difference within ~1 s.e. (provisional, 8 reps).
### D16 comparison: mean posterior mass within +-3 days, averaged over the 5 fractions (delay 14, h=0.02)
| attack_target_types | statistic | model | mean_mass3_over_fractions | sem | n |
|---|---|---|---|---|---|
| all | exceed | bocpd | 0.3642 | 0.0464 | 40 |
| all | exceed | prior_only | 0.1014 | 0.0000 | 40 |
| all | exceed | single_cp | 0.4149 | 0.0372 | 40 |
| all | exceed | single_cp_uniform | 0.4655 | 0.0358 | 40 |
| all | trimmed_mean | bocpd | 0.1039 | 0.0204 | 40 |
| all | trimmed_mean | prior_only | 0.1014 | 0.0000 | 40 |
| all | trimmed_mean | single_cp | 0.1194 | 0.0220 | 40 |
| all | trimmed_mean | single_cp_uniform | 0.2021 | 0.0239 | 40 |
| high_entropy | exceed | bocpd | 0.2458 | 0.0472 | 40 |
| high_entropy | exceed | prior_only | 0.1014 | 0.0000 | 40 |
| high_entropy | exceed | single_cp | 0.2406 | 0.0387 | 40 |
| high_entropy | exceed | single_cp_uniform | 0.3320 | 0.0348 | 40 |
| high_entropy | trimmed_mean | bocpd | 0.1346 | 0.0280 | 40 |
| high_entropy | trimmed_mean | prior_only | 0.1014 | 0.0000 | 40 |
| high_entropy | trimmed_mean | single_cp | 0.1189 | 0.0250 | 40 |
| high_entropy | trimmed_mean | single_cp_uniform | 0.1943 | 0.0284 | 40 |

### Mass within +-3 days of true start vs damage fraction (delay 14, h=0.02)
| attack_target_types | statistic | model | 1.0 | 0.5 | 0.25 | 0.1 | 0.05 |
|---|---|---|---|---|---|---|---|
| all | exceed | bocpd | 0.4935 | 0.5106 | 0.4410 | 0.2551 | 0.1207 |
| all | exceed | prior_only | 0.1014 | 0.1014 | 0.1014 | 0.1014 | 0.1014 |
| all | exceed | single_cp | 0.5396 | 0.3828 | 0.3939 | 0.4944 | 0.2638 |
| all | exceed | single_cp_uniform | 0.5872 | 0.4345 | 0.4338 | 0.5202 | 0.3517 |
| all | trimmed_mean | bocpd | 0.1605 | 0.0605 | 0.1610 | 0.0875 | 0.0499 |
| all | trimmed_mean | prior_only | 0.1014 | 0.1014 | 0.1014 | 0.1014 | 0.1014 |
| all | trimmed_mean | single_cp | 0.1580 | 0.1393 | 0.1721 | 0.0947 | 0.0333 |
| all | trimmed_mean | single_cp_uniform | 0.2334 | 0.2385 | 0.2944 | 0.1792 | 0.0650 |
| high_entropy | exceed | bocpd | 0.5485 | 0.3342 | 0.1209 | 0.0863 | 0.1391 |
| high_entropy | exceed | prior_only | 0.1014 | 0.1014 | 0.1014 | 0.1014 | 0.1014 |
| high_entropy | exceed | single_cp | 0.4903 | 0.3120 | 0.2463 | 0.0622 | 0.0919 |
| high_entropy | exceed | single_cp_uniform | 0.5266 | 0.3583 | 0.3503 | 0.1838 | 0.2412 |
| high_entropy | trimmed_mean | bocpd | 0.2128 | 0.0937 | 0.1696 | 0.0476 | 0.1492 |
| high_entropy | trimmed_mean | prior_only | 0.1014 | 0.1014 | 0.1014 | 0.1014 | 0.1014 |
| high_entropy | trimmed_mean | single_cp | 0.2132 | 0.1363 | 0.0861 | 0.0289 | 0.1298 |
| high_entropy | trimmed_mean | single_cp_uniform | 0.2638 | 0.2102 | 0.2092 | 0.0885 | 0.1998 |

### Mass within +-3 days vs discovery delay (fraction 10%, h=0.02)
| attack_target_types | statistic | model | 3 | 7 | 14 | 21 | 30 |
|---|---|---|---|---|---|---|---|
| all | exceed | bocpd | 0.3210 | 0.2862 | 0.2551 | 0.2106 | 0.3403 |
| all | exceed | prior_only | 0.1014 | 0.1014 | 0.1014 | 0.1014 | 0.1014 |
| all | exceed | single_cp | 0.3845 | 0.3638 | 0.4944 | 0.4976 | 0.4836 |
| all | exceed | single_cp_uniform | 0.5251 | 0.4365 | 0.5202 | 0.5152 | 0.4957 |
| all | trimmed_mean | bocpd | 0.1597 | 0.0877 | 0.0875 | 0.0762 | 0.0758 |
| all | trimmed_mean | prior_only | 0.1014 | 0.1014 | 0.1014 | 0.1014 | 0.1014 |
| all | trimmed_mean | single_cp | 0.1197 | 0.0692 | 0.0947 | 0.1126 | 0.1236 |
| all | trimmed_mean | single_cp_uniform | 0.3214 | 0.2234 | 0.1792 | 0.1622 | 0.1523 |
| high_entropy | exceed | bocpd | 0.1488 | 0.1064 | 0.0863 | 0.0699 | 0.0590 |
| high_entropy | exceed | prior_only | 0.1014 | 0.1014 | 0.1014 | 0.1014 | 0.1014 |
| high_entropy | exceed | single_cp | 0.0907 | 0.0600 | 0.0622 | 0.0694 | 0.0798 |
| high_entropy | exceed | single_cp_uniform | 0.4190 | 0.2736 | 0.1838 | 0.1393 | 0.1354 |
| high_entropy | trimmed_mean | bocpd | 0.1296 | 0.0836 | 0.0476 | 0.0347 | 0.0263 |
| high_entropy | trimmed_mean | prior_only | 0.1014 | 0.1014 | 0.1014 | 0.1014 | 0.1014 |
| high_entropy | trimmed_mean | single_cp | 0.0386 | 0.0303 | 0.0289 | 0.0223 | 0.0242 |
| high_entropy | trimmed_mean | single_cp_uniform | 0.2032 | 0.1259 | 0.0885 | 0.0702 | 0.0585 |

### MAP errors (delay 14, h=0.02; MAP = 'not started' counts as missed)
| attack_target_types | statistic | model | median_map_error | missed_rate | mean_p_started | mean_expected_abs_error |
|---|---|---|---|---|---|---|
| all | exceed | bocpd | 1.5000 | 0.3000 | 0.8716 | 6.1255 |
| all | exceed | prior_only |  | 1.0000 | 0.4654 | 7.9914 |
| all | exceed | single_cp | 2.0000 | 0.2750 | 0.8628 | 5.3110 |
| all | exceed | single_cp_uniform | 2.0000 | 0.0750 | 0.9888 | 5.1544 |
| all | trimmed_mean | bocpd | 13.0000 | 0.6750 | 0.5780 | 9.4381 |
| all | trimmed_mean | prior_only |  | 1.0000 | 0.4654 | 7.9914 |
| all | trimmed_mean | single_cp | 10.5000 | 0.6000 | 0.6205 | 8.7069 |
| all | trimmed_mean | single_cp_uniform | 11.0000 | 0.2250 | 0.9574 | 8.5818 |
| high_entropy | exceed | bocpd | 4.0000 | 0.5750 | 0.7220 | 7.0744 |
| high_entropy | exceed | prior_only |  | 1.0000 | 0.4654 | 7.9914 |
| high_entropy | exceed | single_cp | 4.0000 | 0.6250 | 0.6351 | 6.5016 |
| high_entropy | exceed | single_cp_uniform | 6.0000 | 0.1250 | 0.9691 | 6.3823 |
| high_entropy | trimmed_mean | bocpd | 10.5000 | 0.7000 | 0.5793 | 9.3176 |
| high_entropy | trimmed_mean | prior_only |  | 1.0000 | 0.4654 | 7.9914 |
| high_entropy | trimmed_mean | single_cp | 15.0000 | 0.5250 | 0.6408 | 9.6978 |
| high_entropy | trimmed_mean | single_cp_uniform | 12.5000 | 0.2500 | 0.9551 | 9.5047 |

### Signed MAP error, single-CP + exceedances (positive = estimate later than truth)
| attack_target_types | damage_fraction | median_signed_error | late_gt3 | early_gt3 | missed |
|---|---|---|---|---|---|
| all | 0.0500 | 1.0000 | 0.1250 | 0.0000 | 0.6250 |
| all | 0.1000 | 3.0000 | 0.3750 | 0.0000 | 0.1250 |
| all | 0.2500 | 2.0000 | 0.2500 | 0.0000 | 0.2500 |
| all | 0.5000 | 0.5000 | 0.2500 | 0.0000 | 0.2500 |
| all | 1.0000 | 2.0000 | 0.3750 | 0.0000 | 0.1250 |
| high_entropy | 0.0500 |  | 0.0000 | 0.0000 | 1.0000 |
| high_entropy | 0.1000 |  | 0.0000 | 0.0000 | 1.0000 |
| high_entropy | 0.2500 | 5.0000 | 0.3750 | 0.0000 | 0.5000 |
| high_entropy | 0.5000 | 5.5000 | 0.3750 | 0.0000 | 0.5000 |
| high_entropy | 1.0000 | 1.0000 | 0.1250 | 0.1250 | 0.1250 |

### Clean (attack-free) machines, h=0.02
| statistic | model | discovery_delay | prior_p_started | mean_p_started | false_alarm_p05 | false_alarm_p09 | n |
|---|---|---|---|---|---|---|---|
| exceed | bocpd | 3 | 0.3324 | 0.3603 | 0.1250 | 0.0000 | 8 |
| exceed | bocpd | 14 | 0.4654 | 0.4931 | 0.5000 | 0.0000 | 8 |
| exceed | bocpd | 30 | 0.6131 | 0.6317 | 1.0000 | 0.0000 | 8 |
| exceed | prior_only | 3 | 0.3324 | 0.3324 | 0.0000 | 0.0000 | 8 |
| exceed | prior_only | 14 | 0.4654 | 0.4654 | 0.0000 | 0.0000 | 8 |
| exceed | prior_only | 30 | 0.6131 | 0.6131 | 1.0000 | 0.0000 | 8 |
| exceed | single_cp | 3 | 0.3324 | 0.2818 | 0.2500 | 0.0000 | 8 |
| exceed | single_cp | 14 | 0.4654 | 0.3031 | 0.2500 | 0.0000 | 8 |
| exceed | single_cp | 30 | 0.6131 | 0.4034 | 0.2500 | 0.0000 | 8 |
| exceed | single_cp_uniform | 3 | 0.9524 | 0.9102 | 1.0000 | 0.6250 | 8 |
| exceed | single_cp_uniform | 14 | 0.9688 | 0.9183 | 1.0000 | 0.7500 | 8 |
| exceed | single_cp_uniform | 30 | 0.9792 | 0.9380 | 1.0000 | 0.8750 | 8 |
| trimmed_mean | bocpd | 3 | 0.3324 | 0.4475 | 0.2500 | 0.2500 | 8 |
| trimmed_mean | bocpd | 14 | 0.4654 | 0.5179 | 0.5000 | 0.2500 | 8 |
| trimmed_mean | bocpd | 30 | 0.6131 | 0.5746 | 0.5000 | 0.2500 | 8 |
| trimmed_mean | prior_only | 3 | 0.3324 | 0.3324 | 0.0000 | 0.0000 | 8 |
| trimmed_mean | prior_only | 14 | 0.4654 | 0.4654 | 0.0000 | 0.0000 | 8 |
| trimmed_mean | prior_only | 30 | 0.6131 | 0.6131 | 1.0000 | 0.0000 | 8 |
| trimmed_mean | single_cp | 3 | 0.3324 | 0.3702 | 0.2500 | 0.2500 | 8 |
| trimmed_mean | single_cp | 14 | 0.4654 | 0.4374 | 0.2500 | 0.2500 | 8 |
| trimmed_mean | single_cp | 30 | 0.6131 | 0.5190 | 0.5000 | 0.3750 | 8 |
| trimmed_mean | single_cp_uniform | 3 | 0.9524 | 0.9074 | 1.0000 | 0.5000 | 8 |
| trimmed_mean | single_cp_uniform | 14 | 0.9688 | 0.9337 | 1.0000 | 0.7500 | 8 |
| trimmed_mean | single_cp_uniform | 30 | 0.9792 | 0.9098 | 1.0000 | 0.5000 | 8 |

### Sensitivity: clean machines at hazard 0.005, delay 14
| statistic | model | prior_p_started | mean_p_started | false_alarm_p05 |
|---|---|---|---|---|
| exceed | bocpd | 0.1439 | 0.1698 | 0.0000 |
| exceed | prior_only | 0.1439 | 0.1439 | 0.0000 |
| exceed | single_cp | 0.1439 | 0.0877 | 0.0000 |
| exceed | single_cp_uniform | 0.9688 | 0.9183 | 1.0000 |
| trimmed_mean | bocpd | 0.1439 | 0.3176 | 0.2500 |
| trimmed_mean | prior_only | 0.1439 | 0.1439 | 0.0000 |
| trimmed_mean | single_cp | 0.1439 | 0.2979 | 0.2500 |
| trimmed_mean | single_cp_uniform | 0.9688 | 0.9337 | 1.0000 |

### Sensitivity: mass within +-3 days at hazard 0.005, exceedances, delay 14
| attack_target_types | model | 1.0 | 0.5 | 0.25 | 0.1 | 0.05 |
|---|---|---|---|---|---|---|
| all | bocpd | 0.5799 | 0.5592 | 0.4101 | 0.2551 | 0.0964 |
| all | prior_only | 0.0323 | 0.0323 | 0.0323 | 0.0323 | 0.0323 |
| all | single_cp | 0.5104 | 0.3141 | 0.3571 | 0.4876 | 0.1985 |
| all | single_cp_uniform | 0.5872 | 0.4345 | 0.4338 | 0.5202 | 0.3517 |
| high_entropy | bocpd | 0.5591 | 0.3101 | 0.1177 | 0.0254 | 0.0443 |
| high_entropy | prior_only | 0.0323 | 0.0323 | 0.0323 | 0.0323 | 0.0323 |
| high_entropy | single_cp | 0.4762 | 0.2727 | 0.1757 | 0.0178 | 0.0326 |
| high_entropy | single_cp_uniform | 0.5266 | 0.3583 | 0.3503 | 0.1838 | 0.2412 |

runtime: inference_ms median 6.81 max 276.98 ; score_ms_per_day median 6.41

**Honest reading**
- The exceedance statistic beats the trimmed mean in 18 of 20 (model x target x fraction) cells; the two
  exceptions are high-entropy 5%, where both are near the prior. The trimmed mean stays close to
  the prior-only baseline (single-CP/BOCPD cells range 0.0289-0.2132 vs 0.1014; above it in 11 of 20
  cells, below in 9), i.e. it carries little information.
- Start recovery is moderate even when the detector sees the damage: single-CP + exceedances puts
  0.2638-0.5396 mass within +-3 days on the "any type" target set, with 12.5-62.5% of machines missed
  (MAP = not started) at day +14.
- **Hard regime fails.** High-entropy targets at 5% and 10% damage: single-CP + exceedances is missed on 8/8
  machines and its mass within +-3 (0.0919, 0.0622) is *below* the prior-only 0.1014. The detector evidence
  adds nothing there, as M1 predicted; the retention layer will have to rely on the prior.
- **Errors are late, not early.** When the start is found, the MAP is later than the truth (median +0.5 to
  +5.5 days; 12.5-37.5% of machines more than 3 days late; more than 3 days early in only one cell,
  high-entropy 100%, 1/8 machines). The first
  damaged files are often undetectable types. For retention this is the dangerous direction; M3 must
  hedge toward earlier snapshots.
- **Benign daily exceedances are very bursty** (example trace: up to 0.33 vs a mean of ~0.043). One rewrite
  of a compressed file contributes 10-20 correlated chunks. A file-level statistic (files with flagged
  chunks / files changed) would match the model's independence assumptions better. Not done; listed as next step.
- **Clean machines**: single-CP + exceedances lowers P(started) below the prior on average (0.3031 vs prior
  0.4654 at day +14) but 2/8 clean machines still exceed 0.5. BOCPD stays at the prior (it cannot argue
  *against* a change). At hazard 0.005 single-CP has 0/8 clean false alarms with similar attack recovery
  on the "any type" set, so the placeholder hazard 0.02 looks too aggressive (team decision D13).
- The "suspicion only" ablation has the highest mass within +-3 only because its flat prior almost never
  says "not started": it flags 8/8 clean machines. The timing prior is what keeps false alarms down.
- Runtime: inference median 6.81 ms per posterior (max 276.98 ms), scoring median 6.41 ms per machine-day.

## Workstream A - fixes to M1/M2 (2026-10-08)

All data synthetic (benign_source=synthetic, damage_source=synthetic_random). No pooled AUROC is
reported any more: per-type AUROC plus weighted averages (`WAVG_*`, uniform type weights,
decision D17) with stratified file-cluster bootstrap CIs.

**A1, encoders (confirmed by tests, not assertion).** `tests/test_validity.py` decodes every
generated type with a real decoder: Pillow full pixel decode (png, jpg), `zipfile.testzip` with
deflate members (zip, docx; docx is built with `zipfile`, not python-docx), zlib/lzma
decompression, and an MPEG frame-chain walk (mp3, LAME). No type is random bytes plus a header.

**A2.** Both detector figures were regenerated by this re-run (needed anyway for A3).

**A3, whole-file format validity** (`slowburn/detector/validity.py`; zip/docx CRC-32, png chunk
CRCs + IDAT inflate, jpg marker/entropy-stream structure, mp3 frame chain, zlib Adler-32, xz
check, strict UTF-8 for txt/csv; `bin` has no check). M1 re-run: 1500 files,
142875 chunks, 28521 test chunks, seed 11.

### Share of file versions flagged invalid (test files)
| file_type | none 0% | striped 5% | striped 10% | striped 25% | striped 50% | striped 100% | whole 5% | whole 10% | whole 25% | whole 50% | whole 100% |
|---|---|---|---|---|---|---|---|---|---|---|---|
| csv | 0.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| docx | 0.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| jpg | 0.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| lzma | 0.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| mp3 | 0.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| png | 0.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| txt | 0.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| zip | 0.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| zlib | 0.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |

### Chunk AUROC, striped damage: LightGBM base (no validity)
| file_type | 100% | 50% | 25% | 10% | 5% |
|---|---|---|---|---|---|
| WAVG_ALL | 0.9112 | 0.8563 | 0.7980 | 0.7242 | 0.6861 |
| WAVG_HIGH_ENTROPY | 0.8732 | 0.7946 | 0.7116 | 0.6085 | 0.5563 |
| WAVG_LOW_ENTROPY | 0.9997 | 1.0000 | 0.9997 | 0.9943 | 0.9889 |
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

### Chunk AUROC, striped damage: LightGBM + format validity
| file_type | 100% | 50% | 25% | 10% | 5% |
|---|---|---|---|---|---|
| WAVG_ALL | 1.0000 | 1.0000 | 1.0000 | 0.9995 | 0.9976 |
| WAVG_HIGH_ENTROPY | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| WAVG_LOW_ENTROPY | 1.0000 | 1.0000 | 1.0000 | 0.9983 | 0.9921 |
| bin | 1.0000 | 1.0000 | 1.0000 | 0.9949 | 0.9762 |
| csv | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| docx | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| jpg | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| lzma | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| mp3 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| png | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| txt | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| zip | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| zlib | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |

### Chunk AUROC, striped damage: format validity alone (rule)
| file_type | 100% | 50% | 25% | 10% | 5% |
|---|---|---|---|---|---|
| WAVG_ALL | 0.9500 | 0.9500 | 0.9500 | 0.9500 | 0.9500 |
| WAVG_HIGH_ENTROPY | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| WAVG_LOW_ENTROPY | 0.8333 | 0.8333 | 0.8333 | 0.8333 | 0.8333 |
| bin | 0.5000 | 0.5000 | 0.5000 | 0.5000 | 0.5000 |
| csv | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| docx | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| jpg | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| lzma | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| mp3 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| png | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| txt | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| zip | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| zlib | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |

### Chunk AUROC, whole-chunk damage: LightGBM base
| file_type | 100% | 50% | 25% | 10% | 5% |
|---|---|---|---|---|---|
| WAVG_ALL | 0.9077 | 0.9151 | 0.9075 | 0.9105 | 0.9139 |
| WAVG_HIGH_ENTROPY | 0.8683 | 0.8789 | 0.8680 | 0.8722 | 0.8771 |
| WAVG_LOW_ENTROPY | 0.9996 | 0.9997 | 0.9996 | 0.9999 | 0.9999 |
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

### Chunk AUROC, whole-chunk damage: LightGBM + format validity
| file_type | 100% | 50% | 25% | 10% | 5% |
|---|---|---|---|---|---|
| WAVG_ALL | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| WAVG_HIGH_ENTROPY | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| WAVG_LOW_ENTROPY | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| bin | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| csv | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| docx | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| jpg | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| lzma | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| mp3 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| png | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| txt | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| zip | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| zlib | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |

### Chunk AUROC, whole-chunk damage: format validity alone
| file_type | 100% | 50% | 25% | 10% | 5% |
|---|---|---|---|---|---|
| WAVG_ALL | 0.9500 | 0.9500 | 0.9500 | 0.9500 | 0.9500 |
| WAVG_HIGH_ENTROPY | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| WAVG_LOW_ENTROPY | 0.8333 | 0.8333 | 0.8333 | 0.8333 | 0.8333 |
| bin | 0.5000 | 0.5000 | 0.5000 | 0.5000 | 0.5000 |
| csv | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| docx | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| jpg | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| lzma | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| mp3 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| png | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| txt | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| zip | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| zlib | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |

### File-level AUROC, weighted averages
| detector | damage_model | file_type | 100% | 50% | 25% | 10% | 5% |
|---|---|---|---|---|---|---|---|
| lgbm_base | striped | WAVG_ALL | 0.9584 | 0.8982 | 0.8318 | 0.7459 | 0.7028 |
| lgbm_base | striped | WAVG_HIGH_ENTROPY | 0.9406 | 0.8546 | 0.7597 | 0.6370 | 0.5757 |
| lgbm_base | striped | WAVG_LOW_ENTROPY | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 0.9993 |
| lgbm_base | whole | WAVG_ALL | 0.9498 | 0.9419 | 0.8831 | 0.8297 | 0.7741 |
| lgbm_base | whole | WAVG_HIGH_ENTROPY | 0.9283 | 0.9170 | 0.8337 | 0.7567 | 0.6777 |
| lgbm_base | whole | WAVG_LOW_ENTROPY | 1.0000 | 1.0000 | 0.9985 | 1.0000 | 0.9989 |
| lgbm_validity | striped | WAVG_ALL | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 0.9998 |
| lgbm_validity | striped | WAVG_HIGH_ENTROPY | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| lgbm_validity | striped | WAVG_LOW_ENTROPY | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 0.9993 |
| lgbm_validity | whole | WAVG_ALL | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| lgbm_validity | whole | WAVG_HIGH_ENTROPY | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| lgbm_validity | whole | WAVG_LOW_ENTROPY | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| validity_rule | striped | WAVG_ALL | 0.9500 | 0.9500 | 0.9500 | 0.9500 | 0.9500 |
| validity_rule | striped | WAVG_HIGH_ENTROPY | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| validity_rule | striped | WAVG_LOW_ENTROPY | 0.8333 | 0.8333 | 0.8333 | 0.8333 | 0.8333 |
| validity_rule | whole | WAVG_ALL | 0.9500 | 0.9500 | 0.9500 | 0.9500 | 0.9500 |
| validity_rule | whole | WAVG_HIGH_ENTROPY | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| validity_rule | whole | WAVG_LOW_ENTROPY | 0.8333 | 0.8333 | 0.8333 | 0.8333 | 0.8333 |

### Type-conditional conformal false-alarm check (benign test chunks, weighted averages)
| file_type | variant | alpha | empirical_fpr | n_benign | detector |
|---|---|---|---|---|---|
| WAVG_ALL | type_conditional | 0.0100 | 0.0072 | 3301 | lgbm_base |
| WAVG_HIGH_ENTROPY | type_conditional | 0.0100 | 0.0081 | 2323 | lgbm_base |
| WAVG_LOW_ENTROPY | type_conditional | 0.0100 | 0.0051 | 978 | lgbm_base |
| WAVG_ALL | type_conditional | 0.0500 | 0.0494 | 3301 | lgbm_base |
| WAVG_HIGH_ENTROPY | type_conditional | 0.0500 | 0.0539 | 2323 | lgbm_base |
| WAVG_LOW_ENTROPY | type_conditional | 0.0500 | 0.0388 | 978 | lgbm_base |
| WAVG_ALL | type_conditional | 0.1000 | 0.1073 | 3301 | lgbm_base |
| WAVG_HIGH_ENTROPY | type_conditional | 0.1000 | 0.1077 | 2323 | lgbm_base |
| WAVG_LOW_ENTROPY | type_conditional | 0.1000 | 0.1063 | 978 | lgbm_base |
| WAVG_ALL | type_conditional | 0.0100 | 0.0082 | 3301 | lgbm_validity |
| WAVG_HIGH_ENTROPY | type_conditional | 0.0100 | 0.0091 | 2323 | lgbm_validity |
| WAVG_LOW_ENTROPY | type_conditional | 0.0100 | 0.0062 | 978 | lgbm_validity |
| WAVG_ALL | type_conditional | 0.0500 | 0.0467 | 3301 | lgbm_validity |
| WAVG_HIGH_ENTROPY | type_conditional | 0.0500 | 0.0510 | 2323 | lgbm_validity |
| WAVG_LOW_ENTROPY | type_conditional | 0.0500 | 0.0368 | 978 | lgbm_validity |
| WAVG_ALL | type_conditional | 0.1000 | 0.0912 | 3301 | lgbm_validity |
| WAVG_HIGH_ENTROPY | type_conditional | 0.1000 | 0.0981 | 2323 | lgbm_validity |
| WAVG_LOW_ENTROPY | type_conditional | 0.1000 | 0.0749 | 978 | lgbm_validity |
| WAVG_ALL | type_conditional | 0.0100 | 0.0000 | 3301 | validity_rule |
| WAVG_HIGH_ENTROPY | type_conditional | 0.0100 | 0.0000 | 2323 | validity_rule |
| WAVG_LOW_ENTROPY | type_conditional | 0.0100 | 0.0000 | 978 | validity_rule |
| WAVG_ALL | type_conditional | 0.0500 | 0.0000 | 3301 | validity_rule |
| WAVG_HIGH_ENTROPY | type_conditional | 0.0500 | 0.0000 | 2323 | validity_rule |
| WAVG_LOW_ENTROPY | type_conditional | 0.0500 | 0.0000 | 978 | validity_rule |
| WAVG_ALL | type_conditional | 0.1000 | 0.0000 | 3301 | validity_rule |
| WAVG_HIGH_ENTROPY | type_conditional | 0.1000 | 0.0000 | 2323 | validity_rule |
| WAVG_LOW_ENTROPY | type_conditional | 0.1000 | 0.0000 | 978 | validity_rule |

**Reading.** On this synthetic data, format validity catches 100% of damaged file versions at
every fraction in every checked type, with 0% false flags on pristine files; LightGBM + validity is
0.9976-1.0000 (weighted average) in every cell, and only `bin` (no check) stays below 1 at low
damage. The "compressed types near chance" blind spot exists only without validity (LightGBM base:
WAVG high-entropy 0.5563 at striped 5%). Caveat: synthetic benign files are always valid; real benign
files can be truncated or malformed, so these validity numbers are an upper bound until real data.
**This changes the paper's motivation wording; see NEEDS DECISION in OPEN_QUESTIONS.md.**

**A4.** Headline outputs (figures, tables, console) now show per-type and weighted-average AUROC
only.

**A5, start prior.** P(attack within 60 days) swept over {0.005, 0.01, 0.05, 0.2} (constant daily
hazard). Alarm thresholds for target ever-alarm rates 1/5/10% are set on 200 attack-free DEV
machines only (D19). The primary prior is chosen after Workstream C, on dev (D22).

**A6, memory.** No leak found: per-machine traced peak 100-114 MB, 0.3-2.3 MB retained afterwards.
The first relaunch failed (a worker died; BrokenProcessPool); leftover worker processes were
~1.35 GB each. Consistent with every worker starting a full LightGBM/OpenMP thread pool, pinning
each worker to one thread brought peak worker RSS to 330-341 MB (measured), and the re-run
completed. Also added: per-machine results persisted to disk with resume, and automatic pool
restart. M2 re-run on DEV (102400 attack-machine rows, 64000 clean-machine
rows): outputs -> C:\PROJECTS\ISM\results\inference  {'split': 'dev', 'n_machines': 520, 'workers': 5, 'wall_s': 1883.0, 'mean_machine_s': 17.98, 'mean_score_s': 14.27, 'max_worker_peak_rss_mb': 340.7}

### M2: mass within +-3 days of the true start (exceedance statistic, day +14), all priors
| detector | attack_target_types | model | p_attack_within_window | 100% | 50% | 25% | 10% | 5% |
|---|---|---|---|---|---|---|---|---|
| lgbm_base | all | bocpd | 0.0050 | 0.5291 | 0.2701 | 0.3058 | 0.2646 | 0.2199 |
| lgbm_base | all | bocpd | 0.0100 | 0.5117 | 0.2553 | 0.3033 | 0.2699 | 0.2256 |
| lgbm_base | all | bocpd | 0.0500 | 0.4368 | 0.2166 | 0.3022 | 0.2729 | 0.2232 |
| lgbm_base | all | bocpd | 0.2000 | 0.3408 | 0.1720 | 0.2830 | 0.2843 | 0.2373 |
| lgbm_base | all | prior_only | 0.0050 | 0.0006 | 0.0006 | 0.0006 | 0.0006 | 0.0006 |
| lgbm_base | all | prior_only | 0.0100 | 0.0012 | 0.0012 | 0.0012 | 0.0012 | 0.0012 |
| lgbm_base | all | prior_only | 0.0500 | 0.0059 | 0.0059 | 0.0059 | 0.0059 | 0.0059 |
| lgbm_base | all | prior_only | 0.2000 | 0.0245 | 0.0245 | 0.0245 | 0.0245 | 0.0245 |
| lgbm_base | all | single_cp | 0.0050 | 0.3617 | 0.3450 | 0.1614 | 0.1627 | 0.1347 |
| lgbm_base | all | single_cp | 0.0100 | 0.3870 | 0.3606 | 0.1858 | 0.1808 | 0.1564 |
| lgbm_base | all | single_cp | 0.0500 | 0.4353 | 0.3977 | 0.2562 | 0.2314 | 0.2196 |
| lgbm_base | all | single_cp | 0.2000 | 0.4690 | 0.4309 | 0.3133 | 0.2922 | 0.2763 |
| lgbm_base | high_entropy | bocpd | 0.0050 | 0.4763 | 0.1252 | 0.1088 | 0.0096 | 0.0017 |
| lgbm_base | high_entropy | bocpd | 0.0100 | 0.4727 | 0.1302 | 0.1149 | 0.0168 | 0.0032 |
| lgbm_base | high_entropy | bocpd | 0.0500 | 0.4439 | 0.1561 | 0.1330 | 0.0484 | 0.0128 |
| lgbm_base | high_entropy | bocpd | 0.2000 | 0.3977 | 0.1603 | 0.1577 | 0.0831 | 0.0364 |
| lgbm_base | high_entropy | prior_only | 0.0050 | 0.0006 | 0.0006 | 0.0006 | 0.0006 | 0.0006 |
| lgbm_base | high_entropy | prior_only | 0.0100 | 0.0012 | 0.0012 | 0.0012 | 0.0012 | 0.0012 |
| lgbm_base | high_entropy | prior_only | 0.0500 | 0.0059 | 0.0059 | 0.0059 | 0.0059 | 0.0059 |
| lgbm_base | high_entropy | prior_only | 0.2000 | 0.0245 | 0.0245 | 0.0245 | 0.0245 | 0.0245 |
| lgbm_base | high_entropy | single_cp | 0.0050 | 0.3341 | 0.2178 | 0.1800 | 0.0062 | 0.0006 |
| lgbm_base | high_entropy | single_cp | 0.0100 | 0.3746 | 0.2290 | 0.1989 | 0.0109 | 0.0011 |
| lgbm_base | high_entropy | single_cp | 0.0500 | 0.4612 | 0.2598 | 0.2400 | 0.0317 | 0.0057 |
| lgbm_base | high_entropy | single_cp | 0.2000 | 0.5157 | 0.2889 | 0.2765 | 0.0669 | 0.0223 |
| lgbm_validity | all | bocpd | 0.0050 | 0.5808 | 0.4506 | 0.4805 | 0.4919 | 0.2898 |
| lgbm_validity | all | bocpd | 0.0100 | 0.5780 | 0.4412 | 0.4781 | 0.4757 | 0.2821 |
| lgbm_validity | all | bocpd | 0.0500 | 0.5281 | 0.4246 | 0.4525 | 0.4380 | 0.2716 |
| lgbm_validity | all | bocpd | 0.2000 | 0.4737 | 0.4054 | 0.4186 | 0.4135 | 0.2611 |
| lgbm_validity | all | prior_only | 0.0050 | 0.0006 | 0.0006 | 0.0006 | 0.0006 | 0.0006 |
| lgbm_validity | all | prior_only | 0.0100 | 0.0012 | 0.0012 | 0.0012 | 0.0012 | 0.0012 |
| lgbm_validity | all | prior_only | 0.0500 | 0.0059 | 0.0059 | 0.0059 | 0.0059 | 0.0059 |
| lgbm_validity | all | prior_only | 0.2000 | 0.0245 | 0.0245 | 0.0245 | 0.0245 | 0.0245 |
| lgbm_validity | all | single_cp | 0.0050 | 0.5713 | 0.6211 | 0.5379 | 0.6031 | 0.6081 |
| lgbm_validity | all | single_cp | 0.0100 | 0.5802 | 0.6263 | 0.5452 | 0.6128 | 0.6139 |
| lgbm_validity | all | single_cp | 0.0500 | 0.5910 | 0.6371 | 0.5566 | 0.6321 | 0.6191 |
| lgbm_validity | all | single_cp | 0.2000 | 0.5924 | 0.6451 | 0.5629 | 0.6494 | 0.6189 |
| lgbm_validity | high_entropy | bocpd | 0.0050 | 0.4402 | 0.4814 | 0.5084 | 0.4397 | 0.5096 |
| lgbm_validity | high_entropy | bocpd | 0.0100 | 0.4262 | 0.4693 | 0.4946 | 0.4291 | 0.4921 |
| lgbm_validity | high_entropy | bocpd | 0.0500 | 0.3856 | 0.3990 | 0.4695 | 0.3934 | 0.4491 |
| lgbm_validity | high_entropy | bocpd | 0.2000 | 0.3309 | 0.3453 | 0.4376 | 0.3534 | 0.4156 |
| lgbm_validity | high_entropy | prior_only | 0.0050 | 0.0006 | 0.0006 | 0.0006 | 0.0006 | 0.0006 |
| lgbm_validity | high_entropy | prior_only | 0.0100 | 0.0012 | 0.0012 | 0.0012 | 0.0012 | 0.0012 |
| lgbm_validity | high_entropy | prior_only | 0.0500 | 0.0059 | 0.0059 | 0.0059 | 0.0059 | 0.0059 |
| lgbm_validity | high_entropy | prior_only | 0.2000 | 0.0245 | 0.0245 | 0.0245 | 0.0245 | 0.0245 |
| lgbm_validity | high_entropy | single_cp | 0.0050 | 0.5953 | 0.5732 | 0.6038 | 0.6532 | 0.6617 |
| lgbm_validity | high_entropy | single_cp | 0.0100 | 0.5980 | 0.5776 | 0.6112 | 0.6608 | 0.6658 |
| lgbm_validity | high_entropy | single_cp | 0.0500 | 0.6028 | 0.5841 | 0.6201 | 0.6765 | 0.6731 |
| lgbm_validity | high_entropy | single_cp | 0.2000 | 0.6030 | 0.5846 | 0.6209 | 0.6813 | 0.6754 |

### M2: errors at day +14, P(attack within 60 d) = 0.01
| detector | attack_target_types | model | mass_within_3 | missed_rate | median_signed_error | late_gt3 | early_gt3 | mean_p_started | n |
|---|---|---|---|---|---|---|---|---|---|
| lgbm_base | all | bocpd | 0.3132 | 0.3688 | 1.0000 | 0.2313 | 0.0563 | 0.6582 | 160 |
| lgbm_base | all | single_cp | 0.2541 | 0.6000 | 2.0000 | 0.1437 | 0.0187 | 0.4990 | 160 |
| lgbm_base | high_entropy | bocpd | 0.1476 | 0.6312 | 5.0000 | 0.2000 | 0.0250 | 0.3975 | 160 |
| lgbm_base | high_entropy | single_cp | 0.1629 | 0.7562 | 2.0000 | 0.0813 | 0.0063 | 0.3179 | 160 |
| lgbm_validity | all | bocpd | 0.4510 | 0.0688 | 2.0000 | 0.4437 | 0.0375 | 0.9450 | 160 |
| lgbm_validity | all | single_cp | 0.5957 | 0.0938 | 1.0000 | 0.2375 | 0.0063 | 0.9334 | 160 |
| lgbm_validity | high_entropy | bocpd | 0.4623 | 0.0437 | 3.0000 | 0.4562 | 0.0250 | 0.9629 | 160 |
| lgbm_validity | high_entropy | single_cp | 0.6227 | 0.0375 | 1.0000 | 0.2562 | 0.0125 | 0.9732 | 160 |

### M2: attack-free DEV machines at day +14 (exceedance statistic)
| detector | model | p_attack_within_window | prior_p_started | mean_p_started | frac_p_started_gt_05 | n |
|---|---|---|---|---|---|---|
| lgbm_base | bocpd | 0.0050 |  | 0.0140 | 0.0100 | 200 |
| lgbm_base | bocpd | 0.0100 |  | 0.0201 | 0.0100 | 200 |
| lgbm_base | bocpd | 0.0500 |  | 0.0572 | 0.0200 | 200 |
| lgbm_base | bocpd | 0.2000 |  | 0.1588 | 0.0550 | 200 |
| lgbm_base | prior_only | 0.0050 | 0.0026 | 0.0026 | 0.0000 | 200 |
| lgbm_base | prior_only | 0.0100 | 0.0052 | 0.0052 | 0.0000 | 200 |
| lgbm_base | prior_only | 0.0500 | 0.0262 | 0.0262 | 0.0000 | 200 |
| lgbm_base | prior_only | 0.2000 | 0.1089 | 0.1089 | 0.0000 | 200 |
| lgbm_base | single_cp | 0.0050 | 0.0026 | 0.0062 | 0.0000 | 200 |
| lgbm_base | single_cp | 0.0100 | 0.0052 | 0.0112 | 0.0000 | 200 |
| lgbm_base | single_cp | 0.0500 | 0.0262 | 0.0365 | 0.0250 | 200 |
| lgbm_base | single_cp | 0.2000 | 0.1089 | 0.0955 | 0.0450 | 200 |
| lgbm_validity | bocpd | 0.0050 |  | 0.0045 | 0.0000 | 200 |
| lgbm_validity | bocpd | 0.0100 |  | 0.0087 | 0.0000 | 200 |
| lgbm_validity | bocpd | 0.0500 |  | 0.0379 | 0.0050 | 200 |
| lgbm_validity | bocpd | 0.2000 |  | 0.1255 | 0.0300 | 200 |
| lgbm_validity | prior_only | 0.0050 | 0.0026 | 0.0026 | 0.0000 | 200 |
| lgbm_validity | prior_only | 0.0100 | 0.0052 | 0.0052 | 0.0000 | 200 |
| lgbm_validity | prior_only | 0.0500 | 0.0262 | 0.0262 | 0.0000 | 200 |
| lgbm_validity | prior_only | 0.2000 | 0.1089 | 0.1089 | 0.0000 | 200 |
| lgbm_validity | single_cp | 0.0050 | 0.0026 | 0.0066 | 0.0050 | 200 |
| lgbm_validity | single_cp | 0.0100 | 0.0052 | 0.0105 | 0.0050 | 200 |
| lgbm_validity | single_cp | 0.0500 | 0.0262 | 0.0305 | 0.0100 | 200 |
| lgbm_validity | single_cp | 0.2000 | 0.1089 | 0.0839 | 0.0350 | 200 |

### Alarm thresholds on DEV clean machines (P(attack within 60 d) = 0.01)
| detector | statistic | model | p_attack_within_window | fa_target | threshold | empirical_fa | n_clean_machines |
|---|---|---|---|---|---|---|---|
| lgbm_base | exceed | single_cp | 0.0100 | 0.0100 | 0.9693 | 0.0050 | 200 |
| lgbm_base | exceed | single_cp | 0.0100 | 0.0500 | 0.2596 | 0.0450 | 200 |
| lgbm_base | exceed | single_cp | 0.0100 | 0.1000 | 0.0681 | 0.0950 | 200 |
| lgbm_base | exceed | bocpd | 0.0100 | 0.0100 | 0.8399 | 0.0050 | 200 |
| lgbm_base | exceed | bocpd | 0.0100 | 0.0500 | 0.5626 | 0.0450 | 200 |
| lgbm_base | exceed | bocpd | 0.0100 | 0.1000 | 0.2052 | 0.0950 | 200 |
| lgbm_validity | exceed | single_cp | 0.0100 | 0.0100 | 0.9983 | 0.0050 | 200 |
| lgbm_validity | exceed | single_cp | 0.0100 | 0.0500 | 0.1825 | 0.0450 | 200 |
| lgbm_validity | exceed | single_cp | 0.0100 | 0.1000 | 0.0241 | 0.0950 | 200 |
| lgbm_validity | exceed | bocpd | 0.0100 | 0.0100 | 0.5906 | 0.0050 | 200 |
| lgbm_validity | exceed | bocpd | 0.0100 | 0.0500 | 0.1536 | 0.0450 | 200 |
| lgbm_validity | exceed | bocpd | 0.0100 | 0.1000 | 0.0722 | 0.0950 | 200 |

### Detection with those thresholds (attack machines, P(attack within 60 d) = 0.01)
| detector | model | fa_target | attack_target_types | pre_start_alarm_rate | detected_by_day_30 | median_delay_days |
|---|---|---|---|---|---|---|
| lgbm_base | bocpd | 0.0100 | all | 0.0000 | 0.8812 | 6.0000 |
| lgbm_base | bocpd | 0.0100 | high_entropy | 0.0000 | 0.5312 | 8.0000 |
| lgbm_base | bocpd | 0.0500 | all | 0.0000 | 0.9000 | 6.0000 |
| lgbm_base | bocpd | 0.0500 | high_entropy | 0.0000 | 0.5938 | 8.0000 |
| lgbm_base | bocpd | 0.1000 | all | 0.0250 | 0.9313 | 5.0000 |
| lgbm_base | bocpd | 0.1000 | high_entropy | 0.0125 | 0.6188 | 5.0000 |
| lgbm_base | single_cp | 0.0100 | all | 0.0000 | 0.6250 | 11.0000 |
| lgbm_base | single_cp | 0.0100 | high_entropy | 0.0000 | 0.3625 | 11.0000 |
| lgbm_base | single_cp | 0.0500 | all | 0.0187 | 0.9000 | 6.0000 |
| lgbm_base | single_cp | 0.0500 | high_entropy | 0.0000 | 0.5625 | 5.5000 |
| lgbm_base | single_cp | 0.1000 | all | 0.0250 | 0.9500 | 4.0000 |
| lgbm_base | single_cp | 0.1000 | high_entropy | 0.0000 | 0.6562 | 6.0000 |
| lgbm_validity | bocpd | 0.0100 | all | 0.0000 | 1.0000 | 2.5000 |
| lgbm_validity | bocpd | 0.0100 | high_entropy | 0.0000 | 1.0000 | 2.0000 |
| lgbm_validity | bocpd | 0.0500 | all | 0.0063 | 1.0000 | 2.0000 |
| lgbm_validity | bocpd | 0.0500 | high_entropy | 0.0000 | 1.0000 | 1.0000 |
| lgbm_validity | bocpd | 0.1000 | all | 0.0063 | 1.0000 | 1.0000 |
| lgbm_validity | bocpd | 0.1000 | high_entropy | 0.0125 | 1.0000 | 1.0000 |
| lgbm_validity | single_cp | 0.0100 | all | 0.0000 | 0.9812 | 5.0000 |
| lgbm_validity | single_cp | 0.0100 | high_entropy | 0.0000 | 0.9812 | 4.0000 |
| lgbm_validity | single_cp | 0.0500 | all | 0.0187 | 0.9938 | 1.0000 |
| lgbm_validity | single_cp | 0.0500 | high_entropy | 0.0000 | 1.0000 | 0.5000 |
| lgbm_validity | single_cp | 0.1000 | all | 0.0500 | 1.0000 | 0.0000 |
| lgbm_validity | single_cp | 0.1000 | high_entropy | 0.0187 | 1.0000 | 0.0000 |

**Reading.**
- With the base detector the hard regime still fails: high-entropy targets at 5% damage give
  single-CP mass within +-3 of 0.0006-0.0223 across priors.
- With LightGBM + validity, single-CP + exceedances reaches 0.5379-0.6813 mass within +-3 and
  P(started) 0.9334 / 0.9732 at day +14 (prior 0.01), yet 23.75% / 25.62% of machines are still
  more than 3 days late. **The late bias is not only a detection problem.** Exceedances are defined
  at alpha = 0.05, so 5% of benign chunks exceed by construction, in file-correlated bursts. The
  benign model must allow strong overdispersion and then explains an isolated attack spike as noise.
  Proposed (not done): a file-level statistic and an alpha frozen on dev (F0).
- Alarming: at a 5% false-alarm target, BOCPD + validity detects every attacked machine (median
  delay 1-2 days); single-CP + base detects 90.00% (any type) / 56.25% (high-entropy) by day 30.
- A7: the per-type calibration is described as type-conditional (Mondrian) conformal outlier
  p-values (Vovk et al.; Bates et al. 2023) in code and notes.

## 2026-10-14 - F0, C, B1-B3, DEV tuning (no test-split runs yet)

**F0** (committed 48808d8, 862f84a): shared runner, seed/split registry, frozen gate, stats,
LaTeX, benign validation failures (paired machines, auxiliary stream), token-mode simulator,
file-level statistic with file-level conformal calibration, abstract detector.

**Statistic tuning, DEV (rule D24 v2; v1 set aside as defective, see OPEN_QUESTIONS.md).**
Single-CP, prior 0.01, day +14, 36 attack cells x 16 machines:

| statistic | score (mass +-3 d) | clean FA | late > 3 d | missed | eligible |
|---|---|---|---|---|---|
| chunk a0.01 | 0.3711 | 0.0667 | 0.1389 | 0.3802 | no |
| chunk a0.05 | 0.3502 | 0.0700 | 0.1510 | 0.4184 | no |
| file a0.01 | 0.1151 | 0.0000 | 0.0017 | 0.9028 | **chosen** |
| file a0.05 | 0.0533 | 0.0000 | 0.0000 | 0.9427 | yes |

The chunk statistic's false alarms come only from benign validation failures with the validity
detector (0.16 at 1%, 0.24-0.26 at 5%): a benign invalid file flags all its chunks at once.
The file statistic never false-alarms but has low power: one flagged file is worth only 0.7-1.6
nats, because ~50 warm-up files cannot rule out benign flag rates up to ~0.05.
Late-bias ablation (validity detector, no benign failures, machines where a start was found):
more than 3 days late, chunk 0.2128 (n = 94) vs file 0.0476 (n = 21). The chunk statistic
accounts for most of the late bias (small n for the file statistic).

**Retention tuning, DEV (rule D27), headline grid, 10 machines per cell.** Chosen:
p_attack_within_window 0.05, restore_quantile 0.1, penalty 30, assumed discovery uniform up to 60
days. At these settings (delay 14):
- clean recovery 1.000 at every delay for GFS, prior-only and SlowBurn (stage-2 settings);
  Tower of Hanoi 0.000 at d >= 21 (history condition s >= 2d of Theorem 2 violated: s = 30);
  keep-last-N 0.000 at d >= 7 (Proposition 1); threshold vault 0.015-0.075 at d >= 7.
- whole-system work lost (h): GFS 576.0 at every q; SlowBurn 734.4 (q 0) -> 592.8 (q 1);
  prior-only 736.8 -> 643.2; Tower of Hanoi 696.0; keep-last-N 1056.0.

**This contradicts the second half of the claim on DEV**: SlowBurn improves with detector
quality but does not beat GFS on work lost at any q, and recovery saturates at 1.000 for the
best fixed schedule. Reported to the team before freezing; no test run made.

**B1-B3**: docs/theory.md (NEEDS HUMAN REVIEW). Theorem 2(a): zero violations in 48,686 ToH
cases, bound attained (max W/3d = 1.000); Theorem 2(b): within 1 of the exhaustive minimum;
Theorem 3: DP = brute force on 120 random instances.

## 2026-10-15: items 1-5 of the team decision, DEV tuning D30 (v3), test run stopped

Commits 188a3d7..384e0f9. DEV only; no test machine evaluated (the stopped run had written no
test rows; its empty log is in `results/headline_unread_aborted/`).

**Built (tests + ruff clean):** verified restore (D29) with the DP loss matched exactly (DP =
brute force for gates {0, 0.5, 0.9} and forced backbone days; gated loss = independent per-start
evaluation); hybrid ToH backbone (D30) with Theorem 2(c) (0 superset and 0 bound violations for
(K, R) = (6,3) 596 cases, (8,4) 1181, (12,6) 4439, (12,4) 1181); fleet-pooled benign rate (D31);
oracle-ideal work lost on every row; pre-registered grid (D32) in frozen.yaml with a test gate;
D33 (prior-only restores with its own posterior), D34 (restore posterior conditioned on the
discovery day).

**D30 v3 stage 1** (`results/tune_retention_v2/stage1_scoreboard.csv`, mean clean recovery over
the six baselines, 96000 rows each): (p, gate) (0.01, 0.95) 0.48082; (0.05, 0.95) 0.48060;
(0.01, 0.8) 0.47611; (0.05, 0.8) 0.47589 [chosen: lowest work lost 2484.376 h in the tie];
(0.2, 0.95) 0.46227; (0.2, 0.8) 0.45807; (0.05, 0.5) 0.43294; (0.01, 0.5) 0.43293; (0.2, 0.5)
0.42411. At the chosen pair (penalty 90, max 60, backbone 0.25): SlowBurn 0.929 / 1357.8 h,
GFS 0.641 / 2076.1 h, ToH 0.593 / 2387.7 h, prior-only 0.575 / 2112.9 h, threshold vault
0.068 / 3459.4 h, keep-last-N 0.050 / 3512.3 h (clean recovery / whole-system work lost).

**D30 v3 stage 2** (SlowBurn, 16000 rows each), top rows: (270, 90, 0.0) 0.99900 / 3333.6 h;
(270, 60, 0.0) 0.99875 / 3329.9 h [chosen]; (270, 90, 0.25) 0.98225 / 3264.7 h; (270, 60, 0.25)
0.97763 / 3223.1 h; (270, 90, 0.5) 0.95900 / 2657.3 h; (270, 60, 0.5) 0.93850 / 2549.7 h;
(90, 60, 0.25) 0.92900 / 1357.8 h; (90, 60, 0.5) 0.90100 / 1480.5 h; (90, 60, 0.0) 0.88350 /
1340.7 h. Lowest work lost: (90, 30, 0.0) 0.600 / 1302.6 h.

**Problem (D35):** the chosen setting is degenerate: median restore point day 13 (end of
warm-up), oldest retained age 138.6 d at every K, work lost 3329.9 h vs GFS 2076.1 h. Recovery
0.99875 comes from keeping the first backup forever. Test run stopped; decision asked.

**Also corrected:** a D34 statement (prior-only 0.65 after the fix) was wrong; prior-only's
restore points are identical before and after D33/D34 (see OPEN_QUESTIONS D34 correction).

## 2026-10-15: HEADLINE TEST grid (frozen D30 stage 1 + D36), 2400 test machines, 1728000 rows

`results/headline/grid_summary.csv` (1600 cells per policy; clean recovery avg / worst; whole-
system work lost avg / worst, h; oracle-ideal avg 772.8 h):
keep_first 0.999687 / 0.966667, 3647.0510 / 4776.0; oracle 0.999687 / 0.966667, 776.5100 /
1555.2; slowburn 0.932583 / 0.0, 1368.8045 / 4776.0; gfs 0.643750 / 0.0, 2072.2055 / 4776.0;
tower_of_hanoi 0.597542 / 0.0, 2379.6550 / 4776.0; prior_only 0.575000 / 0.0, 2112.9000 /
4272.0; amoeba_style 0.151396 / 0.0 (file-level work lost only); threshold_vault 0.068521 / 0.0,
3461.9340 / 4776.0; keep_last_n 0.050000 / 0.0, 3512.3390 / 4776.0.
Prior-only (0.575) does NOT match GFS (0.644) on test, as on DEV. Per-cell tests:
`results/headline/paired_tests.csv`. Figures: `paper/generated/` (`slowburn fig all`).

## 2026-10-15: D37 bug fix (K = 12) and full TEST grid RERUN, 2400 test machines, 1728000 rows

Fix (commit e2668b1): retention deletes only when held + today > K; tie-break smallest largest
gap, then delete newest. No hyperparameter retuned; frozen.yaml unchanged; same seed and
machines (every baseline's numbers identical to the first run). Run time 14817.8 s.
`results/headline_v2/grid_summary.csv` (clean recovery avg / worst; whole-system work lost avg /
worst, h; oracle-ideal avg 772.8 h): keep_first 0.999687 / 0.966667, 3647.0510 / 4776.0; oracle
0.999687 / 0.966667, 776.5100 / 1555.2; prior_only 0.980708 / 0.0, 1758.8845 / 4776.0;
slowburn 0.967187 / 0.0, 1743.0375 / 4776.0; gfs 0.643750 / 0.0, 2072.2055 / 4776.0;
tower_of_hanoi 0.597542 / 0.0, 2379.6550 / 4776.0; amoeba_style 0.151396 / 0.0;
threshold_vault 0.068521 / 0.0, 3461.9340 / 4776.0; keep_last_n 0.050000 / 0.0, 3512.3390 /
4776.0. First run for comparison: slowburn 0.932583 / 1368.8045 h, prior_only 0.575000 /
2112.9000 h.

Per K (`results/headline_v2/k12_fix_by_budget.csv`; kept / recovery / work lost h), first run ->
rerun: SlowBurn K=4 2.0 / 0.894 / 1336.254 -> 4.0 / 0.980 / 1824.662; K=6 3.0 / 0.959 /
1295.804 -> 6.0 / 0.976 / 1806.296; K=8 3.0 / 0.959 / 1295.804 -> 8.0 / 0.953 / 1788.930; K=12
4.0 / 0.918 / 1547.356 -> 12.0 / 0.960 / 1552.262. Prior-only K=4 2.0 / 0.300 / 2917.200 ->
4.0 / 1.000 / 1959.960; K=6 3.0 / 0.500 / 2248.800 -> 6.0 / 0.983 / 1800.612; K=8 3.0 / 0.500 /
2248.800 -> 8.0 / 0.979 / 1706.436; K=12 4.0 / 1.000 / 1036.800 -> 12.0 / 0.961 / 1568.530.

After the fix a clean snapshot is retained in every case (clean_snapshot_retained = 1.0 for
SlowBurn and prior-only at every K); all remaining failures are the verified restore choosing a
dirty snapshot that passes verification, at low detection probability and 45-60 day delays
(prior-only at delay 60: 1.000 / 0.913 / 0.895 / 0.806 for K = 4 / 6 / 8 / 12; SlowBurn at q =
0: 0.902 / 0.891 / 0.825 / 0.873). Work lost by q (0 / 0.2 / 0.5 / 0.9 / 1): SlowBurn 1978.5 /
1786.0 / 1706.3 / 1628.4 / 1616.0 h; prior-only 1842.3 / 1781.6 / 1742.4 / 1714.6 / 1713.6 h.

**CONTRADICTS THE DRAFT CLAIM:** prior-only (no detector) now beats every fixed schedule and
has higher mean clean recovery than SlowBurn (0.981 vs 0.967) at similar work lost (1758.9 vs
1743.0 h). Evidence lowers work lost at q >= 0.5 but lowers recovery at q <= 0.2. Reported to
the team; Tier 2 not started.

## 2026-10-15: DEV grid rerun after D37 (reporting only, nothing retuned), 800 machines

`results/headline_dev_v2/grid_summary.csv` (clean recovery avg; work lost avg h): prior_only
0.978437 / 1772.1585; slowburn 0.961312 / 1760.0100; gfs 0.640750 / 2076.0630; tower_of_hanoi
0.593000 / 2387.7150; oracle 0.999563 / 776.8230. Per K (kept / recovery / work lost h):
SlowBurn 4.0 / 0.977 / 1834.926, 6.0 / 0.972 / 1841.820, 8.0 / 0.936 / 1832.562, 12.0 / 0.961 /
1530.732; prior-only 4.0 / 1.000 / 1970.400, 6.0 / 0.979 / 1819.140, 8.0 / 0.978 / 1718.244,
12.0 / 0.957 / 1580.850. Same pattern as the TEST rerun.

## 2026-10-16: Timing-prior misspecification sweep (DEV only, reporting), 800 machines x 9 priors

`results/sweep_prior/sweep_summary.csv` (frozen hyperparameters; only the assumed attack-timing
prior replaced; mean over every grid cell; clean recovery / whole-system work lost h):
frozen_geometric: prior-only 0.978437 / 1772.1585, SlowBurn 0.961313 / 1760.0100, GFS 0.640750
/ 2076.0630, ToH 0.593000 / 2387.7150 (reproduces the DEV rerun exactly).
flat: 0.978437 / 1746.9285, 0.959625 / 1764.7230, GFS 0.640250 / 2076.4815, ToH 0.593000 /
2386.6590. matched (normal, center 121, sd 12): 1.000000 / 1409.5800, 0.981875 / 1370.4930,
GFS 0.646062 / 2003.3205, ToH 0.611062 / 2310.0015. earlier_30: 0.968250 / 1813.5885,
0.993313 / 1587.6960, GFS 0.650000 / 2083.7610, ToH 0.612500 / 2457.9480. earlier_60: 1.000000
/ 2192.9250, 0.999875 / 2132.0370, GFS 0.650000 / 2113.0875, ToH 0.612500 / 2540.1720.
later_30: 0.754125 / 1528.6230, 0.848187 / 1428.9075, GFS 0.531438 / 2225.2365, ToH 0.500750 /
2423.1360. later_60: 0.361938 / 2171.4180, 0.621125 / 1755.8670, GFS 0.418125 / 2437.7610, ToH
0.375625 / 2632.7985. narrow (sd 3): 0.873188 / 1327.2930, 0.853625 / 1347.3915, GFS 0.564937 /
2131.8255, ToH 0.568063 / 2355.0840. wide (sd 48): 0.979437 / 1812.3540, 0.962063 / 1834.9725,
GFS 0.644687 / 2057.1420, ToH 0.598125 / 2363.9820.
GFS and ToH change with the prior only through the shared verified restore (its gate uses the
posterior); their retention is prior-free (clean snapshot retained 0.650 / 0.6125 throughout).
The frozen prior is NOT the generating distribution (constant hazard, P(start within 60 d) =
0.05, vs a certain start at day 112 + o); it behaves like the flat prior.
