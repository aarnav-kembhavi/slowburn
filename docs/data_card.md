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
