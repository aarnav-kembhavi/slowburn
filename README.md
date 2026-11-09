# SlowBurn

Defensive research prototype (Information Storage Management course). Slow ransomware damages
small parts of files over many days, staying under per-snapshot alarm thresholds, while fixed
retention ("keep the last N") deletes the last clean snapshots. SlowBurn estimates *when* an
attack started from weak evidence that accumulates over days, and uses that posterior to choose
which snapshots to keep under a storage budget and to restore only the damaged files.

**Safety scope.** The project contains no encryptor, key handling, spreading logic or payload.
A "damaged" chunk is modelled abstractly: bytes are overwritten with seeded high-entropy random
bytes, or with bytes from public datasets of real ransomware-encrypted samples (NapierOne). The
only outputs are per-chunk benign/damaged labels and backup-retention decisions.

## History note

On 2026-11-09 this repository's history was rewritten to remove the manuscript sources, figures and
generated tables (`paper/ieee_access/`, `paper/sections/`, `paper/generated/`, `paper/main.tex`,
`paper/references.bib`). Every commit hash changed; commit hashes quoted in `OPEN_QUESTIONS.md`,
`configs/frozen_v2.yaml` and the reports are the pre-rewrite hashes, and the original hashes are kept
in the private audit record. `paper/scripts/` (the experiment and analysis scripts) is unchanged.
Scripts that write to `paper/generated/` or `paper/ieee_access/` create those directories.

## Setup

```sh
uv sync --extra dev          # or: pip install -e ".[dev]"
```

Python 3.11+, CPU only.

## Commands

```sh
uv run pytest                                         # tests (ruff: uv run ruff check . && uv run ruff format --check .)
uv run slowburn bench configs/smoke.yaml              # M0 end-to-end smoke benchmark
uv run slowburn detector configs/detector.yaml        # detector variants + per-type AUROC (~3 min)
uv run slowburn inference configs/inference.yaml      # start-day inference study, DEV (~30 min)
uv run slowburn tune-statistic configs/tune_statistic.yaml   # DEV rule D24 v2 -> configs/frozen.yaml
uv run slowburn preregister-grid configs/headline.yaml  # record the scenario grid (D32) in configs/frozen.yaml
uv run slowburn tune-retention configs/tune_retention.yaml   # DEV rule D30   -> configs/frozen.yaml
uv run slowburn retention configs/headline.yaml       # headline grid (TEST split; needs frozen.yaml incl. the grid)
uv run slowburn theory-check configs/theory.yaml      # numerical checks for docs/theory.md
uv run slowburn fig all                               # paper figures/tables -> paper/generated/ (output dir; not tracked here)
```

`configs/*_smoke.yaml` variants run the same pipelines in seconds. Experiments use 4-6 worker
processes, one thread each, and resume from `results/<experiment>/machines/` if interrupted.

**Integrity rules.** Hyperparameters are chosen on DEV machines only, by pre-registered rules
(OPEN_QUESTIONS.md), and recorded in `configs/frozen.yaml` with provenance. Any TEST-split run is
refused unless that file is frozen and the run does not override it. Paper numbers come only
from `slowburn fig`.

Outputs go to `results/<experiment>/` as tidy CSV plus PNG plots. Every result row records
`benign_source` and `damage_source` (`synthetic`, `synthetic_random`, `napierone`, ...) so
synthetic and real-data results are always reported separately.

## Layout

| Path | Contents |
|---|---|
| `slowburn/detector/` | chunk features, LightGBM classifier, calibration |
| `slowburn/inference/` | daily statistic, changepoint models |
| `slowburn/retention/` | DP optimiser and baseline policies |
| `slowburn/store/` | deduplicated snapshot store, selective restore |
| `slowburn/sim/` | benign content generators, damage model, scenario simulator |
| `slowburn/bench/` | experiment runner, metrics, plots |
| `configs/` | YAML experiment configs (one global `seed` each) |
| `data/` | local datasets (gitignored), see `data/README.md` |
| `results/` | generated outputs (gitignored except `CHANGELOG.md`) |

Status, numbers per milestone: `results/CHANGELOG.md`. Team decisions pending: `OPEN_QUESTIONS.md`.
