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

#: The pages that carry a script. A page added without entering here would not
#: be checked — the witness below therefore requires them all to carry
#: JavaScript, otherwise the name is stale.
PAGES_WITH_SCRIPT = ("/console", "/", "/guide", "/mcp", "/login", "/account")

BLOCK_SCRIPT = re.compile(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", re.S | re.I)


def _node():
    path = shutil.which("node")
    if path is None:
        # No `skip`: a skip would say "nothing to check here", while it would
        # mean "I did not check" (point 140). Node is declared in
        # .github/workflows/ci.yml for that reason.
        pytest.fail("node is required to analyze the served JavaScript")
    return path


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    """A REAL server, like the rest of the suite.

    ``fastapi.testclient`` is the rejected path: it requires ``httpx2`` on recent
    Starlette versions — green locally with a mere deprecation warning, RED in
    CI. And it is better here: what we want to analyze is what comes out over
    HTTP, not what an in-memory client reconstructs.
    """
    application = create_app(workspace=tmp_path_factory.mktemp("js"))
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    server = uvicorn.Server(
        uvicorn.Config(application, host="127.0.0.1", port=port, log_level="error")
    )
    fil = threading.Thread(target=server.run, daemon=True)
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
            pytest.fail("the server did not start")
        inscription = session.post(
            f"{base}/api/auth/register",
            json={"email": "js@example.test", "password": "MotDePasse-123"},
            timeout=10,
        )
        assert inscription.status_code == 201, inscription.text
        yield base, session
    finally:
        server.should_exit = True
        fil.join(timeout=10)


def _scripts_of(client, path):
    base, session = client
    response = session.get(f"{base}{path}", timeout=10)
    assert response.status_code == 200, f"{path} : {response.status_code}"
    return BLOCK_SCRIPT.findall(response.text)


@pytest.mark.parametrize("path", PAGES_WITH_SCRIPT)
def test_the_served_javascript_parses_without_error(client, path, tmp_path):
    node = _node()
    blocks = _scripts_of(client, path)
    assert blocks, f"{path} serves no script: this entry is stale"
    for index, block in enumerate(blocks):
        file = tmp_path / f"{path.strip('/') or 'racine'}-{index}.js"
        file.write_text(block, encoding="utf-8")
        result = subprocess.run(
            [node, "--check", str(file)],
            capture_output=True, text=True, check=False,
        )
        assert result.returncode == 0, (
            f"{path}, script #{index}: invalid JavaScript — the page is "
            f"dead in a browser.\n{result.stderr}"
        )


def test_the_console_serves_the_start_button_with_its_apostrophe(client):
    """The named counter-proof: THIS string had broken the page."""
    node = _node()
    blocks = _scripts_of(client, "/console")
    whole = "\n".join(blocks)
    assert "Start the project" in whole, "the button disappeared from the served script"
    # The apostrophe must be ESCAPED in the literal, not bare.
    assert "Start the project\\'s API" in whole, (
        "the apostrophe is bare in the served JavaScript literal: "
        "a Python templating layer ate the backslash"
    )
    assert node
