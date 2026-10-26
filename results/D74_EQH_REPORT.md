# D74 eqh arm (DEV, descriptive; OPEN_QUESTIONS 2026-10-26, 214a625)

Run d74_attack_napierone_eqh 14:42-18:11 (2026-10-26), exit 0, first attempt; config 8d7ca58,
report paper/scripts/d74_eqh_report.py (1a10135; output results/dev_d74_eqh_report/, log
results/dev_d74_eqh_report.txt). NapierOne v2, restore A, same machines, seeds, grid, c = 3.

**Coverage.** Under the D68 rule (M = 60) only ToH-eqh at K = 8 exists at K 4 / 8, and it is
base 2: the default Tower of Hanoi rotation (horizon 63 >= 60). Its rows are identical to the
default Tower of Hanoi rows at K = 8 (26,923 of 26,923 rows: recovery, whole-system and per-file
work lost, snapshots held). GFS-eqh and ToH-eqh at K = 4: no configuration reaches M.

**Result.** Best-response attacker (recovery-minimising, evaluation half), recovery by delay
7 / 14 / 30 / 45 / 60 / 90 / 120 days, K = 8: ToH (= ToH-eqh) 1.00 / 1.00 / 0.90 / 0.65 / 0.30
/ 0.05 / 0.00; SlowBurn 1.00 / 0.85 / 0.90 / 0.85 / 0.30 / 0.05 / 0.05; ToH loses less per-file
work at every delay (e.g. 45 days 5,716 vs 7,871 h; 120 days 6,476 vs 11,974 h). Realistic
attacker, K = 8: ToH 0.990 recovery at 5,303 h vs SlowBurn 1.000 at 7,255 h. So at K = 8 a
rotation whose horizon reaches the discovery bound matches SlowBurn on recovery against the
adaptive attacker and loses less work, consistent with "horizon, not placement".

**Synthetic arm: not run.** It would only duplicate the existing D74 synthetic Tower of Hanoi
rows at K = 8 (same rule, same rotation); no new information.
