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

## 2026-10-16: prior wiring check, freeze check K = 6, restore-time failure analysis (1c)

**Prior wiring (D39).** `results/sweep_prior` frozen_geometric vs `results/headline_dev_v2`:
64000 paired rows, restore_point / oldest_retained_age / gate_candidates / estimated_start /
clean_recovery / work_lost identical in 1.0000 of rows (same prior, same seeds). Share of paired
rows whose restore point differs from the frozen prior (prior-only / SlowBurn / GFS): flat
0.027 / 0.018 / 0.004; matched 1.000 / 0.990 / 0.137; earlier_30 1.000 / 0.980 / 0.095;
earlier_60 0.586 / 0.513 / 0.114; later_30 0.988 / 0.977 / 0.274; later_60 1.000 / 0.996 /
0.387; narrow 1.000 / 0.994 / 0.272; wide 0.418 / 0.289 / 0.035. New test
`test_timing_prior_reaches_dp_and_restore_gate` (smoke machine, start 12, discovery 22): gate day
9 vs 14 (SlowBurn), 8 vs 18 (prior-only) for priors centred on day 8 vs 20; kept sets
[6, 7, 8, 22] vs [9, 13, 14, 22] (SlowBurn), [6, 7, 8, 22] vs [12, 15, 17, 22] (prior-only).

**Freeze check, K = 6 added** (scratchpad replay, 400 days, gate 0.8, penalty 90): today's
snapshot deleted on 0.0 of deletion days; yesterday's 0.964 (backbone 0) / 0.0 (backbone 0.25);
newest non-today kept age median / max 18.0 / 36 (bb 0), 1.0 / 1 (bb 0.25); last-day ages
[0, 15, 51, 87, 123, 159] (bb 0), [0, 1, 4, 46, 88, 130] (bb 0.25); replay recovery 1.0, work lost
17.163 / 19.82 days.

**Restore-time failures (D40), share of rows with a clean snapshot retained but recovery failed**
(`slowburn fig table-restore-failures`; CSVs `restore_failures_by_{detect_prob,budget,
discovery_delay}.csv` next to each results CSV). Every such failure has verified = 1.

| TEST | overall | q=0 | q=0.2 | q=0.5 | q=0.9 | q=1 | K=4 | K=6 | K=8 | K=12 | d=45 | d=60 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| SlowBurn | 0.0328 | 0.1272 | 0.0261 | 0.0098 | 0.0004 | 0.0004 | 0.0204 | 0.0242 | 0.0470 | 0.0396 | 0.0314 | 0.1302 |
| Prior-only | 0.0193 | 0.0544 | 0.0293 | 0.0124 | 0.0004 | 0.0000 | 0.0000 | 0.0173 | 0.0211 | 0.0388 | 0.0000 | 0.0965 |
| GFS | 0.0062 | 0.0256 | 0.0041 | 0.0014 | 0.0001 | 0.0001 | 0.0000 | 0.0004 | 0.0008 | 0.0238 | 0.0127 | 0.0148 |
| ToH | 0.0150 | 0.0700 | 0.0038 | 0.0006 | 0.0002 | 0.0002 | 0.0000 | 0.0003 | 0.0298 | 0.0298 | 0.0019 | 0.0717 |

Delays 7 / 14 / 30 are at most 0.0022 for every policy. No clean snapshot retained: GFS 0.35,
ToH 0.3875, SlowBurn and prior-only 0. DEV overall: SlowBurn 0.0387, prior-only 0.0216, GFS
0.0092, ToH 0.0195. DEV q = 0: on the 425 of 3200 rows where SlowBurn fails, it restores 22.4
days later (median 14) than prior-only on the same machine-cell; gate candidates 4.62 vs 3.92.

## 2026-10-16: P0 consolidation for the systems paper (D42-D44)

**New direction (D42)** recorded; **v1 TEST split marked SPENT (D43)**: nothing from
`results/headline` or `results/headline_v2` is a headline result; v2 claims come only from a fresh
pre-registered TEST.

**Restore gate logged per restore (D44).** `verified_restore` now records `gate_day` and
`restore_p_clean` next to `gate_candidates` and `verified`. DEV v2 rerun with logging
(`configs/headline_dev_v2_gatelog.yaml` -> `results/headline_dev_v2_gatelog`, same seeds): all
576000 rows match `results/headline_dev_v2` in every one of the 45 shared columns (wall-clock
timings excluded), i.e. the logging changes nothing else.

**Measured gate, v1 DEV** (`slowburn fig table-gate-q` -> `paper/generated/table_gate_q.tex`,
`results/headline_dev_v2_gatelog/gate_by_detect_prob.csv`; 3200 rows per policy and q):

| policy | q | gate - start, mean d | median d | gate admits start | restore-time failure |
|---|---|---|---|---|---|
| SlowBurn | 1.0 | -7.51375 | -4.0 | 0.0275 | 0.0 |
| SlowBurn | 0.9 | -7.63 | -5.0 | 0.07625 | 0.00375 |
| SlowBurn | 0.5 | -10.81875 | -8.0 | 0.18 | 0.0146875 |
| SlowBurn | 0.2 | -12.36875 | -10.0 | 0.24875 | 0.0421875 |
| SlowBurn | 0.0 | -10.36 | -9.0 | 0.36 | 0.1328125 |
| Prior-only | every q | -18.8 | -20.0 | 0.2 | 0.0 / 0.0025 / 0.0165625 / 0.035625 / 0.053125 (q = 1 / .9 / .5 / .2 / 0) |

At q = 0, SlowBurn's gate day is later than prior-only's on the same machine-cell by 8.44 days on
average (median 11, 3200 rows); on the 425 rows where SlowBurn fails with a clean snapshot
retained, by 11.02 days (median 12), and its gate admits the true start day in 1.0 of them
(prior-only: 0.7976). The restore point lies inside SlowBurn's gate in 1.0 of those rows (mean
restore_p_clean 0.8932). The D40 explanation is now measured, not inferred. Prototype appendix:
`paper/sections/appendix_prototype.tex`.

## 2026-10-16 (night): P1 simulator v2 and the new DEV baseline (D45-D47, D50)

`configs/dev_v2.yaml` -> `results/dev_v2` (seed 202; 4 worlds x 15 evidence cells x 40 reps =
2400 machines, 552000 rows, 1805.7 s, 5 workers). Byte-budget multipliers (keep-last-N footprint
/ day-0 size, 40 attack-free calibration machines): 14 d 1.7450643130492298, 30 d
2.66980547090922, 90 d 6.146835909945129. Attack starts drawn (40 per world): uniform mean 136.2
(28-278), early 86.3 (28-203), late 217.9 (82-279), bursty 189.3 (93-271). Oracle-ideal work lost
772.8 h in every world. Generated: `world_summary.csv`, `world_by_{budget,detect_prob,
discovery_delay}.csv`.

**Count budgets (K = 4, 6, 8, 12 pooled; all evidence cells and delays), clean recovery / work lost (h):**

| world | prior-only | SlowBurn | GFS | Tower of Hanoi | keep last N | keep first | oracle |
|---|---|---|---|---|---|---|---|
| uniform | 0.979083 / 1687.168 | 0.9795 / 1642.93 | 0.563583 / 2488.84 | 0.545833 / 2514.428 | 0.05 / 3860.052 | 0.999833 / 4013.152 | 0.999833 / 777.354 |
| early | 0.9815 / 1544.374 | 0.976917 / 1517.21 | 0.61125 / 1781.774 | 0.52075 / 1982.586 | 0.049917 / 2720.888 | 0.999833 / 2818.846 | 0.999833 / 776.85 |
| late | 0.97575 / 1860.822 | 0.977 / 1756.486 | 0.534417 / 3474.616 | 0.585917 / 3368.278 | 0.05 / 5721.132 | 1.0 / 5974.12 | 1.0 / 776.382 |
| bursty | 0.986 / 1794.414 | 0.985417 / 1661.258 | 0.574083 / 2937.988 | 0.5935 / 3000.572 | 0.05 / 5069.048 | 0.999917 / 5288.478 | 0.999917 / 776.91 |
| all | 0.980583 / 1721.6945 | 0.979708 / 1644.471 | 0.570833 / 2670.8045 | 0.5615 / 2716.466 | 0.049979 / 4342.78 | 0.999896 / 4523.649 | 0.999896 / 776.874 |

12000 rows per world and policy. Clean snapshot retained: prior-only and SlowBurn 1.0 in every
world; GFS 0.53625-0.615; Tower of Hanoi 0.5325-0.60375; keep last N 0.05.

**Byte budgets (14, 30, 90 days of keep-last-N storage pooled), clean recovery / work lost (h):**

| world | prior-only | SlowBurn | GFS | Tower of Hanoi | keep last N | oracle |
|---|---|---|---|---|---|---|
| uniform | 0.645667 / 2290.544 | 0.667222 / 2193.576 | 0.522222 / 2548.669333 | 0.520111 / 2518.618667 | 0.491778 / 2553.848 | 0.759889 / 1695.485333 |
| early | 0.618 / 1897.754667 | 0.659667 / 1753.114667 | 0.553667 / 1864.770667 | 0.505667 / 1993.149333 | 0.486778 / 1969.456 | 0.761556 / 1404.682667 |
| late | 0.621 / 3144.352 | 0.646222 / 2942.778667 | 0.49 / 3642.186667 | 0.495889 / 3664.706667 | 0.474444 / 3646.621333 | 0.749222 / 2228.050667 |
| bursty | 0.603 / 2916.170667 | 0.658667 / 2651.530667 | 0.523111 / 3116.872 | 0.513556 / 3212.165333 | 0.484778 / 3250.032 | 0.754778 / 2019.992 |
| all | 0.621917 / 2562.205333 | 0.657944 / 2385.25 | 0.52225 / 2793.124667 | 0.508806 / 2847.16 | 0.484444 / 2854.989333 | 0.756361 / 1837.052667 |

By byte budget (uniform world): 14 d prior-only 0.21, SlowBurn 0.214667, GFS 0.17, ToH 0.16,
keep last N 0.2, oracle 0.41; 30 d 0.804 / 0.882667 / 0.489333 / 0.464333 / 0.409 / 0.999;
90 d 0.923 / 0.904333 / 0.907333 / 0.936 / 0.866333 / 0.870667 (other worlds in
`world_by_budget.csv`). At 14 days even the oracle cannot keep the day-(s-1) snapshot next to
today's in most cases (the pair costs ~1.9x the day-0 size under the simulated churn). At 90 days
the oracle (0.870667) is below Tower of Hanoi (0.936): the oracle's ~36 newest snapshots put
more damaged candidates inside the restore gate (restore-time failures; the oracle's retention
knows the start, its restore does not).

**q = 0 restore-time failure (count budgets), SlowBurn vs prior-only:** uniform 0.069583 vs
0.047917; early 0.085833 vs 0.054167; late 0.08125 vs 0.0625; bursty 0.060833 vs 0.0425;
pooled 0.074375 vs 0.051770833. The excess (0.018333 to 0.031666) is above the pre-registered 1-point
margin in every world: the v1 failure persists in simulator v2. Measured gate at q = 0: SlowBurn
gate - start mean -10.7367 / -8.4917 / -11.1533 / -11.425 d (uniform / early / late / bursty) vs
prior-only -17.155 / -15.54 / -18.8 / -18.8; gate admits the start day 0.34 / 0.3617 / 0.3467 /
0.3333 vs 0.2 in every world.

**Versus the old simulator (v1 DEV, benign rates 0 / .01 / .05 only, all q):** prior-only 0.979667 /
1787.298 h, SlowBurn 0.964167 / 1786.894, GFS 0.642417 / 2079.484, Tower of Hanoi 0.594833 /
2404.872, keep last N 0.05 / 3512.314. In v2: SlowBurn's recovery gap to prior-only shrinks
(-0.000875 vs -0.0155), SlowBurn's work lost falls below prior-only's in every world (by 27.164 to
133.156 h), and GFS / Tower of Hanoi lose 0.071584 / 0.033333 recovery (v1's start offsets included
GFS's best case o = 0). SlowBurn's work lost is 1.953 (early) to 2.262 (late) times the oracle's.

**Headline claim (3) on v2 DEV (D50, reported, claim NOT changed):** with the policy's flat
timing assumption fixed and the generating world varied, no world makes prior-only collapse (its
recovery is 0.97575-0.986 in all four), so detector evidence adds no recovery: SlowBurn minus
prior-only = +0.000417 (uniform), -0.004583 (early), +0.00125 (late), -0.000583 (bursty). Evidence
lowers work lost in every world (by 27.164-133.156 h) and raises recovery under byte budgets
(+0.021555 to +0.055667). The v1 robustness result (60 days late: prior-only 0.362 vs SlowBurn
0.621) came from a concentrated prior placed 60 days late, which the v2 design no longer has.

## 2026-10-16 (night): P1 worst-case timing grid on the v2 DEV seed (D47)

`configs/dev_v2_worst.yaml` -> `results/dev_v2_worst/worst_case_timing.csv`: starts 112..143 x
delays {7, 14, 30, 45, 60}, q in {1, .5, 0}, benign 0.01, 5 reps per start (480 machines). Per
policy, budget and q: mean over the 160 timing cells and the worst cell. With 5 reps a cell's
recovery moves in steps of 0.2, so "worst cell" is coarse and biased low; the TEST grid needs
more reps per timing cell. Pooled over budgets and q (mean of cell means / min of worst cells /
mean work lost / max worst work lost, h):

| budget kind | policy | recovery avg | recovery worst | work lost avg | work lost worst |
|---|---|---|---|---|---|
| count | prior-only | 0.974063 | 0.0 | 1770.5975 | 4800.0 |
| count | SlowBurn | 0.959167 | 0.0 | 1771.57 | 4752.0 |
| count | GFS | 0.599583 | 0.0 | 2250.885 | 4872.0 |
| count | Tower of Hanoi | 0.578542 | 0.0 | 2515.425 | 4872.0 |
| count | keep last N | 0.049896 | 0.0 | 3660.87 | 4872.0 |
| count | keep first | 0.999687 | 0.8 | 3806.9575 | 4872.0 |
| count | oracle | 0.999687 | 0.8 | 777.255 | 1464.0 |
| bytes | prior-only | 0.617083 | 0.0 | 2311.38 | 4872.0 |
| bytes | SlowBurn | 0.66125 | 0.0 | 2146.206667 | 4872.0 |
| bytes | GFS | 0.539722 | 0.0 | 2382.746667 | 4872.0 |
| bytes | Tower of Hanoi | 0.512639 | 0.0 | 2514.343333 | 4872.0 |
| bytes | keep last N | 0.485417 | 0.0 | 2489.086667 | 4872.0 |
| bytes | oracle | 0.755972 | 0.0 | 1666.796667 | 4872.0 |

Count budgets, worst cell at q = 1: prior-only 1.0 at every K; SlowBurn 0.8 at K = 4 (start 130,
delay 60), 1.0 otherwise; GFS 0.0 at every K (start 112 or 120, delay 45-60); Tower of Hanoi 0.0
at K = 4 and 6, 1.0 at K = 8 and 12. At q = 0 every policy except keep first and the oracle has
a worst cell of 0.0, and SlowBurn's mean is below prior-only's at every K (K = 4: 0.885 vs
0.9375; K = 6: 0.895 vs 0.98125; K = 8: 0.91125 vs 0.93875; K = 12: 0.86 vs 0.88125), again the
q = 0 restore-time failure. Byte budget 30 d at q = 1: SlowBurn 0.99 (worst 0.8) vs prior-only
0.71125 (worst 0.0), GFS 0.5175, Tower of Hanoi 0.45625, oracle 1.0.

## 2026-10-16 (night): P1 assumed discovery-delay sweep on the v2 DEV seed (D47, reporting only)

`configs/dev_v2_delay.yaml` -> `results/dev_v2_delay/sweep_{summary,by_budget,by_q,by_delay}.csv`:
the policy's assumed delay distribution replaced, true delays 7-60, all four worlds, q in
{1, .5, .2, 0}, benign 0.01, 40 reps, count budgets (3200 rows per variant, world and policy).
Mean over the four worlds, clean recovery / work lost (h):

| assumed delay | prior-only | SlowBurn | GFS | Tower of Hanoi |
|---|---|---|---|---|
| uniform 1-14 | 0.35125 / 3259.78125 | 0.348984 / 3265.760625 | 0.3575 / 3205.591875 | 0.271641 / 3558.894375 |
| uniform 1-30 | 0.565703 / 2542.336875 | 0.566328 / 2506.275 | 0.486016 / 2856.3 | 0.382969 / 3079.68375 |
| uniform 1-60 (frozen) | 0.973203 / 1732.39125 | 0.972109 / 1660.003125 | 0.571641 / 2671.13625 | 0.558906 / 2716.74375 |
| uniform 1-90 | 1.0 / 2224.695 | 0.993672 / 2158.83 | 0.573359 / 2676.2175 | 0.571094 / 2783.30625 |
| uniform 1-120 | 1.0 / 2816.5875 | 0.997109 / 2509.940625 | 0.573438 / 2677.5975 | 0.572656 / 2818.32375 |
| geometric, mean 30, max 60 | 0.976406 / 1734.38625 | 0.962422 / 1668.3825 | 0.560859 / 2683.123125 | 0.547891 / 2732.859375 |

By true delay, prior-only recovery: assumed 14 -> 1.0 / 0.75625 / 0.0 / 0.0 / 0.0 (true 7 / 14 /
30 / 45 / 60); assumed 30 -> 1.0 / 1.0 / 0.828516 / 0.0 / 0.0; assumed 60 -> 1.0 / 1.0 / 1.0 / 1.0
/ 0.866016; assumed 90 and 120 -> 1.0 at every true delay. An assumed maximum delay shorter than
the true delay makes the restore gate trust snapshots taken after the attack started, and
recovery collapses for every policy that shares the restore (GFS and Tower of Hanoi too). A
longer assumption is safe for recovery and costs work lost (prior-only +492.30375 h at 90,
+1084.19625 h at 120, relative to 60). SlowBurn's work lost is below prior-only's for every
assumption except uniform 1-14 (+5.979375 h).

## 2026-10-17 (night, cont.): method v2 stage A on the v2 DEV seed (D48 applied; D51 incident)

`configs/dev_v2_method_a.yaml` -> `results/dev_v2_method_a/` (1920 machines: 4 worlds x q in
{1, .5, .2, 0} x benign {0, .01, .05} x 40 reps; count budgets; 9600 rows per variant, world and
policy). Rule D48 applied mechanically (`slowburn.bench.method_v2.select_stage_a`;
`stage_a_scoreboard.csv`, `q0_excess_by_world.csv`):

| blind weight | SlowBurn recovery | SlowBurn work lost (h) | worst-world q = 0 excess | eligible |
|---|---|---|---|---|
| 0 (v1) | 0.974922 | 1673.2425 | 0.031667 | no |
| 0.25 | 0.979323 | 1655.116875 | 0.025417 | no |
| 0.5 | 0.978646 | 1634.5425 | 0.00625 | yes |
| 0.75 | 0.97875 | 1644.030625 | 0.006667 | yes |
| 0.9 | 0.977135 | 1646.56875 | 0.0025 | yes |

q = 0 excess by world (bursty / early / late / uniform): v1 0.018333 / 0.031667 / 0.01875 /
0.021667; 0.5: 0.00625 / 0.00125 / -0.004167 / 0.001667. **Chosen: blind weight 0.5** (eligible;
0.75 has the highest eligible recovery, 0.5 is within 0.001 of it with lower work lost).
Prior-only on the same machines: recovery 0.9762239583, work lost 1736.83375 h.

Per world, recovery / work lost (h), prior-only vs v1 SlowBurn vs v2 (w = 0.5): bursty 0.982708 /
1806.7625 vs 0.981771 / 1697.2725 vs 0.983437 / 1671.275; early 0.977187 / 1550.195 vs 0.971146 /
1536.265 vs 0.977812 / 1485.27; late 0.969688 / 1889.7025 vs 0.97125 / 1796.395 vs 0.974688 /
1764.5325; uniform 0.975313 / 1700.675 vs 0.975521 / 1663.0375 vs 0.978646 / 1617.0925. By q,
recovery (prior-only / v1 / v2): q = 0 0.948229 / 0.925625 / 0.946979; 0.2 0.967917 / 0.978542 /
0.974167; 0.5 0.98875 / 0.995521 / 0.993542; 1.0 1.0 / 1.0 / 0.999896. Restore-time failure at
q = 0: 0.051771 / 0.074375 / 0.053021. Work lost at q = 1: 1657.6725 / 1513.0075 / 1455.0775.
v2 gives up a little of v1's recovery at q = 0.2 and 0.5 (0.004375, 0.001979) and gains 0.021354
at q = 0.

**Where work lost comes from (new diagnostic `newest_clean_kept`):** mean work lost if the
restore used the newest truly clean kept snapshot: prior-only 1177.83 h, v1 1241.398, v2
1194.649, against actual 1736.834 / 1673.242 / 1634.542 and the oracle-ideal 772.8. For v2,
439.893 h of the 861.742 h above the oracle are the restore choosing an older snapshot than the
best kept one (the gate), and 421.849 h are retention spacing.

**Incident (D51):** stage A ran TWICE at the same time for ~95 min (10 workers, above the cap of
6): an earlier `nohup` launch that I believed had not started did start, next to the tracked
launch. Both wrote the same output directory. Integrity check: all 1920 per-machine cache files
load with 200 rows each and no duplicate keys; the first 384000 rows of the CSV equal them in
every compared column; 6 tasks recomputed from scratch are identical to the cache; the CSV had
15 trailing garbage lines from the second writer. `tuning_sweep.csv` was rebuilt from the cache
(the corrupt file is kept in the session scratchpad, not in the repo); summaries were recomputed
from the rebuilt file and match. No other run was affected (each had one launch).

## 2026-10-17 (night, cont.): method v2 stage B, adaptive restore gate (D49 applied)

`configs/dev_v2_method_b.yaml` -> `results/dev_v2_method_b/` (same 1920 machines, blind weight 0.5,
count budgets; 230400 rows, split dev only). Rule D49 (`select_stage_b`; `stage_b_scoreboard.csv`,
`q0_excess_by_world.csv`):

| restore gate | SlowBurn recovery | SlowBurn work lost (h) | worst-world q = 0 excess | eligible |
|---|---|---|---|---|
| fixed 0.8 (control) | 0.978646 | 1634.5425 | 0.00625 | yes |
| adaptive, min 0.5 | 0.970443 | 1621.1475 | 0.02875 | no |
| adaptive, min 0.65 | 0.974193 | 1625.624375 | 0.02125 | no |

**Outcome: the fixed gate is kept.** Both adaptive variants break the q = 0 criterion (excess by
world, bursty / early / late / uniform: min 0.5 0.02875 / 0.010833 / 0.007083 / 0.016667; min 0.65
0.02125 / 0.005833 / 0.0025 / 0.01) and lower recovery at every q < 1, for 8.918125-13.395 h less
work lost. Mean restore gate at q = 0 / 0.2 / 0.5 / 1: min 0.5 0.755022 / 0.711703 / 0.65058 /
0.581867; min 0.65 0.777511 / 0.755851 / 0.72529 / 0.690933. The concentration measure lowers the
gate even without detector signal (q = 0), because the discovery-conditioned posterior is already
somewhat concentrated. The work lost from the gate (439.893 h above the best kept snapshot) is not
recovered by loosening the gate this way: restores move only slightly newer while restore-time
failures rise (q = 0: 0.067604 / 0.061667 vs 0.053021).

## 2026-10-17 (night, cont.): method v2 (blind weight 0.5, fixed gate) vs v1 on the full v2 DEV grid

`configs/dev_v2_method_full.yaml` -> `results/dev_v2_method_full/` (2400 machines, count and byte
budgets, policies prior-only, SlowBurn, GFS, Tower of Hanoi, keep last N, oracle; 1008000 rows).
The v1 variant reproduces `results/dev_v2` exactly (504000 rows; restore point, recovery, work
lost, gate day, retained bytes and snapshot count identical in 1.0 of rows). The blind weight
changes the evidence posterior, so it also moves the shared restore of the other policies.

Count budgets, all worlds, recovery / work lost (h): SlowBurn v2 0.982708 / 1601.852, v1
0.979708 / 1644.471, prior-only 0.980583 / 1721.6945; GFS v2 0.573104 / 2670.2885 (v1 0.570833 /
2670.8045); Tower of Hanoi v2 0.566417 / 2713.804 (v1 0.5615 / 2716.466). Per world, SlowBurn v2
vs prior-only: bursty 0.98675 / 1633.384 vs 0.986 / 1794.414; early 0.981833 / 1463.502 vs 0.9815
/ 1544.374; late 0.97975 / 1718.93 vs 0.97575 / 1860.822; uniform 0.9825 / 1591.592 vs 0.979083 /
1687.168. q = 0 restore-time failure, SlowBurn v2 / v1 / prior-only: bursty 0.04875 / 0.060833 /
0.0425; early 0.055417 / 0.085833 / 0.054167; late 0.058333 / 0.08125 / 0.0625; uniform 0.049583 /
0.069583 / 0.047917.

Byte budgets, all worlds: SlowBurn v2 0.665583 / 2361.655333, v1 0.657944 / 2385.25, prior-only
0.621917 / 2562.205333, oracle v2 0.765194. q = 0 restore-time failure, SlowBurn v2 / v1 /
prior-only: bursty 0.063333 / 0.103333 / 0.060556; early 0.068889 / 0.122222 / 0.063333; late
0.061111 / 0.098333 / 0.058889; uniform 0.062778 / 0.106667 / 0.06.

Worst-case grid (`configs/dev_v2_worst_method.yaml` ->
`results/dev_v2_worst_method/worst_case_timing_by_variant.csv`; the v1 variant reproduces
`results/dev_v2_worst` in all 126 matching rows). Count budgets pooled, mean / worst-cell recovery:
SlowBurn v2 0.973125 / 0.0 (v1 0.959167 / 0.0), prior-only 0.974063 / 0.0; work lost 1686.7825 vs
1771.57 (v1) vs 1770.5975 h. At q = 0 SlowBurn v2 is still below prior-only in mean recovery at
K = 4 (0.93125 vs 0.9375), K = 6 (0.9725 vs 0.98125) and K = 8 (0.9225 vs 0.93875; gap 0.01625),
above it at K = 12 (0.88625 vs 0.88125). Byte budgets pooled: SlowBurn v2 0.670556 vs v1 0.66125
vs prior-only 0.617083.

## 2026-10-17: D50 test, under-estimated discovery delay (v2 DEV); D52-D54

`configs/dev_v2_underdelay.yaml` -> `results/dev_v2_underdelay/` (2400 machines: 4 worlds x 15
evidence cells x 40 reps; count budgets; assumed max delay 14 / 30 / 60 x SlowBurn v1 (blind
weight 0) / method v2 (0.5); true delays 7-60). Tables: `underdelay_by_world_q.csv` (per assumed
max, world, q and policy; all delays and true delay > assumed), `v2_vs_prior_only_under_tests.csv`.
The assumed-60 variants reproduce `results/dev_v2_method_full` (method v2 0.982708 / 1601.852 h,
prior-only 0.980583 / 1721.6945 h).

**Where the delay is under-estimated (true delay > assumed max), clean recovery is 0.0 for
prior-only, SlowBurn v1, method v2, GFS and Tower of Hanoi (with either restore), in every world
and at every q, including q = 1** (assumed 14: 5760 paired rows per q, true delays 30 / 45 / 60;
assumed 30: 3840 per q, true delays 45 / 60). McNemar v2 vs prior-only: no discordant pairs at any
q. Pooled over all true delays (mean of worlds), recovery / work lost (h):

| assumed max | prior-only | SlowBurn v1 | method v2 | GFS (v2 restore) | Tower of Hanoi (v2 restore) |
|---|---|---|---|---|---|
| 14 | 0.361 / 3225.488 | 0.359125 / 3229.3665 | 0.361208 / 3222.0655 | 0.363792 / 3178.5445 | 0.279312 / 3533.9175 |
| 30 | 0.573625 / 2511.941 | 0.574563 / 2468.599 | 0.577271 / 2458.4685 | 0.493312 / 2833.6145 | 0.388833 / 3050.714 |
| 60 | 0.980583 / 1721.6945 | 0.979708 / 1644.471 | 0.982708 / 1601.852 | 0.573104 / 2670.2885 | 0.566417 / 2713.804 |

Recovery by q at assumed 14 (prior-only / v1 / v2): q = 0 0.318542 / 0.300417 / 0.309062; 1.0
0.4 / 0.399792 / 0.399896. At assumed 30: q = 0 0.538646 / 0.522604 / 0.539896; 1.0 0.6 / 0.6 /
0.599792. The recovered cases are exactly those with true delay <= assumed max.

**Mechanism (measured on the under-estimated rows, v2 variants):** the restore gate day is after
the true start in 1.0 of rows for every policy; the verification scan window starts (estimated
start L) after the true start in 1.0 of rows, so damaged versions written before L are never
checked and the damaged snapshot passes verification (verified 1.0 for prior-only at 14 and 30,
0.999514 / 0.999583 for SlowBurn); retention keeps a clean snapshot in 0.156771 (prior-only) /
0.18559 (SlowBurn) of rows at assumed 14, 0.985156 / 0.946719 at assumed 30, yet the restore
point is after the start in 0.932552 / 0.923385 of rows at 30. The assumed delay distribution
gives zero probability to starts before discovery minus its maximum, in the evidence posterior as
well as the prior one, so detector evidence cannot move the restore earlier than that bound.

**Outcome for claim (3), by the team's rule:** evidence does not rescue recovery under an
under-estimated delay, so claim (3) is to be dropped (D55). The proposed replacement role of
evidence ("reduces work lost ~7% at equal recovery, and is safe when the detector is blind") is
half supported on v2 DEV: work lost 1601.852 vs 1721.6945 h (-6.960729676%, full grid, recovery
0.982708 vs 0.980583); "safe when blind" holds on the four worlds (q = 0 restore-time failure
excess 0.00125-0.00625 count budgets) but not on the worst-case timing grid (D54: significantly
worse than prior-only at K = 6 and 8 after Holm, gap up to 0.01625). No claim text changed.

## 2026-10-17: D57 blind-weight re-selection and method v3 (soft assumed delay), v2/v3 DEV

**D57** (rule fixed before the runs; `results/dev_v2_blind_worst/d57_{scoreboard,units}.csv`):
units passing of 8 / SlowBurn recovery / work lost (h) on the worlds grid: w = 0: 0 / 0.974922 /
1673.2425; 0.25: 5 / 0.979323 / 1655.116875; 0.5: 7 / 0.978646 / 1634.5425 (fails worst-case K = 8,
excess 0.01625, Holm p 0.0177); 0.75: 8 / 0.97875 / 1644.030625; 0.9: 8 / 0.977135 / 1646.56875;
0.95: 8 / 0.977266 / 1650.74875. **Chosen: w = 0.75** (largest excess 0.00875, worst-case K = 8,
Holm p 0.261719). Prior-only on the same machines 0.9762239583 / 1736.83375 h.

**Method v3, D56** (rule fixed before the runs, amended before any result to add w = 0.75;
`results/dev_v3_{under,normal,worst}[_w075]/`, `results/dev_v3_normal/d56_{scoreboard,units,
report}`, `results/dev_v3_under/d56_{rescue_tests,b_by_world_q}.csv`). 12 variants (tail 0.05 /
0.1 / 0.2 x w 0 / 0.5 / 0.75 / 0.9). **No variant is eligible and none shows a clear rescue.**

- C1 (q = 0, vs prior-only with the same soft assumption): all 12 pass all 8 units (largest
  excess 0.00125, worst-case K = 12, tail 0.1 and 0.2 with w = 0).
- C2 (cost on the normal grid): all fail. SlowBurn v3 work lost 3784.02375 to 3956.44375 h
  (limit 1.10 x 1634.5425 = 1797.99675 h); recovery 0.997318 to 0.998047 (v2: 0.978646).
- (a) prior-only with the soft assumption stops collapsing. True delay > assumed core:
  recovery 1.0 (core 14, every tail) and 0.988281 to 0.992969 (core 30), against 0.0 with the
  hard bound; work lost 4378.25-4381.625 h (14) and 4401.01875-4438.74375 h (30) vs 4858.05 and
  4757.77125 h hard. All true delays: 1.0 / 0.993828-0.996016 vs 0.359812 / 0.571937 hard.
- (b) evidence adds nothing beyond the soft prior: SlowBurn v3 minus prior-only (soft) on the
  under-estimated rows, q in {0.2, 0.5, 1}, ranges -0.0140625 to +0.0109375 (largest: tail 0.1,
  w 0, core 30, q 0.2, Holm p 0.000366; below the 0.10 rescue threshold).
- (c) the cost: with true delays 7 / 14 days, prior-only (soft) loses 3412.2-3556.3125 h vs
  783.40125 (core 14) and 816.24375 h (core 30) with the hard bound; on the normal grid prior-only
  (soft) loses 3802.54875-3844.428125 h vs 1736.83375 h (hard, same machines). A never-zero tail on
  top of the flat timing prior puts enough mass on very old starts that the gate restores from far
  back on every machine, whatever the true delay.

Claim (3) is not reinstated ("detection protects you when attacks stay hidden longer than you
planned for" fails the pre-defined rescue test: the soft assumption itself, not detection,
removes the collapse, at 2.189356782-2.213469266x the work lost on the normal grid and 4.180368916-4.539579813x when
the true delay is 7-14 days).

## 2026-10-21: evidence wording at w = 0.75; method v4 (D60) on DEV; FSL download restarted

**Evidence wording (D59)**: `results/dev_v2_method_full_w075` (run 2026-10-17, first read today),
count budgets, all worlds and cells: SlowBurn 0.982729 / 1611.0825 h vs prior-only 0.980583 /
1721.6945 h, -6.4246008801% work lost (w = 0.5 gave -6.960729676%). Wording: "about 6%".

**Method v4, D60** (rule, scoring code and configs committed before any run; `configs/
dev_v4_*.yaml` -> `results/dev_v4_*`). Hard variant reproduces v2 w 0.75 on G2 (1644.030625 h).
**Not adopted: C1 passes for every tail, C2 fails for every tail** (G2 work lost 3755.944375-
3769.360625 h vs limit 1808.4336875 h). Pooled recovery / work lost (h), SlowBurn:

| grid | hard (v2) | soft tail 0.02 (v3) | v4 tail 0.02 | v4 tail 0.05 | v4 tail 0.1 |
|---|---|---|---|---|---|
| normal (M 60) | 0.97875 / 1644.030625 | 0.997682 / 3779.123125 | 0.997292 / 3769.360625 | 0.997214 / 3768.303125 | 0.997292 / 3755.944375 |
| worst case, q 0 | 0.933438 / 1868.895 | 1.0 / 3023.34 | 1.0 / 2999.925 | 1.0 / 2992.02 | 1.0 / 2970.12 |
| under, M 14 | 0.351953 / 3256.220625 | 0.992188 / 4063.588125 | 0.508906 / 4060.164375 | 0.504766 / 4061.1225 | 0.506016 / 4055.66625 |
| under, M 30 | 0.565 / 2510.356875 | 0.991406 / 3911.446875 | 0.665 / 3913.625625 | 0.660156 / 3912.770625 | 0.656172 / 3907.29375 |

Under-estimated rows (true delay > M), v4 recovery at q = 0 / 0.2 / 0.5 / 1 (tail 0.02): M 14
0.0266 / 0.0307 / 0.1458 / 0.5229, M 30 0.0156 / 0.018 / 0.1297 / 0.5055; hard 0.0 everywhere;
soft tail 0.02 0.9729-0.9979 (no evidence needed). Rescue (gain >= 0.10, Holm over 6): q = 0.2 none; q = 0.5 tail
0.02 only; q = 1 every tail. Restore depth (days, SlowBurn, normal grid): hard 64.97, soft
157.38, v4 156.40-156.96; beyond the hard bound 0.617 / 0.870 / 0.866-0.867; walked back in
0.51-0.56% of restores. Mechanism: newest clean kept snapshot 155.37 days back under soft-tail
retention vs 49.83 hard, same restore gate (45.15 days): the cost is retention, not the gate
(corrects the D56 diagnosis). Claim (3) dropped for good (D60 outcome).

**FSL download**: found dead since 2026-10-17 15:15 (about 17 GB of 56 GB on disk, no process
running, no error logged); restarted on the fixed block (`results/fetch_run2.log`).

## 2026-10-22: D62-D64a restore-time verification fix (adopted), stop rule triggered

The original F1 wording ("under-estimating the delay collapses every policy to 0, even with a
perfect detector") was PARTLY A SCAN-WINDOW ARTIFACT: D29 verification never scanned versions
older than L (start-posterior 0.001 quantile), which an under-estimated bound pushes after the
true start, so a snapshot holding flagged damaged versions verified clean and files damaged
before L were not restored. The adopted restore (D64a "verify_snap": every version in the
candidate scanned with the shared write-time draw, any flag rejects, plus restoring files whose
current version is flagged) fixes this (`tests/test_damage_persistence.py`).

Adopted pipeline (`results/dev_d64a_under`), SlowBurn recovery beyond the bound at q = 0 / 0.2 /
0.5 / 1: hard M 14 0 / 0 / 0.0026 / 0.1495; hard M 30 0 / 0 / 0.0062 / 0.8891 (equal to the
fraction of rows with a clean snapshot retained). v4 beyond the bound (all tails): M 14 0 / 0 /
0.0042 / 1.0; M 30 0 / 0 / 0.0062 / 1.0 (old pipeline: q = 0.5 0.0977-0.1458, q = 1 0.4469-0.5229).

Cost (`results/dev_d64a_worst`, worst-case grid, q = 0, paired old -> new): work lost prior-only
+16.2043%, SlowBurn +16.6013%; recovery +0.010938 / +0.011563. Past the team's thresholds: stopped
before the full-grid, worlds-grid, D57 and v4 reruns. Earlier diagnostics (unadopted, for
reference only): `results/diag_d62_*` (options select / verify).

## 2026-10-22 (step 1, D64b): every verification-dependent DEV result rerun under verify_snap

- Reruns: `dev_d64a_blind_worst`, `dev_d64a_blind_worlds` (D57 table), `dev_d64a_full`,
  `dev_d64a_worst_all` (old and new restore side by side, every policy), `dev_d64a_v4_normal`,
  `dev_d64a_v4_worst`; same seed and machines; paired old-vs-new CSVs with machine-cluster
  bootstrap CIs in each directory.
- w = 0.75 passes all 8 blind units. claims.md C1 / C2 / C3' replaced; F1 / F3 rewritten from
  the adopted pipeline; F2 numbers updated.
- Main moves: work lost +25-27% (prior-only, SlowBurn) on the worlds grid, +16-19% worst case;
  recovery +0.004-0.012; C3' -6.42% -> -4.72%; C2 vs GFS not significant in the early world.
- Fix during analysis: the pairing key now includes the variant (multi-variant runs).

## 2026-10-22 (D65): method v2.1 rejected

- Significance-based snapshot accept rule (D60 Beta-Binomial, alpha 0.05): work lost -15% / -22%
  (worst case / full grid) but SlowBurn recovery -0.012 to -0.020 per world and -0.019 on the
  worst case, failing criterion (a). Step 1 numbers in claims.md stand; no further iterations.

## 2026-10-22 (D63): delay characterisation sweep under the adopted restore

- `results/dev_d63_delay_grid`; guideline figure and CSVs in `paper/generated/`. Under-estimated
  rows: nothing recovers at q = 0; at q = 1 Tower of Hanoi beats SlowBurn for short bounds
  (M 7-30), SlowBurn wins at M 60-90. claims.md F1 updated with the fixed-schedule numbers.

## 2026-10-22 (late): FSL fetch stopped below the free-space floor; G1 wording

**Fetch stopped by hand at 42.8 GB free (floor 45 GB).** The per-archive guard checks each
file alone, so parallel in-flight downloads and other writers on C: took free space below the
floor without a StopFetch. Fetcher and watchdog processes killed, scheduled task "SlowBurn FSL
download watchdog" disabled; nothing deleted (2 `.part` files, 0.36 GB, resume later).
State (data/MANIFEST.json): FSL block 2011-09-16..2011-12-03, 60 days, 13 users, 767 files,
55.95 GB planned; 619 files / 43.59 GB present with published SHA-256 match, 0 mismatches.
Complete and verified: 48 of 60 days (contiguous, 2011-09-16..2011-11-03); 2011-11-04 has 8 of
13 users; the last 11 days have none; 12.36 GB missing. No user is complete over the 60 days.
NapierOne on disk 43.69 GB, not ~20 GB: archives kept next to their extractions (benign zip
17.74 + extracted 17.74; encrypted zips 3.91 + extracted 4.30).

**G1 (docs/claims.md):** Theorem 2(a)'s 48,686-case check is Tower of Hanoi only, K in
{4, 5, 6, 8}, d = 0..2^(K-2) - 1 inclusive with s >= 2d, held set only. The D63 zero at K = 8,
M = 7, delay 7 is prior-only and SlowBurn (DP), not Tower of Hanoi (held 1.0, restored 0.80 at
q = 0). Wording fixed to state horizon, history condition and held-not-restored.

## 2026-10-22/23: disk steps 3a-3d (team decision 2026-10-22)

**3a. What the pipeline reads.** `slowburn/detector/datasets.py`: damage bytes from
`data/napierone/encrypted/**/*` (extracted), benign from `data/napierone/benign/**/*`
(extracted). No zip is read by any code. No committed config reads NapierOne at all (every
config uses `damage_source: synthetic_random`, `benign_source: synthetic`; napierone benign
raises NotImplementedError in `build_chunk_dataset`).
**3b. Deleted:** `data/napierone/benign_zip/NapierOne-tiny.zip`, 17,737,521,386 bytes,
SHA-256 cca04ab9...304c (kept in MANIFEST.json with an `archive_deleted` record). Before deleting:
all 100 members SHA-256 identical to the extracted files. No published hash exists for it.
Kept: encrypted zips (3.91 GB, they match the published SHA-256) AND their extractions (read by
the loader), since there the hash-matched copy is not the used one. Check: `detector_smoke`
and the same config with `damage_source: napierone` (reads the extracted encrypted files), each
run twice before (deterministic) and once after the deletion: all 12 output files byte
identical in both. 
**3c. Compressed** every `results/*/machines*/*.pkl` resume cache (57 runs, 55,783 files) to
`.pkl.xz` (lzma preset 1): 8.341 GB -> 0.410 GB, 7.93 GB freed; every file checked by
decompressing and comparing bytes before the original was removed (0 mismatches), and one file
per run loaded back with pickle and compared (57/57). `run_tasks` reads `.pkl.xz` caches.
Per-row `tuning_sweep.csv` files (9.2 GB) were not touched.
**3d. Fetch guard** (`slowburn/datasets/fetch.py`): checks count bytes due on all in-flight
downloads; free space is re-checked before every 1 MB chunk; one StopFetch stops every thread;
FSL starts only with free >= 45 GB + remaining + 10 GB; finished NapierOne steps are skipped
(no re-download of the deleted zip). Tests: `tests/test_fetch.py`, `tests/test_f0_infra.py`.

## 2026-10-23: data correction (team decision item 1)

Every DEV result so far uses synthetic benign files and synthetic damage; NapierOne is
downloaded but not yet used. Stated in docs/data_card.md (new section "Data actually used so
far"), docs/claims.md (header) and results/STATUS.md. Basis: every committed config sets
`benign_source: synthetic` / `damage_source: synthetic_random` (detector) or runs token content
with the abstract detector (retention); `benign_source: napierone` raises NotImplementedError.
The data card's NapierOne rows describe the planned use only.

## 2026-10-23: D67 detector AUROC, synthetic vs NapierOne (DEV; nothing reselected)

`configs/detector_napierone.yaml` (detector.yaml unchanged except the data: NapierOne benign,
NapierOne encrypted, 9 types, D67 splits), exit 0, `results/detector_napierone/`. Default variant
lgbm_validity, uniform mean over the 9 shared types (lzma excluded on both sides),
`results/detector_napierone/auroc_side_by_side_9types.csv`:
- chunk level, NapierOne / synthetic: 0.985-0.988 / 0.997-1.000 (striped and whole, all
  fractions 0.05-1.0); difference -0.012 to -0.014.
- file level: 0.978-0.986 / 1.000; difference -0.014 to -0.022 (largest for whole-chunk damage at
  5-10%).
- per type, file level, striped 10%: every type 1.000 except zip 0.884 and bin 0.979 (synthetic
  1.000 for all). Synthetic detector: results/detector (seed 11, 2026-10-14).
Reading: the synthetic table was saturated; real data opens a gap, concentrated in compressed
containers (zip) and binaries, where real benign files are already high entropy.

## 2026-10-23 02:40 D67 arms failed (attempt 1): byte accounting bug, fixed
- Both D67 full-grid arms (synthetic bytes, NapierOne bytes) exited 1 in the tuning stage:
  `ByteIndex` refused traces where a chunk disappears and later reappears ("a chunk reappeared:
  interval accounting does not apply"). Byte mode with byte budgets had never been run before;
  real and synthetic file bytes repeat chunks (shared headers, padding, files redrawn from a
  small pool), token mode never does.
- Fix (no spec change): such traces now use the exact union of chunk sets (one bitset per day).
  Token-mode traces keep the interval formula, so every earlier result is unchanged. Test updated.
- Attempt 1 logs kept as results/dev_d67_full_{synthetic,napierone}_run_attempt1.log. The arms
  rerun as attempt 2 after D68 and D69 (one job at a time); a second failure is logged and skipped.

## 2026-10-23 D71b: PPMd zip validator bug fixed; NapierOne detector rebuilt; D67 NapierOne arm and D71 item 3 rerun

- Bug: `file_validity` marked PPMd-compressed zips INVALID because Python `zipfile` raises
  NotImplementedError on compression method 98. 7-Zip (`7z t`) reads them. 2 of the 5 DEV zip
  pool files are PPMd, so 40% of benign NapierOne zip versions were flagged. Rule fixed by the
  team before the check (OPEN_QUESTIONS D71b): the external tool decides.
- Fix (e44df6e): PPMd members are decoded with pyppmd (new dependency) and CRC-32 checked; tests
  `test_ppmd_zip_members_are_checked_not_rejected`, `test_napierone_dev_ppmd_zips_are_valid`.
  Synthetic content is unaffected (synthetic zips are deflate).
- NapierOne detector rebuilt from the unchanged config and seed (flag alpha 0.01 unchanged; old
  as results/detector_napierone_v1): file-level AUROC zip 0.884 -> 1.000, 9-type mean 0.985 ->
  0.997, other types within 0.016.
- D67 NapierOne arm (old outputs `_v1`): C3' work lost SlowBurn vs prior-only +1.5% -> -11.9%
  [-13.4, -10.5]; C2 vs GFS +7.9% -> -34.4%, vs Tower of Hanoi -2.3% -> -35.7%; recovery
  unchanged. C2 and C3' now hold on NapierOne bytes (docs/claims.md updated).
- D71 item 3 NapierOne: benign flag rate at rate 0 0.036 -> 0.0004; clean snapshots holding a
  flagged version 0.88 -> 0.005; damaged versions detected 0.746 -> 0.947.
- Details: results/D71_REPORT.md section 6.

## 2026-10-24: D72 and D72-C2R (DEV)

- D72: per-file restore method C (monotone changepoint) NOT adopted under scoring option (iii):
  fails vs A (recovery, residuals) whenever detection is imperfect, and vs B (per-file work lost)
  everywhere. B is near the per-file oracle with perfect detection and collapses otherwise.
  results/D72_REPORT.md section 1. D73 primary restore stays A; D74 per-file restore is B.
- D72-C2R: C2 holds vs default GFS / ToH (D67 numbers reproduced exactly) and, small and not in
  the early world, vs Bar-On recursive / round robin; fails vs the equal-horizon GFS / ToH
  configurations. docs/claims.md C2 restated. results/D72_REPORT.md section 2.
- D73 started 2026-10-24 (results/overnight_queue.log).

## 2026-10-24: D73 fleet-aware retention (DEV)

- FLEET not adopted: passes all criteria on synthetic bytes; fails criterion 1 (recovery) on
  NapierOne bytes vs both splits (worst cell -0.025; 52 of 54 losing rows from one N = 20 fleet).
  Per-file work lost -9% to -18% pooled on both arms. FLEET hardly reallocates slots; its effect
  is the pooled start posterior. Greedy optimal in 99.0% of 500 small cases (max excess 24%).
  results/D73_REPORT.md.

## 2026-10-24: D75 pools enlarged (v2)

- NapierOne simulation pools v2 built under the D75 rule (11:29-11:38): six per-subset small
  archives verified against the published SHA-256 and deleted after sampling; zip / png / jpg
  from unused tiny files. v2 DEV pool sizes 59 to 115 per type (v1: 5 to 15). docs/data_card.md.
- Reruns of the D67 and D72 NapierOne arms on v2 started 11:39 (v1 runs kept).
- D75 results (14:07): on the v2 pools C2 (vs default GFS / ToH) and C3' still hold on NapierOne
  but shrink (C2 -14.0% / -19.6%, C3' -3.8%; v1 -34.4% / -35.7% / -11.9%); cause: the small v1
  pools were easy (benign false flags 0.000 -> 0.017 at rate 0, png invalid files; damage
  detection 0.947 -> 0.875, txt and bin). Detector AUROC on new files 0.991 vs 0.997 (png 0.93).
  claims.md NapierOne numbers replaced by v2. results/D75_REPORT.md.

## 2026-10-25: process incident (no effect on results)

- Stopping the first D74 queue (variable-shadowing fix, 16:36) did not kill its bash loop: it
  started its own "attempt 2" of d74_attack_synthetic at 16:36:00, which ran in parallel with the
  restarted queue's run (16:37:30) for 4.5 h (two heavy jobs at once, against the rule), and at
  21:12 it began d74_attack_napierone twice. Found at 21:11, killed by PID tree 21:12-21:14; the
  NapierOne attempts wrote nothing. Both synthetic runs are deterministic and share one task
  cache, so no result changes. Logged in results/overnight_queue.log. Lesson: stop a queue by
  its process tree, not by the tool's task handle.
