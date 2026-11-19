"""ADDED (long-term roadmap, multi-worker rate limiting): checks that rate
limiting is shared between several uvicorn workers — the quota (5 attempts /
60 s / IP) applies GLOBALLY, not per worker.

With the old in-process counter, two workers would have allowed 2×5 = 10
attempts before blocking. The counter now being in the (shared) database, the
6th failure is blocked (429) whatever the number of workers.
"""
import os
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time

import requests

from monl.ast_validator import MonlAST
from monl.generator import MonlSecureGenerator
from monl.parser import parse_monl_string
from tests.support.process import stop_process
from tests.support.server import free_port as _find_free_port

SPEC = """app RL

entity User
    name: String

actor User selfRegister

workflow W for User
    Read User
"""


MARKER_PRET = "Application startup complete"


def _wait(port, timeout=20):
    start = time.time()
    while time.time() - start < timeout:
        try:
            requests.get(f"http://127.0.0.1:{port}/docs", timeout=1)
            return True
        except requests.exceptions.ConnectionError:
            time.sleep(0.3)
    return False


def _wait_for_both_workers(proc, log, expected_items=2, timeout=40):
    """Wait until EACH worker has started, not only the first.

    An HTTP probe proves nothing here: with `--workers N`, the uvicorn
    supervisor opens the socket, then forks. A successful GET therefore proves
    the socket accepts — not that someone is behind each worker. Connections
    handed to a worker still starting are RESET, and that is exactly what CI
    showed: `ConnectionResetError(104)` in the middle of the burst, on perfectly
    correct server code.

    uvicorn writes `Application startup complete` ONCE PER WORKER: we count
    these lines rather than guess. The pipe must be drained in a separate
    thread — left full, it would end up blocking the server being observed.
    """
    debut = time.time()
    while time.time() - debut < timeout:
        if sum(MARKER_PRET in line for line in list(log)) >= expected_items:
            return True
        if proc.poll() is not None:
            return False
        time.sleep(0.2)
    return False


def _log(proc):
    log = []

    def _empty():
        for line in proc.stderr:
            log.append(line)

    threading.Thread(target=_empty, daemon=True).start()
    return log


def test_rate_limit_is_shared_across_workers():
    with tempfile.TemporaryDirectory() as workdir:
        ast = MonlAST(parse_monl_string(SPEC)).validate_and_audit()
        MonlSecureGenerator(ast, output_dir=workdir).generate_all()

        port = _find_free_port()
        proc = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app:app", "--port", str(port), "--workers", "2"],
            cwd=workdir, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
            text=True,
        )
        log = _log(proc)
        try:
            assert _wait_for_both_workers(proc, log), (
                "the two workers did not report their startup:\n"
                + "".join(log[-20:]))
            assert _wait(port), "the multi-worker server did not start"
            base = f"http://127.0.0.1:{port}"
            codes = []
            for _ in range(7):
                r = requests.post(f"{base}/login",
                                  json={"username": "inconnu", "password": "mauvais123"})
                codes.append(r.status_code)

            # The first 5 attempts are allowed (401: invalid credentials), the
            # 6th and beyond are blocked (429), even with 2 workers — proof
            # that the quota is global, not per worker.
            assert codes[:5] == [401] * 5, codes
            assert codes[5] == 429, codes
            assert codes[6] == 429, codes
        finally:
            stop_process(proc, delay=5)


def test_startup_survives_an_already_locked_database():
    """A worker must not DIE because another writes at the same moment.

    Found by CI, on months-old code: started with `--workers 2`, one worker wrote
    the schema while the other ran `PRAGMA journal_mode = WAL`, and that pragma
    is the ONLY place of the base that `busy_timeout` does not protect —
    measured: against a read transaction it waits the full delay then fails
    anyway, against a write transaction it fails in 0.00 s. The worker died, and
    uvicorn stopped the whole server.

    The test does not RACE: it holds the write lock itself while the server
    starts, then releases it. Without the fix, startup fails every time; with it,
    it waits and starts.
    """
    with tempfile.TemporaryDirectory() as workdir:
        ast = MonlAST(parse_monl_string(SPEC)).validate_and_audit()
        MonlSecureGenerator(ast, output_dir=workdir).generate_all()

        # A database that already exists and that ANOTHER process is writing —
        # exactly the state the second worker finds.
        path = os.path.join(workdir, "app.db")
        rival = sqlite3.connect(path, timeout=10.0)
        rival.execute("CREATE TABLE IF NOT EXISTS _verrou_essai (x INTEGER)")
        rival.commit()
        rival.execute("BEGIN IMMEDIATE")
        rival.execute("INSERT INTO _verrou_essai VALUES (1)")

        port = _find_free_port()
        proc = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app:app", "--port", str(port)],
            cwd=workdir, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
            text=True,
        )
        log = _log(proc)
        try:
            # Released AFTER the pragma and the first schema attempt have
            # happened: that is the window a real second worker lives. From the
            # MAIN thread — a SQLite connection belongs only to the thread that
            # opened it, and a `threading.Timer` therefore failed silently,
            # leaving the lock held forever.
            time.sleep(3.0)
            rival.rollback()
            rival.close()
            assert _wait_for_both_workers(proc, log, expected_items=1), (
                "the server died on a locked database:\n"
                + "".join(log[-20:]))
            assert _wait(port), "the server did not start"
            # Surviving is not enough: the old fallback started too, but giving
            # up WAL. The pragma now retries within the busy_timeout budget —
            # so the database must have switched to WAL.
            mode = sqlite3.connect(path)
            try:
                assert mode.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
            finally:
                mode.close()
        finally:
            stop_process(proc, delay=5)
