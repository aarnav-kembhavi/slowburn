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

