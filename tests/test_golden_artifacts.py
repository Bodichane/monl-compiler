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

# Banc backend dédié aux deux sources ajoutées au point 181. Il reste
# séparé de SPEC : le golden historique doit continuer à prouver que les
# artefacts d'une spec sans ces règles ne changent pas. Ici, les deux index
# supplémentaires sont effectivement présents dans _LOOKUP_INDEXES.
SPEC_LOOKUP_SOURCES = """app GoldenLookup

entity Note
    titre: String
    status: String

entity Message
    contenu: Text
    member_id: Integer
    recipient_id: Integer

actor Reader selfRegister

rule Note.Read publicWhen status "published"
rule Message.Read accessibleBy member_id, recipient_id

workflow Lire for Reader
    Read Note
    Read Message
"""

# WAL startup now retries within the busy timeout and propagates expiry.
# POINT 201 : les trois bancs gagnent l'import field_validator dans app.py.
# monl.json scelle cette empreinte et language_version (point 200).
# Tous les autres artefacts mesurés restent identiques à l'octet.
# MIGRATION ANGLAISE, LOT 3 : tout artefact qui porte du texte LU change —
# messages d'erreur d'app.py et de manage.py, en-tête de schema.sql, wrapper
# serve.py, notes du contrat, brief frontend, AGENTS.md et README.md ; monl.json
# scelle ces empreintes. Le contrôle de portée tient : Dockerfile,
# requirements.txt et .dockerignore restent identiques à l'octet — traduire
# ne touche ni aux dépendances ni au déploiement.
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
    # POINT 191 : le diff réel ajoute la liste des colonnes oneOf réservées à
    # l'après-paiement et généralise l'UNIQUE boucle du point 89 qui compte les
    # NULL irrécupérables. Aucune route ni aucun contrat ne change ici.
    "app.py": "0cb4c86e4ef7e1a9b469862489884c5deec653ba1d34317eb55f036169c9833c",
    "schema.sql": "e33bc5b4cf0dbf78cb0290372e41521db6752de5691f43a9566b79e8137641be",
    # `sandbox_ai.py` SORT des empreintes, et ce n'est pas un relâchement : la
    # spec de banc n'a aucun bloc `custom`, donc le module n'est plus produit.
    # Il ne contenait qu'un commentaire, `app.py` l'importait sans jamais
    # l'appeler, et le supprimer faisait échouer le démarrage — un fichier qui
    # ne fait rien et qu'on ne peut pas enlever. Son absence est AFFIRMÉE
    # ci-dessous plutôt que simplement cessée d'être regardée, et sa présence
    # avec un bloc `custom` est gardée par `tests/test_bloc_custom_absent.py`.
    # app.py perd donc sa ligne d'import : son empreinte change avec.
    "manage.py": "252dc4b6f1c87a488be8f84423a418b7c348e56cc28fa3752a0669b2e4cadc83",
    # POINT 133 : le Dockerfile lançait `app:app`, donc l'image servait l'API
    # et répondait 404 sur /site et sur les photos — le wrapper qui les monte
    # n'était écrit que par 'monl run'. Il est désormais produit par
    # 'monl compile' et le CMD le lance. serve.py entre ici : un artefact
    # produit et non figé serait un angle mort, et c'est lui qui décide quels
    # dossiers sont servis. app.py, schema.sql, manage.py et sandbox_ai.py ne
    # bougent PAS — le contrôle de portée du changement.
    "serve.py": "29767912bcffa904b3b9afca78d22b449c8862298572b5367e3ec80b29e40993",
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
    "Dockerfile": "4c19d2ee5a783537c784ddfcc69472c658ec9381088e6e17efc9aff488a31f0f",
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
    "frontend_contract.json": "d3cfebcebc8bdc43f98bc59363d67f62b7baf652f49d73030312041f7972a92c",
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
    "docs/FRONTEND_PROMPT.md": "584f80272c12f7b8a2df9e9cfc63de854ee520a7a67b68a42567cf6481d4e403",
    "AGENTS.md": "cdf84f9c37cbc5b23818d9f769704285a11c52ce7f48149f390bb19d3a5188c8",
    "README.md": "a20e092d4391b8de165f8ec3b705b55828dcb3ed89373a20492c198ff7c89be7",
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
    # 0.9.0-beta.9 : seul monl.json bouge, et `diff -r` entre deux compilations
    # du même code sous beta.8 puis beta.9 ne montre qu'une ligne —
    # `compiler_version`. Quatrième version de suite où c'est vrai.
    # POINT 191 : le diff réel ne change que backend_sha256.app.py, reflet de
    # la boucle de comptage ci-dessus ; toutes les autres empreintes sont fixes.
    # 0.9.0-beta.10 : `diff -r` entre deux compilations du même code sous
    # beta.9 puis beta.10 ne montre que `compiler_version` (et le
    # `.jwt_secret`, tiré au hasard, hors de ce test). Cinquième version de
    # suite.
    "monl.json": "045e6e116e2d43a62952a5bfd5a24c4e8dbafdc8658cc861b5e1a3a897ec4da9",
}

# POINT 203 : app.py gagne l’enveloppe ASGI de sécurité globale ;
# monl.json scelle son empreinte. Les autres artefacts restent identiques.

# Empreintes de la fixture qui porte réellement `publicWhen` et
# `accessibleBy` : le correctif ajoute les index de `status` et
# `recipient_id` au runtime, et monl.json scelle le nouvel app.py.
LOOKUP_GOLDENS = {
    # Recalculées à la fusion des points 182 et 183 : chaque branche avait
    # inscrit SON empreinte, et le code combiné en produit une TROISIÈME. La
    # fusion automatique de git ne l'a pas signalé — seul ce test l'a fait.
    # Vérifié avant de réinscrire : l'app.py mesuré porte bien le pool
    # (`_close_database_pool`) ET les index d'`accessibleBy`/`publicWhen`
    # (`recipient_id` dans `_LOOKUP_INDEXES`), et rien d'autre n'a bougé.
    # POINT 191 : même diff runtime que le golden principal — nouvelle liste
    # post-paiement vide ici, et comptage mutualisé avec l'horodatage.
    "app.py": "6c96a32742129565c9027ea1e6b28e3d64a750d0933bf36f49d403282af04037",
    # 0.9.0-beta.9 : monl.json seul, pour la même raison que ci-dessus.
    # POINT 191 : le diff réel ne change que l'empreinte app.py scellée.
    # 0.9.0-beta.10 : monl.json seul, `compiler_version`, comme ci-dessus.
    "monl.json": "1291a22be672f206e608f0b5b515127faf2171fd34498d2453a0963223fe483a",
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


def test_deux_repertoires_produisent_les_memes_sources(tmp_path, capsys):
    """Le chemin de sortie et le secret local ne doivent pas contaminer les sources."""
    spec = tmp_path / "spec.ml"
    spec.write_text(SPEC, encoding="utf-8")
    premier, second = tmp_path / "premier", tmp_path / "second"
    premier.mkdir()
    second.mkdir()

    compile_project(str(spec), str(premier))
    capsys.readouterr()
    compile_project(str(spec), str(second))
    capsys.readouterr()

    for name in GOLDENS:
        assert (premier / name).read_bytes() == (second / name).read_bytes(), name


def test_les_sources_de_filtrage_du_point_181_sont_dans_le_golden(
        tmp_path, capsys):
    """Le golden backend exerce les deux familles de filtres ajoutées."""
    spec = tmp_path / "spec.ml"
    spec.write_text(SPEC_LOOKUP_SOURCES, encoding="utf-8")

    compile_project(str(spec), str(tmp_path))
    capsys.readouterr()
    empreintes = _empreintes(tmp_path)
    assert {name: empreintes[name] for name in ("app.py", "monl.json")} == {
        name: LOOKUP_GOLDENS[name] for name in ("app.py", "monl.json")
    }


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


# D3–D5 : seuls les artefacts B4 portent la version de session, le mot de
# passe requis pour TOTP, la récupération opérateur et leur documentation.
# Les deux bancs historiques ci-dessus restent inchangés à l'octet près.
B4_GOLDENS = {
    'app.py': '0d08ea56e0dc1b5a29db96a8e768e5bf9e3316767143497f015df55eddc54bf3',
    'schema.sql': 'e433095c18c9ecdbd10fe9b91e47d4ed9d68ad1907260dd4ae72963cd5078117',
    'manage.py': '8890b92555cde836199dca66d97721f38eeb52c23eccae563134ae3d2a0df310',
    'frontend_contract.json': 'd401b1bb32e18760c2d4731ce0f506fe0265efe6744639d5200a304a5825a482',
    'README.md': 'e443518e613cc0c531ad30c7c7ad54290873380700cc70f6e7cee100821f6d6d',
    'monl.json': '1c081522d4bb96d3689528e91d2d3aedb7beadf32614d65f982b987ebc631618',
}


def test_empreintes_b4_securite(tmp_path, capsys):
    from tests.test_authentification_b4 import SPEC_B4

    spec = tmp_path / "spec.ml"
    spec.write_text(SPEC_B4, encoding="utf-8")
    for _ in range(2):
        compile_project(str(spec), str(tmp_path))
        capsys.readouterr()
        assert {name: hashlib.sha256((tmp_path / name).read_bytes()).hexdigest()
                for name in B4_GOLDENS} == B4_GOLDENS
