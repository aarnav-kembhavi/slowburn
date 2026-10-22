"""FSL churn extraction (D66): rewrite days from content digests, empty days, machine schedule."""

import io
import tarfile

import numpy as np

from slowburn.datasets import fsl_churn
from tests.test_hashfile import _v7


def _archive(tmp_path, user, date, files):
    name = f"fslhomes-{user}-{date}"
    p = tmp_path / f"{name}.tar.bz2"
    data = _v7(files)
    with tarfile.open(p, "w:bz2") as tf:
        for member, payload in ((f"{name}/README", b"readme"),
                                (f"{name}/{name}.8kb.hash.anon", data)):  # fmt: skip
            ti = tarfile.TarInfo(member)
            ti.size = len(payload)
            tf.addfile(ti, io.BytesIO(payload))
    return p


def test_extract_rewrites_empty_days_and_present_files(tmp_path):
    a, b, c = (b"aaaaaa", 6, 0), (b"bbbbbb", 6, 0), (b"cccccc", 6, 0)
    days = [
        ("2011-09-16", [("/x", 6, [a]), ("/y", 6, [b]), ("/z", 6, [c])]),
        ("2011-09-17", [("/x", 6, [b]), ("/y", 6, [b]), ("/z", 6, [c])]),  # x rewritten
        ("2011-09-18", []),  # empty: missing
        ("2011-09-19", [("/x", 6, [b]), ("/y", 6, [a])]),
    ]  # y rewritten, z gone
    arch = [_archive(tmp_path, "user001", d, f) for d, f in days]
    users = fsl_churn.extract(arch, str(tmp_path / "churn.json.gz"), workers=1, log=lambda *_: 0)
    u = users["user001"]
    assert u["dates"] == ["2011-09-16", "2011-09-17", "2011-09-19"]
    assert u["empty_dates"] == ["2011-09-18"]
    assert u["n_present_all_days"] == 2  # z is missing on the last non-empty day
    assert sorted(map(tuple, u["changes"])) == [(1,), (2,)]  # x at snapshot 1, y at snapshot 2


def test_machine_schedule_replays_rewrites_circularly():
    churn = {"u1": {"dates": ["d0", "d1", "d2", "d3"], "n_present_all_days": 3,
                    "changes": [[1, 3], [2]]}}  # fmt: skip
    user, sched = fsl_churn.machine_schedule(churn, np.random.default_rng(0), 3, 20)
    assert user == "u1" and sched[0] == []
    counts = np.zeros(3, int)
    for day in sched[1:]:
        for i in day:
            counts[i] += 1
    # 19 replayed days over a 3-transition cycle: every day replays exactly one transition, so
    # the two edited files share the 19 days (each transition 6 or 7 times), the static file
    # is never edited, and the file rewritten twice per cycle gets the larger share
    c = sorted(counts)
    assert c[0] == 0 and c[1] + c[2] == 19 and 6 <= c[1] <= 7 and 12 <= c[2] <= 13
