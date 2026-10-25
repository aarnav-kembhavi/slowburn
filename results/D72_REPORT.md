# D72 and D72-C2R report (DEV, 2026-10-24)

Pre-registration: OPEN_QUESTIONS D72 (506a585), amendments 133868f and 2b01cda (scoring option
(iii): criteria must pass under SlowBurn AND Bar-On recursive retention). Post-D71b detector.
Runs (results/overnight_queue.log): dev_d72_full 21:22-21:46, dev_d72_worst 21:46-21:52,
dev_d72_bytes_synthetic 21:52-23:38, dev_d72_bytes_napierone 23:38-01:01 (2026-10-23/24), all
exit 0, first attempt. Outputs: results/dev_d72_report/{summary,criteria,verdict}.csv,
results/dev_d72_c2r/{c2_restated,d67_reproduction}.csv, logs results/dev_d72_*_report.txt.

## 1. D72 verdict: method C (monotone changepoint per file) is NOT adopted

C must beat both A (verify_snap) and B (per-file walk-back) on criteria a, b and c, in every
scored unit, under both SlowBurn and Bar-On recursive retention. It does not.

| unit | C vs A | C vs B |
|---|---|---|
| full grid, q 0.2 / 0.5 | fails a and b | fails c |
| full grid, q 1 | fails b (residual +0.001, CI [0, +0.003]) | fails c |
| worst grid, q 0.2 / 0.5 | fails a and b | fails c |
| worst grid, q 1 | passes | fails c |
| synthetic bytes | passes | fails c |
| NapierOne bytes | fails a and b | fails c |

Same pattern under SlowBurn and Bar-On recursive (criteria.csv). C loses to A on recovery
whenever detection is imperfect, and loses to B on per-file work lost everywhere.

SlowBurn retention, means (recovery / residual damaged files / per-file work lost, hours):

| unit | A verify_snap | B walk-back | C changepoint | D oracle per file | E oracle snapshot |
|---|---|---|---|---|---|
| full, q 0.2 | 0.980 / 0.05 / 6452 | 0.001 / 13.4 / 175 | 0.801 / 0.76 / 3914 | 1.000 / 0 / 736 | 1.000 / 0 / 3712 |
| full, q 0.5 | 0.995 / 0.01 / 6222 | 0.015 / 8.4 / 401 | 0.876 / 0.23 / 3879 | 1.000 / 0 / 736 | 1.000 / 0 / 3712 |
| full, q 1 | 1.000 / 0 / 5944 | 1.000 / 0 / 793 | 0.999 / 0.001 / 3701 | 1.000 / 0 / 741 | 1.000 / 0 / 3712 |
| synthetic bytes | 1.000 / 0 / 5952 | 1.000 / 0 / 766 | 1.000 / 0 / 3711 | 1.000 / 0 / 710 | 1.000 / 0 / 3704 |
| NapierOne bytes, v2 pools (D75; the source) | 0.999 / 0.001 / 7130 | 0.230 / 2.02 / 715 | 0.969 / 0.033 / 3848 | 1.000 / 0 / 712 | 1.000 / 0 / 3640 |
| NapierOne bytes, v1 pools (sensitivity only) | 1.000 / 0 / 4801 | 0.504 / 0.85 / 670 | 0.994 / 0.006 / 3212 | 1.000 / 0 / 679 | 1.000 / 0 / 3316 |

C vs A, per-file work lost: -33% to -40% in every unit (pooled CIs all below 0), but recovery
-0.12 to -0.19 at q 0.2 / 0.5 and -0.005 [-0.011, -0.001] on NapierOne bytes. q = 0 (reported,
not scored): C recovery 0.800 vs A 0.959.

Findings the criteria do not capture (descriptive, no adoption implied):
- B is near the per-file oracle when detection is perfect: q 1 and synthetic bytes, recovery
  1.000 and per-file work lost 793 / 766 h vs oracle 741 / 710 h (A: 5944 / 5952 h). It closes
  99% of the A-to-oracle work-lost gap there. With any missed damage it collapses: recovery
  0.001 / 0.015 at q 0.2 / 0.5 and 0.230 on NapierOne bytes v2 (detection 0.875; v1 0.504), because an
  unflagged damaged version is taken as clean.
- C closes 36% to 47% of the A-to-oracle per-file work-lost gap (zip and non-zip alike) at a
  recovery cost that grows as detection weakens.
- The oracle snapshot restore (E) loses about as much per-file work as C: most of A's excess over
  E is restore-point choice, most of E's excess over D is the snapshot granularity itself.
- Per-file restore choice, not retention, dominates per-file work lost: A to D is a 7 to 8x gap
  at fixed retention, larger than any retention effect in C2 / C3'.

Consequences fixed by the pre-registrations: D73 uses restore A as primary (D73 amendment); D74
uses method B as its per-file restore ("D72 method C if adopted, else method B"). No second
iteration of C without a new pre-registration.

## 2. D72-C2R: C2 restated against stronger baselines

SlowBurn (w 0.75, verify_snap) vs each baseline, paired on the same machines, count budgets,
pooled over worlds, budgets and benign rates; 95% machine-cluster bootstrap CIs. Sanity check:
the default GFS / Tower of Hanoi rows reproduce D67 post-fix exactly (d67_reproduction.csv).

| baseline | synthetic bytes: recovery diff / work lost | NapierOne bytes, v1 pools (sensitivity only; v2 below): recovery diff / work lost | holds |
|---|---|---|---|
| GFS (default) | +0.426 / -27.6% [-31.0, -24.0] | +0.426 / -34.4% [-37.7, -30.8] | yes / yes |
| Tower of Hanoi (default) | +0.427 / -30.2% [-32.8, -27.5] | +0.427 / -35.7% [-38.3, -32.9] | yes / yes |
| Bar-On recursive | +0.001 [-0.000, +0.002] / -4.4% [-7.5, -1.1] | +0.002 [0.000, +0.004] / -3.4% [-6.3, -0.3] | yes / yes |
| Bar-On round robin | +0.000 / -6.8% [-10.0, -3.6] | +0.000 / -5.1% [-8.0, -2.1] | yes / yes |
| GFS equal horizon (K = 12 only) | 0.000 / **+16.1% [+12.1, +20.1]** | 0.000 / **+6.9% [+3.6, +10.5]** | no / no |
| ToH equal horizon (K = 8, 12) | +0.059 [+0.038, +0.083] / **+10.1% [+6.3, +13.9]** | +0.059 / +3.0% [-0.5, +6.4] | no / no |

- Against Bar-On recursive and round robin, C2 holds pooled but the effect is small (-3% to
  -7%) and not uniform: in the early world SlowBurn loses MORE work than both (+10% to +11%, CI
  above 0, both arms); late is significantly lower (-12% to -18%); bursty is significantly
  lower against round robin only (-10%); uniform is not significant.
- Against the equal-horizon GFS / Tower of Hanoi configurations (the D68 variants, horizon >= M),
  C2 fails: SlowBurn loses more work (+7% to +16%, significant except ToH-eqh on NapierOne) at
  equal recovery (GFS-eqh) or higher recovery (+0.059 vs ToH-eqh). These variants exist only at
  K = 12 (GFS) and K in {8, 12} (ToH), so the comparison covers those budgets only.
- SlowBurn's recovery advantage over default GFS / ToH (+0.43) disappears against every stronger
  baseline: the default configurations are weak on recovery because their horizon is shorter
  than the assumed discovery bound.

**Update 2026-10-25 (D75): NapierOne is restated on the v2 pools; the v1 column above is a
sensitivity row only.** NapierOne bytes, v2 pools (results/dev_d72_bytes_napierone_v2pool):

| baseline | v2 recovery diff / work lost | holds |
|---|---|---|
| GFS (default) | +0.425 / -14.0% [-18.3, -9.4] | yes |
| Tower of Hanoi (default) | +0.428 / -19.6% [-23.0, -16.0] | yes |
| Bar-On recursive | +0.002 [0.000, +0.006] / -5.3% [-8.6, -2.0] | yes |
| Bar-On round robin | +0.001 / -6.7% [-10.5, -2.9] | yes |
| GFS equal horizon (K = 12) | +0.001 / **+24.9% [+19.8, +30.3]** | no |
| ToH equal horizon (K = 8, 12) | +0.061 / **+14.9% [+10.5, +19.8]** | no |

By world on v2: SlowBurn loses more work than both Bar-On variants in the early world (+8.6%,
+10.7%, CIs above 0); vs default GFS the early world is +4.2% [-2.9, +11.7]. The D67 v1
reproduction check still matches exactly (napierone_bytes_v1pool rows).

Status for claims.md: C2 is restated as holding against the default GFS / Tower of Hanoi
configurations and (small, not uniform across worlds) against Bar-On, and failing against the
equal-horizon configurations. All provisional NapierOne caveats still apply.
