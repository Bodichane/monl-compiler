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
    # CHANTIER A3 : app.py bouge pour les healthchecks, CORS opt-in, logs
    # structurés et le refus du mode production sans secret. monl.json bouge
    # aussi parce qu'il enregistre l'empreinte du backend généré. Les deux
    # artefacts de conteneur sont inclus ici pour figer leur gabarit initial ;
    # ils restent néanmoins non scellés et préservés s'ils sont édités.
    "app.py": "08cafba0acb455ff1f45e6972c542d2479e48d77bd4635983c10a3a51e610c1c",
    "schema.sql": "d8813137e80284dd94632ae49b3a9d9c8cc541776d52bac03f07e5161bb7a5d1",
    "sandbox_ai.py": "53bcf473618c141b6df5b9326c540984d16b3fa2c64b7ed7787003b5da019c07",
    "manage.py": "417bdff729cc9bec28804e5ba9f490c014e96b94c6e36c14d595473864b04cd0",
    "Dockerfile": "2ab01b5b3b75eef46d0fd626410fc088a0979aeca0ed8761e3cd6aae1be400ec",
    ".dockerignore": "7b7115e2c802900c8522a4090b06ad13d6f7733dcba154ee3bd392020219ff0b",
    # Le contrat et le brief restent identiques à l'octet : A3 ne change pas
    # ce que le frontend doit dessiner.
    "frontend_contract.json": "9ac0c4b0fc7c2100f1b94dbe626131384d2b6927310240c23986d56198ff5884",
    "FRONTEND_PROMPT.md": "3ffc727a681395fee8800b4554e929dd0f15a9d80d3d025555292c8673f746a6",
    "CLAUDE.md": "ebf07f5ca26ffa6bf8571ca6e0379afc31978b600b2cecd2ffe330719495183f",
    "monl.json": "3e9c1e420c14e190d6e8e5efb1b1cc96c24b9da153710a7d4386e1af1c178d45",
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
