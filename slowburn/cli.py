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
    plot_auroc_by_type(res["auroc"], out)
    print(f"run info: {res['info']}")
    print("chunk-level AUROC:")
    print(headline_summary(res["auroc"]).to_string())
    cal = res["calibration"]
    print("conformal false-alarm check (test benign, ALL):")
    print(cal[cal.file_type.isin(["ALL", "HIGH_ENTROPY"])].to_string(index=False))
    print(f"outputs -> {out}")


def _inference(cfg: dict) -> None:
    from slowburn.bench.inference_experiment import run_inference_experiment, summarise
    from slowburn.bench.plots import plot_example_trace, plot_start_accuracy
    from slowburn.utils.config import resolve_path

    res = run_inference_experiment(cfg)
    out = resolve_path(cfg["output_dir"])
    h = res["hazards"][0]
    d = res["headline_delay"]
    plot_start_accuracy(res["results"], h, out, delay=d)
    start = int(cfg["scenario"]["attack_start"])
    for f in (0.05, 0.1, 0.25):
        for tgt in ("all", "high_entropy"):
            plot_example_trace(res["traces"], out, f, tgt, start)
    for name, tbl in summarise(res["results"], h, delay=d).items():
        tbl.to_csv(out / f"summary_{name}.csv")
        print(f"== {name} (hazard {h}, headline delay {d} days)")
        print(tbl.round(4).to_string())
    print(f"outputs -> {out}")


COMMANDS = {"bench": _bench, "detector": _detector, "inference": _inference}


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
