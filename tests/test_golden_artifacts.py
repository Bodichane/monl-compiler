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
    # CHANTIER A1 : app.py porte le choix de dialecte au démarrage, les
    # migrations PostgreSQL et les intégrités structurées. schema.sql change
    # aussi pour employer DOUBLE PRECISION côté SQLite/PostgreSQL. manage.py
    # réutilise désormais la connexion du backend. monl.json bouge parce qu'il
    # scelle l'empreinte du backend généré.
    # Deux correctifs de revue A1 déplacent app.py et manage.py une seconde
    # fois : l'`except` d'intégrité se termine par un `raise` inconditionnel
    # (sans lui une quatrième espèce d'erreur sortait sans rien lever), et
    # manage.py importe app.py depuis _connect() et non en tête de fichier
    # (importé en tête, il cessait de fonctionner depuis un autre dossier).
    "app.py": "b8ae8154d5b154c3d6d27b0c984c4586ed789c12ba135f862919e2fd753cc4c7",
    "schema.sql": "a2366f02b9fa979f0435264019150f296b7de055af7bc2fa8d643840a3887ad3",
    "sandbox_ai.py": "53bcf473618c141b6df5b9326c540984d16b3fa2c64b7ed7787003b5da019c07",
    "manage.py": "7155285aa59cbae26ebfc3351544c6a9c2f24aa30b537d0602a2c388c8ca30bf",
    "Dockerfile": "2ab01b5b3b75eef46d0fd626410fc088a0979aeca0ed8761e3cd6aae1be400ec",
    ".dockerignore": "7b7115e2c802900c8522a4090b06ad13d6f7733dcba154ee3bd392020219ff0b",
    # Le contrat et le brief restent identiques à l'octet : A1 ne change pas
    # ce que le frontend doit dessiner.
    "frontend_contract.json": "9ac0c4b0fc7c2100f1b94dbe626131384d2b6927310240c23986d56198ff5884",
    "FRONTEND_PROMPT.md": "3ffc727a681395fee8800b4554e929dd0f15a9d80d3d025555292c8673f746a6",
    "CLAUDE.md": "ebf07f5ca26ffa6bf8571ca6e0379afc31978b600b2cecd2ffe330719495183f",
    "monl.json": "6d52ee33813063452fd890d3175e97737f400a953a3ba2b570ae49443e03fe2e",
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
