"""DEV pool inventory for the paper's data card (descriptive; the same counts as
paper/scripts/test_inventory.py, on the DEV v2 pool and the DEV damage families). Reads DEV
content only. Run from the repo root:

    uv run python paper/scripts/dev_inventory.py
"""

import json
import sys
from pathlib import Path

from test_inventory import ROOT

from slowburn.detector.napierone import (
    ContentPool,
    PoolFile,
    encrypted_samples,
    family_splits,
    read_benign,
    truncated_png,
)
from slowburn.detector.validity import INVALID, NOT_APPLICABLE, file_validity

OUT = Path("results/exploratory/dev_inventory.json")


def main():
    pool = ContentPool(ROOT, "sim_dev", "v2")
    types = {}
    for t, files in sorted(pool.files.items()):
        n_bad = n_na = n_trunc = n_v2 = 0
        for f in files:
            v2 = isinstance(f, PoolFile)
            data = Path(f.path).read_bytes() if v2 else read_benign(pool.root, f)
            v = file_validity(data, t)
            n_bad += v == INVALID
            n_na += v == NOT_APPLICABLE
            n_trunc += t == "png" and truncated_png(pool, f)
            n_v2 += v2
        types[t] = {"files": len(files), "from_v1_sim_dev": len(files) - n_v2,
                    "from_benign_v2_dev": n_v2, "validity_failures": int(n_bad),
                    "validity_not_applicable": int(n_na)}  # fmt: skip
        if t == "png":
            types[t]["truncated_png"] = int(n_trunc)
    fams = family_splits(pool.root)["sim_dev"]
    out = {"pool": "sim_dev / v2", "types": types, "damage_families": len(fams),
           "encrypted_samples": len(encrypted_samples(pool.root, fams))}  # fmt: skip
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    sys.exit(main())
