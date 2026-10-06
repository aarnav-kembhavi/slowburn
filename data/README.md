# Datasets

Nothing here is downloaded automatically. Place datasets manually; loaders fail with a clear
message if a path is missing. This directory is gitignored (except this file).

## NapierOne -> `data/napierone/`

Public corpus of common file types plus versions encrypted by real ransomware families.
Primary source of real damaged-vs-benign chunks. May require registration.

Use in this project: real encrypted bytes replace the seeded random bytes as the `DamageSource`
(spliced into the same offsets for the striped / whole-chunk damage models), and the benign
originals extend the hard-negative set. Rows that use it are tagged `damage_source=napierone`.

Expected layout: **to be confirmed once the download is in hand** (see `OPEN_QUESTIONS.md`).
The loader will be configured from `configs/` rather than hardcoding the directory structure.

## RanSAP -> `data/ransap/`

Open dataset of storage access patterns under real ransomware. Contains I/O traces, not file
contents, so it is used only to calibrate the churn and attack-timing simulator (realism checks),
never as detector training data.

## Synthetic data (always available)

`slowburn/sim/content.py` generates benign files of each type with the real encoders (zipfile,
Pillow PNG/JPEG, LAME MP3, zlib, lzma) applied to synthetic source material. Damage without a
dataset sample is seeded random bytes (`damage_source=synthetic_random`).
