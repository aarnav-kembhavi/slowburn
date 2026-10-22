# Product retention defaults (D66 retention audit; DEV only, descriptive)

Written 2026-10-23, BEFORE any audit code or run. Each rule is a vendor default as documented
at the URL given (read on 2026-10-22/23); nothing here is tuned. The audit asks one descriptive
question: under the existing attack grid and the adopted restore (D64a verify_snap), how does
clean recovery fall with the true discovery delay for each product default? Nothing in
docs/claims.md changes on the basis of this audit.

## Rules

Two kinds of retention. **Per-file version histories**: every write to a file creates a new
version of that file, trimmed per file. **Snapshot products**: whole-volume or whole-backup
snapshots, trimmed per snapshot (daily snapshots, like every other policy in this repo).

| id | product | kind | rule as simulated | source |
|---|---|---|---|---|
| `dropbox_30d` | Dropbox Basic, Plus, Family | per file | every version superseded within the last 30 days is kept; no count limit | https://help.dropbox.com/security/version-history-overview ("30 days: Basic, Plus, and Family") |
| `dropbox_180d` | Dropbox Professional, Essentials, Business, Standard | per file | as above, 180 days | same page |
| `dropbox_365d` | Dropbox Business Plus, Advanced, Enterprise | per file | as above, 365 days | same page |
| `gdrive_30d_100v` | Google Drive (non-Google files: PDF, images, Office, ...) | per file | a version is deleted 30 days after it was superseded, or once it has 100 newer versions, whichever comes first | https://support.google.com/drive/answer/2409045 ("A version might be permanently deleted after 30 days or if there are 100 newer versions.") |
| `onedrive_personal_25v` | OneDrive, personal Microsoft account | per file | the last 25 versions (current included) | https://support.microsoft.com/en-us/office/view-previous-versions-of-office-files-5c1e076f-a9c9-41b8-8ace-f77b9642e2c2 ("If you sign in with a personal Microsoft account, you can retrieve the last 25 versions.") |
| `onedrive_personal_25v_30d` | same, variant | per file | last 25 versions AND superseded within 30 days | https://support.microsoft.com/en-us/office/restore-a-previous-version-of-a-file-stored-in-onedrive-159cad6d-d76e-4981-88ef-de6e96c93893 ("File version history is retained for 30 days."; the page does not say which account type, so this is a labelled variant, not the primary rule) |
| `onedrive_business_500v` | OneDrive for Business / SharePoint Online, organisation default | per file | the last 500 major versions, no expiry | https://learn.microsoft.com/en-us/sharepoint/set-default-org-version-limits ("Default Version History limits for your organization is set to Manual version history limits with 500 major version count limit and no expiration.") |
| `restic_docs_dwmy` | restic `forget --keep-daily 7 --keep-weekly 5 --keep-monthly 12 --keep-yearly 75` | snapshot | daily backups; keep the newest snapshot of each of the last 7 days, 5 weeks, 12 months, 75 years that hold a snapshot (calendar periods, restic semantics) | https://restic.readthedocs.io/en/stable/060_forget.html (worked example for daily backups) |
| `restic_docs_within` | restic `forget --keep-within-daily 7d --keep-within-weekly 1m --keep-within-monthly 1y --keep-within-yearly 75y` | snapshot | daily backups; newest snapshot per day within 7 days, per week within 1 month, per month within 1 year, per year within 75 years of the latest snapshot | same page (irregular-backup example) |
| `restic_keep_within_7d` | restic `forget --keep-within 7d` | snapshot | every snapshot within 7 days of the latest | same page (append-only example) |
| `restic_keep_last_1` | restic `forget --keep-last 1` | snapshot | only the newest snapshot | same page (first example) |
| `netapp_arpai` | NetApp ONTAP ARP/AI, NAS volume, defaults | snapshot | periodic snapshots are kept 12 hours (at daily resolution: only the snapshots of the discovery day and the day before); when ARP/AI suspects an attack, the snapshots taken before it are locked until the administrator responds (here: until discovery, i.e. the pre-attack snapshot of the day before the first detection is held); after a true-positive response they are kept 7 more days, which is after the restore and so does not change recovery | https://github.com/NetAppDocs/ontap/blob/main/anti-ransomware/learn-about-arpai.adoc ("Snapshots are normally retained for 12 hours"; "NAS volumes: If an attack is confirmed by file-analysis, snapshots created before the attack are retained until the administrator marks the attack as true or a false positive"; "7 days for true-positive retention"); option table: https://github.com/NetAppDocs/ontap/blob/main/anti-ransomware/modify-snapshot-options-arpai.adoc (docs.netapp.com returned 403; the GitHub source is NetApp's published docs repository) |

Notes on the sources, as found:
- Dropbox does not state a per-file version count limit; none is simulated.
- Google's "30 days" does not say from what. Primary: 30 days after the version was superseded
  (point-in-time semantics, as Dropbox and SharePoint state theirs). Sensitivity, reported
  separately and labelled: `gdrive_30d_100v_created`, 30 days after the version was created.
- The OneDrive personal count (25) is from the Office "view previous versions" page; the OneDrive
  restore page says 30 days without naming an account type. Both are run; 25 versions is primary.
- SharePoint has an "Automatic" setting that admins can choose; the documented organisation
  default is manual, 500 major versions, no expiry. Minor versions are not modelled.
- NetApp ARP/AI is detector-driven. Its own detector is not available, so its trigger is modelled
  with this repo's write-time flags: ARP/AI fires on the first damaged version that is flagged
  (probability q per damaged write). Benign flags are assumed to be cleared by the administrator
  as false positives (24 h retention, then normal), so they never pin a snapshot through to the
  discovery day. This is an assumption, not a vendor statement.

## How the audit simulates them

- **Grid**: the existing attack grid of D63 (seed 202, DEV split, four start-time worlds on days
  28-280, 40 reps per world, slow partial attack at 0.5 files per day, striped 10% damage, benign
  invalid rate 0.01), q in {0, 1}. True discovery delays: 1, 2, 3, 5, 7, 10, 14, 21, 30, 45, 60,
  90, 120, 180, 270, 365, 400 days.
- **Restore**: the adopted one (D64a verify_snap, gate 0.8, frozen operating point, assumed hard
  bound M = 60 for the restore posterior), shared by every product.
  - Snapshot products: `verified_restore` unchanged, on the snapshots the rule holds.
  - Per-file products: a point-in-time restore that mirrors verify_snap. Candidate restore points
    are every day 0..discovery that passes the same gate, newest first. At a candidate T each
    file resolves to its newest retained version written on or before T, or, if the product kept
    none that old, to its oldest retained version. A candidate is rejected if any resolved version
    carries a write-time flag. The selection, the residual-damage count and the work-lost
    accounting are those of verify_snap ("select").
- **Clean recovery** is the repo's definition: 1 only if no damaged file remains after the
  restore (`clean_recovery = int(residual == 0)`).
- **A second curve, "clean point held"**, isolates retention from the restore: 1 if restoring to
  the day before the attack (T = s - 1), with the product's retained versions, would leave no
  damaged file.
- **Per-file churn from FSL Homes** (item 2 of the team request). Each simulated machine takes
  one FSL user (drawn per machine from the seed) and 40 of that user's regular files, sampled
  uniformly. These must be present in every non-empty snapshot of the 48 complete,
  checksum-verified days, 2011-09-16..2011-11-03. A file is rewritten on a day when its content
  digest changes from the previous non-empty snapshot. Empty snapshots (0 files) count as missing
  days. The simulator's benign edits are replaced by these real per-file rewrite days, replayed
  in order from a random offset and wrapping around (circular), for as many days as the machine
  needs. The attacker, damage model and detector are unchanged. Daily snapshots show at most one
  rewrite per file per day, but a sync product creates a version for every save. So version
  counts are LOWER bounds, and count-limit results are optimistic.
- **Attack model consequence**, stated before the run: in this grid a damaged file gets no further
  writes (the simulator's attacker writes each file once and benign edits skip damaged files).
  So any count limit of 2 or more keeps every file's last clean version. Count limits can then
  only change which older version a restore lands on, not whether a clean version exists.
  Attacks that write a file several times (version flushing) are NOT in the grid and are not
  added here.
- **Outputs**, per product and q: mean clean recovery and mean "clean point held" against true
  delay (curve), and the first grid delay at which recovery drops below 0.5 and below 0.1.
  These are reported as the first grid delay below the threshold, not interpolated.

Model only: no code here writes, rewrites or flushes files on any real system.
