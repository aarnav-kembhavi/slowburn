# Data card

Status: DRAFT (2026-10-17). Downloads in progress under the team's approval (OPEN_QUESTIONS D58);
the "What was kept" section is filled from `data/MANIFEST.json` once they finish. Nothing in
`data/` is committed (gitignored).

## Data actually used so far (correction, 2026-10-23)

**Every DEV result so far uses synthetic benign files and synthetic damage. NapierOne is
downloaded but not yet used by any experiment.**
- Retention, restore and claims runs (C1, C2, C3', F1-F3, D45-D65, D63) simulate files as
  abstract chunk tokens (`content: tokens`), damage as fresh random tokens, and detector evidence
  as an abstract detection probability q plus a benign flag rate. No file bytes are involved.
- Detector runs (`configs/detector*.yaml`) use `benign_source: synthetic` (the `slowburn.sim`
  generator) and `damage_source: synthetic_random`. The NapierOne loader exists, but no committed
  config selects it, and `benign_source: napierone` raises NotImplementedError.
- FSL Homes churn is used only by the D66 retention audit (per-file rewrite days; no content).
The rows below marked NapierOne describe the planned use (decision of 2026-10-23: integrate
before the fresh test set), not the results reported so far.

**Update (2026-10-23, later):** NapierOne bytes are now used by the D67 byte arm and D71
diagnostics (`configs/dev_d67_full_napierone.yaml`, detector `configs/detector_napierone.yaml`);
the paragraph above describes the state before D67.

**Known limitations of the NapierOne use (D71b):**
- Small DEV content pools. Simulated machines draw benign contents from the DEV pool files of at
  most 1 MiB: txt 15, csv 15, bin 15, docx 13, zip 5, png 5, jpg 14, mp3 15, zlib 5. A file type
  with 5 files is a handful of distinct contents repeated across every machine. The pools are to
  be enlarged per type (seeded, stratified, rule in OPEN_QUESTIONS first) before the fresh test
  set is generated.
- Strict UTF-8 validity fails on 0.158 of benign NapierOne CSV and 0.042 of benign TXT files in
  the detector data (real files in other encodings). Not changed; at injected benign rate 0 they
  produce no benign flags in the simulated machines (D71 item 3). Rechecked after the pools grow.
- Zip validity before D71b: PPMd-compressed zips were wrongly invalid (Python zipfile does not
  decode PPMd); fixed with a PPMd decoder, detector rebuilt (results/CHANGELOG.md).

## What is real and what is simulated

| component | source | real or simulated |
|---|---|---|
| benign file contents (v2 experiments so far) | `slowburn.sim` synthetic generator | simulated |
| benign file contents (P2 onward) | NapierOne benign, 100 files per type | real files (2021 collection) |
| damaged file contents | NapierOne ransomware-encrypted, 100 files per family; partial damage, if needed, uses blocks taken from these real encrypted files | real encryptor output; any partial pattern built from it is simulated and will be labelled as such |
| file churn: which files change, when, how much | FSL Homes `2011-8kb-only` | real metadata and chunk hashes; **from 2011 student home directories** at Stony Brook University (13 users, Sept-Dec 2011) |
| mapping of churn onto content | file extension in the FSL trace -> NapierOne file of the same type | simulated ("trace driven, semi synthetic") |
| attack start, speed, files hit, discovery delay | simulator parameters | simulated |
| detector evidence | abstract detection probability and benign flag rate (v2); LightGBM chunk detector trained on separate NapierOne files (later) | simulated / model output |

**D75 enlarged NapierOne simulation pools (2026-10-24, OPEN_QUESTIONS D75 rule).** Pool
version v2 = v1 plus the DEV half of a seeded sample of up to 200 files per type (<= 1 MiB, no
content hash in the tiny set, no duplicates), the other half reserved for the fresh TEST pool.
Detector training and calibration are unchanged. Archives (per-subset "small", 1,000 files per
subset, s3://napierone.com NapierOne/Data/<T>/<T>-small.zip) were downloaded one at a time,
matched the published SHA-256, and were deleted after sampling; record in
data/napierone/benign_v2/manifest.json. zip and png have fewer unused files than 200, so their
v2 DEV pools stay below 100 (69, 59).

| type | source | candidates | v1 DEV | v2 DEV | v2 TEST additions | archive SHA-256 matches published |
|---|---|---|---|---|---|---|
| txt | TXT-small.zip | 846 | 15 | 115 | 100 | yes |
| csv | CSV-small.zip | 821 | 15 | 115 | 100 | yes |
| bin | BIN-small.zip | 836 | 15 | 115 | 100 | yes |
| docx | DOCX-small.zip | 784 | 13 | 113 | 100 | yes |
| zip | NapierOne-tiny unused files | 127 | 5 | 69 | 63 | n/a (no download) |
| png | NapierOne-tiny unused files | 108 | 5 | 59 | 54 | n/a (no download) |
| jpg | NapierOne-tiny unused files | 474 | 14 | 114 | 100 | n/a (no download) |
| mp3 | MP3-small.zip | 651 | 15 | 115 | 100 | yes |
| zlib | ZLIB-small.zip | 269 | 5 | 105 | 100 | yes |

**Evaluation finding (D75, stays in): content pool size changed the NapierOne effect sizes by
about 2.5x.** Same machines, seeds, detector and grid; only the benign pool grew from 5 to 15
(v1) to 59 to 115 files per type (v2). C2 vs default GFS -34.4% -> -14.0% (2.5x), vs default
Tower of Hanoi -35.7% -> -19.6% (1.8x); C3' -11.9% -> -3.8% (3.1x). Cause: the small pools had
no benign files failing validity and easier-to-detect damage (benign false flags at injected
rate 0: 0.000 -> 0.017; damage detection 0.947 -> 0.875). Real-data evaluations with a few
files per type can overstate evidence-based gains; results/D75_REPORT.md.

**Truncated png files (counted 2026-10-25; kept in the pools, team decision).** 13 of the 100
NapierOne-tiny PNG-FROM-WEB files are exactly 1,048,576 bytes (none larger) and fail both our PNG
check and PIL ("Truncated File Read"): NapierOne cut these web downloads at 1 MiB. The v1 DEV
png pool holds 0 of them (of 5); the v2 DEV png pool holds 9 (of 59). The TEST pool was not
inspected. They stay in every scored pool; a labelled, unscored sensitivity row excludes them
(pool v2_notrunc, 50 png files; configs/dev_d67_full_napierone_v2notrunc.yaml).
Result (2026-10-26, unscored): without the 9 truncated pngs, SlowBurn vs default GFS work lost is
-32.2% [-35.7, -28.2] (v2: -14.0%) and C3' -9.7% [-11.0, -8.5] (v2: -3.8%); recovery unchanged.
Most of the v1 -> v2 effect shrinkage comes from these 9 files (results/PNG_SENSITIVITY.md).

## Sources and licences

- **NapierOne** (Edinburgh Napier University): https://github.com/simonrdavies/NapierOne,
  https://registry.opendata.aws/napierone/, bucket `s3://napierone.com` (eu-north-1). Licence:
  Edinburgh Napier University License Agreement (permissive, attribution requested); per-subset
  licence and attribution terms are in each subset's PDF. Ransomware archives contain encrypted
  files only ("the actual ransomware sample (executable) is not included"). Partial or
  intermittent encryption is not documented and is measured by us.
- **FSL Homes** (File systems and Storage Lab, Stony Brook University):
  https://tracer.filesystems.org/traces/fslhomes/ and SNIA IOTTA
  (https://iotta.snia.org/traces/static/5231), SNIA Trace Data Files Download License. Paths and
  chunk hashes are anonymized; file extensions are kept. SNIA warns the traces are over 10 years
  old: the churn reflects 2011 student home directories, not a modern office or server workload.

## Handling

- Archives are untrusted data: nothing in them is executed; zip members with absolute paths or
  `..` are refused; the NapierOne benign folders APK, DLL, ELF, EXE and POWERSHELL are not
  extracted.
- Every download is checked against the server's byte count, and against the published SHA-256
  where one exists (FSL `.sha256` files; NapierOne `*_zip_hashes.txt` when it lists the archive).
- Disk rules: `data/` at most 100 GB, at least 45 GB kept free on C:, checked before every
  archive and extraction; nothing deleted to make room. FSL archives stay compressed and are read
  by streaming.

## Counts per type

**NapierOne encrypted (100 per family):** 30 family archives downloaded (3,914,326,784 bytes),
each matching its published SHA-256; extracted to `data/napierone/encrypted/<FAMILY>/`, 3,030
files (101 per family: 100 encrypted files, named `<seq>-<type>.<type>.<family extension>`, plus one description PDF),
4,301,073,838 bytes.

**NapierOne benign (100 per subset):** `NapierOne-tiny.zip` (17,737,521,386 bytes) is a zip of
100 per-subset zips (44 types plus variants such as `-PASSWORD`, `-ENCRYPTED`, `-NOMAGIC`,
`-FROM-WEB` and per-compression 7ZIP/ZIP subsets). The 100 inner zips were extracted to
`data/napierone/benign/` (17,737,505,702 bytes); their contents are read directly from the inner
zips when needed, not unpacked, to leave room under the cap. The APK, DLL, ELF, EXE and POWERSHELL
inner zips were written as still-compressed archives (the type filter matched folder names, not
these file names); nothing in them has been opened or run, and they are excluded from all use.
Per-type file counts: to be filled when the inner zips are indexed.

## What was kept

To be filled from `data/MANIFEST.json` when the downloads finish (for FSL: first and last day,
users, number of days, bytes, and why the block ends).
