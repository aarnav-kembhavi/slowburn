"""Dataset fetch guards (D58): budget checks, zip safety, FSL contiguous-day plan. No network."""

import zipfile

import pytest

from slowburn.datasets.fetch import Budget, StopFetch, plan_contiguous_block, safe_members


def test_budget_refuses_cap_and_reserve(tmp_path):
    (tmp_path / "a.bin").write_bytes(b"x" * 100)
    b = Budget(tmp_path, cap_bytes=150, reserve_bytes=0)
    b.check(50, "ok")
    with pytest.raises(StopFetch, match="cap"):
        b.check(51, "too big")
    huge = Budget(tmp_path, cap_bytes=10**18, reserve_bytes=10**18)
    with pytest.raises(StopFetch, match="reserve"):
        huge.check(1, "reserve")


def test_safe_members_skips_types_and_refuses_traversal(tmp_path):
    p = tmp_path / "z.zip"
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("NapierOne/PDF/a.pdf", b"1")
        z.writestr("NapierOne/EXE/b.exe", b"2")
    with zipfile.ZipFile(p) as z:
        names = [m.filename for m in safe_members(z, {"EXE"})]
    assert names == ["NapierOne/PDF/a.pdf"]
    bad = tmp_path / "bad.zip"
    with zipfile.ZipFile(bad, "w") as z:
        z.writestr("../evil.txt", b"x")
    with zipfile.ZipFile(bad) as z, pytest.raises(ValueError, match="unsafe"):
        safe_members(z)


def test_fsl_plan_is_a_contiguous_block_from_the_fullest_day():
    files = [(f"f-{u}-{d}", u, d) for d, us in
             (("d1", ["u1"]), ("d2", ["u1", "u2"]), ("d3", ["u1", "u2"]), ("d4", ["u1", "u2"]))
             for u in us]  # fmt: skip
    sizes = {f: 10 for f, _, _ in files}
    chosen, s = plan_contiguous_block(files, sizes, room=45)
    assert s["first_day"] == "d2" and s["last_day"] == "d3" and s["days"] == 2
    assert s["users"] == ["u1", "u2"] and s["bytes"] == 40
    assert "f-u1-d1" not in chosen and "f-u1-d4" not in chosen


def test_napierone_published_sha256_parses_utf8_and_utf16():
    from slowburn.datasets.fetch import napierone_published_sha256

    h = "b7eadda70d854bb19f10c6fdb0910345bda6e78522413a524b9e6537872027a3"
    txt = f" MD5   16   e2add58330e7556145e6ddd505b81bd0\n SHA256      32      {h.upper()}\n"
    assert napierone_published_sha256(txt.encode()) == h
    assert napierone_published_sha256(txt.encode("utf-16")) == h
    assert napierone_published_sha256(b"nothing") is None


# ---- D61 download watchdog -----------------------------------------------------------------

import sys  # noqa: E402

from slowburn.datasets.watchdog import run as watchdog  # noqa: E402


def _wd(tmp_path, code, max_restarts=2):
    (tmp_path / "data").mkdir(exist_ok=True)
    cmd = (sys.executable, "-c", code)
    n = watchdog(str(tmp_path / "data"), str(tmp_path / "f.log"), str(tmp_path / "w.log"),
                 check_s=0.3, stall_s=0.5, max_restarts=max_restarts, cmd=cmd)  # fmt: skip
    return n, (tmp_path / "w.log").read_text()


def test_watchdog_restarts_a_stalled_fetcher_and_logs_it(tmp_path):
    n, log = _wd(tmp_path, "import time; time.sleep(60)")
    assert n == 2 and log.count("RESTART") == 2 and "no bytes written" in log
    assert "giving up after 2 restarts" in log


def test_watchdog_stops_when_the_fetcher_finishes(tmp_path):
    n, log = _wd(tmp_path, "print('DONE')")
    assert n == 0 and "fetcher finished: DONE" in log


def test_watchdog_restarts_a_crashed_fetcher(tmp_path):
    n, log = _wd(tmp_path, "raise SystemExit(3)", max_restarts=1)
    assert n == 1 and "exited with code 3 before finishing" in log


# ---- D61 range resume (local server, no network) -------------------------------------------

import hashlib  # noqa: E402
import threading  # noqa: E402
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer  # noqa: E402

from slowburn.datasets.fetch import download  # noqa: E402

BODY = bytes(range(256)) * 400


def _server(honour_range: bool):
    class H(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            rng = self.headers.get("Range")
            if rng and honour_range:
                start = int(rng.split("=")[1].rstrip("-"))
                self.send_response(206)
                self.send_header("Content-Range", f"bytes {start}-{len(BODY) - 1}/{len(BODY)}")
                body = BODY[start:]
            else:
                self.send_response(200)
                body = BODY
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}/f.bin"


@pytest.mark.parametrize("honour", [True, False])
@pytest.mark.parametrize("partial", [0, 1000, len(BODY) + 5])
def test_download_resumes_with_range_and_verifies(tmp_path, honour, partial):
    srv, url = _server(honour)
    try:
        dest = tmp_path / "f.bin"
        part = tmp_path / "f.bin.part"
        if partial:
            part.write_bytes((BODY + b"xxxxx")[:partial])
        logs = []
        rec = download(url, dest, Budget(tmp_path, reserve_bytes=0), logs.append, len(BODY))
        assert dest.read_bytes() == BODY and not part.exists()
        assert rec["sha256"] == hashlib.sha256(BODY).hexdigest()
        resumed = any("resuming at 1000" in s for s in logs)
        assert resumed == (honour and partial == 1000)
    finally:
        srv.shutdown()


def test_corrupt_partial_fails_the_hash(tmp_path):
    srv, url = _server(True)
    try:
        (tmp_path / "f.bin.part").write_bytes(b"\0" * 1000)  # wrong bytes, right length
        rec = download(url, tmp_path / "f.bin", Budget(tmp_path, reserve_bytes=0), print,
                       len(BODY))  # fmt: skip
        assert rec["sha256"] != hashlib.sha256(BODY).hexdigest()  # caught by the published hash
    finally:
        srv.shutdown()


def test_watchdog_single_instance_and_done_marker(tmp_path):
    from slowburn.datasets.watchdog import _lock

    held = _lock(tmp_path / "w.lock")
    assert held is not None
    n = watchdog(str(tmp_path), str(tmp_path / "f.log"), str(tmp_path / "w.log"),
                 check_s=0.1, stall_s=0.2, cmd=(sys.executable, "-c", "print('DONE')"))  # fmt: skip
    assert n == -1  # another instance holds the lock
    held.close()
    _wd(tmp_path, "print('DONE')")
    assert (tmp_path / "w.done").exists()
    assert _wd(tmp_path, "print('DONE')")[0] == -1  # finished earlier: exits at once


# ---- 2026-10-22 guard: bytes due in flight, free space re-checked before every chunk ---------


def test_budget_counts_bytes_due_on_every_in_flight_download(tmp_path):
    free = Budget(tmp_path).free()
    b = Budget(tmp_path, cap_bytes=10**18, reserve_bytes=free - 100)
    b.start("a", 60)  # alone it fits (60 <= 100)
    with pytest.raises(StopFetch, match="due in flight"):
        b.start("b", 60)  # 60 + 60 due > 100: the old per-archive check would have allowed it
    assert b.stopped
    with pytest.raises(StopFetch, match="stopped"):
        b.chunk("a", 10)  # every other thread stops at its next chunk


def test_download_stops_mid_file_when_free_space_drops(tmp_path):
    srv, url = _server(True)
    try:
        b = Budget(tmp_path, reserve_bytes=1)
        frees = iter([10**15] * 2 + [0] * 100)  # free space vanishes after start and chunk 1
        b.free = lambda: next(frees)
        with pytest.raises(StopFetch, match="due in flight"):
            download(url, tmp_path / "f.bin", b, print, len(BODY))
        assert not (tmp_path / "f.bin").exists() and b.due == {}  # partial kept, tally cleared
    finally:
        srv.shutdown()
