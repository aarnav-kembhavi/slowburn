# Morning report: 2026-10-17 (unattended night of 2026-10-16)

Everything here is DEV (design) data from the simulator: no TEST set was generated or run, nothing
was downloaded or installed, nothing was pushed, and no paper claim was edited. Numbers are copied
from the result CSVs at full printed precision; each table names its source. All data is
synthetic (`benign_source=synthetic`, `damage_source=abstract_token`). Full entries with every
number are in `results/CHANGELOG.md`; decisions in `OPEN_QUESTIONS.md` D42-D51.

## TL;DR

1. **Done:** P0 (gate day logged per restore, v1 TEST marked spent, prototype appendix); P1
   (simulator v2: four generating worlds, byte budgets, worst-case timing grid, assumed-delay
   sweep; new DEV seed 202); baseline numbers per world; method v2 stages A and B.
2. **Claim (3) does not reproduce on v2 DEV (D50, your decision).** With the flat timing
   assumption fixed and the generating world varied, prior-only recovers 0.97575-0.986 in every
   world, so there is nothing for detector evidence to rescue: SlowBurn (v1) minus prior-only =
   -0.004583 to +0.00125. Evidence lowers work lost in every world (by 27.164-133.156 h) and
   raises recovery under byte budgets (+0.021555 to +0.055667). I did not touch the claim.
3. **Claims (1) and (2) hold on v2 DEV:** GFS 0.534417-0.61125 and Tower of Hanoi
   0.52075-0.5935 recovery; prior-only and SlowBurn 0.97575-0.986 (count budgets).
4. **Method v2 = blind-detector weight 0.5, fixed gate.** Chosen by the rules fixed before the
   runs (D48, D49). It removes the q = 0 penalty (worst-world excess over prior-only 0.00625,
   was 0.031667) and is at or above prior-only's recovery in every world with lower work lost.
   The adaptive gate failed its rule and is not adopted. On the full v2 DEV grid it reaches 0.982708 recovery / 1601.852 h work lost (count
   budgets; prior-only 0.980583 / 1721.6945, v1 0.979708 / 1644.471). On the fixed-start
   worst-case grid at q = 0 it is still below prior-only at K = 4, 6 and 8 (largest gap
   0.01625 at K = 8).
5. **Incident (D51):** method stage A ran twice at once for ~95 min (10 workers, above the cap).
   Data verified and the CSV rebuilt from the per-machine cache; details below.
6. **New findings:** an assumed maximum delay shorter than the true one collapses recovery for
   every policy (assumed 14 d: prior-only 0.35125); byte budgets are harsh under the simulated
   churn (14 days of storage: even the oracle recovers only 0.37-0.41); work lost above the
   oracle splits about evenly between the restore gate (439.893 h) and retention spacing
   (421.849 h).

## 1. What is done (commits)

| step | what | commit(s) |
|---|---|---|
| P0 | `gate_day`, `restore_p_clean` logged per restore (with `gate_candidates`, `verified`); DEV v2 rerun row-identical to `results/headline_dev_v2` (576000 rows, 45 columns); v1 TEST spent (D43); prototype appendix `appendix_prototype.tex` (manuscript source; not kept in this repository) with `table_gate_q.tex` | d6424a6 |
| P1 | `slowburn/sim/worlds.py` (uniform, early, late, bursty), `slowburn/retention/bytes.py` (exact unique bytes, byte budgets via each policy's own deletion rule), worst-case grid and assumed-delay sweep configs, Oracle keeps today's snapshot | 6158122 |
| DEV | `results/dev_v2` (2400 machines), `results/dev_v2_worst` (480), `results/dev_v2_delay` (640 x 6 variants) | 544ba32, a514088, ac1862c, 925c516 |
| P4 | blind-detector weight and adaptive gate options, mechanical selection rules (`slowburn/bench/method_v2.py`), stage A and B runs, full-grid comparison | cab1e61, 1de5602, 3ea8a3b, 706eb7a, e10b518, a8687fd, and the commit containing this report |

Tests pass and ruff is clean at every commit.

## 2. Per-world results (v2 DEV, method v1 = the frozen operating point)

Source: `results/dev_v2/world_summary.csv`. Count budgets K = 4, 6, 8, 12 pooled, all 15 evidence
cells and 5 delays (12000 rows per world and policy). Clean recovery / whole-system work lost (h).
Oracle-ideal work lost is 772.8 h in every world.

| world | prior-only | SlowBurn | GFS | Tower of Hanoi | keep last N | keep first | oracle |
|---|---|---|---|---|---|---|---|
| uniform | 0.979083 / 1687.168 | 0.9795 / 1642.93 | 0.563583 / 2488.84 | 0.545833 / 2514.428 | 0.05 / 3860.052 | 0.999833 / 4013.152 | 0.999833 / 777.354 |
| early | 0.9815 / 1544.374 | 0.976917 / 1517.21 | 0.61125 / 1781.774 | 0.52075 / 1982.586 | 0.049917 / 2720.888 | 0.999833 / 2818.846 | 0.999833 / 776.85 |
| late | 0.97575 / 1860.822 | 0.977 / 1756.486 | 0.534417 / 3474.616 | 0.585917 / 3368.278 | 0.05 / 5721.132 | 1.0 / 5974.12 | 1.0 / 776.382 |
| bursty | 0.986 / 1794.414 | 0.985417 / 1661.258 | 0.574083 / 2937.988 | 0.5935 / 3000.572 | 0.05 / 5069.048 | 0.999917 / 5288.478 | 0.999917 / 776.91 |

Byte budgets (storage keep-last-N needs for 14, 30 and 90 days, pooled; 9000 rows per world and
policy; keep first cannot meet a byte budget and is count-only):

| world | prior-only | SlowBurn | GFS | Tower of Hanoi | keep last N | oracle |
|---|---|---|---|---|---|---|
| uniform | 0.645667 / 2290.544 | 0.667222 / 2193.576 | 0.522222 / 2548.669333 | 0.520111 / 2518.618667 | 0.491778 / 2553.848 | 0.759889 / 1695.485333 |
| early | 0.618 / 1897.754667 | 0.659667 / 1753.114667 | 0.553667 / 1864.770667 | 0.505667 / 1993.149333 | 0.486778 / 1969.456 | 0.761556 / 1404.682667 |
| late | 0.621 / 3144.352 | 0.646222 / 2942.778667 | 0.49 / 3642.186667 | 0.495889 / 3664.706667 | 0.474444 / 3646.621333 | 0.749222 / 2228.050667 |
| bursty | 0.603 / 2916.170667 | 0.658667 / 2651.530667 | 0.523111 / 3116.872 | 0.513556 / 3212.165333 | 0.484778 / 3250.032 | 0.754778 / 2019.992 |

By byte budget (uniform world), recovery: 14 d prior-only 0.21, SlowBurn 0.214667, GFS 0.17,
Tower of Hanoi 0.16, keep last N 0.2, oracle 0.41; 30 d 0.804 / 0.882667 / 0.489333 / 0.464333 /
0.409 / 0.999; 90 d 0.923 / 0.904333 / 0.907333 / 0.936 / 0.866333 / 0.870667. At 90 d the oracle
is below Tower of Hanoi because its ~36 newest snapshots put more damaged candidates inside the
restore gate (its retention knows the start; its restore does not).

**Worst-case timing** (`results/dev_v2_worst/worst_case_timing.csv`; starts 112-143 x delays 7-60,
q in {1, .5, 0}, 5 reps per start, so cell recovery moves in steps of 0.2 and "worst" is coarse):
count budgets pooled, mean / worst-cell recovery: prior-only 0.974063 / 0.0, SlowBurn 0.959167 /
0.0, GFS 0.599583 / 0.0, Tower of Hanoi 0.578542 / 0.0, keep last N 0.049896 / 0.0, keep first and
oracle 0.999687 / 0.8. At q = 1: prior-only's worst cell is 1.0 at every K, SlowBurn's 0.8 at
K = 4 (start 130, delay 60) and 1.0 otherwise, GFS 0.0 at every K, Tower of Hanoi 0.0 at K = 4
and 6. Byte budget 30 d at q = 1: SlowBurn 0.99 (worst 0.8), prior-only 0.71125 (worst 0.0).

**Assumed discovery delay** (`results/dev_v2_delay/sweep_summary.csv`, mean of the four worlds,
recovery / work lost h): uniform 1-14 prior-only 0.35125 / 3259.78125, SlowBurn 0.348984 /
3265.760625; 1-30 0.565703 / 2542.336875 and 0.566328 / 2506.275; 1-60 (frozen) 0.973203 /
1732.39125 and 0.972109 / 1660.003125; 1-90 1.0 / 2224.695 and 0.993672 / 2158.83; 1-120 1.0 /
2816.5875 and 0.997109 / 2509.940625; geometric (mean 30, max 60) 0.976406 / 1734.38625 and
0.962422 / 1668.3825. Assuming a shorter maximum than the true delay makes the gate trust
post-start snapshots (recovery 0.0 at true delays above the assumed maximum, for every policy
sharing the restore); a longer one is safe and costs work lost.

## 3. What changed versus the old simulator

| | v1 DEV (benign 0 / .01 / .05, all q) | v2 DEV (count budgets, all worlds) |
|---|---|---|
| attack starts | {112, 115, 118, 139}, one per grid cell | per machine from a world on [28, 280] |
| prior-only | 0.979667 / 1787.298 | 0.980583 / 1721.6945 |
| SlowBurn (v1 method) | 0.964167 / 1786.894 | 0.979708 / 1644.471 |
| GFS | 0.642417 / 2079.484 | 0.570833 / 2670.8045 |
| Tower of Hanoi | 0.594833 / 2404.872 | 0.5615 / 2716.466 |
| keep last N | 0.05 / 3512.314 | 0.049979 / 4342.78 |

- SlowBurn's recovery gap to prior-only shrinks from -0.0155 to -0.000875, and its work lost
  falls below prior-only's in every world.
- GFS loses 0.071584 recovery: v1's starts included GFS's best case (start on a month boundary).
- The q = 0 restore-time failure persists: SlowBurn 0.074375 vs prior-only 0.051770833 pooled; at
  q = 0 SlowBurn's measured gate admits the start day in 0.3333-0.3617 of restores per world vs
  0.2 for prior-only.
- New axes v1 did not have: byte budgets, a worst-case timing grid, the assumed-delay sweep.

## 4. Method v2 progress (DEV only)

**Stage A, uncertain detector sensitivity (D48).** The evidence model gets a "detector blind"
component with prior weight w (w = 0 is v1, tested identical). Rule fixed before the run:
eligible if, in every world, SlowBurn's q = 0 restore-time failure is at most prior-only's + 0.01;
then highest recovery, ties within 0.001 by lower work lost. Source
`results/dev_v2_method_a/stage_a_scoreboard.csv` (1920 machines, count budgets):

| w | SlowBurn recovery | work lost (h) | worst-world q = 0 excess | eligible |
|---|---|---|---|---|
| 0 (v1) | 0.974922 | 1673.2425 | 0.031667 | no |
| 0.25 | 0.979323 | 1655.116875 | 0.025417 | no |
| **0.5 (chosen)** | 0.978646 | 1634.5425 | 0.00625 | yes |
| 0.75 | 0.97875 | 1644.030625 | 0.006667 | yes |
| 0.9 | 0.977135 | 1646.56875 | 0.0025 | yes |

Same machines, prior-only: 0.9762239583 / 1736.83375 h. Per world, recovery for prior-only / v1 /
v2: bursty 0.982708 / 0.981771 / 0.983437; early 0.977187 / 0.971146 / 0.977812; late 0.969688 /
0.97125 / 0.974688; uniform 0.975313 / 0.975521 / 0.978646. q = 0 recovery 0.948229 / 0.925625 /
0.946979. v2 gives up a little of v1's recovery at q = 0.2 and 0.5 (0.004375, 0.001979).

**Stage B, adaptive restore gate (D49): not adopted.** Gate = min + (0.8 - min)(1 - c), c = the
largest start-posterior mass in 7 days. Min 0.5: recovery 0.970443, work lost 1621.1475 h,
worst-world q = 0 excess 0.02875; min 0.65: 0.974193, 1625.624375, 0.02125; fixed gate 0.978646,
1634.5425, 0.00625. Both adaptive variants fail the q = 0 criterion, for 8.918125-13.395 h less
work lost; the concentration measure lowers the gate even without detector signal.

**Where work lost comes from.** With method v2, mean work lost 1634.542 h, best possible from the
kept snapshots 1194.649 h, oracle-ideal 772.8 h: 439.893 h from the restore choosing an older
snapshot than the best kept one, 421.849 h from retention spacing. Both are open for a later,
separately pre-specified stage.

**Method v2 on the full v2 DEV grid** (`results/dev_v2_method_full/`, 2400 machines; the v1
variant reproduces `results/dev_v2` exactly, 504000 rows). Recovery / work lost (h):

| world | prior-only | SlowBurn v1 | SlowBurn v2 | GFS (v2 restore) | Tower of Hanoi (v2 restore) |
|---|---|---|---|---|---|
| uniform, count | 0.979083 / 1687.168 | 0.9795 / 1642.93 | 0.9825 / 1591.592 | 0.566333 / 2486.106 | 0.549 / 2520.744 |
| early, count | 0.9815 / 1544.374 | 0.976917 / 1517.21 | 0.981833 / 1463.502 | 0.614583 / 1780.356 | 0.52475 / 1979.594 |
| late, count | 0.97575 / 1860.822 | 0.977 / 1756.486 | 0.97975 / 1718.93 | 0.5355 / 3477.918 | 0.59175 / 3366.402 |
| bursty, count | 0.986 / 1794.414 | 0.985417 / 1661.258 | 0.98675 / 1633.384 | 0.576 / 2936.774 | 0.600167 / 2988.476 |
| uniform, bytes | 0.645667 / 2290.544 | 0.667222 / 2193.576 | 0.680667 / 2145.789333 | 0.528889 / 2538.045333 | 0.526222 / 2518.821333 |
| early, bytes | 0.618 / 1897.754667 | 0.659667 / 1753.114667 | 0.664667 / 1758.834667 | 0.563 / 1856.704 | 0.513889 / 1988.344 |
| late, bytes | 0.621 / 3144.352 | 0.646222 / 2942.778667 | 0.648333 / 2946.885333 | 0.496778 / 3621.888 | 0.501889 / 3656.402667 |
| bursty, bytes | 0.603 / 2916.170667 | 0.658667 / 2651.530667 | 0.668667 / 2595.112 | 0.529444 / 3099.832 | 0.520778 / 3193.376 |

q = 0 restore-time failure, SlowBurn v2 / v1 / prior-only (count): bursty 0.04875 / 0.060833 /
0.0425; early 0.055417 / 0.085833 / 0.054167; late 0.058333 / 0.08125 / 0.0625; uniform 0.049583 /
0.069583 / 0.047917 (bytes: excess over prior-only 0.002222-0.005556 for v2, 0.039444-0.058889 for
v1). Worst-case grid, count budgets: SlowBurn v2 mean 0.973125 (v1 0.959167, prior-only 0.974063),
work lost 1686.7825 h (v1 1771.57, prior-only 1770.5975); at q = 0 v2 is still below prior-only
at K = 4 (0.93125 vs 0.9375), 6 (0.9725 vs 0.98125) and 8 (0.9225 vs 0.93875), above at 12
(0.88625 vs 0.88125). With method v2, evidence now adds recovery in every world (+0.000333 to
+0.004 over prior-only, count budgets) and lowers work lost by 80.872-161.03 h; this is still
small next to the v1 robustness effect claimed in (3).

## 5. Decisions made for you (all logged in OPEN_QUESTIONS.md)

- **D45 worlds:** window [28, 280]; early = Beta(1, 3), late = Beta(3, 1) on the window; bursty =
  3 centres [99, 139, 267] drawn once from a seeded stream, jitter sd 3 d; new DEV seed 202;
  evidence grid q in {1, .9, .5, .2, 0} x benign {0, .01, .05} (v1's 0.001 level dropped to
  afford 40 starts per world); threshold vault and AMOEBA-style left out of the v2 DEV baseline
  (they return in the P5 grid).
- **D46 byte budgets:** unique bytes of the kept snapshots; enforced with each policy's own
  deletion rule, one at a time (no policy is byte-aware); levels = keep-last-N storage for 14, 30,
  90 days, calibrated on 40 attack-free DEV machines (multipliers 1.7450643130492298,
  2.66980547090922, 6.146835909945129 of the day-0 size). A first choice (keep-last-4/8/12
  footprints) was discarded before any evaluation run because no policy could keep anything older
  than 2-3 weeks. keep first is count-only. Oracle now always keeps today's snapshot (count
  budgets >= 2 unchanged).
- **D47 worst case and delay sweep:** starts 112-143 (every residue mod 7, 28, 32), 5 reps per
  start; assumed delay uniform 1-{14, 30, 60, 90, 120} and geometric.
- **D48 / D49 rules** fixed before the runs; outcomes above. Method v2 (w = 0.5, fixed gate) is
  what I would pre-register for P5 unless you object.
- **D50:** claim (3) reported as not reproduced on v2 DEV; claim untouched; runs continued
  because none depended on it.
- **D51:** duplicate stage-A run, verified and rebuilt; process fix recorded.

## 6. Incident (D51)

An early `nohup` launch of the stage-A chain that I believed had not started did start, next to
the tracked launch, so two identical runs overlapped for ~95 min (10 workers; the cap is 6) and
wrote to the same output directory. Checks: all 1920 per-machine cache files load, 200 rows each,
no duplicate keys; the first 384000 CSV rows equal them in every compared column; 6 tasks
recomputed from scratch are identical; the CSV had 15 trailing garbage lines. I rebuilt
`tuning_sweep.csv` from the cache and recomputed the summary (40 rows, every column equal). No
other run had more than one launch (checked with the Windows process list).

## 7. Needs you

1. **D50:** how to restate or test claim (3). Options: (a) restate as "evidence lowers work lost
   and helps under tight storage, and method v2 removes the blind-detector penalty"; (b) add a
   concentrated, misplaced assumption as a "wrong assumption" axis next to the flat one (this
   reproduced the effect in v1).
2. Dataset and restic-workload paths and disk caps (still placeholders) before P2/P5.
3. P2 next: I will report FSL Homes availability, format and size, and NapierOne's
   partial-encryption coverage before any download.
4. The synthetic churn (~5% of bytes new per day, spread over all files) makes old snapshots
   expensive under byte budgets; real traces (P2) should change the byte-budget picture.
5. docs/theory.md review (unchanged).
