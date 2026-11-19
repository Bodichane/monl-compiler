"""Proofs of the HTTP replay of the guided dialogue in the console."""

import socket
import threading
import time

import pytest
import requests
import uvicorn

from monl.dialogue_engine import GuidedDialogue
from monl_platform.app import create_app
from monl_platform.dialogue import (
    MAX_DIALOGUE_ANSWER_BYTES,
    MAX_DIALOGUE_ANSWERS,
    bounded_answers,
    replay,
)
from tests.test_dialogue_engine import SCENARIO_PORTFOLIO


@pytest.fixture()
def running_platform(tmp_path):
    application = create_app(workspace=tmp_path / "projects", domain="localhost")
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    server = uvicorn.Server(
        uvicorn.Config(application, host="127.0.0.1", port=port, log_level="error")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(100):
            try:
                if requests.get(f"{base}/health", timeout=0.2).status_code == 200:
                    break
            except requests.RequestException:
                time.sleep(0.02)
        else:
            pytest.fail("le serveur de console n'a pas démarré")
        yield base
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        assert not thread.is_alive()


def _session(base):
    session = requests.Session()
    response = session.post(
        f"{base}/api/auth/register",
        json={"email": "dialogue@example.test", "password": "MotDePasse-123"},
        timeout=10,
    )
    assert response.status_code == 201, response.text
    return session


def test_the_replay_is_bounded_without_truncating():
    with pytest.raises(ValueError, match="at most"):
        bounded_answers(["x"] * (MAX_DIALOGUE_ANSWERS + 1))
    with pytest.raises(ValueError, match="bytes"):
        bounded_answers(["x" * (MAX_DIALOGUE_ANSWER_BYTES + 1)])
    with pytest.raises(ValueError, match="list of strings"):
        bounded_answers("pas une liste")


def test_the_full_http_replay_produces_the_expected_backend(running_platform):
    """The whole journey goes over HTTP against uvicorn, without a server session."""
    base = running_platform
    session = _session(base)
    reponses = []
    derniere = None

    for reponse in SCENARIO_PORTFOLIO:
        derniere = session.post(
            f"{base}/api/dialogue", json={"answers": reponses}, timeout=30
        )
        assert derniere.status_code == 200, derniere.text
        assert derniere.json()["complete"] is False
        assert derniere.json()["question"]
        reponses.append(reponse)

    derniere = session.post(
        f"{base}/api/dialogue", json={"answers": reponses}, timeout=30
    )
    assert derniere.status_code == 200, derniere.text
    resultat = derniere.json()
    assert resultat["complete"] is True
    assert resultat["question"] is None
    assert "What the spec will declare" in "\n".join(resultat["messages"])
    assert "No vulnerabilities" in "\n".join(resultat["messages"])
    spec = resultat["spec"]
    assert spec.splitlines()[0] == "app StudioTest"
    assert len(spec.splitlines()) == 44
    attendu = iter(SCENARIO_PORTFOLIO)
    spec_directe = GuidedDialogue(ask=lambda _prompt: next(attendu)).run()
    assert spec == spec_directe

    validee = session.post(f"{base}/api/validate", json={"spec": spec}, timeout=30)
    assert validee.status_code == 200, validee.text
    assert validee.json()["valid"] is True

    compilee = session.post(f"{base}/api/compile", json={"spec": spec}, timeout=120)
    assert compilee.status_code == 201, compilee.text
    manifeste = compilee.json()
    assert manifeste["summary"]["app"] == "StudioTest"
    assert {"app.py", "schema.sql", "frontend_contract.json"} <= set(manifeste["files"])


def test_the_replay_refuses_inputs_bounded_by_http(running_platform):
    session = _session(running_platform)
    trop_long = session.post(
        f"{running_platform}/api/dialogue",
        json={"answers": ["x"] * (MAX_DIALOGUE_ANSWERS + 1)},
        timeout=30,
    )
    trop_grand = session.post(
        f"{running_platform}/api/dialogue",
        json={"answers": ["x" * (MAX_DIALOGUE_ANSWER_BYTES + 1)]},
        timeout=30,
    )
    assert trop_long.status_code == 422, trop_long.text
    assert trop_grand.status_code == 422, trop_grand.text
    assert "at most" in trop_long.json()["detail"]
    assert "bytes" in trop_grand.json()["detail"]


def test_the_pure_replay_stays_stable_and_stops_at_the_next_question():
    premier = replay([])
    suivant = replay(["1"])
    assert premier == replay([])
    assert "What type of application are you building?" in premier["question"]
    assert suivant["question"] == "Application name (e.g. StudioNova) > "


def test_three_typos_do_not_kill_the_dialogue(running_platform):
    """The defect found while reviewing Codex, measured before being fixed.

    The engine retries three times before raising (``max_retries``), and the
    browser never popped: a refused answer stayed in the list and burned an
    attempt FOREVER. At the third typo on the same question, every later replay
    answered 422 — forty-eight answers lost, with no way back, while the console
    politely offered to "start over".

    The fix: the server returns the AUTHORITATIVE list, and an answer it refused
    does not enter it. This test sends SIX mistakes — twice the attempt budget —
    then checks that the right answer still goes through.
    """
    session = _session(running_platform)
    retenues = []
    for essai in range(6):
        reponse = session.post(
            f"{running_platform}/api/dialogue",
            json={"answers": retenues, "answer": "réponse invalide"},
            timeout=30,
        )
        assert reponse.status_code == 200, f"faute {essai + 1} : {reponse.text}"
        data = reponse.json()
        assert data["accepted"] is False
        assert data["answers"] == [], "une réponse refusée ne doit JAMAIS être retenue"
        # The user must know WHY: without the message, their question comes
        # back unexplained and they make the same mistake again.
        assert any("✗" in ligne for ligne in data["messages"]), data["messages"]
        retenues = data["answers"]

    suite = session.post(
        f"{running_platform}/api/dialogue",
        json={"answers": retenues, "answer": "1"},
        timeout=30,
    )
    assert suite.status_code == 200, suite.text
    assert suite.json()["accepted"] is True
    assert suite.json()["answers"] == ["1"]
    assert "Application name" in suite.json()["question"]


# ────────── POINT 171: the list of choices is no longer thrown away ──────────
#
# `_ask` had always received `kind` and `options` and NEVER used them: the
# console only received the TERMINAL text and stuck it in a <pre>. Eleven
# templates showed as a mess of brackets. These witnesses are about what the
# ROUTE returns, not what the engine computes: the metadata got lost between
# the two.

def _premiere_question(base):
    session = _session(base)
    reponse = session.post(f"{base}/api/dialogue", json={"answers": []}, timeout=10)
    assert reponse.status_code == 200, reponse.text
    return reponse.json()


def test_the_choices_reach_the_route(running_platform):
    data = _premiere_question(running_platform)
    assert data["kind"] == "choice"
    assert data["title"] == "What type of application are you building?"
    options = data["options"]
    assert len(options) == 11, options
    assert [o["value"] for o in options] == [str(n) for n in range(1, 12)]
    assert options[0]["label"] == "Portfolio / showcase site"
    # The terminal text is still served: a client that displayed it keeps
    # working.
    assert "[1] Portfolio" in data["question"]


def test_each_choice_carries_its_help(running_platform):
    data = _premiere_question(running_platform)
    aides = data["hints"]
    for option in data["options"]:
        assert aides.get(option["label"]), option["label"]


def test_the_value_to_answer_comes_from_the_server_never_the_rank():
    """"none" is answered with 0, and this rule lives in only one place.

    Without the server carrying it, a presentation layer would number "none"
    from its rank in the list and send 12 out of eleven templates — two
    implementations of the same rule always diverge (point 146).
    """
    dialogue = GuidedDialogue(ask=lambda _prompt: "0")
    assert dialogue._ask_choice("Une question ?", ["a", "b"],
                                allow_none=True) is None
    assert dialogue.derniere_question["options"] == [
        {"label": "a", "value": "1"},
        {"label": "b", "value": "2"},
        {"label": "none", "value": "0"},
    ]
