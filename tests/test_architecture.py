# Les frontières d'architecture, rendues EXÉCUTABLES (point 63).
#
# CLAUDE.md les énonce depuis longtemps — « le compilateur ignore
# l'orchestrateur », « aucune logique de dialogue dans tui.py », « le
# catalogue est de la donnée, pas du code ». Elles tenaient parce qu'on
# s'en souvenait. Une clause que rien ne vérifie n'est pas une clause
# (point 48) : ce fichier les vérifie.
#
# Pourquoi ce test plutôt qu'import-linter : l'outil est désormais utilisable
# (src/monl/ est un vrai paquet depuis le point 65), mais il ajouterait une
# dépendance et une étape de CI pour ce que 60 lignes de stdlib obtiennent
# déjà — en tournant dans la suite existante. Il devient le bon choix le jour
# où les contrats se compteront par dizaines, pas par six.
#
# Les imports DANS les fonctions comptent autant que ceux en tête de
# fichier : c'est précisément là que les dépendances interdites se cachent.
import ast
import fnmatch
import os
import re
import sys

SRC = os.path.join(os.path.dirname(__file__), "..", "src", "monl")

# Les modules du projet. Un PAQUET compte pour un seul nœud : son découpage
# interne est une affaire de couches, pas de frontières.
#
# La liste est LUE SUR LE DISQUE, jamais écrite à la main. Elle nommait
# `generator` en dur, et le jour où `ast_validator` est devenu un paquet à son
# tour il a disparu de MODULES sans un mot — son contrat serait resté dans
# INTERDITS en ne regardant plus rien. C'est le défaut que l'en-tête de ce
# fichier dénonce, arrivé par la porte de la liste plutôt que par celle des
# imports relatifs.
MODULES = sorted(
    [f[:-3] for f in os.listdir(SRC)
     if f.endswith(".py") and f not in ("main.py", "__init__.py")]
    + [d for d in os.listdir(SRC)
       if os.path.isfile(os.path.join(SRC, d, "__init__.py"))])


def _imports_du_projet(chemin, profondeur=0):
    """Tous les modules du projet importés par un fichier, où que l'import
    se trouve — en tête, dans une fonction, dans une méthode.

    PIÈGE (point 65) : depuis le passage en paquet, les dépendances internes
    s'écrivent en RELATIF (`from .parser import …`). Les ignorer, comme le
    faisait la première version, aurait rendu ce test muet du jour au
    lendemain — il aurait continué à passer en ne regardant plus rien.
    `profondeur` dit à quel étage du paquet vit le fichier : un `from .x`
    dans monl/ désigne un module de premier niveau, le même écrit dans
    monl/generator/ désigne un voisin du sous-paquet."""
    with open(chemin, encoding="utf-8") as fh:
        arbre = ast.parse(fh.read(), filename=chemin)
    trouves = set()
    for noeud in ast.walk(arbre):
        if isinstance(noeud, ast.Import):
            for alias in noeud.names:
                trouves.add(alias.name.split(".")[0])
        elif isinstance(noeud, ast.ImportFrom):
            if noeud.level == 0:
                if noeud.module:
                    trouves.add(noeud.module.split(".")[0])
            elif noeud.level == profondeur + 1:
                # Remonte jusqu'à la racine du paquet : c'est un module de
                # premier niveau. `from . import generator` compte aussi,
                # via les noms importés.
                if noeud.module:
                    trouves.add(noeud.module.split(".")[0])
                else:
                    trouves.update(a.name for a in noeud.names)
    return {m for m in trouves if m in MODULES}


def _depend_de(module):
    """Le graphe de dépendance d'un module du projet, ses PAQUETS compris.

    Le graphe d'un paquet est l'union de ceux de ses modules, moins lui-même :
    un sous-module qui importe son voisin (`from .socle import …`) ne franchit
    aucune frontière, et `profondeur=1` fait justement remonter les `..` au
    premier étage."""
    dossier = os.path.join(SRC, module)
    if os.path.isdir(dossier):
        vus = set()
        for nom in sorted(os.listdir(dossier)):
            if nom.endswith(".py"):
                vus |= _imports_du_projet(os.path.join(dossier, nom), profondeur=1)
        return vus - {module}
    return _imports_du_projet(os.path.join(SRC, module + ".py"))


# ---- Les contrats ---------------------------------------------------
# (source, interdits, pourquoi) — le « pourquoi » s'affiche à l'échec.
INTERDITS = [
    ("parser", ["cli", "dialogue_engine", "frontend_ai", "tui", "app_templates",
                "smoke_test", "frontend_contract", "ast_validator", "generator"],
     "le parseur est la première couche : il ne connaît rien d'autre"),
    ("ast_validator", ["cli", "dialogue_engine", "frontend_ai", "tui",
                       "app_templates", "smoke_test", "frontend_contract",
                       "generator"],
     "le validateur travaille sur l'AST, jamais sur ce qui en sortira"),
    ("generator", ["cli", "dialogue_engine", "frontend_ai", "tui",
                   "app_templates", "smoke_test", "frontend_contract"],
     "le compilateur ignore l'orchestrateur — c'est ce qui l'a rendu "
     "réutilisable après le pivot"),
    ("app_templates", MODULES,
     "le catalogue est de la DONNÉE : le dialogue l'assemble, il ne "
     "s'assemble pas lui-même"),
    ("tui", ["dialogue_engine", "cli", "parser", "ast_validator", "generator",
             "app_templates", "frontend_contract", "frontend_ai"],
     "la présentation ne connaît pas le moteur ; l'inverse ne passe que "
     "par l'interface PlainDialogueUI"),
    ("frontend_contract", ["cli", "frontend_ai", "dialogue_engine", "smoke_test"],
     "le contrat se déduit de la spec compilée, pas de qui l'a demandé"),
    ("serving", MODULES,
     "serving ne porte QUE le texte du wrapper : c'est une feuille, et c'est "
     "ce qui permet à cli et smoke_test de le partager sans cycle (point 83)"),
    ("assets_tool", ["cli", "generator", "frontend_contract", "dialogue_engine",
                     "tui", "app_templates", "smoke_test", "frontend_ai", "serving"],
     "l'outil d'assets n'a besoin que de PARSER et VALIDER : c'est ce qui lui "
     "permet de revalider une spec avant de l'écrire sans rien compiler, et ce "
     "qui empêche le cycle avec cli qui l'appelle (point 84)"),
]


def test_les_frontieres_darchitecture_tiennent():
    violations = []
    for source, interdits, pourquoi in INTERDITS:
        for cible in _depend_de(source) & set(interdits):
            violations.append(f"{source} → {cible} : {pourquoi}")
    assert not violations, "frontières franchies :\n  " + "\n  ".join(violations)


def test_le_compilateur_reste_utilisable_seul():
    """Conséquence concrète des contrats ci-dessus : la chaîne de
    compilation doit s'importer sans rien tirer de l'orchestrateur."""
    orchestration = {"cli", "dialogue_engine", "frontend_ai", "tui",
                     "app_templates", "smoke_test"}
    for module in ("parser", "ast_validator", "generator"):
        assert not _depend_de(module) & orchestration, module


def test_aucun_module_ne_simporte_lui_meme_en_cercle():
    """Un cycle direct (A importe B qui importe A) est toléré nulle part
    ailleurs qu'entre cli et frontend_ai, où il est connu et documenté."""
    connu = {("cli", "frontend_ai"), ("frontend_ai", "cli")}
    cycles = set()
    graphe = {m: _depend_de(m) for m in MODULES}
    for source, cibles in graphe.items():
        for cible in cibles:
            if source in graphe.get(cible, set()):
                cycles.add((source, cible))
    assert cycles <= connu, f"nouveaux cycles d'import : {sorted(cycles - connu)}"


def test_le_graphe_voit_vraiment_quelque_chose():
    """Garde-fou du garde-fou : un test de frontières qui ne détecte plus
    aucune dépendance passerait toujours, et ne dirait plus rien. Les
    dépendances connues du dépôt doivent donc apparaître."""
    assert {"parser", "generator", "frontend_contract"} <= _depend_de("cli")
    assert {"tui", "app_templates", "parser"} <= _depend_de("dialogue_engine")
    assert "frontend_contract" in _depend_de("smoke_test")


def test_monl_ne_simporte_jamais_monl_platform():
    """La plateforme dépend du compilateur, jamais l'inverse."""
    violations = []
    for root, _dirs, files in os.walk(SRC):
        for filename in files:
            if not filename.endswith(".py"):
                continue
            chemin = os.path.join(root, filename)
            with open(chemin, encoding="utf-8") as fh:
                arbre = ast.parse(fh.read(), filename=chemin)
            for noeud in ast.walk(arbre):
                if isinstance(noeud, ast.Import):
                    noms = [alias.name for alias in noeud.names]
                elif isinstance(noeud, ast.ImportFrom):
                    noms = [noeud.module or ""]
                else:
                    continue
                if any(nom == "monl_platform" or nom.startswith("monl_platform.")
                       for nom in noms):
                    violations.append(os.path.relpath(chemin, SRC))
    assert not violations, "monl importe monl_platform : " + ", ".join(violations)


def test_chaque_contrat_porte_sur_un_module_que_le_graphe_connait():
    """Un contrat dont la SOURCE a disparu de MODULES ne refuse plus rien.

    Le cas s'est produit : `MODULES` nommait `generator` en dur, et le jour où
    `ast_validator` est devenu un paquet il est sorti de la liste — son contrat
    restait écrit dans INTERDITS, entièrement muet. Rien ne serait devenu rouge.
    Ce témoin porte sur la LISTE, pas sur les imports : c'est l'autre façon dont
    un test d'architecture cesse de regarder."""
    inconnus = [source for source, _, _ in INTERDITS if source not in MODULES]
    assert not inconnus, (
        "contrat sans module : " + ", ".join(inconnus)
        + " — MODULES est lu sur le disque, un renommage ou un passage en "
          "paquet a dû casser la correspondance")


def test_le_socle_du_validateur_ne_lit_rien_de_son_paquet():
    """`ast_validator/socle.py` est la FEUILLE : c'est ce qui rend un cycle
    d'import impossible dans le paquet.

    Sa docstring l'affirme ; sans ce test l'affirmation ne tiendrait qu'à la
    discipline, et le premier `from .core import …` glissé dedans casserait
    l'import du compilateur entier — au chargement, donc partout à la fois."""
    chemin = os.path.join(SRC, "ast_validator", "socle.py")
    with open(chemin, encoding="utf-8") as fh:
        arbre = ast.parse(fh.read(), filename=chemin)
    voisins = [noeud.module or "."
               for noeud in ast.walk(arbre)
               if isinstance(noeud, ast.ImportFrom) and noeud.level == 1]
    assert not voisins, (
        "le socle lit son propre paquet : " + ", ".join(voisins)
        + " — il doit ne dépendre que de la stdlib et de `..errors`")


def test_aucune_exception_de_ruff_ne_vise_un_fichier_disparu():
    """Une exception `per-file-ignores` dont le chemin n'existe plus n'excuse
    rien — elle fait croire qu'une règle est encore assouplie là où elle ne
    l'est plus, et personne ne s'en aperçoit.

    Le cas s'est produit deux fois d'un coup : `src/monl/parser.py` et
    `src/monl/frontend_ai.py` sont devenus des PAQUETS, et leurs deux
    exceptions ont continué de vivre dans `pyproject.toml` en ne portant plus
    sur rien. Même famille que le contrat d'architecture devenu muet : ce qui
    cesse de regarder ne fait pas de bruit."""
    try:
        import tomllib
    except ModuleNotFoundError:      # 3.10 : `tomllib` n'arrive qu'en 3.11
        import tomli as tomllib      # noqa: I001  (déclaré dans l'extra `dev`)

    racine = os.path.join(os.path.dirname(__file__), "..")
    with open(os.path.join(racine, "pyproject.toml"), "rb") as fh:
        config = tomllib.load(fh)
    ignores = (config.get("tool", {}).get("ruff", {}).get("lint", {})
               .get("per-file-ignores", {}))
    absents = [chemin for chemin in ignores
               if not os.path.exists(os.path.join(racine, chemin))]
    assert not absents, (
        "exception ruff sur un fichier disparu : " + ", ".join(absents)
        + " — la déplacer sur le nouveau chemin, ou la retirer si elle n'a "
          "plus lieu d'être")


# ─────────────────────────────────────────────────────────────────────
# LA TAILLE DES FICHIERS, ET DES FONCTIONS (point 155)
#
# Neuf fichiers du compilateur pesaient de 700 à 2 800 lignes, et deux
# fonctions dépassaient 900. Les découper n'a de valeur que si rien ne les
# laisse regrossir : une règle que rien ne vérifie n'est pas une règle
# (point 48, déjà l'argument de l'en-tête de ce fichier).
#
# Le plafond porte sur `src/`, pas sur `tests/` : un fichier de test est une
# suite de cas indépendants qu'on lit un par un, pas une pièce dont la
# complexité croît avec la longueur. Le découper le rendrait plus dur à
# retrouver, pas plus simple.
#
# Les exceptions portent chacune SA RAISON, comme celles de ruff dans
# pyproject.toml. Toutes deux sont de la DONNÉE : un catalogue et une
# grammaire. Le plafond vise la complexité, et un littéral n'en a pas — le
# couper en deux moitiés arbitraires rendrait le fichier plus dur à lire, ce
# qui est exactement l'inverse du but.
PLAFOND_FICHIER = 400
PLAFOND_FONCTION = 400
EXCEPTIONS_DE_TAILLE = {
    "monl/app_templates.py":
        "TEMPLATES est un littéral de données : les dix modèles du catalogue, "
        "un par entrée. Le couper séparerait des lignes qui se lisent en table.",
    "monl/parser/grammaire.py":
        "La grammaire Lark est UNE chaîne. La couper en deux ferait deux "
        "moitiés dont aucune n'est une grammaire.",
}


def _fichiers_de_src():
    for racine, _d, fichiers in os.walk(os.path.join(SRC, "..")):
        if "__pycache__" in racine:
            continue
        for f in sorted(fichiers):
            if f.endswith(".py"):
                chemin = os.path.join(racine, f)
                rel = os.path.relpath(chemin, os.path.join(SRC, "..")).replace(os.sep, "/")
                yield rel, chemin


def test_aucun_fichier_de_src_ne_depasse_le_plafond():
    trop = {}
    for rel, chemin in _fichiers_de_src():
        with open(chemin, encoding="utf-8") as fh:
            n = len(fh.read().splitlines())
        if n > PLAFOND_FICHIER and rel not in EXCEPTIONS_DE_TAILLE:
            trop[rel] = n
    assert not trop, (
        f"fichiers au-dessus de {PLAFOND_FICHIER} lignes sans exception "
        f"écrite : {trop}")


def test_aucune_fonction_ne_depasse_le_plafond():
    """Un fichier court fait de deux fonctions de 500 lignes n'a rien gagné."""
    trop = {}
    for rel, chemin in _fichiers_de_src():
        with open(chemin, encoding="utf-8") as fh:
            arbre = ast.parse(fh.read())
        for n in ast.walk(arbre):
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                taille = n.end_lineno - n.lineno + 1
                if taille > PLAFOND_FONCTION:
                    trop[f"{rel}:{n.name}"] = taille
    assert not trop, f"fonctions au-dessus de {PLAFOND_FONCTION} lignes : {trop}"


def test_chaque_exception_de_taille_vise_un_fichier_qui_depasse_encore():
    """Une exception qui ne dispense plus de rien doit DISPARAÎTRE.

    Le pendant exact de `test_aucune_exception_de_ruff_ne_vise_un_fichier_disparu` :
    une dispense oubliée finit par couvrir un fichier qu'on croyait tenu."""
    tailles = {}
    for rel, chemin in _fichiers_de_src():
        with open(chemin, encoding="utf-8") as fh:
            tailles[rel] = len(fh.read().splitlines())
    for rel, raison in EXCEPTIONS_DE_TAILLE.items():
        assert rel in tailles, f"exception sur un fichier disparu : {rel}"
        assert tailles[rel] > PLAFOND_FICHIER, (
            f"{rel} tient désormais dans {PLAFOND_FICHIER} lignes "
            f"({tailles[rel]}) : retirer l'exception")
        assert len(raison) > 40, f"exception sans raison écrite : {rel}"


# ---- La complexité cyclomatique ------------------------------------
#
# Ruff mesure utilement la complexité, mais ce garde-fou doit rester
# exécutable avec la suite minimale du projet : il compte donc lui-même son
# AST. Le plafond est volontairement 15, le seuil au-delà duquel le chantier
# a commencé. Les exceptions sont explicites et portent la valeur observée ;
# elles sont des cliquets, pas des plafonds de confort.
PLAFOND_COMPLEXITE = 15
EXCEPTIONS_DE_COMPLEXITE = {
    "monl/assets_tool/commandes.py:ajouter_asset": (25, "La commande assemble une liste de contrôles et reste hors des cinq cibles refactorées."),
    "monl/assets_tool/resolution.py:_resoudre_seed": (37, "Le résolveur conserve plusieurs cas métier liés aux seeds ; il est hors périmètre et borné par son cliquet."),
    "monl/ast_validator/acces.py:_valider_controle_dacces": (38, "Validation emmêlée non traitée dans ce chantier ; l'exception rend cette dette visible et bornée."),
    "monl/ast_validator/assets.py:_valider_assets_et_seeds": (16, "Validation emmêlée non traitée dans ce chantier ; l'exception rend cette dette visible et bornée."),
    "monl/ast_validator/assets.py:_valider_parent_de_seed": (18, "Validation emmêlée non traitée dans ce chantier ; l'exception rend cette dette visible et bornée."),
    "monl/ast_validator/audit.py:_audit_security_rules": (17, "Validation emmêlée non traitée dans ce chantier ; l'exception rend cette dette visible et bornée."),
    "monl/ast_validator/capacites.py:_valider_capacites": (43, "Validation emmêlée non traitée dans ce chantier ; l'exception rend cette dette visible et bornée."),
    "monl/ast_validator/capacites.py:_valider_identifiant_de_compte": (18, "Validation emmêlée non traitée dans ce chantier ; l'exception rend cette dette visible et bornée."),
    "monl/ast_validator/champs.py:_valider_champs_categorises": (18, "Validation emmêlée non traitée dans ce chantier ; l'exception rend cette dette visible et bornée."),
    "monl/ast_validator/champs.py:_valider_champs_enumeres": (20, "Validation emmêlée non traitée dans ce chantier ; l'exception rend cette dette visible et bornée."),
    "monl/ast_validator/champs.py:_valider_contraintes_de_champ": (19, "Validation emmêlée non traitée dans ce chantier ; l'exception rend cette dette visible et bornée."),
    "monl/ast_validator/champs_calcules.py:_valider_champs_agreges": (30, "Validation emmêlée non traitée dans ce chantier ; l'exception rend cette dette visible et bornée."),
    "monl/ast_validator/champs_calcules.py:_valider_champs_derives": (34, "Validation emmêlée non traitée dans ce chantier ; l'exception rend cette dette visible et bornée."),
    "monl/ast_validator/champs_calcules.py:_valider_effets_compteurs": (21, "Validation emmêlée non traitée dans ce chantier ; l'exception rend cette dette visible et bornée."),
    "monl/ast_validator/champs_calcules.py:_valider_regles_once_per": (20, "Validation emmêlée non traitée dans ce chantier ; l'exception rend cette dette visible et bornée."),
    "monl/ast_validator/collisions.py:_valider_regles_message": (20, "Validation emmêlée non traitée dans ce chantier ; l'exception rend cette dette visible et bornée."),
    "monl/ast_validator/collisions.py:_valider_workflows_et_collisions": (20, "Validation emmêlée non traitée dans ce chantier ; l'exception rend cette dette visible et bornée."),
    "monl/ast_validator/commerce.py:_valider_requires_own_et_payable": (28, "Validation emmêlée non traitée dans ce chantier ; l'exception rend cette dette visible et bornée."),
    "monl/ast_validator/commerce.py:_valider_securite_calculs_paiement": (18, "Validation emmêlée non traitée dans ce chantier ; l'exception rend cette dette visible et bornée."),
    "monl/ast_validator/cycle_de_vie.py:_valider_regle_apres_paiement": (23, "Validation emmêlée non traitée dans ce chantier ; l'exception rend cette dette visible et bornée."),
    "monl/ast_validator/cycle_de_vie.py:_valider_regles_liberation": (19, "Validation emmêlée non traitée dans ce chantier ; l'exception rend cette dette visible et bornée."),
    "monl/ast_validator/migrations.py:_valider_migrations": (18, "Validation emmêlée non traitée dans ce chantier ; l'exception rend cette dette visible et bornée."),
    "monl/ast_validator/presentation.py:_valider_landing": (16, "Validation emmêlée non traitée dans ce chantier ; l'exception rend cette dette visible et bornée."),
    "monl/ast_validator/uploads.py:_valider_champs_uploades": (41, "Validation emmêlée non traitée dans ce chantier ; l'exception rend cette dette visible et bornée."),
    "monl/cli/couverture.py:_frontend_route_coverage": (26, "Contrôle de couverture hors des cinq cibles ; sa dette est conservée explicitement et cliquetée."),
    "monl/cli/delta.py:_rapporter_delta": (46, "Rapport de delta hors des cinq cibles ; sa dette est conservée explicitement et cliquetée."),
    "monl/cli/delta.py:_write_update_brief": (18, "Émission ligne par ligne conservée pour rester lisible ; cette fonction est hors des cinq cibles."),
    "monl/cli/dispatch.py:_dispatch": (27, "Routage de commandes hors des cinq cibles ; sa dette est conservée explicitement et cliquetée."),
    "monl/cli/lancement.py:cmd_run": (17, "Orchestration de commande hors des cinq cibles ; sa dette est conservée explicitement et cliquetée."),
    "monl/cli/signature.py:_contract_signature": (53, "Sérialisation et émission de signature conservées ligne par ligne ; cas plat hors des cinq cibles."),
    "monl/content_tool.py:_lisez_moi": (17, "Assemblage éditorial hors des cinq cibles ; sa dette est conservée explicitement et cliquetée."),
    "monl/design_system/profil.py:_guarantees": (18, "Sélection de garanties hors des cinq cibles ; sa dette est conservée explicitement et cliquetée."),
    "monl/design_system/profil.py:infer_design_profile": (23, "Inférence de profil hors des cinq cibles ; sa dette est conservée explicitement et cliquetée."),
    "monl/design_system/rendu.py:render_design_system": (22, "Rendu de design hors des cinq cibles ; sa dette est conservée explicitement et cliquetée."),
    "monl/dialogue_engine/commerce.py:_ask_payable": (32, "Parcours de dialogue hors des cinq cibles ; sa dette est conservée explicitement et cliquetée."),
    "monl/dialogue_engine/libre.py:_run_free": (46, "Parcours de dialogue hors des cinq cibles ; sa dette est conservée explicitement et cliquetée."),
    "monl/dialogue_engine/parcours.py:_run_from_template": (36, "Parcours de dialogue hors des cinq cibles ; sa dette est conservée explicitement et cliquetée."),
    "monl/frontend_ai/agents.py:generate_with_cli_agent": (34, "Orchestration d'agent hors des cinq cibles ; sa dette est conservée explicitement et cliquetée."),
    "monl/frontend_ai/controles_fichiers.py:_frontend_local_reference_errors": (17, "Contrôle de fichiers hors des cinq cibles ; sa dette est conservée explicitement et cliquetée."),
    "monl/frontend_ai/orchestration.py:generate_and_verify": (29, "Orchestration frontend hors des cinq cibles ; sa dette est conservée explicitement et cliquetée."),
    "monl/frontend_contract/brief.py:_render_prompt": (46, "Émission de prompt ligne par ligne conservée pour rester lisible ; cas plat hors des cinq cibles."),
    "monl/frontend_contract/contrat_entites.py:_specs_des_entites": (25, "Assemblage de contrat hors des cinq cibles ; sa dette est conservée explicitement et cliquetée."),
    "monl/frontend_contract/contrat_routes.py:_routes_du_contrat": (21, "Assemblage de routes hors des cinq cibles ; sa dette est conservée explicitement et cliquetée."),
    "monl/frontend_contract/roles_de_champs.py:_assign_field_roles": (39, "Attribution de rôles hors des cinq cibles ; sa dette est conservée explicitement et cliquetée."),
    "monl/generator/core.py:__init__": (24, "Initialisation déclarative du générateur conservée telle quelle ; fonction hors des cinq cibles."),
    "monl/generator/pipeline.py:build_compilation_plans": (21, "Assemblage de plans de compilation hors des cinq cibles ; dette cliquetée."),
    "monl/generator/proprietaire.py:_identity_fk_columns": (16, "Déduction de colonnes hors des cinq cibles ; sa dette est conservée explicitement et cliquetée."),
    "monl/generator/routes_creation.py:_generate_create_route_lines": (43, "Émission de routes ligne par ligne : liste plate légitime, conservée hors des cinq cibles."),
    "monl/generator/routes_lecture.py:_generate_read_route_lines": (49, "Émission de routes ligne par ligne : liste plate légitime, conservée hors des cinq cibles."),
    "monl/generator/routes_lecture_filtree.py:_generate_read_route_lines_with_query": (51, "Émission de routes ligne par ligne : liste plate légitime, conservée hors des cinq cibles."),
    "monl/generator/routes_modification.py:_generate_update_route_lines": (42, "Émission de routes ligne par ligne : liste plate légitime, conservée hors des cinq cibles."),
    "monl/generator/routes_paiement.py:_generate_payment_routes": (17, "Émission de routes ligne par ligne : liste plate légitime, conservée hors des cinq cibles."),
    "monl/generator/routes_prestataires.py:_generate_postpayment_routes": (19, "Émission de routes ligne par ligne : liste plate légitime, conservée hors des cinq cibles."),
    "monl/generator/routes_suppression.py:_generate_delete_route_lines": (28, "Émission de routes ligne par ligne : liste plate légitime, conservée hors des cinq cibles."),
    "monl/generator/runtime_connexion.py:_socle_authentification": (16, "Émission de socle ligne par ligne : liste plate légitime, hors des cinq cibles."),
    "monl/generator/schemas.py:_generate_schema_lines": (34, "Émission de schéma ligne par ligne : liste plate légitime, hors des cinq cibles."),
    "monl/image_ai.py:call": (19, "Appel de service hors des cinq cibles ; sa dette est conservée explicitement et cliquetée."),
    "monl/parser/transformer_structure.py:app": (30, "Transformation d'AST hors des cinq cibles ; sa dette est conservée explicitement et cliquetée."),
    "monl/smoke_test/etapes.py:_eprouver_les_routes": (27, "Parcours de smoke test hors des cinq cibles ; sa dette est conservée explicitement et cliquetée."),
    "monl/smoke_test/etapes.py:_frontend_dans_jsdom": (16, "Parcours de smoke test hors des cinq cibles ; sa dette est conservée explicitement et cliquetée."),
    "monl/ui_patterns.py:select_ui_patterns": (23, "Sélection de motifs hors des cinq cibles ; sa dette est conservée explicitement et cliquetée."),
    "monl/usage.py:_aggregate": (19, "Agrégation de métriques hors des cinq cibles ; sa dette est conservée explicitement et cliquetée."),
    "monl/usage.py:_load_prices": (23, "Chargement de tarifs hors des cinq cibles ; sa dette est conservée explicitement et cliquetée."),
    "monl_platform/store_core.py:_reject_non_additive_project_schema": (16, "Contrôle de schéma plateforme hors des cinq cibles ; dette explicitement cliquetée."),
}


class _CompteurComplexite(ast.NodeVisitor):
    """Compteur local et déterministe, distinct de la définition de Ruff.

    Le score commence à 1 et ajoute un point pour chaque ``if`` (donc chaque
    ``elif``, représenté par un ``if`` dans le ``orelse``), ``for``/``async
    for``, ``while``, gestionnaire ``except``, ternaire ``IfExp``, nœud
    booléen ``and``/``or``, générateur de compréhension et filtre ``if`` de
    compréhension, ainsi que pour chaque ``assert``. Les fonctions, lambdas
    et classes imbriquées sont volontairement ignorées pendant la visite de
    leur parente ; ``ast.walk`` les mesure séparément. Une compréhension à
    plusieurs générateurs compte donc chaque générateur et chaque filtre.
    """

    def __init__(self):
        self.score = 1

    def visit_FunctionDef(self, _node):
        pass

    def visit_AsyncFunctionDef(self, _node):
        pass

    def visit_Lambda(self, _node):
        pass

    def visit_ClassDef(self, _node):
        pass

    def visit_If(self, node):
        self.score += 1
        self.generic_visit(node)

    def visit_For(self, node):
        self.score += 1
        self.generic_visit(node)

    def visit_AsyncFor(self, node):
        self.score += 1
        self.generic_visit(node)

    def visit_While(self, node):
        self.score += 1
        self.generic_visit(node)

    def visit_ExceptHandler(self, node):
        self.score += 1
        self.generic_visit(node)

    def visit_IfExp(self, node):
        self.score += 1
        self.generic_visit(node)

    def visit_BoolOp(self, node):
        self.score += 1
        self.generic_visit(node)

    def visit_comprehension(self, node):
        self.score += 1 + len(node.ifs)
        self.generic_visit(node)

    def visit_Assert(self, node):
        self.score += 1
        self.generic_visit(node)


def _complexite_fonction(noeud):
    compteur = _CompteurComplexite()
    for instruction in noeud.body:
        compteur.visit(instruction)
    return compteur.score


def _fonctions_de_src():
    for rel, chemin in _fichiers_de_src():
        with open(chemin, encoding="utf-8") as fh:
            arbre = ast.parse(fh.read(), filename=chemin)
        for noeud in ast.walk(arbre):
            if isinstance(noeud, (ast.FunctionDef, ast.AsyncFunctionDef)):
                yield f"{rel}:{noeud.name}", _complexite_fonction(noeud)


def _violations_de_complexite(fonctions, exceptions):
    violations = {}
    for nom, score in fonctions:
        limite = exceptions.get(nom, (PLAFOND_COMPLEXITE, ""))[0]
        if score > limite:
            violations[nom] = {"mesure": score, "limite": limite}
    return violations


def test_aucune_fonction_de_src_ne_depasse_le_plafond_de_complexite():
    """Le plafond commun s'applique aussi aux fonctions nouvelles."""
    violations = _violations_de_complexite(
        _fonctions_de_src(), EXCEPTIONS_DE_COMPLEXITE)
    assert not violations, (
        f"fonctions au-dessus de {PLAFOND_COMPLEXITE} sans cliquet valide : "
        f"{violations}")


def test_chaque_exception_de_complexite_sert_encore():
    """Une exception repassée sous le plafond doit être retirée.

    C'EST ICI que vit le cliquet, dans l'égalité stricte au score enregistré
    — pas dans un test à part. Un second test rejouant
    `_violations_de_complexite` a existé sous le nom « le cliquet interdit
    toute régression » : mesuré, il ne rougissait JAMAIS seul (contre-épreuve
    faite sur les trois façons de casser le garde-fou), il refaisait mot pour
    mot l'assertion du plafond. Un témoin qui annonce une garantie portée
    ailleurs finit par la faire croire deux fois gardée — point 167bis.
    """
    fonctions = dict(_fonctions_de_src())
    for nom, (valeur, raison) in EXCEPTIONS_DE_COMPLEXITE.items():
        assert nom in fonctions, f"exception sur une fonction disparue : {nom}"
        assert fonctions[nom] > PLAFOND_COMPLEXITE, (
            f"{nom} tient désormais dans {PLAFOND_COMPLEXITE} lignes de score "
            f"({fonctions[nom]}) : retirer l'exception")
        assert fonctions[nom] == valeur, (
            f"{nom} a changé de score ({fonctions[nom]} au lieu de {valeur}) : "
            "mettre à jour le code ou le cliquet après revue")
        assert len(raison) > 40, f"exception sans raison écrite : {nom}"


def test_le_compteur_de_complexite_compte_les_constructions_annoncees():
    source = """\
def probe(values):
    def nested(value):
        if value:
            return value
        return 0
    for value in values:
        if value and value > 0 or value < 0:
            pass
        elif value:
            pass
        while value:
            break
        try:
            assert value
        except ValueError:
            pass
    return [value if value else 0 for value in values if value]
"""
    arbre = ast.parse(source, filename="synthetic.py")
    fonctions = [n for n in ast.walk(arbre)
                 if isinstance(n, ast.FunctionDef)]
    scores = {n.name: _complexite_fonction(n) for n in fonctions}
    assert scores == {"probe": 12, "nested": 2}


def test_le_garde_fou_rougit_pour_une_fonction_trop_complexe():
    source = "def trop_complexe(value):\n" + "".join(
        "    if value:\n        pass\n" for _ in range(16))
    arbre = ast.parse(source, filename="synthetic.py")
    fonctions = [(f"synthetic.py:{n.name}", _complexite_fonction(n))
                 for n in ast.walk(arbre)
                 if isinstance(n, ast.FunctionDef)]
    assert _violations_de_complexite(fonctions, {}) == {
        "synthetic.py:trop_complexe": {"mesure": 17, "limite": 15}}


def test_le_garde_fou_rougit_si_on_retire_une_exception_utile():
    fonctions = list(_fonctions_de_src())
    exceptions = dict(EXCEPTIONS_DE_COMPLEXITE)
    retiree = next(iter(exceptions))
    del exceptions[retiree]
    violations = _violations_de_complexite(fonctions, exceptions)
    assert retiree in violations


def test_aucun_test_ne_saute_faute_de_bibliotheque():
    """`pytest.importorskip` rend du vert sans rien vérifier.

    Trouvé par la CI, pas en local : Pillow n'était déclaré que dans l'extra
    `ai`, que la CI n'installe pas. Le test de réencodage JPEG SAUTAIT donc à
    chaque exécution — et le seul motif pour lequel on l'a su est qu'un test
    voisin, lui, échouait franchement. Le saut, lui, n'aurait jamais parlé.

    C'est le point 140 par une autre porte : un saut ne dit pas « rien à
    vérifier ici », il dit « je n'ai pas vérifié ». Une bibliothèque dont un
    test a besoin se DÉCLARE dans l'extra `dev` — celui que la CI installe —
    au lieu d'être contournée.

    Les `pytest.skip` conditionnels restent permis : ils gardent une
    intégration qu'on peut légitimement ne pas demander (un vrai PostgreSQL),
    et ils la NOMMENT. Une bibliothèque Python installable, non.
    """
    dossier = os.path.dirname(__file__)
    fautifs = []
    for nom in sorted(os.listdir(dossier)):
        if not nom.endswith(".py"):
            continue
        chemin = os.path.join(dossier, nom)
        with open(chemin, encoding="utf-8") as fh:
            source = fh.read()
        for noeud in ast.walk(ast.parse(source, filename=nom)):
            if (isinstance(noeud, ast.Call)
                    and isinstance(noeud.func, ast.Attribute)
                    and noeud.func.attr == "importorskip"):
                fautifs.append(f"{nom}:{noeud.lineno}")

    assert not fautifs, (
        "importorskip rend du vert sans vérifier — déclarer la bibliothèque "
        "dans l'extra `dev` : " + ", ".join(fautifs))


def test_tout_fichier_statique_de_la_plateforme_est_embarque_dans_le_paquet():
    """Un fichier non déclaré dans `package-data` n'est PAS installé.

    Mesuré, pas supposé : `package-data` ne déclarait que `static/*.png`, donc
    `favicon.ico` restait dans l'arbre de travail et jamais dans le paquet. Or
    `theme.py` le lit AU NIVEAU DU MODULE (pour en dériver l'empreinte de
    cache) : depuis une installation normale, `import monl_platform.app`
    levait `FileNotFoundError` — **la plateforme entière était indéployable**.

    Pourquoi la CI ne l'a pas vu : son garde-fou « le paquet s'installe et la
    commande répond » tourne après un `pip install -e .`, donc les modules
    pointent vers l'arbre source où le fichier EST. L'installation éditable
    masque exactement cette classe de défaut.

    Ce test se lit sur le DISQUE et non sur une liste écrite à la main : un
    `.svg` ou un `.woff2` ajouté demain rouvrirait le même trou en silence.
    """
    try:
        import tomllib
    except ModuleNotFoundError:      # 3.10 : `tomllib` n'arrive qu'en 3.11
        import tomli as tomllib      # noqa: I001  (déclaré dans l'extra `dev`)

    racine = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    statiques = os.path.join(racine, "src", "monl_platform", "static")
    with open(os.path.join(racine, "pyproject.toml"), "rb") as fh:
        motifs = tomllib.load(fh)["tool"]["setuptools"]["package-data"]["monl_platform"]

    presents = sorted(nom for nom in os.listdir(statiques)
                      if os.path.isfile(os.path.join(statiques, nom)))
    assert presents, "aucun fichier statique : ce test ne garde plus rien"
    absents = [nom for nom in presents
               if not any(fnmatch.fnmatch(f"static/{nom}", m) for m in motifs)]

    assert not absents, (
        "ces fichiers ne seront PAS installés avec le paquet — ajouter leur "
        f"motif à [tool.setuptools.package-data] : {', '.join(absents)}")


def test_aucun_test_ne_monte_la_plateforme_avec_testclient():
    """`starlette.testclient` exige `httpx2`, que la CI n'installe pas.

    La décision est ÉCRITE depuis longtemps, en tête de
    `tests/test_platform_web.py` : ce fichier montait la plateforme avec
    `TestClient`, la suite s'arrêtait à la COLLECTE sur les trois versions de
    Python, et tout a été refait contre un uvicorn éphémère.

    Rien ne la gardait. Un test neuf a donc réintroduit `TestClient` et rougi
    la CI exactement de la même façon — vert en local avec un simple
    avertissement de dépréciation, cassé là où ça compte. **Une décision
    écrite mais non gardée se réapprend en la cassant** ; c'est le point 152
    (« une garantie qui cesse de porter ne fait aucun bruit ») appliqué à une
    consigne de prose.

    Le remède n'est pas d'ajouter `httpx2` : un client en processus ne
    traverse ni la couche ASGI réelle, ni le démarrage du serveur.
    """
    dossier = os.path.dirname(__file__)
    fautifs = []
    for nom in sorted(os.listdir(dossier)):
        if not nom.endswith(".py"):
            continue
        with open(os.path.join(dossier, nom), encoding="utf-8") as fh:
            source = fh.read()
        for noeud in ast.walk(ast.parse(source, filename=nom)):
            if isinstance(noeud, ast.ImportFrom) and noeud.module and (
                    noeud.module.endswith("testclient")):
                fautifs.append(f"{nom}:{noeud.lineno}")
            elif isinstance(noeud, ast.Import):
                for alias in noeud.names:
                    if alias.name.endswith("testclient"):
                        fautifs.append(f"{nom}:{noeud.lineno}")

    assert not fautifs, (
        "TestClient exige httpx2 et n'exerce pas le vrai serveur — monter un "
        "uvicorn éphémère à la place : " + ", ".join(fautifs))


# Les arbres du dépôt que les tests exercent. `outils/` en fait partie parce
# que Pillow n'y entre que par `outils/fabriquer_images.py`, et `scripts/`
# parce que le garde-fou de publication y vit (point 168).
ARBRES_EXERCES = ("tests", "outils", "scripts")


def _normalise_distribution(nom):
    """PEP 503 : `PyYAML`, `pyyaml` et `Py_Yaml` sont la MÊME distribution."""
    return re.sub(r"[-_.]+", "-", nom).lower()


def _distributions_du_module(module):
    """Rend les distributions qui fournissent *module*, ou None si inconnu.

    None ne veut pas dire « aucune » mais « pas installé ici, donc pas
    mesurable » : la correspondance nom d'import → nom de distribution est
    portée par l'environnement, pas par le code.
    """
    from importlib.metadata import packages_distributions

    fournisseurs = packages_distributions().get(module)
    if fournisseurs is None:
        return None
    return {_normalise_distribution(nom) for nom in fournisseurs}


def _modules_du_depot():
    """Tout ce qui vit dans l'arbre : ni à déclarer, ni à installer."""
    racine = os.path.join(os.path.dirname(__file__), "..")
    noms = set(ARBRES_EXERCES)
    for base in ARBRES_EXERCES + ("src",):
        chemin = os.path.join(racine, base)
        if not os.path.isdir(chemin):
            continue
        for dossier, sous_dossiers, fichiers in os.walk(chemin):
            noms |= {f[:-3] for f in fichiers
                     if f.endswith(".py") and f != "__init__.py"}
            noms |= {d for d in sous_dossiers
                     if os.path.exists(os.path.join(dossier, d, "__init__.py"))}
    return noms


def _modules_tiers_importes_par_les_tests():
    """Les modules de TIERCE PARTIE importés sous `tests/`, par l'AST.

    Par l'AST et non par `grep` : un import multi-lignes ou un accès par
    attribut échappe au texte (point 153). Les modules entrés dans la
    bibliothèque standard APRÈS la version minimale sont écartés — sur
    Python 3.10, `tomllib` n'est pas dans `sys.stdlib_module_names` et serait
    pris pour une dépendance de tierce partie.
    """
    interne = _modules_du_depot()
    standard = set(sys.stdlib_module_names) | set(APRES_LA_VERSION_MINIMALE)
    vus = {}
    dossier = os.path.join(os.path.dirname(__file__))
    for racine_courante, _, fichiers in os.walk(dossier):
        for nom in sorted(f for f in fichiers if f.endswith(".py")):
            chemin = os.path.join(racine_courante, nom)
            with open(chemin, encoding="utf-8") as fh:
                arbre = ast.parse(fh.read(), filename=chemin)
            for noeud in ast.walk(arbre):
                if isinstance(noeud, ast.Import):
                    cibles = [alias.name for alias in noeud.names]
                elif isinstance(noeud, ast.ImportFrom) and not noeud.level:
                    cibles = [noeud.module] if noeud.module else []
                else:
                    continue
                for cible in cibles:
                    tete = cible.split(".")[0]
                    if tete not in standard and tete not in interne:
                        vus.setdefault(tete, set()).add(nom)
    return vus


def test_les_bibliotheques_dont_les_tests_ont_besoin_sont_dans_dev():
    """Le pendant du test ci-dessus : la déclaration, pas seulement l'absence
    de contournement.

    Sans lui, retirer Pillow de l'extra `dev` ferait échouer la CI sans qu'un
    test explique POURQUOI — et la tentation serait de remettre un saut.

    **La liste des bibliothèques est DÉRIVÉE, jamais écrite ici.** Elle l'a
    été, et elle nommait `pytest`, `requests` et `pillow` — trois sur les neuf
    que les tests importaient réellement. Une borne exprimée par une liste de
    noms cesse de borner dès qu'un nom s'ajoute, et sans faire de bruit : c'est
    le défaut du point 162bis (`OUTILS_QUI_COMPILENT`), du point 164 (la page
    `/mcp`) et du point 167 (les versions de Python). Ajouter `packaging` et
    `PyYAML` au point 168 n'aurait rien réveillé.

    **Sa limite est ÉNONCÉE** : associer un module à sa distribution
    (`PIL` → `pillow`, `yaml` → `PyYAML`) exige que le module soit INSTALLÉ,
    car c'est l'environnement qui porte cette correspondance. Ce qu'on ne peut
    pas associer, on ne le juge pas — on le NOMME dans le message, plutôt que
    de deviner un nom de distribution et de refuser une déclaration correcte
    (même arbitrage qu'au point 83 : sans `base_dir`, le validateur se tait).
    Sur la CI la question ne se pose pas : un module qu'aucune installation ne
    fournit fait échouer la collecte du fichier qui l'importe.
    """
    try:
        import tomllib
    except ModuleNotFoundError:      # 3.10 : `tomllib` n'arrive qu'en 3.11
        import tomli as tomllib      # noqa: I001  (déclaré dans l'extra `dev`)

    racine = os.path.join(os.path.dirname(__file__), "..")
    with open(os.path.join(racine, "pyproject.toml"), "rb") as fh:
        config = tomllib.load(fh)

    # Ce que `pip install -e ".[dev,postgres]"` — la ligne exacte de ci.yml —
    # pose réellement. Pas seulement `dev` : une bibliothèque déclarée dans
    # les dépendances du paquet est là aussi.
    requis = list(config["project"].get("dependencies", []))
    for extra in ("dev", "postgres"):
        requis += config["project"]["optional-dependencies"].get(extra, [])
    installees = {_normalise_distribution(re.split(r"[<>=!;\[ ]", ligne.strip())[0])
                  for ligne in requis}

    manquantes, non_mesurables = [], []
    for module, fichiers in sorted(_modules_tiers_importes_par_les_tests().items()):
        distributions = _distributions_du_module(module)
        if distributions is None:
            non_mesurables.append(module)      # non installé : voir docstring
        elif not (distributions & installees):
            manquantes.append(f"{module} (distribution {sorted(distributions)}, "
                              f"importé par {sorted(fichiers)[0]})")

    assert not manquantes, (
        f"la CI installe `.[dev,postgres]` et n'y trouvera pas : {manquantes}. "
        f"Les tests qui en dépendent échoueront à la collecte, ou sauteront — "
        f"et un saut ne dit pas « rien à vérifier », il dit « je n'ai pas "
        f"vérifié » (point 140). Non mesurables ici : {non_mesurables or 'aucun'}")


# Modules entrés dans la bibliothèque standard APRÈS la version minimale
# déclarée par `requires-python` (3.10). Les importer EN TÊTE de fichier fait
# échouer la COLLECTE sur la plus vieille version que la CI couvre — donc tout
# le fichier, pas seulement le test concerné.
APRES_LA_VERSION_MINIMALE = {
    "tomllib": "3.11",     # lecture de pyproject.toml
    "asyncio.taskgroups": "3.11",
}


def test_aucun_test_n_importe_en_tete_un_module_absent_de_la_version_minimale():
    """Un import de tête tue la COLLECTE, pas seulement son test.

    `import tomllib` posé en tête de `test_architecture.py` a rendu la CI rouge
    sur Python 3.10 (`ModuleNotFoundError`) alors que la suite était verte en
    local : cette machine est en 3.14, où le module existe. Le fichier portait
    DÉJÀ deux fois le repli correct — un `try/except ModuleNotFoundError` dans
    la fonction — et l'import de tête le contournait.

    Le repli doit rester DANS la fonction : là, seul le test qui a besoin du
    module échoue si `tomli` manque, et il le dit. En tête, c'est le fichier
    entier qui disparaît de la collecte, ce qui ressemble à « rien à vérifier »
    (point 140).
    """
    dossier = os.path.dirname(os.path.abspath(__file__))
    fichiers = sorted(nom for nom in os.listdir(dossier)
                      if nom.startswith("test_") and nom.endswith(".py"))
    assert fichiers, "aucun fichier de test lu : ce témoin ne garde plus rien"

    fautes = []
    for nom_fichier in fichiers:
        with open(os.path.join(dossier, nom_fichier), encoding="utf-8") as fh:
            arbre = ast.parse(fh.read())
        for noeud in arbre.body:            # le CORPS du module, pas les fonctions
            if isinstance(noeud, ast.Import):
                noms = [alias.name for alias in noeud.names]
            elif isinstance(noeud, ast.ImportFrom):
                noms = [noeud.module or ""]
            else:
                continue
            for nom in noms:
                if nom in APRES_LA_VERSION_MINIMALE:
                    fautes.append(
                        f"{nom_fichier}:{noeud.lineno} importe « {nom} » en tête "
                        f"(entré en {APRES_LA_VERSION_MINIMALE[nom]}, minimum "
                        f"déclaré 3.10)")

    assert not fautes, (
        "import(s) de tête absent(s) de la version minimale — la collecte du "
        "fichier ENTIER échoue sur cette version : " + " ; ".join(fautes))
