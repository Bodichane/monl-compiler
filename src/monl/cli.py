# ─────────────────────────────────────────────────────────────────────
# CLI ORCHESTRATEUR — pivot "monl orchestrateur" (brique 3).
#
# monl ne cherche plus à tout générer : il coordonne. Le CLI matérialise
# le cycle de vie complet d'un projet :
#
#   monl                  → dialogue guidé (sans IA) → spec.ml → backend
#                              + contrat frontend (à donner à une IA UI)
#   monl compile spec.ml  → recompilation directe d'une spec existante
#   monl run [DIR]        → vérifie la COHÉRENCE (spec/artefacts/contrat/
#                              frontend) puis lance l'application
#   monl update [DIR]     → recompile après évolution de la spec, régénère
#                              le contrat, et rapporte le DELTA (routes et
#                              champs ajoutés/retirés) à transmettre à l'IA
#                              frontend — la base de données est préservée
#                              (migrations additives au démarrage, point 32).
#
# L'état du projet vit dans monl.json (dossier du projet) : chemin de la
# spec, empreinte SHA-256 de la spec compilée et du contrat. C'est ce qui
# permet à 'run' de détecter une spec modifiée mais non recompilée, et à
# 'update' de mesurer le delta.
# ─────────────────────────────────────────────────────────────────────
import argparse
import contextlib
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import tempfile

from .artifacts import copy_preserved_files, publish_files, staging_directory
from .ast_validator import MonlAST
from .errors import MonlError
from .frontend_ai import RETOUCHE_PROMPT_FILENAME, UPDATE_PROMPT_FILENAME
from .frontend_contract import (
    CONTRACT_FILENAME,
    PROMPT_FILENAME,
    contract_sha256,
    generate_frontend_contract,
)
from .generator import MonlSecureGenerator
from .parser import parse_monl_file
from .serving import rendre_wrapper

STATE_FILENAME = "monl.json"


def _sha256_file(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def _load_state(project_dir):
    path = os.path.join(project_dir, STATE_FILENAME)
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _erreur_de_chemin(project_dir):
    """Message d'erreur quand le DOSSIER lui-même n'existe pas, ou None.

    POINT 105 : « monl.json introuvable — ce dossier n'est pas un projet monl »
    s'affichait aussi quand le dossier n'existait pas du tout, et `monl frontend`
    allait jusqu'à conseiller « lancer 'monl compile' ». Le message envoyait donc
    corriger une compilation absente alors que c'est le CHEMIN qui était faux —
    une hypothèse affichée comme un diagnostic, exactement ce que le point 97
    reproche au conseil de reformulation.

    Deux niveaux, dans l'ordre où les questions se posent : le dossier
    existe-t-il, PUIS porte-t-il un projet. Répondre à la seconde quand la
    première a échoué, c'est répondre à côté."""
    if os.path.isdir(project_dir):
        return None
    lignes = [f" ❌ Dossier introuvable : {project_dir}"]
    # La faute la plus courante, et celle qui a motivé ce point : un chemin
    # RELATIF écrit avec une barre oblique de tête. `/projets/X` n'est pas
    # « projets/X ici » — c'est « X dans le dossier projets À LA RACINE DU
    # SYSTÈME », qui n'existe évidemment pas.
    if project_dir.startswith(os.sep):
        voisin = project_dir.lstrip(os.sep)
        if os.path.isdir(voisin):
            lignes.append(
                f"    Le chemin commence par « {os.sep} » : il est cherché à la "
                f"racine du système, pas depuis ici.")
            lignes.append(f"    Vouliez-vous dire : {voisin}")
    lignes.append("    (le contenu du dossier n'a pas encore été regardé : "
                  "c'est le chemin qui bloque, pas la compilation)")
    return "\n".join(lignes)


# Ce que la spec produit et que personne ne doit retoucher à la main
# (manage.py et sandbox_ai.py compris : ils portent des droits).
SCELLE_ARTEFACTS = ("app.py", "schema.sql", "sandbox_ai.py", "manage.py")
PROJECT_ARTEFACTS = (
    *SCELLE_ARTEFACTS,
    ".jwt_secret",
    CONTRACT_FILENAME,
    PROMPT_FILENAME,
    "CLAUDE.md",
    STATE_FILENAME,
)


def _save_state(project_dir, spec_relpath, spec_source_path=None):
    from . import __version__
    spec_path = spec_source_path or os.path.join(project_dir, spec_relpath)
    state = {
        "spec": spec_relpath,
        # POINT 85 : avec QUOI ce projet a été construit. Purement informatif —
        # la détection d'un artefact périmé (point 81) reste fondée sur une
        # régénération, parce qu'un numéro de version peut ne pas bouger quand
        # la génération, elle, a changé. C'est exactement ce qui s'est produit
        # des points 74 à 84. Le numéro sert à NOMMER l'écart, pas à le trouver.
        "compiler_version": __version__,
        "spec_sha256": _sha256_file(spec_path),
        "contract_sha256": contract_sha256(project_dir),
        # POINT 64 : empreinte du backend généré. « app.py reste scellé » était
        # une promesse que RIEN ne mesurait : la cohérence ne vérifiait que
        # l'existence de ces fichiers, et une retouche à la main passait sans
        # bruit — alors que 'monl run' annonce « spec ↔ backend ↔ contrat ↔
        # frontend » vérifiés. Découvert en écrivant le premier test du
        # parcours de commandes, pas en relisant le code.
        "backend_sha256": {
            nom: _sha256_file(os.path.join(project_dir, nom))
            for nom in SCELLE_ARTEFACTS
            if os.path.exists(os.path.join(project_dir, nom))
        },
    }
    with open(os.path.join(project_dir, STATE_FILENAME), "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=2)
    return state


# ---------------------------------------------------------------- compile --
def compile_project(spec_path, project_dir, base_dir=None, save_state=True):
    """Pipeline complet : spec → backend + contrat frontend + état.
    Réutilise compile_monl (main.py) pour le backend et son résultat validé,
    puis ajoute la couche contrat sans reparsing ni second audit.

    POINT 103 : `base_dir` et `save_state` existent pour `monl diff`, qui
    compile dans un dossier JETABLE. Les assets déclarés vivent, eux, dans le
    vrai projet — les chercher dans le dossier temporaire ferait échouer la
    compilation pour une raison qui n'existe pas. Hors `diff`, le projet de
    référence est par défaut le dossier de la spec, pas le dossier de sortie :
    c'est ce qui permet à `monl compile spec.ml --output build/` de fonctionner
    avec des assets voisins de la spec. Un dry-run, lui, n'a pas à déposer
    d'état."""
    from .main import compile_monl
    reference_dir = base_dir or os.path.dirname(os.path.abspath(spec_path))
    spec_abs = os.path.abspath(spec_path)
    proj_abs = os.path.abspath(project_dir)
    spec_rel = (os.path.relpath(spec_abs, proj_abs)
                if spec_abs.startswith(proj_abs + os.sep) else spec_abs)
    with staging_directory(proj_abs) as temporary:
        # Le secret et un éventuel CLAUDE.md personnel ne sont jamais
        # régénérés depuis zéro dans le staging : ils survivent à la
        # compilation et restent protégés contre un remplacement accidentel.
        copy_preserved_files(proj_abs, temporary, (".jwt_secret", "CLAUDE.md"))
        compilation = compile_monl(
            spec_path, output_dir=temporary, base_dir=reference_dir)
        contract = generate_frontend_contract(
            compilation.ir, compilation.plans, temporary)
        if save_state:
            _save_state(temporary, spec_rel, spec_source_path=spec_abs)
        artefacts = PROJECT_ARTEFACTS if save_state else tuple(
            name for name in PROJECT_ARTEFACTS if name != STATE_FILENAME)
        publish_files(temporary, proj_abs, artefacts)

    print(f" -> Contrat frontend      : {CONTRACT_FILENAME} + {PROMPT_FILENAME}")
    if save_state:
        print(f" -> État du projet        : {STATE_FILENAME}")
    return contract


# ------------------------------------------------------------------- init --
def cmd_init(project_dir=None):
    # Dialogue guidé à règles, entièrement déterministe (aucune IA, aucun
    # appel réseau). La spec produite est revalidée par le vrai parseur avant
    # d'être écrite.
    from .dialogue_engine import run_interactive_dialogue
    spec_text = run_interactive_dialogue()
    app_match = re.match(r"app\s+(\w+)", spec_text)
    app_name = app_match.group(1) if app_match else "MonProjet"
    project_dir = os.path.abspath(project_dir or app_name)
    os.makedirs(project_dir, exist_ok=True)
    spec_path = os.path.join(project_dir, "spec.ml")
    with open(spec_path, "w", encoding="utf-8") as fh:
        fh.write(spec_text)
    print(f"\n✅ Spécification écrite : {spec_path}")
    compile_project(spec_path, project_dir)
    print("\nProchaines étapes :")
    print(f"  1. Donner {PROMPT_FILENAME} (dans {project_dir}) à une IA frontend")
    print(f"     — elle doit écrire son résultat dans {project_dir}/frontend/")
    print("  2. monl run", project_dir)
    return project_dir


# ------------------------------------------------------------ cohérence ----
def _empreintes_regenerees(spec_path):
    """Empreintes des artefacts qu'une recompilation produirait MAINTENANT,
    ou None si la spec ne compile plus (le contrôle ne doit pas devenir une
    panne : la spec modifiée est déjà signalée par son propre contrôle).

    La recompilation a lieu dans un dossier temporaire — le projet n'est jamais
    touché — et sa sortie est capturée : un contrôle de cohérence n'a pas à
    rejouer l'audit de sécurité à l'écran."""
    import contextlib
    import io
    import tempfile

    empreintes = {}
    with tempfile.TemporaryDirectory() as temporaire:
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                # base_dir = le dossier de la SPEC, pas le dossier temporaire :
                # c'est là que vivent les assets à vérifier (brique 13).
                normalized = MonlAST(
                    parse_monl_file(spec_path),
                    base_dir=os.path.dirname(os.path.abspath(spec_path)),
                ).validate_and_audit()
                generator = MonlSecureGenerator(normalized, output_dir=temporaire)
                generator.generate_all()
                generate_frontend_contract(normalized, generator, temporaire)
        except Exception:
            return None
        for nom in ("app.py", "schema.sql", "sandbox_ai.py", CONTRACT_FILENAME):
            chemin = os.path.join(temporaire, nom)
            if os.path.exists(chemin):
                empreintes[nom] = _sha256_file(chemin)
    return empreintes


def check_coherence(project_dir):
    """Vérifie que spec, backend, contrat et frontend forment un ensemble
    cohérent. Retourne (ok, erreurs, avertissements)."""
    errors, warnings = [], []
    project_dir = os.path.abspath(project_dir)

    souci = _erreur_de_chemin(project_dir)
    if souci:
        errors.append(souci.replace(" ❌ ", "").strip())
        return False, errors, warnings

    state = _load_state(project_dir)
    if state is None:
        errors.append(f"{STATE_FILENAME} introuvable — ce dossier n'est pas un projet "
                      "monl compilé (lancer 'monl' ou 'monl compile').")
        return False, errors, warnings

    spec_path = state["spec"] if os.path.isabs(state["spec"]) \
        else os.path.join(project_dir, state["spec"])
    if not os.path.exists(spec_path):
        errors.append(f"Spec introuvable : {spec_path}")
        return False, errors, warnings

    if _sha256_file(spec_path) != state["spec_sha256"]:
        errors.append("La spec a été modifiée depuis la dernière compilation — "
                      "lancer 'monl update' pour resynchroniser backend et contrat.")

    for artefact in ("app.py", "schema.sql", CONTRACT_FILENAME):
        if not os.path.exists(os.path.join(project_dir, artefact)):
            errors.append(f"Artefact manquant : {artefact}")
    if errors:
        return False, errors, warnings

    # Le backend est scellé (point 64) : il se régénère depuis la spec, il ne
    # se retouche pas. Un état antérieur à cette empreinte n'est pas une
    # erreur — il est simplement muet, et le dire vaut mieux que laisser
    # croire à une vérification qui n'a pas eu lieu.
    empreintes = state.get("backend_sha256")
    if not empreintes:
        warnings.append("État antérieur au scellé du backend : recompiler "
                        "('monl update') pour que app.py et schema.sql soient "
                        "réellement vérifiés.")
    else:
        for nom, attendu in sorted(empreintes.items()):
            chemin = os.path.join(project_dir, nom)
            if os.path.exists(chemin) and _sha256_file(chemin) != attendu:
                errors.append(
                    f"{nom} a été modifié à la main — le backend est généré "
                    "depuis la spec. Modifier la spec puis 'monl update' ; "
                    "toute retouche directe sera écrasée.")
        if errors:
            return False, errors, warnings

    if contract_sha256(project_dir) != state["contract_sha256"]:
        errors.append(f"{CONTRACT_FILENAME} a été modifié à la main — le contrat est "
                      "dérivé de la spec, il ne se modifie que via 'monl update'.")
        return False, errors, warnings

    # AJOUT (point 81) : les contrôles ci-dessus comparent aux empreintes
    # ENREGISTRÉES à la compilation. Ils détectent donc une retouche à la main
    # — leur but — et rien d'autre. Un projet dont les artefacts ont été
    # produits par un compilateur ANTÉRIEUR les passait tous, et 'monl run'
    # annonçait « cohérence vérifiée (spec ↔ backend ↔ contrat ↔ frontend) »
    # sur un backend que le compilateur courant n'écrirait plus — y compris
    # après qu'un correctif ait fermé un trou de sécurité.
    #
    # Pourquoi comparer à une RÉGÉNÉRATION plutôt qu'à un numéro de version :
    # `__version__` n'a pas bougé pendant les points 74 à 81, donc un tampon de
    # version n'aurait rien vu. La génération est déterministe (c'est ce sur
    # quoi reposent déjà les empreintes ci-dessus) : recompiler dans un dossier
    # temporaire et comparer dit exactement quels artefacts changeraient.
    #
    # Pourquoi un AVERTISSEMENT et non une erreur : précédent explicite quelques
    # lignes plus haut, pour l'état antérieur au scellé du backend — « il est
    # simplement muet, et le dire vaut mieux que laisser croire à une
    # vérification qui n'a pas eu lieu ». Une erreur bloquerait 'monl run' sur
    # tout projet après n'importe quelle évolution du compilateur, y compris
    # celles qui ne le concernent pas. L'avertissement NOMME les artefacts
    # concernés et la commande qui resynchronise : c'est actionnable en une
    # commande, sans immobiliser une application qui tourne.
    frais = _empreintes_regenerees(spec_path)
    if frais is None:
        warnings.append("Impossible de recompiler la spec pour comparer les artefacts "
                        "au compilateur courant — vérification non effectuée.")
    else:
        perimes = sorted(nom for nom, empreinte in frais.items()
                         if os.path.exists(os.path.join(project_dir, nom))
                         and _sha256_file(os.path.join(project_dir, nom)) != empreinte)
        if perimes:
            from . import __version__
            construit_avec = state.get("compiler_version")
            depuis = (f" (construit avec monl {construit_avec}, courant "
                      f"{__version__})" if construit_avec else "")
            warnings.append(
                f"Artefacts produits par un compilateur antérieur : {', '.join(perimes)}"
                f"{depuis}. La spec n'a pas changé, monl si — lancer 'monl update' pour "
                f"resynchroniser (un correctif de sécurité n'atteint un projet "
                f"qu'après recompilation).")

    # Frontend (optionnel) : vérification best-effort que les chemins d'API
    # référencés existent dans le contrat. On ne bloque pas (un chemin peut
    # être construit dynamiquement) : on AVERTIT, nominalement.
    frontend_dir = os.path.join(project_dir, "frontend")
    if os.path.isdir(frontend_dir):
        if not os.path.exists(os.path.join(frontend_dir, "index.html")):
            errors.append("frontend/ existe mais frontend/index.html est absent "
                          "(point d'entrée exigé par le contrat).")
            return False, errors, warnings
        with open(os.path.join(project_dir, CONTRACT_FILENAME), encoding="utf-8") as fh:
            contract = json.load(fh)
        known_prefixes = {r["path"].split("/")[1] for r in contract["routes"]}
        known_prefixes |= {"register", "login", "logout", "docs", "app", "site", "workflow"}
        referenced = set()
        # POINT 92 : les routes de NAVIGATION d'une application monopage
        # (`href="#/catalogue"`, `aller('/compte')`) ne sont pas des chemins
        # d'API, et l'avertissement les dénonçait toutes — quatre sur quatre sur
        # SneakerLab, dont aucune n'était un défaut. Un avertissement qui crie au
        # loup sur un site correct n'est pas prudent, il apprend à ne plus lire
        # les avertissements. La preuve est DANS le fichier : si `#/x` y figure,
        # `/x` est une route de navigation. Un vrai chemin d'API mal tapé, lui,
        # n'apparaît jamais derrière un dièse — il reste donc signalé.
        routes_client = set()
        for root, _dirs, files in os.walk(frontend_dir):
            for name in files:
                if not name.endswith((".html", ".js")):
                    continue
                with open(os.path.join(root, name), encoding="utf-8", errors="ignore") as fh:
                    contenu = fh.read()
                routes_client |= set(re.findall(r"#/([a-z_]+)", contenu))
                # Le littéral ENTIER est examiné, pas seulement son début
                # (point 57) : `'/edit">Modifier</a>'` est la fin d'une
                # route de navigation `#/article/<id>/edit` coupée par une
                # concaténation — du balisage, jamais une URL d'API. Toute
                # application monopage en produisait, et l'avertissement
                # criait au loup à chaque fois. Un chemin qui contient de
                # l'espace ou un chevron n'est pas un chemin.
                for match in re.finditer(r"""(['"`])(/[^'"`\n]*)\1""", contenu):
                    chemin = match.group(2)
                    if any(c in chemin for c in "<> "):
                        continue
                    segment = re.match(r"/([a-z_]+)(?:[/?#]|$)", chemin)
                    if segment:
                        referenced.add(segment.group(1))
        unknown = sorted(referenced - known_prefixes - routes_client)
        if unknown:
            warnings.append("Le frontend référence des chemins absents du contrat : "
                            + ", ".join(f"/{u}" for u in unknown))
    else:
        warnings.append("Aucun dossier frontend/ — l'app sera servie avec ses seules "
                        "pages générées (landing, /app, /docs).")

    return True, errors, warnings


def _assets_dir_du_projet(project_dir):
    """Dossier d'assets déclaré, lu dans le CONTRAT et non dans la spec.

    Le contrat est déjà dérivé de la spec et vérifié cohérent avec elle : le
    relire ici éviterait un second parseur à faire dériver. Retourne None si le
    projet n'en déclare pas — le wrapper n'ajoute alors aucun montage."""
    chemin = os.path.join(project_dir, CONTRACT_FILENAME)
    if not os.path.exists(chemin):
        return None
    try:
        with open(chemin, encoding="utf-8") as fh:
            return (json.load(fh).get("assets") or {}).get("dir") or None
    except (OSError, ValueError):
        return None




def cmd_run(project_dir, check_only=False, port=8000, skip_smoke=False):
    ok, errors, warnings = check_coherence(project_dir)
    for w in warnings:
        print(f" ⚠️  {w}")
    if not ok:
        for e in errors:
            print(f" ❌ {e}")
        sys.exit(1)
    print(" ✅ Cohérence statique vérifiée (spec ↔ backend ↔ contrat ↔ frontend).")

    # Point 1 du pivot : la cohérence statique ne garantit pas que ça
    # FONCTIONNE. Smoke test comportemental sur serveur éphémère (base
    # neuve, données réelles intouchées) : routes du contrat éprouvées en
    # HTTP réel, frontend exécuté dans jsdom si Node est disponible.
    if not skip_smoke:
        from .smoke_test import run_smoke_test
        print(" -> Smoke test comportemental (serveur éphémère, base neuve)…")
        smoke_ok, smoke_errors, smoke_warnings = run_smoke_test(project_dir)
        for w in smoke_warnings:
            print(f" ⚠️  {w}")
        if not smoke_ok:
            for e in smoke_errors:
                print(f" ❌ {e}")
            print(" ❌ Smoke test échoué — l'application ne sera pas lancée "
                  "(contourner en connaissance de cause : --skip-smoke).")
            sys.exit(1)
        print(" ✅ Smoke test réussi : l'API répond conformément au contrat"
              + (" et le frontend s'exécute sans erreur." if os.path.isdir(
                  os.path.join(os.path.abspath(project_dir), "frontend")) else "."))
    if check_only:
        return

    project_dir = os.path.abspath(project_dir)
    has_frontend = os.path.isdir(os.path.join(project_dir, "frontend"))
    module = "app:app"
    if has_frontend:
        assets_dir = _assets_dir_du_projet(project_dir)
        with open(os.path.join(project_dir, "serve.py"), "w", encoding="utf-8") as fh:
            fh.write(rendre_wrapper(assets_dir))
        module = "serve:app"
        print(f" -> Frontend monté sur http://127.0.0.1:{port}/site")
        if assets_dir and os.path.isdir(os.path.join(project_dir, assets_dir)):
            print(f" -> Assets ({assets_dir}/) montés sur "
                  f"http://127.0.0.1:{port}/site/{assets_dir}/")
    print(f" -> Lancement : uvicorn {module} (port {port})")
    subprocess.run([sys.executable, "-m", "uvicorn", module,
                    "--host", "127.0.0.1", "--port", str(port)], cwd=project_dir)


# ----------------------------------------------------------------- update --
# Les noms des deux briefs d'évolution vivent dans frontend_ai (qui les
# CONSOMME) et sont importés en tête de ce module (qui les ÉCRIT).


def _write_update_brief(project_dir, added_routes, removed_routes,
                        added_fields, removed_fields,
                        added_acces=(), removed_acces=(),
                        scelles=(), liberes=(),
                        added_prea=(), removed_prea=(),
                        added_verrous=(), removed_verrous=(),
                        added_contenus=(), removed_contenus=(),
                        modifies_contenus=(), changed_liens=()):
    """Point 3 du pivot : le delta n'est pas qu'informatif, il devient une
    CONSIGNE prête à donner à l'IA frontend — la boucle se ferme sans que
    l'humain ait à reformuler le changement."""
    def bullet(items, verb):
        return "\n".join(f"- {verb} `{i}`" for i in sorted(items))
    sections = []
    if added_routes:
        sections.append("## Nouvelles routes à exploiter\n"
                        + bullet(added_routes, "brancher"))
    if removed_routes:
        sections.append("## Routes SUPPRIMÉES — retirer tout appel\n"
                        + bullet(removed_routes, "ne plus appeler"))
    if added_fields:
        sections.append("## Nouveaux champs à afficher/saisir\n"
                        + bullet(added_fields, "intégrer"))
    if removed_fields:
        sections.append("## Champs SUPPRIMÉS — retirer des vues et formulaires\n"
                        + bullet(removed_fields, "retirer"))
    # POINT 88 : un rôle qui gagne l'accès à une route existante n'ajoute aucune
    # route, mais réclame souvent tout un écran (un back-office, une vue de
    # supervision). C'est le cas le plus silencieux du delta : rien n'est cassé,
    # et pourtant il manque quelque chose.
    if added_acces:
        sections.append(
            "## Rôles nouvellement autorisés — écrans à prévoir\n"
            "Ces routes existaient déjà ; un rôle de plus peut désormais les "
            "appeler. Vérifier que l'interface le lui propose, et qu'un rôle "
            "de supervision voit bien l'ensemble des enregistrements — pas "
            "seulement les siens.\n"
            + bullet(added_acces, "ouvrir à"))
    if removed_acces:
        sections.append(
            "## Accès RETIRÉS — masquer ce qui répondra 403\n"
            + bullet(removed_acces, "ne plus proposer à"))
    # POINT 99 : la clé étrangère change de nature sans changer de nom. Deux
    # conséquences bien distinctes pour l'interface — une jointure à refaire, ou
    # un champ obligatoire de plus au formulaire de création — d'où les deux
    # consignes séparées plutôt qu'une phrase qui couvrirait les deux à moitié.
    if changed_liens:
        sections.append(
            "## Rattachements dont la nature a changé\n"
            "Pour chacun : si la ligne dit « un identifiant de compte », joindre "
            "par la colonne HOMONYME de la fiche, jamais par son `id`. Si elle "
            "dit « à envoyer par le client », le formulaire de création doit "
            "proposer de CHOISIR l'enregistrement lié (une liste déroulante "
            "alimentée par la route de lecture correspondante) — sans ce champ, "
            "la création répond 422.\n"
            + bullet(changed_liens, "revoir"))
    # POINT 89 : le champ existe toujours et porte le même nom — seul son sens a
    # changé. C'est le second cas silencieux du delta : rien n'est cassé, et
    # pourtant un formulaire est devenu un affichage.
    if scelles:
        sections.append(
            "## Champs devenus en LECTURE SEULE — retirer des formulaires\n"
            "Le serveur les calcule ou les horodate désormais lui-même. Les "
            "envoyer n'échoue pas : ils sont simplement ignorés, ce qui est "
            "pire — l'utilisateur croit avoir saisi une valeur.\n"
            + bullet(scelles, "ne plus envoyer, seulement afficher"))
    if liberes:
        sections.append(
            "## Champs redevenus SAISISSABLES\n"
            + bullet(liberes, "proposer à la saisie"))
    # POINT 90 : la route n'a pas bougé, son PRÉALABLE oui. C'est le parcours
    # utilisateur qu'il faut reprendre, pas un champ à ajouter.
    if added_prea:
        sections.append(
            "## PRÉALABLES ajoutés — le parcours change, pas seulement l'écran\n"
            "Ces routes existaient déjà et répondent désormais 409 tant que "
            "l'appelant ne possède pas l'enregistrement nommé. Vérifier au "
            "chargement et proposer la création AVANT le formulaire : découvert "
            "à la fin, le refus tombe là où l'utilisateur a déjà tout rempli.\n"
            + bullet(added_prea, "prévoir"))
    if removed_prea:
        sections.append(
            "## Préalables LEVÉS — l'étape intermédiaire n'est plus nécessaire\n"
            + bullet(removed_prea, "ne plus imposer"))
    # POINT 91 : la route n'a pas bougé, elle a gagné un REFUS conditionnel.
    # C'est un bouton à masquer selon l'état de l'enregistrement affiché — pas
    # un écran de plus, pas un champ de plus : le cas le plus facile à manquer
    # en relisant la seule liste des routes.
    if added_verrous:
        sections.append(
            "## VERROUS de paiement — actions à masquer sur un enregistrement payé\n"
            "Ces routes existaient déjà et répondent désormais 409 dès que "
            "l'enregistrement concerné est réglé (`payment_status` vaut "
            "`payee`). Conditionner l'affichage du bouton à ce champ, que les "
            "routes de lecture renvoient déjà : découvert au clic, le refus "
            "arrive après que l'utilisateur a modifié son panier. Un montant "
            "encaissé ne se modifie plus, il se rembourse chez le prestataire.\n"
            + bullet(added_verrous, "conditionner"))
    if removed_verrous:
        sections.append(
            "## Verrous LEVÉS — l'action redevient possible après règlement\n"
            + bullet(removed_verrous, "ne plus conditionner"))
    # POINT 94 : du CONTENU, pas des données. Aucune route ne le sert — il
    # n'existe que dans le contrat, donc une IA qui ne le lit pas ici ne
    # l'apprendra nulle part ailleurs.
    if added_contenus:
        sections.append(
            "## Contenu éditorial AJOUTÉ — à publier sur l'accueil\n"
            "Le texte complet est dans `FRONTEND_PROMPT.md` (rubriques "
            "« Contenu éditorial » et « Questions fréquentes »). Une FAQ se rend "
            "en entrées distinctes — jamais en un seul paragraphe.\n"
            + bullet(added_contenus, "publier"))
    if removed_contenus:
        sections.append(
            "## Contenu RETIRÉ — à faire disparaître de la page\n"
            + bullet(removed_contenus, "retirer"))
    if modifies_contenus:
        sections.append(
            "## Contenu RÉÉCRIT — même titre, texte différent\n"
            "Le titre n'a pas bougé, le texte si : reprendre la version à jour "
            "dans `FRONTEND_PROMPT.md`. C'est le changement le plus facile à "
            "manquer, puisque rien n'a l'air d'avoir bougé.\n"
            + bullet(modifies_contenus, "remplacer le texte de"))
    body = f"""# Mise à jour du frontend (delta généré par 'monl update')

Le backend a évolué. Modifiez le frontend existant dans `frontend/` pour
refléter UNIQUEMENT les changements ci-dessous — ne réécrivez pas ce qui
fonctionne déjà. Le contrat complet à jour est dans `frontend_contract.json`
(les règles de `FRONTEND_PROMPT.md` restent en vigueur).

{chr(10).join(sections)}

Après modification, `monl run` revalidera l'ensemble (cohérence statique
+ smoke test comportemental) avant tout lancement.

Si vous lisez ceci dans une conversation (sans clé API) : rendez le
frontend mis à jour en ZIP téléchargeable ou en `index.html` autonome —
l'utilisateur l'installera avec `monl import <fichier> <projet>`.
"""
    path = os.path.join(project_dir, UPDATE_PROMPT_FILENAME)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(body)
    return path


def _contract_signature(contract):
    routes = {f"{r['method']} {r['path']}" for r in contract["routes"]}
    fields = {f"{e}.{f['name']}" for e, spec in contract["entities"].items()
              for f in spec["fields"]}
    # POINT 88 : QUI a le droit d'appeler une route fait partie de l'interface.
    # Le delta ne comparait que méthode+chemin : ouvrir le carnet de commandes
    # à l'administrateur ne créait aucune route nouvelle — seulement un acteur
    # de plus sur des routes existantes — et 'monl update' répondait « aucun
    # changement d'interface, le frontend existant reste valide ». C'était vrai
    # et trompeur : rien n'était cassé, mais tout un écran manquait, et le
    # rapport de delta existe précisément pour dire ce qu'il reste à écrire.
    acces = {f"{r['method']} {r['path']} → {acteur}"
             for r in contract["routes"]
             for acteur in r.get("allowed_actors") or []}
    # POINT 89 : un champ n'est pas seulement présent ou absent — il est
    # SAISISSABLE ou non, et ça change autant l'interface. Poser
    # 'rule Order.total derivedFrom …' sur un champ qui existait déjà ne
    # renomme rien : le delta répondait « aucun changement » pendant que le
    # formulaire de prix devenait un champ que le serveur ignore. Le même angle
    # mort que le point 88, sur l'autre moitié du contrat.
    lecture_seule = {f"{e}.{f['name']}" for e, spec in contract["entities"].items()
                     for f in spec["fields"] if f.get("server_generated")}
    # POINT 90 : troisième forme du même angle mort. Une route peut gagner un
    # PRÉALABLE sans changer de chemin, d'acteurs ni de champs — et le frontend
    # doit pourtant être réécrit : ici, créer la fiche avant le tunnel d'achat,
    # sous peine de 409 au dernier écran. Comparer les routes ne suffisait pas,
    # comparer les acteurs (point 88) ni les champs en lecture seule (point 89)
    # non plus. C'est la troisième fois : le delta doit comparer TOUT ce que le
    # contrat promet, pas seulement ce qui a un nom nouveau.
    prealables = {f"{r['method']} {r['path']} → exige un {r['requires_own']}"
                  for r in contract["routes"] if r.get("requires_own")}
    # POINT 91 : quatrième fois. Poser 'payable' fige les écritures sur
    # l'enregistrement encaissé ET sur ses lignes : les routes ne changent ni de
    # chemin, ni d'acteurs, ni de champs, mais un bouton « Modifier » dessiné
    # sans le savoir mène à un 409. Un verrou porté par une route qui vient
    # d'apparaître est exclu du rapport — déjà dit par « route ajoutée », même
    # arbitrage anti-doublon qu'aux points 88 à 90.
    verrous = {f"{r['method']} {r['path']} → figé une fois {r['payment_locked']} réglé"
               for r in contract["routes"] if r.get("payment_locked")}
    # POINT 94 : cinquième fois, et la première qui ne concerne pas les données.
    # Le delta ne regardait QUE l'API — ajouter une rubrique éditoriale ou une
    # question de FAQ ne touche aucune route, aucun champ, et 'monl update'
    # répondait « aucun changement d'interface » alors qu'il restait un bloc
    # entier à écrire sur l'accueil. L'angle mort existait pour `section`
    # depuis le point 55 ; la FAQ y serait tombée le jour de sa naissance.
    #
    # Un DICTIONNAIRE et non un ensemble, contrairement aux six autres : le
    # texte compte autant que le titre. Comparer les seuls titres, c'est
    # l'erreur exacte du point 89 — réécrire « Livraison et retours » de fond en
    # comble ne renomme rien, et il faut pourtant re-rendre la page.
    contenus = {f"section « {s['title']} »": hashlib.sha256(
                    "\n".join(s["body"]).encode("utf-8")).hexdigest()
                for s in contract.get("sections") or []}
    contenus.update({f"question « {q['question']} »": hashlib.sha256(
                         "\n".join(q["answer"]).encode("utf-8")).hexdigest()
                     for q in contract.get("faq") or []})
    # POINT 95 : la question du point 94, posée AVANT d'écrire la brique cette
    # fois. Déclarer 'identifier: email' ne crée aucune route et ne renomme
    # aucun champ — le corps de '/register' garde les mêmes clés — mais l'écran
    # d'inscription change : étiquette, type de saisie, message d'erreur. Sans
    # ça, le delta aurait dit « aucun changement d'interface » pendant qu'un
    # formulaire se mettait à répondre 422 sans expliquer pourquoi.
    formes = (contract.get("api", {}).get("auth", {}).get("register", {})
              .get("identifier_forms") or [])
    if formes:
        contenus[f"identifiant de compte ({', '.join(formes)})"] = "forme"
    # POINT 96 : sixième fois. Poser `oneOf` sur un champ existant ne renomme
    # rien — mais un champ texte devient un MENU, et la liste des valeurs peut
    # changer sans que le champ bouge (« expédiée » ajoutée au carnet). Le
    # digest porte donc les valeurs, pas seulement leur présence : comparer les
    # seuls noms serait l'erreur du point 89, pour la troisième fois.
    # POINT 98 : septième fois. Poser `releases` ne crée aucune route et ne
    # change aucun champ — mais un bouton « réactiver » devient un 409, et un
    # écran doit expliquer que l'annulation rend le stock. Le delta le dit.
    for r in contract["routes"]:
        lib = r.get("releases_on")
        if lib:
            contenus[f"libération de {r['method']} {r['path']}"] = hashlib.sha256(
                f"{lib['field']}\n{lib['value']}\n{lib['releases']}".encode()
            ).hexdigest()
    for entite, spec in sorted((contract.get("entities") or {}).items()):
        for champ in spec.get("fields") or []:
            if champ.get("allowed_values"):
                contenus[f"choix de {entite}.{champ['name']}"] = hashlib.sha256(
                    "\n".join(champ["allowed_values"]).encode("utf-8")).hexdigest()
    # POINT 116 : neuvième et dixième fois. `publicWhen` et `oncePer` vivent
    # dans `business_rules`, que la signature ne lisait pas : poser
    # 'rule Article.Read publicWhen status "published"' ne crée aucune route,
    # ne renomme aucun champ et ne change aucun acteur — `monl update`
    # répondait « aucun changement d'interface » pendant qu'il fallait
    # dessiner un état « brouillon », un filtre de liste et un écran de
    # modération. `oncePer` est le même angle mort côté écriture : le bouton
    # « voter » gagne un 409 que personne n'a annoncé. La VALEUR entre dans le
    # digest, pas seulement la présence de la règle : passer de "published" à
    # "validated" ne renomme rien non plus (leçon des points 89 et 96).
    regles_metier = contract.get("business_rules") or {}
    for reference, condition in sorted((regles_metier.get("public_when") or {}).items()):
        contenus[f"publication conditionnelle de {reference}"] = hashlib.sha256(
            f"{condition.get('field')}\n{condition.get('value')}".encode()).hexdigest()
    for regle in regles_metier.get("once_per") or []:
        contenus[f"unicité de {regle['trigger_entity']}"] = hashlib.sha256(
            "\n".join(regle["parents"]).encode("utf-8")).hexdigest()
    # POINT 99 : huitième ensemble, et la question posée AVANT d'écrire le code
    # pour la deuxième fois seulement. Une clé étrangère ne vit pas dans
    # `fields` — le delta ne pouvait donc rien dire quand elle change de NATURE.
    # Or elle en change de deux façons, et les deux réécrivent un écran :
    #
    #   - ce qu'elle CONTIENT : un id de compte ou l'id d'une ligne métier. Le
    #     contrat le dit depuis le point 88, précisément parce qu'une jointure
    #     faite sur la mauvaise des deux marche À MOITIÉ ;
    #   - qui la RENSEIGNE : le serveur depuis le jeton, ou le client. Passer du
    #     premier au second ajoute un champ obligatoire au formulaire de
    #     création — un menu de produits sur « nouvelle variante » — sans
    #     renommer quoi que ce soit. Sans cette ligne, `monl update` répondait
    #     « aucun changement d'interface » et le POST récoltait un 422.
    liens = set()
    for entite, spec in sorted((contract.get("entities") or {}).items()):
        designees = set(spec.get("client_foreign_keys") or [])
        for lien in spec.get("foreign_keys") or []:
            porte = ("un identifiant de compte" if lien.get("references_account")
                     else f"l'id d'un {lien['references']}")
            par = "à envoyer par le client" if lien["column"] in designees \
                else "renseigné par le serveur"
            liens.add(f"{entite}.{lien['column']} → {porte}, {par}")
    return routes, fields, acces, lecture_seule, prealables, verrous, contenus, liens


def _situer_projet(project_dir, geste):
    """(dossier absolu, chemin de la spec) — ou sortie en erreur.

    Partagé par 'update' et 'diff' : les deux partent du même état, et un seul
    des deux qui saurait le lire serait une divergence de plus."""
    project_dir = os.path.abspath(project_dir)
    souci = _erreur_de_chemin(project_dir)
    if souci:
        print(souci)
        sys.exit(1)
    state = _load_state(project_dir)
    if state is None:
        print(f" ❌ {STATE_FILENAME} introuvable — rien à {geste} ici.")
        sys.exit(1)
    spec_path = state["spec"] if os.path.isabs(state["spec"]) \
        else os.path.join(project_dir, state["spec"])
    return project_dir, spec_path


def _signature_precedente(project_dir):
    """La signature du contrat DÉJÀ posé, ou des ensembles vides s'il n'y en a
    pas encore — auquel cas tout est « ajouté », ce qui est exact."""
    contract_path = os.path.join(project_dir, CONTRACT_FILENAME)
    if not os.path.exists(contract_path):
        return (set(), set(), set(), set(), set(), set(), {}, set())
    with open(contract_path, encoding="utf-8") as fh:
        return _contract_signature(json.load(fh))


def _rapporter_delta(ancienne, nouvelle, project_dir, ecrire_brief=True):
    """Compare deux signatures de contrat, imprime le delta, et rend True s'il
    y a de quoi réécrire quelque chose.

    POINT 103 : extrait de `cmd_update` pour que `monl diff` en soit le MÊME
    rapport, et pas une deuxième implémentation. Deux calculs de delta
    finiraient par diverger — et c'est précisément le calcul dont cinq points
    (88 à 91, 94, 99) ont montré qu'il est difficile à tenir juste."""
    (old_routes, old_fields, old_acces, old_ro, old_prea, old_verrous,
     old_contenus, old_liens) = ancienne
    (new_routes, new_fields, new_acces, new_ro, new_prea, new_verrous,
     new_contenus, new_liens) = nouvelle

    added_routes, removed_routes = new_routes - old_routes, old_routes - new_routes
    added_fields, removed_fields = new_fields - old_fields, old_fields - new_fields
    # Les accès d'une route qui vient d'apparaître ou de disparaître sont déjà
    # dits par les deux listes ci-dessus : ne garder que les routes qui EXISTAIENT
    # des deux côtés, sinon chaque ajout serait rapporté deux fois.
    stables = new_routes & old_routes
    added_acces = {a for a in new_acces - old_acces if a.split(" → ")[0] in stables}
    removed_acces = {a for a in old_acces - new_acces if a.split(" → ")[0] in stables}
    # POINT 89 : même filtre, même raison — un champ qui vient d'apparaître est
    # déjà décrit par `added_fields`, où sa lecture seule est annotée.
    champs_stables = new_fields & old_fields
    scelles = (new_ro - old_ro) & champs_stables
    liberes = (old_ro - new_ro) & champs_stables
    # Même filtre que pour les accès : une route qui vient d'apparaître porte
    # son préalable dans « route ajoutée », l'y compter deux fois noierait le
    # signal.
    added_prea = {p for p in new_prea - old_prea if p.split(" → ")[0] in stables}
    removed_prea = {p for p in old_prea - new_prea if p.split(" → ")[0] in stables}
    # POINT 91 : même filtre, quatrième fois. Poser `payable` fige des routes
    # qui existaient déjà — le frontend doit retirer un bouton, sans qu'aucun
    # chemin, acteur ou champ n'ait changé.
    added_verrous = {v for v in new_verrous - old_verrous
                     if v.split(" → ")[0] in stables}
    removed_verrous = {v for v in old_verrous - new_verrous
                       if v.split(" → ")[0] in stables}
    # POINT 94 : trois cas, pas deux — un contenu peut être RÉÉCRIT sans changer
    # de titre, et c'est le cas le plus silencieux des trois.
    added_contenus = set(new_contenus) - set(old_contenus)
    removed_contenus = set(old_contenus) - set(new_contenus)
    modifies_contenus = {c for c in set(new_contenus) & set(old_contenus)
                         if new_contenus[c] != old_contenus[c]}
    # POINT 99 : même arbitrage anti-doublon qu'aux points 88 à 91, appliqué aux
    # entités plutôt qu'aux routes. Les rattachements d'une entité qui vient
    # d'apparaître sont déjà dits par ses routes et ses champs ; seuls ceux
    # d'une entité qui existait des deux côtés méritent une ligne.
    entites_stables = {f.split(".", 1)[0] for f in new_fields & old_fields}
    changed_liens = {li for li in (new_liens - old_liens)
                     if li.split(".", 1)[0] in entites_stables}
    changes = any((added_routes, removed_routes, added_fields, removed_fields,
                   added_acces, removed_acces, scelles, liberes,
                   added_prea, removed_prea, added_verrous, removed_verrous,
                   added_contenus, removed_contenus, modifies_contenus,
                   changed_liens))
    # Le nom seul ne dit pas qu'un champ neuf est en lecture seule ; la rubrique
    # du brief s'intitule « à afficher/saisir », ce qui serait un contresens sur
    # un horodatage ou un total calculé.
    added_fields = {f"{c} (lecture seule — écrit par le serveur)" if c in new_ro else c
                    for c in added_fields}

    print("\n─── Delta du contrat frontend ───")
    for item in sorted(added_routes):
        print(f"  + route ajoutée : {item}")
    for item in sorted(removed_routes):
        print(f"  - route retirée : {item}")
    for item in sorted(added_fields):
        print(f"  + champ ajouté : {item}")
    for item in sorted(removed_fields):
        print(f"  - champ retiré : {item}")
    for item in sorted(added_acces):
        print(f"  + accès ouvert : {item}")
    for item in sorted(removed_acces):
        print(f"  - accès retiré : {item}")
    for item in sorted(scelles):
        print(f"  ! champ devenu en lecture seule : {item}")
    for item in sorted(liberes):
        print(f"  ! champ redevenu saisissable : {item}")
    for item in sorted(added_prea):
        print(f"  ! préalable ajouté : {item}")
    for item in sorted(removed_prea):
        print(f"  ! préalable levé : {item}")
    for item in sorted(added_verrous):
        print(f"  ! verrou de paiement : {item}")
    for item in sorted(removed_verrous):
        print(f"  ! verrou de paiement levé : {item}")
    for item in sorted(changed_liens):
        print(f"  ! rattachement : {item}")
    for item in sorted(added_contenus):
        print(f"  + contenu ajouté : {item}")
    for item in sorted(removed_contenus):
        print(f"  - contenu retiré : {item}")
    for item in sorted(modifies_contenus):
        print(f"  ! contenu réécrit : {item}")
    if not changes:
        print("  (aucun changement d'interface — le frontend existant reste valide)")
    elif ecrire_brief:
        brief_path = _write_update_brief(project_dir, added_routes, removed_routes,
                                         added_fields, removed_fields,
                                         added_acces, removed_acces,
                                         scelles, liberes,
                                         added_prea, removed_prea,
                                         added_verrous, removed_verrous,
                                         added_contenus, removed_contenus,
                                         modifies_contenus, changed_liens)
        print(f"  → Consigne prête pour l'IA frontend : {os.path.basename(brief_path)}")
    print("──────────────────────────────────────────────────────────────────")
    return changes


def cmd_update(project_dir):
    project_dir, spec_path = _situer_projet(project_dir, "mettre à jour")
    ancienne = _signature_precedente(project_dir)
    nouveau = compile_project(spec_path, project_dir)
    _rapporter_delta(ancienne, _contract_signature(nouveau), project_dir)
    print("La base de données existante est préservée : les nouvelles colonnes "
          "sont ajoutées par migration additive au démarrage (docs/MIGRATIONS.md).")


# ------------------------------------------------------------------- diff --
# POINT 103 : `monl update` écrit PUIS rapporte. Tant que le rapport dit ce
# qu'on attendait, l'ordre est sans conséquence ; le jour où il annonce un
# écran entier à réécrire, on aimerait l'avoir su avant d'avoir recompilé et
# remplacé le contrat de référence.
#
# `monl diff` répond à la même question sans rien toucher : il compile dans un
# dossier TEMPORAIRE, compare, imprime, et s'en va. Aucun fichier du projet
# n'est écrit — ni app.py, ni le contrat, ni monl.json, ni la consigne
# d'évolution.
def cmd_diff(project_dir):
    project_dir, spec_path = _situer_projet(project_dir, "comparer")
    ancienne = _signature_precedente(project_dir)

    # Le dossier de sortie est jetable, mais `base_dir` doit rester le VRAI
    # projet : c'est lui qui porte les assets déclarés, et les vérifier dans un
    # dossier vide ferait échouer la compilation pour une raison qui n'existe
    # pas (brique 13, point 83).
    with tempfile.TemporaryDirectory(prefix="monl-diff-") as atelier:
        tampon = io.StringIO()
        try:
            with contextlib.redirect_stdout(tampon):
                nouveau = compile_project(spec_path, atelier,
                                          base_dir=project_dir, save_state=False)
        except MonlError as err:
            # La compilation a échoué : c'est SON message qui est utile, pas le
            # nôtre. Les interruptions système remontent naturellement.
            print(tampon.getvalue(), end="")
            print(f" ❌ {err}")
            raise SystemExit(1) from err

    print("\n[DRY-RUN] Aucun fichier modifié — comparaison seule.")
    changes = _rapporter_delta(ancienne, _contract_signature(nouveau),
                               project_dir, ecrire_brief=False)
    if changes:
        print("Pour appliquer ce changement et écrire la consigne d'évolution : "
              "monl update")
    return changes


# --------------------------------------------------------------- retouche --
# POINT 93 : entre « le site est juste au regard du contrat » et « le site est
# raté », monl n'avait aucun geste. `monl frontend` RECONSTRUIT — on jette un
# site bon à 95 % pour un tirage non déterministe ; `monl update` ne parle que
# du delta de spec, et se tait quand la spec n'a pas bougé. Restait l'édition à
# la main, hors de la boucle de vérification.
#
# La retouche ne fait donc RIEN de neuf : elle réutilise la voie d'évolution du
# point 4 en changeant la seule chose qui manquait — l'origine du brief, une
# phrase humaine au lieu d'un diff. Tout le reste est commun, et doit le
# rester : empreinte des artefacts protégés, empreinte du frontend qui DOIT
# bouger (point 73), cohérence + smoke test, une correction au plus.
#
# CE QUE MONL NE PROMET PAS, et il faut le dire ici : que le résultat soit plus
# BEAU. Le smoke test prouve que la page tourne encore et respecte le contrat,
# jamais que le cadrage s'est amélioré. Même honnêteté qu'au point 83 — monl
# vérifie la complétude, pas le goût. D'où la sauvegarde systématique : la
# seule garantie qu'on peut offrir sur une question de goût, c'est de pouvoir
# revenir en arrière.
def _write_retouche_brief(project_dir, demande):
    body = f"""# Retouche demandée (consigne écrite par 'monl retouche')

Le site fonctionne et respecte le contrat. Un défaut a été CONSTATÉ dessus,
par un humain qui l'a regardé :

> {demande.strip()}

## Ce qu'il faut faire

Corriger ce défaut-là dans le frontend existant (`frontend/`), et lui seul.
Ne pas refaire la mise en page générale, ne pas réécrire ce qui fonctionne :
une retouche se juge à ce qu'elle laisse intact autant qu'à ce qu'elle change.

Si la demande est ambiguë, choisir l'interprétation la plus ÉTROITE — celle
qui touche le moins de choses. Une retouche trop large ne se distingue plus
d'une reconstruction, et c'est précisément ce que cette commande évite.

Si le défaut ne peut PAS se corriger dans `frontend/` — parce qu'il vient de
ce que la spec dit, ou ne dit pas — ne pas le contourner par une astuce
d'affichage : le signaler dans la réponse et laisser le frontend en l'état.
Un texte qu'on découpe à l'aveugle parce que le contrat ne le structure pas
est une structure devinée, qui se reperdra à la prochaine construction.

## Règles inchangées

Le contrat complet reste `frontend_contract.json`, et les règles de
`FRONTEND_PROMPT.md` restent toutes en vigueur — mêmes routes, même origine
d'API, même autonomie (aucun CDN). Ne modifier aucun autre fichier du projet.

Rappel sur l'iconographie, parce que « aucun CDN » se lit facilement comme
« pas d'icônes possibles » : aucune librairie d'icônes n'est atteignable, mais
le SVG écrit EN LIGNE dans le HTML et les fichiers `.svg` déposés dans
`frontend/` fonctionnent et sont servis. C'est un MOYEN disponible, pas une
consigne : rien n'oblige à en mettre.

Après modification, `monl run` revalidera l'ensemble (cohérence statique
+ smoke test comportemental) avant tout lancement.
"""
    path = os.path.join(project_dir, RETOUCHE_PROMPT_FILENAME)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(body)
    return path


def sauvegarder_frontend(project_dir, say=print):
    """Copie frontend/ dans frontend.precedent/ avant une retouche.

    `monl import` sauvegarde depuis toujours (« rien n'est perdu ») ; la
    retouche en a plus besoin encore, puisqu'elle porte sur un site qui MARCHE
    et qu'aucune vérification automatique ne peut trancher une question de
    goût. C'est une COPIE et non un déplacement : l'IA doit trouver l'existant
    en place pour le faire évoluer."""
    import shutil
    source = os.path.join(project_dir, "frontend")
    if not os.path.isdir(source):
        return None
    backup = source + ".precedent"
    shutil.rmtree(backup, ignore_errors=True)
    shutil.copytree(source, backup)
    say(" -> Frontend actuel copié dans frontend.precedent/ (retour en arrière possible).")
    return backup


def _lancer_ia(args, update_mode=False, retouche_mode=False):
    """La voie vers l'IA, partagée par 'frontend' et 'retouche' (point 93).

    Elle était écrite en ligne dans le dispatch ; la recopier pour la retouche
    aurait fait DEUX chemins vers le modèle, donc deux endroits où les
    garde-fous peuvent diverger. CLAUDE.md l'interdit nommément : « ne jamais
    contourner le garde-fou d'empreinte en ajoutant une voie »."""
    from .frontend_ai import (
        CLI_AGENTS,
        DEFAULT_MAX_TURNS,
        DEFAULT_MODEL,
        PROVIDERS,
        FrontendAIError,
        generate_and_verify,
        generate_with_cli_agent,
    )
    try:
        if args.agent_command or args.provider in CLI_AGENTS:
            ok, _errors = generate_with_cli_agent(
                args.dir, update_mode=update_mode, retouche_mode=retouche_mode,
                max_turns=args.max_turns or DEFAULT_MAX_TURNS,
                agent=args.provider, agent_command=args.agent_command)
        else:
            # Le modèle par défaut n'existe QUE pour la voie Anthropic ;
            # ailleurs, openai_provider exige --model et le dit.
            defaut = DEFAULT_MODEL if args.provider == "claude" else None
            provider = PROVIDERS[args.provider](model=args.model or defaut)
            ok, _errors = generate_and_verify(args.dir, provider,
                                              update_mode=update_mode,
                                              retouche_mode=retouche_mode)
    except FrontendAIError as e:
        print(f" ❌ {e}")
        sys.exit(1)
    if not ok:
        sys.exit(1)


def _arguments_inverses(demande, dossier):
    """`monl retouche <dossier> "<ce qui cloche>"` — l'erreur attendue.

    POINT 105 : `retouche` est le SEUL geste dont le premier argument n'est pas
    le dossier ; `run`, `update`, `diff`, `compile` et `frontend` le prennent
    tous en tête. Écrire le dossier en premier est donc le réflexe, et monl
    répondait « ce dossier n'est pas un projet monl » en parlant de la PHRASE.

    Le diagnostic NOMME l'inversion, il ne la corrige pas : remettre les
    arguments en place à la place de l'auteur, ce serait deviner — et se
    tromper le jour où une demande ressemble à un chemin. Même arbitrage que
    partout ailleurs dans ce dépôt."""
    demande, dossier = demande or "", dossier or ""
    ressemble_a_un_chemin = " " not in demande and (
        os.sep in demande or os.path.isdir(demande))
    return ressemble_a_un_chemin and " " in dossier


def cmd_retouche(project_dir, demande, say=print):
    """Écrit la consigne et prépare le terrain. L'appel à l'IA est fait par
    l'appelant (main), qui porte déjà le choix du fournisseur — la retouche
    n'ouvre AUCUNE voie nouvelle vers le modèle."""
    if _arguments_inverses(demande, project_dir):
        say(" ❌ Les deux arguments semblent inversés.")
        say(f"    « {demande} » ressemble à un dossier, et « {project_dir[:50]}"
            f"{'…' if len(project_dir) > 50 else ''} » à ce qui cloche.")
        say("    'retouche' attend la DEMANDE d'abord (c'est le seul geste dans "
            "ce sens) :")
        # La commande proposée doit MARCHER telle quelle : recopier un chemin
        # dont on sait déjà qu'il est faux ferait buter l'auteur une deuxième
        # fois, sur un autre message.
        cible = demande
        if not os.path.isdir(cible) and cible.startswith(os.sep) \
                and os.path.isdir(cible.lstrip(os.sep)):
            cible = cible.lstrip(os.sep)
        say(f'      monl retouche "{project_dir}" {cible}')
        sys.exit(1)
    project_dir = os.path.abspath(project_dir)
    souci = _erreur_de_chemin(project_dir)
    if souci:
        say(souci)
        sys.exit(1)
    if _load_state(project_dir) is None:
        say(f" ❌ {STATE_FILENAME} introuvable — ce dossier n'est pas un projet monl.")
        sys.exit(1)
    if not os.path.exists(os.path.join(project_dir, "frontend", "index.html")):
        say(" ❌ Aucun frontend à retoucher (frontend/index.html absent) — "
            "construire d'abord avec 'monl frontend' ou 'monl import'.")
        sys.exit(1)
    if not demande or not demande.strip():
        say(" ❌ La demande est vide — décrire ce qui cloche, en nommant l'écran "
            "et l'élément.")
        sys.exit(1)
    sauvegarder_frontend(project_dir, say=say)
    chemin = _write_retouche_brief(project_dir, demande)
    say(f" -> Consigne écrite : {os.path.basename(chemin)}")
    return chemin


# ----------------------------------------------------------------- assets --
def _spec_du_projet(project_dir):
    """Chemin de la spec d'un projet compilé, d'après monl.json.

    Passer le chemin à assets_tool plutôt que de lui faire relire monl.json :
    l'état du projet est une affaire du CLI, et un second lecteur de monl.json
    serait un second endroit à corriger."""
    souci = _erreur_de_chemin(os.path.abspath(project_dir))
    if souci:
        print(souci)
        sys.exit(1)
    state = _load_state(os.path.abspath(project_dir))
    if state is None:
        print(f" ❌ {STATE_FILENAME} introuvable — ce dossier n'est pas un projet "
              "monl compilé (lancer 'monl' ou 'monl compile').")
        sys.exit(1)
    spec_path = state["spec"] if os.path.isabs(state["spec"]) \
        else os.path.join(os.path.abspath(project_dir), state["spec"])
    if not os.path.exists(spec_path):
        print(f" ❌ Spec introuvable : {spec_path}")
        sys.exit(1)
    return spec_path


def cmd_assets_add(project_dir, source, pour=None, cible=None, entity=None,
                   field=None, nom=None, force=False):
    from .assets_tool import AssetsToolError, ajouter_asset
    spec_path = _spec_du_projet(project_dir)
    try:
        rapport = ajouter_asset(spec_path, project_dir, source, pour=pour,
                                cible=cible, entity=entity, field=field,
                                nom=nom, force=force)
    except AssetsToolError as err:
        print(f" ❌ {err}")
        sys.exit(1)

    verbe = "déjà en place" if rapport["deja_en_place"] else \
            ("remplacé" if rapport["ecrase"] else "copié")
    print(f" -> Fichier {verbe} : {rapport['fichier']}")
    print(f" -> Déclaré dans   : {rapport['ou']} "
          f"(ligne {rapport['ligne']} de {os.path.basename(spec_path)})")
    if rapport["remplace"]:
        print(f" -> Remplace la valeur précédente : {rapport['remplace']}")
    print(" ✅ Spec revalidée par le compilateur : le chemin écrit existe.")
    if rapport["orphelin"]:
        print(f" ⚠️  '{rapport['orphelin']}' n'est plus déclaré par la spec. Le fichier "
              "est laissé en place : monl ne supprime pas un fichier fourni par vous.")
    for message in rapport["avertissements"]:
        print(f" ⚠️  {message}")


def cmd_assets_list(project_dir):
    from .assets_tool import AssetsToolError, lister_assets
    spec_path = _spec_du_projet(project_dir)
    try:
        rapport = lister_assets(spec_path, project_dir)
    except AssetsToolError as err:
        print(f" ❌ {err}")
        sys.exit(1)

    print(f"─── Assets déclarés — dossier '{rapport['dir']}/' ───")
    if not rapport["declares"]:
        print("  (la spec ne déclare aucun asset : aucun champ 'Image', ni logo, ni favicon)")
    for ligne in rapport["declares"]:
        marque = "✅" if ligne["present"] else "❌"
        octets = ligne["taille"]
        taille = "" if octets is None else (
            f" ({octets // 1024} ko)" if octets >= 1024 else f" ({octets} o)")
        ailleurs = (f" → {ligne['resolu']}"
                    if ligne["resolu"] and ligne["resolu"] != ligne["chemin"] else "")
        print(f"  {marque} {ligne['chemin']}{ailleurs}{taille}"
              f"   ← {', '.join(ligne['origines'])}")
    if rapport["orphelins"]:
        print(f"─── Présents mais non déclarés ({len(rapport['orphelins'])}) ───")
        for chemin in rapport["orphelins"]:
            print(f"  ·  {chemin}")
        print("  (légitime pour un fichier de crédits ou une image posée à la main "
              "dans une page : ce rapport constate, il ne reproche rien)")


def cmd_content_export(project_dir):
    from .content_tool import ContentToolError, exporter_contenu
    spec_path = _spec_du_projet(project_dir)
    try:
        rapport = exporter_contenu(spec_path, project_dir)
    except ContentToolError as err:
        print(f" ❌ {err}")
        sys.exit(1)
    for entite, info in rapport["entites"].items():
        print(f" -> {entite}.csv : {info['fiches']} fiche(s), "
              f"{len(info['colonnes'])} colonne(s)")
    for entite, raison in rapport["ignorees"].items():
        print(f" ⚠️  {entite} non exportée : {raison}.")
    print(" ✅ Contenu exporté dans content/ — lire content/LISEZMOI.txt.")


def cmd_content_import(project_dir):
    from .content_tool import ContentToolError, importer_contenu
    spec_path = _spec_du_projet(project_dir)
    try:
        rapport = importer_contenu(spec_path, project_dir)
    except ContentToolError as err:
        print(f" ❌ {err}")
        sys.exit(1)
    for entite, info in rapport["entites"].items():
        print(f" -> {entite} : {info['fiches']} fiche(s) lue(s)")
    message = ("Spec revalidée par le compilateur et contenu remplacé."
               if rapport["spec_changee"]
               else "Contenu inchangé : la spec n'a pas été réécrite.")
    print(f" ✅ {message}")
    avertissements = next(iter(rapport["entites"].values()), {}).get(
        "avertissements", [])
    for message in avertissements:
        print(f" ⚠️  {message}")


# ------------------------------------------------------------------- main --
def _dispatch(argv=None):
    parser = argparse.ArgumentParser(
        prog="monl",
        description="monl — plateforme d'orchestration : dialogue guidé → "
                    "DSL → backend + contrat frontend → IA UI → run/update.")
    sub = parser.add_subparsers(dest="command")

    p_init = sub.add_parser("init", help="Dialogue guidé (défaut sans sous-commande).")
    p_init.add_argument("--dir", default=None, help="Dossier du projet (défaut : ./NomApp)")

    p_compile = sub.add_parser("compile", help="Compiler une spec .ml existante.")
    p_compile.add_argument("spec")
    p_compile.add_argument("--output", default=None,
                           help="Dossier du projet (défaut : dossier de la spec).")

    p_run = sub.add_parser("run", help="Vérifier la cohérence puis lancer l'application.")
    p_run.add_argument("dir", nargs="?", default=".")
    p_run.add_argument("--check", action="store_true", help="Vérifier sans lancer.")
    p_run.add_argument("--skip-smoke", action="store_true",
                       help="Sauter le smoke test comportemental (déconseillé).")
    p_run.add_argument("--port", type=int, default=8000)

    p_update = sub.add_parser("update", help="Recompiler après évolution de la spec.")
    p_update.add_argument("dir", nargs="?", default=".")

    p_diff = sub.add_parser(
        "diff",
        help="Voir le delta du contrat SANS rien recompiler ni écrire.")
    p_diff.add_argument("dir", nargs="?", default=".")

    p_front = sub.add_parser(
        "frontend", help="Générer le frontend par une IA spécialisée, avec "
                         "re-vérification automatique (cohérence + smoke test).")
    p_front.add_argument("dir", nargs="?", default=".")
    from .frontend_ai import CLI_AGENTS, GENERIC_PROVIDER, OPENAI_COMPATIBLE
    _voies = sorted({"claude", GENERIC_PROVIDER} | set(OPENAI_COMPATIBLE) | set(CLI_AGENTS))
    p_front.add_argument("--provider", default="claude", choices=_voies,
                         help="Clé API : 'claude' (ANTHROPIC_API_KEY) ; "
                              + ", ".join(f"'{n}' ({v})" for n, (_u, v) in
                                          sorted(OPENAI_COMPATIBLE.items()))
                              + f" ; '{GENERIC_PROVIDER}' pour tout autre point de "
                                "terminaison au dialecte OpenAI (MONL_AI_BASE_URL + "
                                "MONL_AI_API_KEY). Hors 'claude', '--model' est exigé. "
                                "Agent en ligne de commande, sans clé : "
                              + ", ".join(f"'{n}'" for n in sorted(CLI_AGENTS))
                              + " — l'agent travaille dans le dossier du projet.")
    p_front.add_argument("--model", default=None, help="Modèle du fournisseur.")
    p_front.add_argument("--agent-command", default=None,
                         help="Gabarit de commande pour un agent absent de la "
                              "liste, {instruction} étant substitué — par exemple "
                              "\"mon-agent --auto {instruction}\". L'emporte sur "
                              "--provider et permet aussi de corriger un préréglage.")
    p_front.add_argument("--max-turns", type=int, default=None,
                         help="Budget de tours de l'agent ('claude-code' "
                              "uniquement). Défaut : 120.")
    p_front.add_argument("--update", action="store_true",
                         help="Faire évoluer le frontend existant à partir de "
                              "FRONTEND_UPDATE_PROMPT.md au lieu de repartir de zéro.")

    # POINT 93 : corriger un défaut CONSTATÉ sur le site, sans le reconstruire.
    # Les options sont rigoureusement celles de 'frontend' — c'est la même voie
    # vers l'IA, avec les mêmes garde-fous ; seule l'origine du brief change.
    p_ret = sub.add_parser(
        "retouche", help="Corriger un défaut constaté sur le site (mise en page, "
                         "cadrage, lisibilité) sans reconstruire le frontend.")
    p_ret.add_argument("demande", help="Ce qui cloche, en une phrase — nommer "
                                       "l'écran et l'élément : \"les images de la "
                                       "section Tendances sont mal cadrées\".")
    p_ret.add_argument("dir", nargs="?", default=".")
    p_ret.add_argument("--provider", default="claude", choices=_voies,
                       help="Mêmes voies que 'monl frontend'.")
    p_ret.add_argument("--model", default=None, help="Modèle du fournisseur.")
    p_ret.add_argument("--agent-command", default=None,
                       help="Gabarit de commande pour un agent absent de la liste, "
                            "{instruction} étant substitué.")
    p_ret.add_argument("--max-turns", type=int, default=None,
                       help="Budget de tours de l'agent. Défaut : 120.")
    p_ret.add_argument("--consigne-seule", action="store_true",
                       help="Écrire FRONTEND_RETOUCHE_PROMPT.md et s'arrêter là — "
                            "pour le donner soi-même à une IA, puis 'monl import'.")

    # BRIQUE 13, COUCHE 2 (point 84) : poser un fichier de l'humain et le
    # DÉCLARER, en une commande. L'outil écrit, le compilateur prouve : la spec
    # obtenue est revalidée avant d'être écrite, donc la couche 2 ne peut pas
    # produire ce que la couche 1 refuse.
    p_assets = sub.add_parser(
        "assets", help="Installer les fichiers fournis par l'humain (photos, "
                       "logo, favicon) et les déclarer dans la spec.")
    sub_assets = p_assets.add_subparsers(dest="assets_command")

    p_add = sub_assets.add_parser(
        "add", help="Copier un fichier dans le dossier d'assets et l'écrire dans la spec.")
    p_add.add_argument("fichier", help="Le fichier à installer (photo, logo…).")
    p_add.add_argument("--for", dest="pour", default=None, metavar="VALEUR",
                       help="Fiche de seed visée, désignée par une de ses valeurs "
                            "— par exemple --for \"Halo RS\".")
    p_add.add_argument("--logo", action="store_true",
                       help="Déclarer ce fichier comme logo du projet (assets.logo).")
    p_add.add_argument("--favicon", action="store_true",
                       help="Déclarer ce fichier comme favicon (assets.favicon).")
    p_add.add_argument("--entity", default=None,
                       help="Lever une ambiguïté quand la valeur de --for existe "
                            "dans plusieurs entités.")
    p_add.add_argument("--field", default=None,
                       help="Champ 'Image' visé, si l'entité en a plusieurs.")
    p_add.add_argument("--as", dest="nom", default=None, metavar="NOM",
                       help="Nom du fichier de destination (défaut : le slug de --for "
                            "plus l'extension d'origine).")
    p_add.add_argument("--force", action="store_true",
                       help="Écraser un fichier de même nom au contenu différent.")
    p_add.add_argument("--dir", default=".", help="Dossier du projet (défaut : .).")

    p_alist = sub_assets.add_parser(
        "list", help="Ce que la spec déclare, ce qui est présent, ce qui traîne.")
    p_alist.add_argument("dir", nargs="?", default=".")

    p_content = sub.add_parser(
        "content", help="Exporter ou réimporter les fiches de démonstration en CSV.")
    sub_content = p_content.add_subparsers(dest="content_command")
    p_cexport = sub_content.add_parser(
        "export", help="Créer content/<Entite>.csv depuis les blocs seed.")
    p_cexport.add_argument("dir", nargs="?", default=".")
    p_cimport = sub_content.add_parser(
        "import", help="Remplacer les blocs seed depuis les fichiers CSV.")
    p_cimport.add_argument("dir", nargs="?", default=".")

    p_import = sub.add_parser(
        "import", help="Installer un frontend obtenu SANS clé API (brief collé "
                       "dans claude.ai, résultat téléchargé) puis re-vérifier.")
    p_import.add_argument("source", help="Fichier .zip, index.html, dossier, ou "
                                         "JSON {'files': ...} téléchargé depuis Claude.")
    p_import.add_argument("dir", nargs="?", default=".", help="Dossier du projet.")

    args = parser.parse_args(argv)

    if args.command in (None, "init"):
        cmd_init(getattr(args, "dir", None))
    elif args.command == "compile":
        project_dir = args.output or os.path.dirname(os.path.abspath(args.spec))
        compile_project(args.spec, project_dir)
    elif args.command == "run":
        cmd_run(args.dir, check_only=args.check, port=args.port, skip_smoke=args.skip_smoke)
    elif args.command == "update":
        cmd_update(args.dir)
    elif args.command == "diff":
        cmd_diff(args.dir)
    elif args.command == "assets":
        if args.assets_command == "add":
            if args.logo and args.favicon:
                print(" ❌ --logo et --favicon désignent deux déclarations "
                      "différentes : les poser en deux commandes.")
                sys.exit(1)
            cible = "logo" if args.logo else ("favicon" if args.favicon else None)
            cmd_assets_add(args.dir, args.fichier, pour=args.pour, cible=cible,
                           entity=args.entity, field=args.field, nom=args.nom,
                           force=args.force)
        elif args.assets_command == "list":
            cmd_assets_list(args.dir)
        else:
            p_assets.print_help()
            sys.exit(1)
    elif args.command == "content":
        if args.content_command == "export":
            cmd_content_export(args.dir)
        elif args.content_command == "import":
            cmd_content_import(args.dir)
        else:
            p_content.print_help()
            sys.exit(1)
    elif args.command == "frontend":
        _lancer_ia(args, update_mode=args.update)
    elif args.command == "retouche":
        cmd_retouche(args.dir, args.demande)
        if args.consigne_seule:
            print("  → Donner ce fichier à une IA, puis installer le résultat "
                  "avec 'monl import'.")
        else:
            _lancer_ia(args, retouche_mode=True)
    elif args.command == "import":
        from .frontend_ai import FrontendAIError, import_and_verify
        try:
            ok, _errors = import_and_verify(args.dir, args.source)
        except FrontendAIError as e:
            print(f" ❌ {e}")
            sys.exit(1)
        if not ok:
            sys.exit(1)


def main(argv=None):
    """Point d'entrée CLI : traduit les erreurs MONL en code de sortie."""
    try:
        return _dispatch(argv)
    except MonlError as err:
        print(f" ❌ {err}")
        raise SystemExit(1) from err


if __name__ == "__main__":
    raise SystemExit(main())
