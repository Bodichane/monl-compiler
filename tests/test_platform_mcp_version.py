"""Issue #90 : le serveur MCP annonce la version du PAQUET.

`serverInfo.version` était écrit en dur à `0.1.0` pendant que le paquet était
en 0.9.0-beta.10 : tout client MCP affichait et journalisait un numéro faux,
et un usager signalant un problème donnait une version que personne ne
pouvait retrouver. Le témoin lance le serveur comme un client le lance — un
processus séparé qui parle en stdio — et confronte sa réponse aux deux sources
de la version : `monl.__version__` et `pyproject.toml`.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

from packaging.version import Version

import monl

RACINE = Path(__file__).resolve().parents[1]


def _initialize(espace):
    requete = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
               "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                          "clientInfo": {"name": "temoin", "version": "0"}}}
    env = dict(os.environ, MONL_PLATFORM_WORKSPACE=str(espace))
    sortie = subprocess.run(
        [sys.executable, "-m", "monl_platform.mcp_server"],
        input=json.dumps(requete) + "\n", capture_output=True, text=True,
        timeout=30, env=env, check=True)
    lignes = [json.loads(ligne) for ligne in sortie.stdout.splitlines() if ligne.strip()]
    # Non-vacuité : sans réponse, les comparaisons ci-dessous ne porteraient
    # sur rien (point 161).
    assert lignes, sortie.stderr
    return lignes[0]["result"]["serverInfo"]


def test_le_serveur_mcp_annonce_la_version_du_paquet(tmp_path):
    info = _initialize(tmp_path)
    assert info["name"] == "monl-compiler"
    assert info["version"] == monl.__version__

    try:
        import tomllib
    except ModuleNotFoundError:      # 3.10 : `tomllib` n'arrive qu'en 3.11
        import tomli as tomllib      # noqa: I001  (déclaré dans l'extra `dev`)
    projet = tomllib.loads((RACINE / "pyproject.toml").read_text(encoding="utf-8"))
    # Par `Version` et jamais par chaîne : `0.9.0-beta.10` et `0.9.0b10` sont
    # la même version (point 169).
    assert Version(info["version"]) == Version(projet["project"]["version"])
