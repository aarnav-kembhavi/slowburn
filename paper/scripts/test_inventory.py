"""TEST pool inventory (OPEN_QUESTIONS "TEST content path"; frozen_v2.yaml prerequisite). Counts
only, computed and committed BEFORE any TEST experiment:

    per type: files in the TEST pool (v1 sim_test <= 1 MiB, benign_v2/<type>/test), validity
    failures (our strict check, as on DEV), files the check does not apply to;
    truncated pngs (exactly 1 MiB and failing the check, the D75 rule);
    TEST damage families and their numbered encrypted samples.

Rule: the inventory changes nothing; no file is removed or added; it is used only to interpret
results. No detector, simulation or experiment runs here. Loads through ContentPool, so it refuses
to open TEST files unless configs/frozen.yaml is frozen and configs/frozen_v2.yaml approved.
Run from the repo root (only after approval):

    uv run python paper/scripts/test_inventory.py
"""

import json
import sys
from pathlib import Path

from slowburn.detector.napierone import (
    ContentPool,
    PoolFile,
    encrypted_samples,
    family_splits,
    read_benign,
    truncated_png,
)
from slowburn.detector.validity import INVALID, NOT_APPLICABLE, file_validity

ROOT = "data/napierone"
OUT = Path("results/test_inventory.json")
RULE = ("inventory changes nothing; no file is removed or added; "
        "it is used only to interpret results")  # fmt: skip


def main():
    pool = ContentPool(ROOT, "sim_test", "v2test")  # TEST content gate
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
        types[t] = {"files": len(files), "from_v1_sim_test": len(files) - n_v2,
                    "from_benign_v2_test": n_v2, "validity_failures": int(n_bad),
                    "validity_not_applicable": int(n_na)}  # fmt: skip
        if t == "png":
            types[t]["truncated_png"] = int(n_trunc)
    fams = family_splits(pool.root)["sim_test"]
    out = {"rule": RULE, "pool": "sim_test / v2test", "types": types,
           "damage_families": len(fams),
           "encrypted_samples": len(encrypted_samples(pool.root, fams))}  # fmt: skip
    OUT.write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    sys.exit(main())
