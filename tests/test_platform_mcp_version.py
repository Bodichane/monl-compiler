"""Issue #90: the MCP server announces the PACKAGE version.

`serverInfo.version` was hard-coded to `0.1.0` while the package was at
0.9.0-beta.10: every MCP client displayed and logged a wrong number, and a
user reporting a problem gave a version nobody could trace. The witness
starts the server the way a client does — a separate process speaking over
stdio — and checks its answer against both sources of the version:
`monl.__version__` and `pyproject.toml`.
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
    # Non-emptiness: without an answer, the comparisons below would bear on
    # nothing (point 161).
    assert lignes, sortie.stderr
    return lignes[0]["result"]["serverInfo"]


def test_the_mcp_server_announces_the_package_version(tmp_path):
    info = _initialize(tmp_path)
    assert info["name"] == "monl-compiler"
    assert info["version"] == monl.__version__

    try:
        import tomllib
    except ModuleNotFoundError:      # 3.10 : `tomllib` n'arrive qu'en 3.11
        import tomli as tomllib      # noqa: I001  (declared in the `dev` extra)
    projet = tomllib.loads((RACINE / "pyproject.toml").read_text(encoding="utf-8"))
    # Through `Version` and never as strings: `0.9.0-beta.10` and `0.9.0b10`
    # are the same version (point 169).
    assert Version(info["version"]) == Version(projet["project"]["version"])
