"""Preuves du rejeu HTTP du dialogue guidé dans la console."""

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


def test_le_rejeu_est_borne_sans_tronquer():
    with pytest.raises(ValueError, match="au plus"):
        bounded_answers(["x"] * (MAX_DIALOGUE_ANSWERS + 1))
    with pytest.raises(ValueError, match="octets"):
        bounded_answers(["x" * (MAX_DIALOGUE_ANSWER_BYTES + 1)])
    with pytest.raises(ValueError, match="liste"):
        bounded_answers("pas une liste")


def test_le_rejeu_http_complet_produit_un_backend_attendu(running_platform):
    """Le parcours entier se fait par HTTP contre uvicorn, sans session serveur."""
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
    assert "Ce que la spec va déclarer" in "\n".join(resultat["messages"])
    assert "Aucune vulnérabilité" in "\n".join(resultat["messages"])
    spec = resultat["spec"]
    assert spec.splitlines()[0] == "app StudioTest"
    assert len(spec.splitlines()) == 42
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


def test_le_rejeu_refuse_les_entrees_bornees_par_http(running_platform):
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
    assert "au plus" in trop_long.json()["detail"]
    assert "octets" in trop_grand.json()["detail"]


def test_le_rejeu_pur_reste_stable_et_s_arrete_a_la_question_suivante():
    premier = replay([])
    suivant = replay(["1"])
    assert premier == replay([])
    assert "Quel type d'application construisez-vous ?" in premier["question"]
    assert suivant["question"] == "Nom de l'application (ex. StudioNova) > "


def test_trois_fautes_de_frappe_ne_tuent_pas_le_dialogue(running_platform):
    """Le défaut trouvé en relisant Codex, mesuré avant d'être corrigé.

    Le moteur retente trois fois avant de lever (``max_retries``), et le
    navigateur ne dépilait jamais : une réponse refusée restait dans la liste
    et brûlait une tentative POUR TOUJOURS. À la troisième faute de frappe sur
    la même question, tout rejeu ultérieur répondait 422 — quarante-huit
    réponses perdues, sans retour possible, pendant que la console proposait
    poliment de « recommencer ».

    La correction : le serveur rend la liste FAISANT AUTORITÉ, et une réponse
    qu'il a refusée n'y entre pas. Ce test envoie SIX fautes — deux fois le
    budget de tentatives — puis vérifie que la bonne réponse passe encore.
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
        # L'usager doit savoir POURQUOI : sans le message, sa question revient
        # sans explication et il refait la même faute.
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
    assert "Nom de l'application" in suite.json()["question"]


# ─────────── POINT 171 : la liste des choix ne se jette plus ───────────
#
# `_ask` recevait `kind` et `options` depuis toujours et ne s'en servait
# JAMAIS : la console ne recevait que le texte de TERMINAL et le collait dans
# un <pre>. Onze modèles s'affichaient en une bouillie de crochets. Ces
# témoins portent sur ce que la ROUTE renvoie, pas sur ce que le moteur
# calcule : c'est entre les deux que la métadonnée se perdait.

def _premiere_question(base):
    session = _session(base)
    reponse = session.post(f"{base}/api/dialogue", json={"answers": []}, timeout=10)
    assert reponse.status_code == 200, reponse.text
    return reponse.json()


def test_les_choix_arrivent_jusqua_la_route(running_platform):
    data = _premiere_question(running_platform)
    assert data["kind"] == "choice"
    assert data["title"] == "Quel type d'application construisez-vous ?"
    options = data["options"]
    assert len(options) == 11, options
    assert [o["value"] for o in options] == [str(n) for n in range(1, 12)]
    assert options[0]["label"] == "Portfolio / site vitrine"
    # Le texte de terminal reste servi : un client qui l'affichait continue.
    assert "[1] Portfolio" in data["question"]


def test_chaque_choix_porte_son_aide(running_platform):
    data = _premiere_question(running_platform)
    aides = data["hints"]
    for option in data["options"]:
        assert aides.get(option["label"]), option["label"]


def test_la_valeur_a_repondre_vient_du_serveur_jamais_du_rang():
    """« aucun » se répond par 0, et cette règle ne vit qu'à un endroit.

    Sans elle portée par le serveur, une couche de présentation numéroterait
    « aucun » d'après son rang dans la liste et enverrait 12 sur onze
    modèles — deux mises en œuvre d'une même règle divergent toujours
    (point 146).
    """
    dialogue = GuidedDialogue(ask=lambda _prompt: "0")
    assert dialogue._ask_choice("Une question ?", ["a", "b"],
                                allow_none=True) is None
    assert dialogue.derniere_question["options"] == [
        {"label": "a", "value": "1"},
        {"label": "b", "value": "2"},
        {"label": "aucun", "value": "0"},
    ]
