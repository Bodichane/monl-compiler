"""Le harnais de test, éprouvé comme le reste.

`uvicorn_server` monte les serveurs de vingt et un fichiers d'intégration
(paiement, agrégation, verrou de paiement, plateforme…). Tant qu'il
convertissait la mort d'un serveur en `pytest.skip`, tous ces fichiers
pouvaient ne rien vérifier en rendant du vert — et c'est arrivé : la suite
complète produisait un `serveur uvicorn arrêté avant de répondre (code 1)`
que personne ne lisait, pendant que les mêmes fichiers passaient un par un.

Un outil de preuve qui n'est pas lui-même prouvé ne prouve rien.
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
    """Monte un serveur qu'on sait condamné et rend le message d'échec.

    Écrit ainsi plutôt qu'avec `pytest.raises` pour une raison MESURÉE : sur
    l'ancien harnais, un `Skipped` levé à l'intérieur d'un
    `pytest.raises(Failed)` traverse et fait SAUTER le test qui l'entoure.
    Deux des tests de ce fichier passaient donc pour verts en ne vérifiant
    rien — le piège qu'on répare, reproduit dans son propre témoin. Un saut
    est ici traité comme la panne qu'il est.
    """
    try:
        with uvicorn_server(**kwargs):
            pass
    except pytest.skip.Exception as saut:
        pytest.fail(f"serveur mort SAUTÉ au lieu d'échouer : {saut}")
    except pytest.fail.Exception as echec:
        return str(echec)
    pytest.fail("un serveur qui ne démarre pas doit faire échouer le test")


def test_un_serveur_qui_ne_demarre_pas_fait_echouer_et_jamais_sauter(tmp_path):
    """Le cœur du correctif.

    Écrit en attrapant les deux issues SÉPARÉMENT plutôt qu'avec un
    `pytest.raises` : un `Skipped` levé dans un `pytest.raises(Failed)` ferait
    SAUTER ce test-ci, donc l'ancien comportement passerait pour vert. Le
    piège qu'on répare se reproduirait dans le test qui le répare.
    """
    (tmp_path / "app.py").write_text(APP_EN_PANNE, encoding="utf-8")
    message = echec_attendu(directory=str(tmp_path), attempts=8)
    assert "s'est arrêté avant de répondre" in message
    # La cause doit être DANS le message : c'est tout l'intérêt d'avoir sorti
    # la sortie d'uvicorn de DEVNULL.
    assert "panne volontaire du harnais" in message, message


def test_le_diagnostic_nomme_le_module_et_le_dossier(tmp_path):
    """Un message qui ne dit ni quoi ni où envoie chercher au mauvais
    endroit — le reproche du point 97, sur un autre outil."""
    (tmp_path / "app.py").write_text(APP_EN_PANNE, encoding="utf-8")
    message = echec_attendu(directory=str(tmp_path), attempts=8)
    assert "app:app" in message
    assert str(tmp_path) in message


def test_un_module_inexistant_est_rapporte_avec_sa_cause(tmp_path):
    """L'autre façon de mourir : le module ne s'importe pas du tout."""
    message = echec_attendu(directory=str(tmp_path), module="absent:app", attempts=8)
    assert "absent:app" in message
    assert "(le serveur n a rien ecrit)" not in message, (
        "la sortie d'uvicorn doit être rapportée, pas perdue")


def test_un_serveur_sain_repond_et_son_port_est_tenu(tmp_path):
    """Le témoin : sans lui, un harnais qui échouerait TOUJOURS passerait les
    trois tests ci-dessus.

    Le second volet mesure ce que le correctif promet — pendant que le
    serveur vit, personne d'autre ne peut prendre son port. On ne vérifie PAS
    qu'il est rendu ensuite : une connexion fermée reste en `TIME_WAIT`, et
    l'affirmer serait énoncer un détail d'OS qu'on n'a pas mesuré."""
    (tmp_path / "app.py").write_text(APP_SAINE, encoding="utf-8")
    with uvicorn_server(str(tmp_path)) as base:
        reponse = requests.get(base + "/openapi.json", timeout=5)
        assert reponse.status_code == 200

        port = int(base.rsplit(":", 1)[1])
        with socket.socket() as intrus:
            intrus.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            with pytest.raises(OSError):
                intrus.bind(("127.0.0.1", port))


def test_le_serveur_ne_passe_plus_par_free_port(tmp_path, monkeypatch):
    """La preuve que la voie racée n'est plus empruntée.

    Lire le code source dirait seulement qu'un `--fd` y figure ; faire
    exploser `free_port` dit que le serveur monte SANS lui.
    """
    appels = []
    monkeypatch.setattr(harnais, "free_port",
                        lambda: appels.append(1) or 65535)
    (tmp_path / "app.py").write_text(APP_SAINE, encoding="utf-8")
    with uvicorn_server(str(tmp_path)) as base:
        assert base.startswith("http://127.0.0.1:")
        assert not base.endswith(":65535"), "le port vient encore de free_port"
    assert appels == [], "uvicorn_server appelle encore free_port"


def test_free_port_relache_son_port_ce_qui_est_la_faille_documentee():
    """Pourquoi `uvicorn_server` ne s'en sert plus.

    Ce test ne dénonce pas un bug à corriger : il ÉNONCE la limite de
    `free_port`, encore appelé par une vingtaine de fichiers qui montent leur
    serveur eux-mêmes. Si un jour il cesse de relâcher, ce test le dira et la
    docstring devra suivre.
    """
    port = free_port()
    with socket.socket() as autre:
        # Personne ne l'en empêche : le port est libre entre les deux gestes.
        autre.bind(("127.0.0.1", port))
        assert autre.getsockname()[1] == port
