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
import os

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
    import tomllib

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
