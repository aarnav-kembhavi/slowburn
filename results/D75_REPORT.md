# D75 report: enlarged NapierOne pools, v1 vs v2 (DEV, 2026-10-24)

Rule: OPEN_QUESTIONS D75 (0ac3331). Pools built 11:29-11:38 (results/d75_pool_fetch.log,
data/napierone/benign_v2/manifest.json, counts in docs/data_card.md). Reruns, same seeds,
machines, grid and detector, only the benign content pool differs: dev_d67_full_napierone_v2pool
11:39-12:54, dev_d72_bytes_napierone_v2pool 12:54-14:06, d75_auroc 14:06-14:07, D71 false-flag
count with a v2 arm (v1 arms from cache), all exit 0. Outputs: results/dev_d75_compare/,
results/dev_d75_compare.txt, results/detector_napierone/d75_auroc_old_vs_new_pools.csv,
results/dev_d71_false_flags/report.txt.

## 1. Headline: the claims still hold on the enlarged pools, but the effects are much smaller

D67 NapierOne arm, count budgets, SlowBurn w 0.75, verify_snap:

| quantity | v1 pools (5 to 15 files per type) | v2 pools (59 to 115) |
|---|---|---|
| C1 recovery SlowBurn / GFS / ToH | 0.9999 / 0.574 / 0.573 | 0.9985 / 0.574 / 0.571 |
| C2 vs default GFS, work lost | -34.4% [-37.7, -30.8] | **-14.0% [-18.3, -9.4]** |
| C2 vs default ToH, work lost | -35.7% [-38.3, -32.9] | **-19.6% [-23.0, -16.0]** |
| C2 vs GFS, early world | -12.4% [-19.1, -4.9] | **+4.2% [-2.9, +11.7], not significant** |
| C3' vs prior-only, work lost | -11.9% [-13.4, -10.5] | **-3.8% [-5.3, -2.4]** |
| C3' by world | -10.5% to -13.5% | -2.5% to -5.0%, every world significant |
| C3' at benign rate 0 / 0.01 / 0.05 | -20.7% / -14.3% / -4.2% | -7.3% / -5.2% / +0.1% [-1.3, +1.6] |
| SlowBurn / prior-only work lost (h) | 1724 / 1957 | 2306 / 2397 |
| oracle-retention recovery | 1.000 | 0.994 |

D72 NapierOne arm (SlowBurn retention; recovery / residual damaged files / per-file work lost h):

| restore | v1 | v2 |
|---|---|---|
| A verify_snap | 1.000 / 0.000 / 4801 | 0.999 / 0.001 / 7130 |
| B walk-back | 0.504 / 0.85 / 670 | 0.230 / 2.02 / 715 |
| C changepoint | 0.994 / 0.006 / 3212 | 0.969 / 0.033 / 3848 |
| D oracle per file | 1.000 / 0 / 679 | 1.000 / 0 / 712 |

The D72 verdict does not change (C fails vs A and vs B under both required policies), and C's
recovery loss vs A grows (-0.030 v2 vs -0.005 v1).

## 2. Why: the small v1 pools happened to be easy

Strict validity of the benign files (detector.validity, unchanged):

| type | v1 DEV pool invalid | new v2 files invalid |
|---|---|---|
| csv | 0 / 15 | 55 / 100 |
| txt | 0 / 15 | 33 / 100 |
| png | 0 / 5 | 9 / 54 |
| others (docx, zip, jpg, mp3, zlib) | 0 | 0 |

(bin has no format check: validity is "not applicable" for every bin file, v1 and v2 alike.)

Simulated evidence (D71 item 3 recount, v2 arm added):

| quantity | v1 | v2 | synthetic bytes |
|---|---|---|---|
| benign rewrite flag rate, injected rate 0 / 0.01 / 0.05 | 0.000 / 0.006 / 0.030 | **0.017 / 0.023 / 0.047** | 0.002 / 0.012 / 0.049 |
| clean snapshots holding a flagged version, rate 0 / 0.01 / 0.05 | 0.009 / 0.24 / 0.71 | **0.51 / 0.63 / 0.86** | 0.09 / 0.36 / 0.84 |
| damaged versions detected | 0.947 | **0.875** | 1.000 |
| damage detected, txt / bin / csv | 0.94 / 0.88 / 0.83 | **0.59 / 0.66** / 0.79 | 1.00 |
| benign png flag rate | 0.020 | **0.167** | n/a |

- The v1 NapierOne arm had a lower natural false-flag rate than synthetic bytes; v2 has a higher
  one at rate 0 (0.017 vs 0.002), mostly png (0.167: the 9 invalid png files) and bin. Half of
  all clean snapshots hold a flagged version even with no injected benign invalidity, so
  verify_snap skips clean snapshots more often, which raises work lost for every evidence-using
  restore and shrinks SlowBurn's advantage.
- Damage detection also drops, mainly txt and bin, consistent with the more varied content.
- csv: 55% of the new benign csv files fail strict UTF-8, yet benign csv is never flagged in the
  simulation (0.000) and csv damage detection barely moves (0.83 to 0.79): the validity bit does
  not drive the csv decision. The CSV/TXT UTF-8 limitation (D71b, "recheck after the pools
  grow") is therefore real for txt (benign txt flags 0.010) and not for csv flags.
- The earlier caveat ("larger NapierOne effects may partly reflect a lower effective false-flag
  rate") is confirmed: with representative pools the NapierOne effects are smaller than synthetic
  bytes (C3' -3.8% vs -9.0%; C2 -14.0% / -19.6% vs -27.6% / -30.2%).

## 3. Detector AUROC, unchanged detector, held-out files vs new files

Striped 10% damage (file level): every type 1.000 on both, except bin 0.969 -> 0.984 and
**png 1.000 -> 0.931** (chunk 0.918); 9-type uniform mean 0.997 -> 0.991. The v1 column
reproduces the D71b table exactly. Largest change over all damage models and fractions 0.084
(png). The AUROC drop is small next to the simulation effect: the shift is in the benign flag
rate at the operating threshold (file p <= 0.01) and in per-type detection at that threshold,
not in ranking quality.

## 4. Consequences

- The NapierOne numbers in docs/claims.md are replaced by the v2 numbers (the v1 numbers were
  marked provisional until this rerun).
- No threshold, prior, validator or detector change follows from this (rule: detector stays as
  is). Whether png validity or the bin/txt detection drop should be addressed is a team
  question, and any change would need its own pre-registration.
- D73 and D74 were pre-registered on the D72 scenario with v1 pools; D73 ran on v1. Whether D74
  (not yet run) uses v1 or v2 pools is a team decision; v2 is the more representative choice.
