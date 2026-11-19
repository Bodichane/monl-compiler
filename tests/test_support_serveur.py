"""The test harness, tested like the rest.

`uvicorn_server` mounts the servers of twenty-one integration files
(payment, aggregation, payment lock, platform…). As long as it turned a
server's death into `pytest.skip`, all these files could check nothing while
returning green — and it happened: the full suite produced a "uvicorn server
stopped before answering (code 1)" nobody read, while the same files passed
one by one.

A proof tool that is not itself proven proves nothing.
"""

import socket

import pytest
import requests

from tests.support import server as harnais
from tests.support.server import free_port, uvicorn_server

APP_SAINE = """
from fastapi import FastAPI

app = FastAPI()

@app.get("/openapi.json")
def openapi():
    return {"openapi": "3.1.0", "info": {"title": "sonde", "version": "0"}}
"""

APP_EN_PANNE = """
raise RuntimeError("panne volontaire du harnais")
"""


def echec_attendu(**kwargs):
    """Mounts a server known to be doomed and returns the failure message.

    Written this way rather than with `pytest.raises` for a MEASURED reason: on
    the old harness, a `Skipped` raised inside a `pytest.raises(Failed)` goes
    through and SKIPS the surrounding test. Two of this file's tests therefore
    looked green while checking nothing — the trap being fixed, reproduced in its
    own witness. A skip is treated here as the failure it is.
    """
    try:
        with uvicorn_server(**kwargs):
            pass
    except pytest.skip.Exception as saut:
        pytest.fail(f"serveur mort SAUTÉ au lieu d'échouer : {saut}")
    except pytest.fail.Exception as echec:
        return str(echec)
    pytest.fail("un serveur qui ne démarre pas doit faire échouer le test")


def test_a_server_that_does_not_start_fails_and_never_skips(tmp_path):
    """The heart of the fix.

    Written by catching both outcomes SEPARATELY rather than with a
    `pytest.raises`: a `Skipped` raised in a `pytest.raises(Failed)` would SKIP
    this very test, so the old behavior would look green. The trap being fixed
    would reproduce itself in the test that fixes it.
    """
    (tmp_path / "app.py").write_text(APP_EN_PANNE, encoding="utf-8")
    message = echec_attendu(directory=str(tmp_path), attempts=8)
    assert "s'est arrêté avant de répondre" in message
    # The cause must be IN the message: that is the whole point of taking
    # uvicorn's output out of DEVNULL.
    assert "panne volontaire du harnais" in message, message


def test_the_diagnostic_names_the_module_and_folder(tmp_path):
    """A message that says neither what nor where sends you looking in the
    wrong place — point 97's complaint, on another tool."""
    (tmp_path / "app.py").write_text(APP_EN_PANNE, encoding="utf-8")
    message = echec_attendu(directory=str(tmp_path), attempts=8)
    assert "app:app" in message
    assert str(tmp_path) in message


def test_a_missing_module_is_reported_with_its_cause(tmp_path):
    """The other way to die: the module does not import at all."""
    message = echec_attendu(directory=str(tmp_path), module="absent:app", attempts=8)
    assert "absent:app" in message
    assert "(le serveur n a rien ecrit)" not in message, (
        "la sortie d'uvicorn doit être rapportée, pas perdue")


def test_a_healthy_server_answers_and_its_port_is_held(tmp_path):
    """The witness: without it, a harness that ALWAYS failed would pass the
    three tests above.

    The second part measures what the fix promises — while the server lives,
    nobody else can take its port. We do NOT check that it is released
    afterwards: a closed connection stays in `TIME_WAIT`, and asserting it would
    state an OS detail we did not measure."""
    (tmp_path / "app.py").write_text(APP_SAINE, encoding="utf-8")
    with uvicorn_server(str(tmp_path)) as base:
        reponse = requests.get(base + "/openapi.json", timeout=5)
        assert reponse.status_code == 200

        port = int(base.rsplit(":", 1)[1])
        with socket.socket() as intrus:
            intrus.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            with pytest.raises(OSError):
                intrus.bind(("127.0.0.1", port))


def test_the_server_no_longer_goes_through_free_port(tmp_path, monkeypatch):
    """The proof that the racy path is no longer taken.

    Reading the source would only say that a `--fd` appears in it; making
    `free_port` explode says the server starts WITHOUT it.
    """
    appels = []
    monkeypatch.setattr(harnais, "free_port",
                        lambda: appels.append(1) or 65535)
    (tmp_path / "app.py").write_text(APP_SAINE, encoding="utf-8")
    with uvicorn_server(str(tmp_path)) as base:
        assert base.startswith("http://127.0.0.1:")
        assert not base.endswith(":65535"), "le port vient encore de free_port"
    assert appels == [], "uvicorn_server appelle encore free_port"


def test_free_port_releases_its_port_which_is_the_documented_flaw():
    """Why `uvicorn_server` no longer uses it.

    This test does not report a bug to fix: it STATES the limit of `free_port`,
    still called by about twenty files that mount their server themselves. If one
    day it stops releasing, this test will say so and the docstring must follow.
    """
    port = free_port()
    with socket.socket() as autre:
        # Nobody prevents it: the port is free between the two steps.
        autre.bind(("127.0.0.1", port))
        assert autre.getsockname()[1] == port
