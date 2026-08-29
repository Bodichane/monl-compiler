"""Le JavaScript RÉELLEMENT SERVI doit s'analyser — sinon la console est morte.

CE QUE CE FICHIER EXISTE POUR ATTRAPER, et qui est passé au travers de 1373
tests et de la CI sur trois versions de Python. Dans une chaîne Python non
brute, ``\\'`` vaut ``'`` : écrire ``'…Démarrer l\\'API…'`` dans un gabarit
émettait ``'…Démarrer l'API…'``, donc une apostrophe NUE au milieu d'un
littéral JavaScript. Le navigateur levait ``SyntaxError: Unexpected identifier
'API'`` et **tout** le script de la console cessait de s'exécuter — plus un
seul bouton ne répondait.

Rien ne l'a vu parce que rien n'exécutait ce JavaScript : les tests lisaient le
HTML servi et y cherchaient des chaînes, ce qu'une page cassée contient tout
aussi bien. C'est le « sur-échappement de backslash entre couches de templating
Python » que CLAUDE.md range parmi les défauts invisibles à la relecture, et
c'est la même leçon qu'au point 83 : *« présent » n'est pas « qui marche »*.

La vérification porte sur ce que la ROUTE rend, jamais sur la constante du
module : c'est entre les deux que l'échappement se perd.
"""

import re
import shutil
import socket
import subprocess
import threading
import time

import pytest
import requests
import uvicorn

from monl_platform.app import create_app

#: Les pages qui embarquent du script. Une page ajoutée sans entrer ici ne
#: serait pas vérifiée — le témoin ci-dessous exige donc qu'elles portent
#: toutes du JavaScript, faute de quoi le nom est périmé.
PAGES_AVEC_SCRIPT = ("/console", "/", "/guide", "/mcp", "/login", "/account")

BLOC_SCRIPT = re.compile(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", re.S | re.I)


def _node():
    chemin = shutil.which("node")
    if chemin is None:
        # Pas de `skip` : un saut dirait « rien à vérifier ici », alors qu'il
        # dirait « je n'ai pas vérifié » (point 140). Node est déclaré dans
        # .github/workflows/ci.yml pour cette raison.
        pytest.fail("node est requis pour analyser le JavaScript servi")
    return chemin


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    """Un VRAI serveur, comme le reste de la suite.

    ``fastapi.testclient`` est la voie écartée : il exige ``httpx2`` sur les
    versions récentes de Starlette — vert en local avec un simple
    avertissement de dépréciation, ROUGE en CI. Et il vaut mieux ici : ce
    qu'on veut analyser est ce qui sort par HTTP, pas ce qu'un client
    en-mémoire reconstitue.
    """
    application = create_app(workspace=tmp_path_factory.mktemp("js"))
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    serveur = uvicorn.Server(
        uvicorn.Config(application, host="127.0.0.1", port=port, log_level="error")
    )
    fil = threading.Thread(target=serveur.run, daemon=True)
    fil.start()
    base = f"http://127.0.0.1:{port}"
    session = requests.Session()
    try:
        for _ in range(200):
            try:
                if requests.get(f"{base}/health", timeout=0.2).status_code == 200:
                    break
            except requests.RequestException:
                time.sleep(0.02)
        else:
            pytest.fail("le serveur n'a pas démarré")
        inscription = session.post(
            f"{base}/api/auth/register",
            json={"email": "js@example.test", "password": "MotDePasse-123"},
            timeout=10,
        )
        assert inscription.status_code == 201, inscription.text
        yield base, session
    finally:
        serveur.should_exit = True
        fil.join(timeout=10)


def _scripts_de(client, chemin):
    base, session = client
    reponse = session.get(f"{base}{chemin}", timeout=10)
    assert reponse.status_code == 200, f"{chemin} : {reponse.status_code}"
    return BLOC_SCRIPT.findall(reponse.text)


@pytest.mark.parametrize("chemin", PAGES_AVEC_SCRIPT)
def test_le_javascript_servi_s_analyse_sans_erreur(client, chemin, tmp_path):
    node = _node()
    blocs = _scripts_de(client, chemin)
    assert blocs, f"{chemin} ne sert aucun script : cette entrée est périmée"
    for index, bloc in enumerate(blocs):
        fichier = tmp_path / f"{chemin.strip('/') or 'racine'}-{index}.js"
        fichier.write_text(bloc, encoding="utf-8")
        resultat = subprocess.run(
            [node, "--check", str(fichier)],
            capture_output=True, text=True, check=False,
        )
        assert resultat.returncode == 0, (
            f"{chemin}, script #{index} : JavaScript invalide — la page est "
            f"morte dans un navigateur.\n{resultat.stderr}"
        )


def test_la_console_sert_le_bouton_de_demarrage_avec_son_apostrophe(client):
    """La contre-épreuve nommée : c'est CETTE chaîne qui avait cassé la page."""
    node = _node()
    blocs = _scripts_de(client, "/console")
    entier = "\n".join(blocs)
    assert "Démarrer l" in entier, "le bouton a disparu du script servi"
    # L'apostrophe doit être ÉCHAPPÉE dans le littéral, pas nue.
    assert "Démarrer l\\'API" in entier, (
        "l'apostrophe est nue dans le littéral JavaScript servi : "
        "une couche de templating Python a mangé l'antislash"
    )
    assert node
