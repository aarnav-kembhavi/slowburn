# D78 report: one fix attempt for the NapierOne detector (DEV, 2026-10-26)

Pre-registration: OPEN_QUESTIONS D78 draft, amendment 1 (power check, false-pass check, final
thresholds -0.02 / -0.05; 1bb6347, 7c7037a), implementation notes (6b1af30). Code ada76d8;
pipeline paper/scripts/d78_run.sh, run 12:14-13:41 (2026-10-26), exit 0, first attempt
(log results/d78_run.log; outputs results/dev_d78/). TEST never read.

## Verdict: NO candidate is accepted. The unchanged detector ships; D80 does not run.

Selection on FIX (v2fix, injected rate 0, 106,889 benign rewrite versions, 160 machines):

| candidate | benign flag rate (unchanged 0.0126) | upper CI | 1 | detection diff pooled [95% CI] | worst type | 2a | 2b | AUROC (unchanged 0.993) | 3 |
|---|---|---|---|---|---|---|---|---|---|
| F1 recalibration | 0.0126 | 0.0132 | fail | -0.034 [-0.039, -0.030] | bin -0.180 | fail | fail | 0.993 | pass |
| F2 validity transition | 0.0128 | 0.0134 | fail | -0.132 [-0.141, -0.123] | csv -0.456 | fail | fail | 0.990 | pass |
| F3 both | 0.0221 | 0.0228 | fail | +0.048 [+0.039, +0.056] | png -0.118 | pass | fail | 0.990 | pass |

No candidate met criteria 1-3 on FIX; none met 2 and 3 together, so by the registered rule the
"closest" is the lowest benign flag rate overall: F1, scored once on CHECK and not adoptable.

Single scoring on CHECK (v2check, 107,085 benign rewrite versions, 160 machines), F1 vs
unchanged: benign flag rate 0.0175 vs 0.0175 (upper CI 0.0184; criterion 1 needs <= 0.005 /
0.008: fail); pooled detection difference -0.032 [-0.037, -0.027] (2a: fail); worst type bin
-0.150 (2b: fail); AUROC 0.9934 vs 0.9934 (3: pass).

## Why it failed (descriptive)

- Every benign flag on FIX comes from png (1,344 of 1,344 for the unchanged detector), i.e.
  from the truncated files, which score at the ceiling of the raw score.
- F1: adding FIX benign files (4 truncated pngs among them) to the file-level calibration set
  raises the threshold, but the truncated pngs sit at the same ceiling score as clearly damaged
  files, so they stay flagged (p = 5 / 535 <= 0.01) while weaker damage drops below the new
  threshold (bin -0.18, txt -0.05).
- F2: in the simulator each benign rewrite draws a new pool file, so a truncated png written
  after a valid png IS a validity transition; F2 removes almost no png flags (1,344 -> 1,216)
  and, without the absolute validity bit, loses damage detection on csv / bin / txt / png.
- F3: F2's classifier with F1's calibration flags more benign csv / txt versions and fails png.
- Calibration and this feature change cannot separate a truncated benign file from a damaged
  one; both fail the same validity check with the same score. A fix would have to change the
  data (exclude defective files) or the validator, which D78 ruled out.

## Consequences (pre-registered)

- The unchanged detector stays for the frozen run; png / txt / bin remain limitations.
- D80 does not run (results/d80_run.log: "D78 accepted no candidate"). The png effect is
  reported as a limitation with the mechanism table (results/dev_png_mechanism.md).
