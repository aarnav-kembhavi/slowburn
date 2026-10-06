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
