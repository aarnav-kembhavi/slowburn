# Data availability (P2 pre-download report, 2026-10-17)

Nothing has been downloaded. Everything below comes from public web pages and public bucket and
directory listings (metadata only), read on 2026-10-17. Sizes from directory listings that round to
MB are marked approximate.

## NapierOne (benign originals and ransomware-encrypted files)

- **Host:** public S3 bucket `napierone.com` (eu-north-1), no account needed; also
  www.napierone.com ("some simple registration may be required"). Documentation:
  https://github.com/simonrdavies/NapierOne, https://registry.opendata.aws/napierone/.
- **Licence:** Edinburgh Napier University License Agreement (permissive, MIT-style, attribution
  requested); each subset has its own licence and attribution terms in its PDF (e.g. Open
  Government Licence v3 for government documents).
- **Benign data:** 44 file-type folders under `NapierOne/Data/` (7ZIP, APK, BIN, BMP, CSS, CSV,
  DLL, DOC, DOCX, DWG, ELF, EPS, EPUB, EXE, EXTRA, GIF, GZIP, HTML, ICS, JAVASCRIPT, JPG, JSON,
  MKV, MP3, MP4, ODS, OXPS, PDF, PNG, POWERSHELL, PPT, PPTX, RANDOM, RAR, SVG, TAR, TIF, TXT,
  WEBP, XLS, XLSX, XML, ZIP, ZLIB). Combined archives: `NapierOne-tiny.zip` 17,737,521,386 bytes
  (100 files per type), `NapierOne-small.zip` 152,484,354,052 bytes (1,000 per type),
  `NapierOne-total.zip` 710,033,086,132 bytes (all; ~5,000 per type). Per-type archives
  exist in each type folder (sizes not yet listed). The GitHub page says the uncompressed total
  is "approaching 2TB". Note: the APK, DLL, ELF, EXE and POWERSHELL folders contain executables
  and scripts; we would not download them.
- **Ransomware-encrypted files:** `NapierOne/Data/EXTRA/`, 30 families (AVOSLOCKER, BADRABBIT,
  BLACKBASTA, BLACKCAT, BLACKMATTER, CERBER, CHIMERA, CLOP, CONTI, CRYPTOLOCKER, CUBA, DARKSIDE,
  DHARMA, GANDCRAB, HELLOKITTY, JIGSAW, LOCKBIT, LORENZ, MAZE, MEDUZALOCKER, NETWALKER, NOTPETYA,
  PHOBOS, RANSOMEXX, RYUK, SODINOKIBI, SUNCRYPT, TESLACRYPT, WANNACRY, WASTEDLOCKER). The README
  says the archives hold files encrypted by the strain with the listed SHA256 and that "the
  actual ransomware sample (executable) is not included". Per family: tiny (100 files)
  13,376,034 to 152,069,109 bytes, small (1,000 files) 99,446,249 to 913,834,883 bytes, total (5,000 files) 2,551,660,034
  to 4,245,856,948 bytes. Sums (decimal GB, from exact byte counts): 30 tiny archives
  3.914326784 GB; 30 small archives 22.661377845 GB; 29 plain total archives 109.510027422 GB
  (SODINOKIBI's total exists only as `RANSOMWARE-SODINOKIBI-total.zip`, 4,018,692,867 bytes;
  with it, 113.528720289 GB). A `RANSOMWARE-<family>` copy of 12 families duplicates the plain
  names.
- **Partial / intermittent encryption coverage: NOT documented.** Neither the README, the GitHub
  page nor the paper says whether files are fully or partially encrypted, or with what pattern.
  Several of the listed families are reported elsewhere to encrypt large files only partly or
  intermittently (e.g. a 2025 study, arXiv 2510.15133, built on NapierOne files, tabulates
  intermittent modes per family), but that is not part of NapierOne's documentation. The only
  way to know is to measure it on the files (per-block entropy against the matching original).
  Proposed first step, if you approve: download only the 30 tiny archives (3.914326784 GB) and measure
  the encrypted fraction and pattern per family; if partial coverage is thin, simulated partial
  damage uses blocks taken from these real encrypted files (your decision 7), stated in the data
  card.
- **NapierThree:** `rw_speed_comparison_paper_dataset.zip`, 90,073,428,009 bytes (a ransomware
  speed-comparison dataset; contents not yet inspected).

## FSL Homes (churn traces)

- **Host:** https://tracer.filesystems.org/traces/fslhomes/ (plain directory listing, no
  registration seen); also SNIA IOTTA (https://iotta.snia.org/traces/static/5231, behind a
  browser check, "free to download under the terms of the SNIA Trace Data Files Download
  License"). IOTTA lists the whole FSL Homes collection (2011-2015) at about 2.88 TB and carries
  the warning that the traces are over 10 years old.
- **Content:** daily (when possible) fs-hasher snapshots of student home directories on a shared
  network file system at Stony Brook; 38 users over three years, 4-11 active at a time.
  Coverage Sept 2011 - May 2014 (release 1), Aug - Nov 2014 (release 2), extended to April 2015.
- **Format:** one `fslhomes-userNNN-YYYY-MM-DD.tar.bz2` per user and day (plus `.sha256`), read
  with `hf-stat` from fs-hasher 0.9.5. Per file: anonymized path (parent-child structure kept,
  equal names map to equal anonymized names), size, blocks, chunk count, UID/GID, permissions,
  atime/mtime/ctime, hardlinks, device, inode, and per chunk: anonymized hash, size, compression
  ratio. **File extensions are NOT anonymized**, so content can be mapped from NapierOne by type.
  Average chunk size 8 KiB until 2012-01-25; after that, seven chunk sizes (2-128 KiB) per
  snapshot, which makes later archives much larger.
- **Sizes by folder (from listings; approximate):**
  - `2011-8kb-only/`: 2011-09-10 to 2011-12-31, 13 users, ~86 daily snapshots per user (gap
    2011-11-13 to 11-30 and a few single days), roughly 80-90 GB in total (listing partly
    summed; user028's tail not read).
  - `2012-8kb-only/`: 2012-01-01 to 2012-01-25, 13 users, 23 snapshots each, ~27 GB (IOTTA:
    26.6 GB). Too short alone for 60-day delays.
  - `2012/`, `2013/`, `2014/`, `2015/`: all chunk sizes; IOTTA lists 2012 at 1.29 TB; the
    visible part of `2013/` alone is ~156 GB.
- **fs-hasher / hf-stat:** source tarball `fs-hasher-0.9.5.tar.gz` on the same site; it would
  have to be built (C) to read the archives. Building it is an install outside the repo unless
  built inside the repo's `tools/`; your call.
- **Proposed first step, if you approve:** `2011-8kb-only/` (~80-90 GB, ~107 days with one
  18-day gap) as the churn source, plus fs-hasher 0.9.5 built in a gitignored `tools/`.

## Govdocs1

Not checked in this pass (not requested yet).
