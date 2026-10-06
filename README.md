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

## Setup

```sh
uv sync --extra dev          # or: pip install -e ".[dev]"
```

Python 3.11+, CPU only.

## Commands

```sh
uv run slowburn bench configs/smoke.yaml          # end-to-end retention benchmark (tiny)
uv run slowburn detector configs/detector.yaml    # M1: train + calibrate detector, AUROC sweep (~2 min)
uv run slowburn inference configs/inference.yaml  # M2: start-day inference (needs the M1 detector)
uv run pytest                                     # tests
uv run ruff check . && uv run ruff format --check .
```

`configs/*_smoke.yaml` variants run the same pipelines in seconds.

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
