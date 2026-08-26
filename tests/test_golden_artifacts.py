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
    # POINT 132 : le socle démarre désormais sans mourir sur une base qu'un
    # autre processus écrit — `_activer_wal` tolérant, et l'initialisation
    # réessayée. Le changement vit dans le RUNTIME, donc seuls app.py et
    # monl.json (qui scelle son empreinte) bougent : schema.sql, manage.py et
    # le Dockerfile restent à l'octet près, ce qui est le contrôle de portée.
    # POINT 138 : l'indicatif téléphonique s'applique désormais même sans zéro
    # de tête (il ne canonicalisait qu'un numéro européen). La normalisation
    # vit aux DEUX endroits qui doivent rester identiques, donc app.py ET
    # manage.py bougent, plus monl.json qui scelle l'empreinte du backend.
    # schema.sql, le contrat, le brief, le wrapper et le conteneur restent à
    # l'octet près : la correction ne touche que l'identifiant de compte.
    "app.py": "43a587eb63fa612dc6083c4e567a624ac5dad2943c0d7fc762dd3415f29abbf5",
    "schema.sql": "244eb93ba9a727aa855bca0a96d76b2a329f8ee69c6b5bf2ba693d4c6eacba1f",
    "sandbox_ai.py": "53bcf473618c141b6df5b9326c540984d16b3fa2c64b7ed7787003b5da019c07",
    "manage.py": "bc1529315536d6f9599efe8635d10b87827abc180b7d1dd77d793fc1f3d1f37f",
    # POINT 133 : le Dockerfile lançait `app:app`, donc l'image servait l'API
    # et répondait 404 sur /site et sur les photos — le wrapper qui les monte
    # n'était écrit que par 'monl run'. Il est désormais produit par
    # 'monl compile' et le CMD le lance. serve.py entre ici : un artefact
    # produit et non figé serait un angle mort, et c'est lui qui décide quels
    # dossiers sont servis. app.py, schema.sql, manage.py et sandbox_ai.py ne
    # bougent PAS — le contrôle de portée du changement.
    "serve.py": "cf2526ab9a4660201617e9204b74b394440b1e08eecf71641e11103f1ca2f3f2",
    "Dockerfile": "e6d8293d7375a5b797901f2678a3e3e27fa85049a3c42826a8f168abc64e21d7",
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
    "FRONTEND_PROMPT.md": "8d6c2c8af49299b0f523eec333f51bb93e2ee8985befe1300475f6796f01df2f",
    "CLAUDE.md": "ebf07f5ca26ffa6bf8571ca6e0379afc31978b600b2cecd2ffe330719495183f",
    # Revue A2 : manage.py NOMME le remède au lieu de laisser filer une
    # trace quand la base attend une migration. app.py ne bouge PAS —
    # la preuve que le correctif ne touche que la commande d'administration.
    # 0.9.0-beta.7, puis 0.9.0-beta.8 : seul monl.json bouge, parce qu'il
    # SCELLE la version du compilateur. Tous les autres artefacts restent
    # identiques a l'octet — la preuve que la montee de version ne change rien
    # a ce qui est genere. Deux versions de suite, donc ce n'est pas une
    # coincidence : c'est ce que ce test est la pour tenir.
    "monl.json": "4ba690fdf13ae3647040480956406c39579660c7e5b68a88b1360285e0e1fdab",
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
