"""D80 (OPEN_QUESTIONS): configs with the D78-accepted detector swapped in, nothing else changed.
Run from the repo root: uv run python paper/scripts/d80_configs.py <candidate>"""

import sys
from pathlib import Path

import yaml

DET = "results/dev_d78/detectors/{}.pkl"


def write(src: str, dst: str, name: str, extra: dict):
    cfg = yaml.safe_load(Path(src).read_text())
    cfg["scenario"]["detector_path"] = DET.format(name)
    cfg.update(extra)
    head = f"# D80: copy of {src} with the D78 detector {name} swapped in; nothing else changed.\n"
    Path(dst).write_text(head + yaml.safe_dump(cfg, sort_keys=False))


def main(name):
    write("configs/dev_d72_bytes_napierone_v2pool.yaml", "configs/dev_d80_c2_napierone.yaml",
          name, {"experiment": "dev_d80_c2_napierone",
                 "output_dir": "results/dev_d80_c2_napierone"})  # fmt: skip
    write("configs/dev_d74_attack_napierone.yaml", "configs/dev_d80_alarm_napierone.yaml",
          name, {"experiment": "dev_d80_alarm_napierone"})


if __name__ == "__main__":
    main(sys.argv[1])
