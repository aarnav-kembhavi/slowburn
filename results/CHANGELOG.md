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
