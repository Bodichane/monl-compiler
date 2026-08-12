"""Golden tests des artefacts déterministes d'une spec représentative."""

import hashlib
from pathlib import Path

from monl.cli import compile_project

SPEC = """app Golden

entity Note
    titre: String
    publiee: Boolean

actor Auteur selfRegister

rule Note.Read public

workflow Ecrire for Auteur
    Create Note
    Read Note
"""

GOLDENS = {
    "app.py": "23fdeec2556e84918aa196cc9651ad64f5c8111c09ab0826c1c218b2caeb721b",
    "schema.sql": "d8813137e80284dd94632ae49b3a9d9c8cc541776d52bac03f07e5161bb7a5d1",
    "sandbox_ai.py": "53bcf473618c141b6df5b9326c540984d16b3fa2c64b7ed7787003b5da019c07",
    "manage.py": "417bdff729cc9bec28804e5ba9f490c014e96b94c6e36c14d595473864b04cd0",
    # POINT 116 : contrat en version 9 (règles métier publicWhen/oncePer
    # déclarées). Seuls ces DEUX fichiers bougent — app.py, schema.sql,
    # manage.py et le brief restent identiques à l'octet, ce qui prouve
    # qu'une spec sans ces règles n'est pas touchée par le point.
    "frontend_contract.json": "9ac0c4b0fc7c2100f1b94dbe626131384d2b6927310240c23986d56198ff5884",
    "FRONTEND_PROMPT.md": "3ffc727a681395fee8800b4554e929dd0f15a9d80d3d025555292c8673f746a6",
    "CLAUDE.md": "ebf07f5ca26ffa6bf8571ca6e0379afc31978b600b2cecd2ffe330719495183f",
    "monl.json": "23dd5387cd9069651aec2de68cf1597090fbb3f45aacc14326101f45bb4ca56c",
}


def _empreintes(project_dir: Path):
    return {
        name: hashlib.sha256((project_dir / name).read_bytes()).hexdigest()
        for name in GOLDENS
    }


def test_une_recompilation_garde_les_artefacts_deterministes(tmp_path, capsys):
    spec = tmp_path / "spec.ml"
    spec.write_text(SPEC, encoding="utf-8")

    compile_project(str(spec), str(tmp_path))
    capsys.readouterr()
    assert _empreintes(tmp_path) == GOLDENS

    compile_project(str(spec), str(tmp_path))
    capsys.readouterr()
    assert _empreintes(tmp_path) == GOLDENS
