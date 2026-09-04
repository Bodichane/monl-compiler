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
    # La génération d'un secret JWT au premier démarrage d'une archive sans
    # `.jwt_secret` est un second changement de runtime : app.py et monl.json
    # bougent volontairement, les autres artefacts restent inchangés.
    # POINT 138 : l'indicatif téléphonique s'applique désormais même sans zéro
    # de tête (il ne canonicalisait qu'un numéro européen). La normalisation
    # vit aux DEUX endroits qui doivent rester identiques, donc app.py ET
    # manage.py bougent, plus monl.json qui scelle l'empreinte du backend.
    # schema.sql, le contrat, le brief, le wrapper et le conteneur restent à
    # l'octet près : la correction ne touche que l'identifiant de compte.
    # Ce chantier ajoute `_LOOKUP_INDEXES` et la dépendance intermédiaire
    # `_identite_du_jeton` dans le runtime compilé : app.py change réellement.
    # Le pool PostgreSQL est lui aussi une évolution du runtime : app.py porte
    # ses réglages, sa fermeture dans le lifespan et son repli explicite ;
    # monl.json en scelle l'empreinte. schema.sql, manage.py et requirements.txt
    # restent hors de portée : psycopg[pool] est l'extra de compilation, pas une
    # dépendance du projet livré.
    "app.py": "2e07af6fed0f42860f6c18af075aa51ac7785fa2798366044fb4e0914df036ee",
    "schema.sql": "244eb93ba9a727aa855bca0a96d76b2a329f8ee69c6b5bf2ba693d4c6eacba1f",
    # `sandbox_ai.py` SORT des empreintes, et ce n'est pas un relâchement : la
    # spec de banc n'a aucun bloc `custom`, donc le module n'est plus produit.
    # Il ne contenait qu'un commentaire, `app.py` l'importait sans jamais
    # l'appeler, et le supprimer faisait échouer le démarrage — un fichier qui
    # ne fait rien et qu'on ne peut pas enlever. Son absence est AFFIRMÉE
    # ci-dessous plutôt que simplement cessée d'être regardée, et sa présence
    # avec un bloc `custom` est gardée par `tests/test_bloc_custom_absent.py`.
    # app.py perd donc sa ligne d'import : son empreinte change avec.
    "manage.py": "bc1529315536d6f9599efe8635d10b87827abc180b7d1dd77d793fc1f3d1f37f",
    # POINT 133 : le Dockerfile lançait `app:app`, donc l'image servait l'API
    # et répondait 404 sur /site et sur les photos — le wrapper qui les monte
    # n'était écrit que par 'monl run'. Il est désormais produit par
    # 'monl compile' et le CMD le lance. serve.py entre ici : un artefact
    # produit et non figé serait un angle mort, et c'est lui qui décide quels
    # dossiers sont servis. app.py, schema.sql, manage.py et sandbox_ai.py ne
    # bougent PAS — le contrôle de portée du changement.
    "serve.py": "cf2526ab9a4660201617e9204b74b394440b1e08eecf71641e11103f1ca2f3f2",
    # LE DOCKERFILE N'ÉNUMÈRE PLUS AUCUNE DÉPENDANCE : il installe
    # `-r requirements.txt`. Deux listes à tenir d'accord divergent toujours,
    # et celle-ci divergeait déjà — le gabarit n'ajoutait 'python-multipart'
    # que si la spec déclare un Upload, quand requirements.txt le listait
    # TOUJOURS. Il dit aussi, désormais, que MONL_ENV=production rend
    # MONL_JWT_SECRET obligatoire : le conteneur refusait de démarrer sans
    # lui, et il fallait avoir lu ses journaux pour l'apprendre.
    # SEULS le Dockerfile et requirements.txt bougent — app.py, schema.sql,
    # manage.py, le contrat, le brief et le wrapper restent à l'octet près :
    # c'est le contrôle de portée d'un changement qui ne touche que le
    # déploiement.
    "Dockerfile": "8296f97a1cb627bc8420715306de7c69cb926153c06eba9809e532686ada93a7",
    # requirements.txt n'était suivi par AUCUNE empreinte alors qu'il est
    # livré dans chaque archive : un artefact que personne ne regarde peut
    # changer sans qu'on le sache.
    "requirements.txt": "27a4075fed32b2a5edc575357721c5946ed99054bd0488bc219463d077f9ea06",
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
    # BRIQUE 30 : le contrat porte `links`, la liste des adresses SORTANTES
    # declarees dans `landing`. Elle est vide ici, et l'empreinte bouge quand
    # meme : la CLE existe desormais toujours, comme `faq` en son temps. Seuls
    # le contrat, le brief et monl.json changent — app.py, schema.sql et
    # manage.py restent identiques a l'octet, la preuve que la brique porte
    # sur ce que le frontend doit DESSINER et pas sur ce que le backend fait.
    "frontend_contract.json": "7ae58f38c5ac1d6baa2769cd40a20d9baf0b6d208884db0e55df365515466079",
    # Le brief gagne le plancher de couverture des workflows, l'interdiction
    # explicite des fichiers image locaux hors manifeste et l'alternative SVG
    # inline, puis la carte exécutable des marqueurs obligatoires : cette
    # empreinte change volontairement avec ces règles, tandis que les artefacts
    # backend restent inchangés à l'octet.
    # POINT 176 : les documents partent dans `docs/` et la mémoire du projet
    # s'appelle AGENTS.md. Le brief change d'empreinte pour une raison de FOND
    # et pas seulement d'emplacement — il dit à l'IA où trouver la direction
    # visuelle, donc il devait apprendre les nouveaux chemins. `README.md`
    # entre ici parce qu'il est livré : un artefact que personne ne regarde
    # peut changer sans qu'on le sache, même argument que requirements.txt.
    # LE CONTRÔLE DE PORTÉE : app.py, schema.sql, manage.py, serve.py, le
    # contrat, le Dockerfile et monl.json restent identiques à l'octet — un
    # rangement de fichiers ne touche rien de ce que le backend FAIT.
    "docs/FRONTEND_PROMPT.md": "3b3226c932f1139b2b247a1e689aea91b0a3076a2384f6ddcb02e78918d82f80",
    "AGENTS.md": "391c122e231bba4634597f498965767fd6427e734e50b9c17c747bd27d80c8a1",
    "README.md": "e325fa18c21c24dda20c8e56c1829dce44db91dbc7f0e494b7c3eeb437cf79b1",
    # Revue A2 : manage.py NOMME le remède au lieu de laisser filer une
    # trace quand la base attend une migration. app.py ne bouge PAS —
    # la preuve que le correctif ne touche que la commande d'administration.
    # 0.9.0-beta.7, puis beta.8, puis la BRIQUE 30 : monl.json bouge pour DEUX
    # causes distinctes — il scelle le numero de version du compilateur, et
    # l'empreinte du contrat, qui vient de gagner sa cle `links`. Les deux se
    # cumulent, donc a chaque fusion l'empreinte n'est celle d'AUCUN des deux
    # cotes et doit etre recalculee. Reprendre l'une des deux donnerait un test
    # qui passe sans rien prouver. Tous les autres artefacts restent identiques
    # a l'octet, trois fois de suite : c'est ce que ce test est la pour tenir.
    # monl.json scelle l'empreinte de ce nouvel app.py ; aucun autre artefact
    # n'est touché par les deux correctifs backend.
    "monl.json": "35bb222280ec90ad923e728f038e2034d502cf6d706fc868340dc820e1fe5775",
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
    _aucun_module_custom_inutile(tmp_path)

    compile_project(str(spec), str(tmp_path))
    capsys.readouterr()
    assert _empreintes(tmp_path) == GOLDENS
    _aucun_module_custom_inutile(tmp_path)


def _aucun_module_custom_inutile(project_dir: Path):
    """Retirer une empreinte n'AFFIRME rien — cesser de regarder n'est pas une
    garantie. La spec de banc n'ayant aucun bloc `custom`, l'absence du module
    est le résultat attendu, et c'est elle qu'on mesure.

    Sa PRÉSENCE quand un bloc `custom` existe est gardée ailleurs
    (`tests/test_bloc_custom_absent.py`) : sans cette contre-épreuve, ne plus
    jamais l'émettre rendrait les deux fichiers verts en tuant la brique.
    """
    assert not (project_dir / "sandbox_ai.py").exists(), (
        "un module 'custom' vide est livré alors que la spec n'en déclare aucun")
