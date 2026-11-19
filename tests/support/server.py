"""Shared lifecycle of the uvicorn applications generated during tests."""

import contextlib
import os
import socket
import subprocess
import sys
import tempfile
import time

import pytest
import requests


def free_port():
    """Briefly reserves a free local port and returns its number.

    **This port is RELEASED before being used**, and nothing holds it in
    between: the OS can hand it to anyone, including an outgoing connection of
    the suite itself — `bind(0)` and client sockets draw from the SAME ephemeral
    range (`/proc/sys/net/ipv4/ip_local_port_range`, here 32768-60999). Hence a
    `uvicorn` dying on "address already in use" only under load, never when the
    file runs alone.

    `uvicorn_server` no longer uses it: it binds its socket and passes it to the
    child, which removes the window instead of retrying. Tests that mount their
    server themselves still call it; they fail plainly if the port escapes them,
    which is noisy but honest.
    """
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _diagnostic(entete, journal, module, directory):
    """What uvicorn wrote before dying.

    This output went to `DEVNULL`: that is why nobody ever knew WHY the server
    stopped. A message that does not say the cause sends you looking in the
    wrong place.
    """
    try:
        journal.seek(0)
        sortie = journal.read().strip()
    except (OSError, ValueError):  # pragma: no cover - log already closed
        sortie = ""
    return (f"{entete}\n"
            f"module={module!r} dossier={directory!r}\n"
            f"--- sortie d'uvicorn ---\n"
            f"{sortie or '(le serveur n a rien ecrit)'}")


@contextlib.contextmanager
def uvicorn_server(directory, *, env=None, module="app:app",
                   ready_path="/openapi.json", attempts=80):
    """Starts a generated application, waits for it to answer, then stops it.

    Business scenarios stay responsible for compiling their spec and preparing
    their database. This utility only carries the process mechanics repeated in
    the integration tests.

    Two decisions not to undo.

    **The socket is bound HERE and passed to the child** (`uvicorn --fd`),
    instead of handing it a port number just released. The port never becomes
    available between choosing and listening: the collision is made IMPOSSIBLE,
    not retried. Retrying would also have hidden a deterministic failure behind
    two more attempts.

    **A server that does not start makes the test FAIL, never skip.** The
    previous version called `pytest.skip`, so the twenty-one integration files
    going through here could check nothing while returning green. It is exactly
    the false green CLAUDE.md forbids.
    """
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    sock.listen(128)
    port = sock.getsockname()[1]
    fd = sock.fileno()
    os.set_inheritable(fd, True)

    journal = tempfile.TemporaryFile(mode="w+", encoding="utf-8", errors="replace")
    try:
        try:
            process = subprocess.Popen(
                [sys.executable, "-m", "uvicorn", module, "--fd", str(fd)],
                cwd=directory,
                env=env or os.environ.copy(),
                pass_fds=(fd,),
                stdout=journal,
                stderr=subprocess.STDOUT,
            )
        finally:
            # The child has its own copy of the descriptor. Keeping ours open
            # would make the kernel accept connections nobody serves any more
            # if the server dies: a failure would become a wait until the
            # timeout, instead of an immediate refusal.
            sock.close()

        base_url = f"http://127.0.0.1:{port}"
        try:
            for _ in range(attempts):
                if process.poll() is not None:
                    pytest.fail(_diagnostic(
                        "le serveur uvicorn s'est arrêté avant de répondre "
                        f"(code {process.returncode})",
                        journal, module, directory))
                try:
                    response = requests.get(base_url + ready_path, timeout=1)
                    if response.status_code < 500:
                        break
                except requests.RequestException:
                    pass
                time.sleep(0.25)
            else:
                pytest.fail(_diagnostic(
                    f"le serveur uvicorn n'a jamais répondu sur {ready_path} "
                    f"après {attempts} essais",
                    journal, module, directory))
            yield base_url
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
    finally:
        journal.close()
