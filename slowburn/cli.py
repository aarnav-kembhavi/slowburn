"""Command-line entry point: ``slowburn <command> <config.yaml>``."""

from __future__ import annotations

import argparse
import sys

from slowburn.utils.config import load_config
from slowburn.utils.seed import seed_everything


def _bench(cfg: dict) -> None:
    from slowburn.bench.plots import plot_recovery_vs_fraction
    from slowburn.bench.runner import output_dir, run_benchmark

    df = run_benchmark(cfg)
    out = output_dir(cfg)
    plot_recovery_vs_fraction(df, out)
    print(f"wrote {len(df)} rows -> {out / 'results.csv'}")
    cols = ["policy", "damage_fraction", "discovery_delay", "clean_recovery"]
    print(df.groupby(cols[:3])["clean_recovery"].mean().to_string())


def _detector(cfg: dict) -> None:
    from slowburn.bench.detector_experiment import headline_summary, run_detector_experiment
    from slowburn.bench.plots import plot_auroc_by_type, plot_auroc_vs_fraction
    from slowburn.utils.config import resolve_path

    res = run_detector_experiment(cfg)
    out = resolve_path(cfg["output_dir"])
    plot_auroc_vs_fraction(res["auroc"], out)
    for model in ("striped", "whole"):
        plot_auroc_by_type(res["auroc"], out, model)
    print(f"run info: {res['info']}")
    print("chunk-level AUROC, weighted averages over types:")
    print(headline_summary(res["auroc"]).to_string())
    cal = res["calibration"]
    print("conformal false-alarm check (test benign, weighted averages):")
    print(cal[cal.file_type.str.startswith("WAVG_")].to_string(index=False))
    print(f"outputs -> {out}")


def _inference(cfg: dict) -> None:
    from slowburn.bench.inference_experiment import (
        load_timing,
        prior_grid,
        run_inference_experiment,
        summarise,
    )
    from slowburn.bench.plots import plot_example_trace, plot_start_accuracy
    from slowburn.utils.config import resolve_path

    res = run_inference_experiment(cfg)
    out = resolve_path(cfg["output_dir"])
    d = res["headline_delay"]
    start = int(cfg["scenario"]["attack_start"])
    for p_win, _ in prior_grid(load_timing(cfg["timing_config"])):
        plot_start_accuracy(res["results"], p_win, out, delay=d)
        for f in (0.05, 0.1, 0.25):
            for tgt in ("all", "high_entropy"):
                plot_example_trace(res["traces"], out, f, tgt, p_win, start)
        for name, tbl in summarise(res["results"], p_win, delay=d).items():
            tbl.to_csv(out / f"summary_{name}_p{p_win}.csv")
    print(f"outputs -> {out}  {res['info']}")


def _tune_statistic(cfg: dict) -> None:
    from slowburn.bench.inference_experiment import run_inference_experiment
    from slowburn.bench.registry import update_frozen
    from slowburn.bench.tune import statistic_rule
    from slowburn.utils.config import resolve_path

    res = run_inference_experiment(cfg)
    out = resolve_path(cfg["output_dir"])
    board, choice = statistic_rule(res["results"], delay=int(cfg.get("headline_delay", 14)))
    board.to_csv(out / "statistic_scoreboard.csv")
    spec = cfg["statistics"][choice]
    update_frozen({"daily_statistic": spec["aggregator"],
                   "daily_statistic_params": dict(spec.get("params", {})),
                   "observation_model": spec["model"]},
                  note=f"rule D24 on {cfg['_config_path']}: chose {choice}")  # fmt: skip
    print(board.to_string())
    print(f"chosen: {choice} -> configs/frozen.yaml (not frozen yet)")


COMMANDS = {
    "bench": _bench,
    "detector": _detector,
    "inference": _inference,
    "tune-statistic": _tune_statistic,
}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="slowburn")
    p.add_argument("command", choices=sorted(COMMANDS))
    p.add_argument("config", help="path to a YAML config under configs/")
    args = p.parse_args(argv)
    cfg = load_config(args.config)
    seed_everything(int(cfg["seed"]))
    COMMANDS[args.command](cfg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
