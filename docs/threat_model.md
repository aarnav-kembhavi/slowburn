# Threat model: simulation rules (working notes behind `paper/sections/threat_model.tex`)

Defensive study only. The attacker exists only as simulation parameters (start day, discovery
delay, files damaged per day, damage placement and fraction, targeted types) and as public
dataset files (NapierOne). No encryptor, evasion technique or tampering code is written.

## Rule D62: persistence of damage (decided 2026-10-22, before any rerun)

**A file the attacker damaged stays damaged until it is restored.** The user never edits a
damaged file afterwards, and never overwrites it entirely. Each damaged file therefore has
exactly one damaged version (written on its damage day), held by every snapshot from that day
on, and it is damaged in all of them.

The detector is deterministic per version: scanning a version again returns the flag it got
when it was written. With detection probability q = 1 every damaged version is flagged, so a
snapshot that holds a damaged version can only "verify clean" if verification does not look at
that version.

Why this rule:

- It is what the simulator already does (`slowburn/sim/scenario.py`, `_benign_edits` picks only
  from files not in `damaged_on`), so stating it changes no result.
- Partial encryption (striped damage of a few percent) leaves most formats unopenable or
  corrupt in the user's application, so incremental user edits of a damaged file are not
  realistic.
- A full overwrite by the user (re-download, re-export, saving a fresh copy over it) does
  happen in practice. It is left out on purpose because it only makes recovery easier: the
  overwritten file is clean at discovery without any restore. Leaving it out is the
  conservative (harder) case for every policy alike. This is a stated limitation.
- Under this rule a damaged file can never "heal" between snapshots, so any snapshot taken on or
  after a file's damage day is a damaged restore point for that file.

## Consequence for verification (D62 finding)

Restore-time verification (D29) scans only versions written on or after L, the 0.001 quantile
of the discovery-conditioned start posterior, and the file selection restores only files changed
on or after max(restore point + 1, L). Versions older than L are treated as clean. When the
assumed delay bound is shorter than the true delay, L falls after the true start, so damaged
versions written between the start and L are neither scanned nor restored, even at q = 1. See
OPEN_QUESTIONS D62.
