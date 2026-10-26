"""D78 candidates (OPEN_QUESTIONS D78, amendment 1, implementation notes): F1 recalibration on the
calib split plus the FIX-half benign files, F2 validity-transition feature (retrained, same
hyperparameters, seed and train split), F3 both. The unchanged detector is copied, not rebuilt.
TEST files are never read. Run from the repo root:

    uv run python paper/scripts/d78_build.py
"""

import copy
import json
import pickle
import shutil
import sys
from pathlib import Path

import numpy as np

from slowburn.detector.calibrate import CalibratedDetector
from slowburn.detector.dataset import build_chunk_dataset
from slowburn.detector.datasets import NapierOneDamageSource
from slowburn.detector.features import FILE_VALID_INDEX, validity_transition
from slowburn.detector.model import ChunkClassifier
from slowburn.detector.napierone import d78_split, encrypted_samples, family_splits
from slowburn.utils.config import load_config, resolve_path

sys.path.insert(0, str(Path(__file__).parent))
from d75_auroc import rows_for  # noqa: E402

CFG = "configs/detector_napierone.yaml"
UNCHANGED = Path("results/detector_napierone/detector.pkl")
OUT = Path("results/dev_d78/detectors")


def transition_column(meta, X) -> np.ndarray:
    """Training / scoring rows with the validity column as a transition: benign rows compare a
    file with itself, damaged rows with the file's original (its benign rows' validity)."""
    orig = meta[meta.label == 0].groupby("file_id").file_valid.first()
    prev = meta.file_id.map(orig).to_numpy()
    X = X.copy()
    cur = meta.file_valid.to_numpy()
    X[:, FILE_VALID_INDEX] = [validity_transition(p if p == p else None, c)
                              for p, c in zip(prev, cur, strict=True)]  # fmt: skip
    return X


def fix_rows(cfg):
    """Benign chunk rows of every FIX-half file (same chunking as the detector build)."""
    d, seed = cfg["data"], int(cfg["seed"])
    root = str(resolve_path(d["napierone_dir"]))
    fams = family_splits(root)["calib"]  # damaged rows are discarded; any non-TEST family works
    source = NapierOneDamageSource(root, samples=encrypted_samples(root, fams))
    files = [(f"{t}_d78fix_{p.name}", t, p.read_bytes())
             for t in d["file_types"] for p in d78_split(root, t)[0]]  # fmt: skip
    m, X = rows_for(files, d, source, seed)
    keep = (m.label == 0).to_numpy()
    return m[keep].reset_index(drop=True), X[keep]


def calibrate(clf, m_cal, X_cal, m_fix=None, X_fix=None):
    ids = (m_cal.file_id + "|" + m_cal.damage_model + "|" + m_cal.fraction.astype(str)).to_numpy()
    X, y, g = X_cal, m_cal.label.to_numpy(), m_cal.file_type.to_numpy()
    if m_fix is not None:
        fid = (m_fix.file_id + "|none|0.0").to_numpy()
        X, y = np.vstack([X, X_fix]), np.r_[y, np.zeros(len(m_fix), int)]
        g, ids = np.r_[g, m_fix.file_type.to_numpy()], np.r_[ids, fid]
    return CalibratedDetector(clf).fit(X, y, groups=g, file_ids=ids)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    cfg = load_config(CFG)
    seed = int(cfg["seed"])
    ds = build_chunk_dataset(cfg)
    m, X = ds.meta, ds.X
    tr, ca = (m.split == "train").to_numpy(), (m.split == "calib").to_numpy()
    m_fix, X_fix = fix_rows(cfg)
    with UNCHANGED.open("rb") as fh:
        unchanged = pickle.load(fh)
    shutil.copy(UNCHANGED, OUT / "unchanged.pkl")

    f1 = calibrate(copy.deepcopy(unchanged.classifier), m[ca], X[ca], m_fix, X_fix)
    Xt = transition_column(m, X)
    clf2 = ChunkClassifier(cfg["model"], seed=seed, feature_set="validity").fit(
        Xt[tr], m.label.to_numpy()[tr])  # fmt: skip
    f2 = calibrate(clf2, m[ca], Xt[ca])
    Xt_fix = transition_column(m_fix, X_fix)
    f3 = calibrate(copy.deepcopy(clf2), m[ca], Xt[ca], m_fix, Xt_fix)
    for name, det in (("F1", f1), ("F2", f2), ("F3", f3)):
        det.validity_mode = "transition" if name in ("F2", "F3") else "absolute"
        det.name = f"d78_{name}"
        with (OUT / f"{name}.pkl").open("wb") as fh:
            pickle.dump(det, fh)
    info = {"fix_benign_files": int(m_fix.file_id.nunique()), "fix_benign_chunks": len(m_fix),
            "calib_chunks": int(ca.sum()), "train_chunks": int(tr.sum())}  # fmt: skip
    (OUT / "build_info.json").write_text(json.dumps(info, indent=1))
    print(info)


if __name__ == "__main__":
    main()
