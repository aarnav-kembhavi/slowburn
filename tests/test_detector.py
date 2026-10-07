import numpy as np
import pandas as pd
import pytest
from sklearn.metrics import roc_auc_score

from slowburn.detector.calibrate import CalibratedDetector, conformal_pvalues
from slowburn.detector.dataset import build_chunk_dataset, split_files
from slowburn.detector.datasets import DatasetMissingError, NapierOneDamageSource, napierone_root
from slowburn.detector.evaluate import bootstrap_auroc, weighted_auroc
from slowburn.detector.model import ChunkClassifier
from slowburn.utils.config import load_config


@pytest.fixture(scope="module")
def smoke_cfg():
    return load_config("configs/detector_smoke.yaml")


@pytest.fixture(scope="module")
def dataset(smoke_cfg):
    return build_chunk_dataset(smoke_cfg)


# ---- dataset ---------------------------------------------------------------------------


def test_split_is_by_file_and_stratified():
    files = pd.DataFrame({"file_id": [f"f{i}" for i in range(40)], "file_type": ["a", "b"] * 20})
    s = split_files(files, {"train": 0.6, "calib": 0.2, "test": 0.2}, np.random.default_rng(0))
    assert set(s) == set(files["file_id"])
    for t in ("a", "b"):
        ids = files.loc[files.file_type == t, "file_id"]
        assert {s[i] for i in ids} == {"train", "calib", "test"}


def test_no_file_crosses_splits(dataset):
    per_file = dataset.meta.groupby("file_id")["split"].nunique()
    assert per_file.max() == 1


def test_every_type_and_hard_negatives_in_train_and_test(dataset, smoke_cfg):
    m = dataset.meta
    for split in ("train", "test"):
        neg = m[(m.split == split) & (m.label == 0)]
        assert set(neg.file_type) == set(smoke_cfg["data"]["file_types"])


def test_dataset_rows_consistent(dataset):
    m, X = dataset.meta, dataset.X
    assert len(m) == len(X)
    assert ((m.label == 1) == (m.damaged_byte_frac > 0)).all()
    assert (m.loc[m.label == 0, "damage_model"] == "none").all()
    assert set(m.loc[m.label == 1, "damage_model"]) == {"whole", "striped"}
    assert (m.loc[m.label == 1, "damage_source"] == "synthetic_random").all()
    assert (m.loc[m.label == 0, "damage_source"] == "none").all()
    assert (m.benign_source == "synthetic").all()


def test_dataset_reproducible(smoke_cfg):
    a = build_chunk_dataset(smoke_cfg)
    b = build_chunk_dataset(smoke_cfg)
    np.testing.assert_array_equal(a.X, b.X)


# ---- evaluation ------------------------------------------------------------------------


def test_weighted_auroc_matches_sklearn_with_ties():
    rng = np.random.default_rng(0)
    s = np.round(rng.random(500), 1)  # many ties
    y = (rng.random(500) < 0.3).astype(int)
    assert weighted_auroc(s, y) == pytest.approx(roc_auc_score(y, s))
    w = rng.integers(1, 4, 500).astype(float)
    assert weighted_auroc(s, y, w) == pytest.approx(roc_auc_score(y, s, sample_weight=w))


def test_weighted_auroc_degenerate():
    assert np.isnan(weighted_auroc(np.array([0.1, 0.2]), np.array([0, 0])))


def test_bootstrap_ci_brackets_point_estimate():
    rng = np.random.default_rng(1)
    files = np.repeat(np.arange(50), 10)
    y = (files % 2).astype(int)
    s = y * 0.6 + rng.random(500)
    point, lo, hi = bootstrap_auroc(s, y, files, n_boot=100, ci=0.95, rng=rng)
    assert lo <= point <= hi
    assert 0.5 < point < 1.0


# ---- model + calibration ---------------------------------------------------------------


def test_conformal_pvalues_valid_under_null():
    rng = np.random.default_rng(0)
    cal, test = rng.normal(size=2000), rng.normal(size=20000)
    p = conformal_pvalues(cal, test)
    assert p.min() > 0 and p.max() <= 1
    for a in (0.01, 0.05, 0.1):
        assert np.mean(p <= a) <= a + 0.01


def test_calibrated_detector_end_to_end(dataset, smoke_cfg):
    m, X = dataset.meta, dataset.X
    tr, ca, te = (
        (m.split == "train").values,
        (m.split == "calib").values,
        (m.split == "test").values,
    )
    clf = ChunkClassifier(smoke_cfg["model"], seed=0).fit(X[tr], m.label.values[tr])
    det = CalibratedDetector(clf).fit(X[ca], m.label.values[ca])
    p = det.score_features(X[te])
    assert p.min() >= 0 and p.max() <= 1
    pv = det.pvalues(X[te])
    assert pv.min() > 0 and pv.max() <= 1
    # fully damaged chunks must be easy even for the tiny smoke model
    easy = te & (m.damage_model == "whole").values | te & (m.label == 0).values
    assert roc_auc_score(m.label.values[easy], det.raw_scores(X[easy])) > 0.9


def test_mondrian_pvalues_use_per_group_calibration():
    class Fixed:  # raw score = first feature
        def raw_scores(self, X):
            return X[:, 0]

    rng = np.random.default_rng(0)
    # group "lo" benign scores ~ U(0, 0.5); group "hi" benign scores ~ U(0.5, 1)
    s = np.r_[rng.uniform(0, 0.5, 500), rng.uniform(0.5, 1, 500)]
    g = np.array(["lo"] * 500 + ["hi"] * 500)
    det = CalibratedDetector(Fixed(), min_group=50).fit(s[:, None], np.zeros(1000, int), g)
    x = np.array([[0.6]])
    # 0.6 is extreme for "lo" but ordinary for "hi"; marginal sits in between
    p_lo = det.pvalues(x, np.array(["lo"]))[0]
    p_hi = det.pvalues(x, np.array(["hi"]))[0]
    p_marg = det.pvalues(x)[0]
    assert p_lo < 0.01 < p_marg < p_hi
    # unknown group falls back to marginal
    assert det.pvalues(x, np.array(["other"]))[0] == p_marg
    # per-group validity under the null
    test = rng.uniform(0, 0.5, 20000)[:, None]
    assert np.mean(det.pvalues(test, np.array(["lo"] * 20000)) <= 0.05) <= 0.06


def test_calibrated_detector_satisfies_detector_protocol(dataset, smoke_cfg):
    from slowburn.detector.base import score

    m, X = dataset.meta, dataset.X
    clf = ChunkClassifier(smoke_cfg["model"], seed=0).fit(X, m.label.values)
    det = CalibratedDetector(clf).fit(X, m.label.values)
    assert 0.0 <= score(det, b"hello world" * 300, "txt", False) <= 1.0


# ---- external datasets -----------------------------------------------------------------


def test_napierone_missing_fails_loudly(tmp_path):
    with pytest.raises(DatasetMissingError, match="data/README.md"):
        napierone_root(tmp_path / "nope")
    (tmp_path / "empty").mkdir()
    with pytest.raises(DatasetMissingError):
        napierone_root(tmp_path / "empty")


def test_napierone_damage_source_reads_offset_aligned(tmp_path):
    enc = tmp_path / "encrypted" / "familyA"
    enc.mkdir(parents=True)
    (enc / "a.docx.locked").write_bytes(bytes(range(256)) * 4)
    src = NapierOneDamageSource(tmp_path, encrypted_glob="encrypted/**/*")
    assert src.name == "napierone"
    out = src.bytes_for("f1", 10, 20)
    assert len(out) == 20
    big = src.bytes_for("f1", 0, 3000)  # longer than the sample: wraps, never fails
    assert len(big) == 3000
    assert src.bytes_for("f1", 10, 20) == out  # deterministic per file key


# ---- per-type evaluation, weights, validity variants ------------------------------------


def test_type_weights():
    from slowburn.detector.evaluate import type_weights

    assert type_weights(["a", "b"]) == {"a": 0.5, "b": 0.5}
    w = type_weights(["a", "b"], {"a": 3, "b": 1})
    assert w == {"a": 0.75, "b": 0.25}
    with pytest.raises(ValueError):
        type_weights(["a", "c"], {"a": 1})


def test_auroc_table_reports_per_type_and_weighted_average_not_pooled():
    from slowburn.detector.evaluate import auroc_table

    rng = np.random.default_rng(0)
    rows, raw = [], []
    for t, sep in (("txt", 2.0), ("zip", 0.0)):  # txt separable, zip at chance
        for f in range(20):
            for lab in (0, 1):
                for _ in range(3):
                    rows.append(
                        {
                            "file_id": f"{t}{f}",
                            "file_type": t,
                            "label": lab,
                            "damage_model": "striped" if lab else "none",
                            "fraction": 0.1 if lab else 0.0,
                            "damaged_byte_frac": 0.1 * lab,
                            "benign_source": "synthetic",
                            "damage_source": "synthetic_random" if lab else "none",
                        }
                    )
                    raw.append(rng.normal(sep * lab))
    meta = pd.DataFrame(rows)
    pv = {"type_conditional": rng.random(len(meta))}
    tbl = auroc_table(meta, np.array(raw), pv, [0.05], 20, 0.95, rng, {"txt": 1, "zip": 3})
    chunk = tbl[tbl.level == "chunk"].set_index("file_type")
    assert "ALL" not in chunk.index  # no pooled AUROC
    expect = 0.25 * chunk.loc["txt", "auroc"] + 0.75 * chunk.loc["zip", "auroc"]
    assert chunk.loc["WAVG_ALL", "auroc"] == pytest.approx(expect)
    assert chunk.loc["WAVG_ALL", "ci_low"] <= expect <= chunk.loc["WAVG_ALL", "ci_high"]


def test_dataset_carries_file_validity(dataset):
    from slowburn.detector.features import FILE_VALID_INDEX

    m, X = dataset.meta, dataset.X
    np.testing.assert_array_equal(X[:, FILE_VALID_INDEX], m.file_valid.to_numpy())
    benign = m[(m.label == 0) & m.file_type.isin(["txt", "zip", "jpg"])]
    assert (benign.file_valid == 1.0).all()  # pristine files decode
    assert (m.loc[m.file_type == "bin", "file_valid"] == -1.0).all()  # no check for raw binary


def test_validity_rule_scores():
    from slowburn.detector.model import ValidityRule

    X = np.zeros((3, 261))
    X[:, 260] = [1.0, 0.0, -1.0]
    np.testing.assert_array_equal(ValidityRule().raw_scores(X), [0.0, 1.0, 0.5])


def test_base_classifier_ignores_validity_column(dataset, smoke_cfg):
    m, X = dataset.meta, dataset.X
    clf = ChunkClassifier(smoke_cfg["model"], seed=0, feature_set="base").fit(X, m.label.values)
    X2 = X.copy()
    X2[:, 260] = 1 - X2[:, 260]
    np.testing.assert_array_equal(clf.raw_scores(X), clf.raw_scores(X2))
