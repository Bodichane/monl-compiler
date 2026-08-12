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
    "app.py": "ea2749849e13d3d8313fe1d57e8fbaee1672f67fdda24e7acb668defc2c8c9c0",
    "schema.sql": "244eb93ba9a727aa855bca0a96d76b2a329f8ee69c6b5bf2ba693d4c6eacba1f",
    "sandbox_ai.py": "53bcf473618c141b6df5b9326c540984d16b3fa2c64b7ed7787003b5da019c07",
    "manage.py": "5da45949451f1da15d17b84fcbe89ea4670116469897941ccd53daaa9c75ca46",
    "Dockerfile": "2ab01b5b3b75eef46d0fd626410fc088a0979aeca0ed8761e3cd6aae1be400ec",
    ".dockerignore": "7b7115e2c802900c8522a4090b06ad13d6f7733dcba154ee3bd392020219ff0b",
    # A2 ajoute l'historique _monl_migrations et le runtime de migrations
    # additives/explicites ; ces artefacts restent déterministes.
    # Le contrat et le brief restent identiques à l'octet : A2 ne change pas
    # ce que le frontend doit dessiner.
    # CONTRAT D'AUTHENTIFICATION : le contrat et le brief NOMMENT désormais les
    # champs que /register et /login renvoient (`access_token`, `token_type`,
    # `status`, `user_id`) au lieu d'annoncer « un token JWT » sans dire sous
    # quel nom le lire. Seuls ces deux artefacts bougent, plus monl.json qui
    # scelle leur empreinte : app.py, schema.sql et manage.py restent
    # identiques à l'octet — la preuve que la correction porte sur ce que le
    # backend DÉCLARE, pas sur ce qu'il fait.
    "frontend_contract.json": "8c2a7691b2a408c6c5624b65a7e70e77584812a4ac475f2e2d3ae38a8cd0e919",
    "FRONTEND_PROMPT.md": "4bc7696e3b31ac7ee13f5389c11f9e1770e0a6cb7725c07b83850481f0475cb4",
    "CLAUDE.md": "ebf07f5ca26ffa6bf8571ca6e0379afc31978b600b2cecd2ffe330719495183f",
    # Revue A2 : manage.py NOMME le remède au lieu de laisser filer une
    # trace quand la base attend une migration. app.py ne bouge PAS —
    # la preuve que le correctif ne touche que la commande d'administration.
    # 0.9.0-beta.7 : seul monl.json bouge, parce qu'il SCELLE la version du
    # compilateur. Tous les autres artefacts restent identiques a l'octet —
    # la preuve que la montee de version ne change rien a ce qui est genere.
    "monl.json": "ae75de61dceabd4d5f39882978db2924b3d90b84cf2523be7163f532fa26aeb8",
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
