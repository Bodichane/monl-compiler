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

# Les modules du projet (le package generator compte pour un seul nœud :
# son découpage interne est une affaire de couches, pas de frontières).
MODULES = sorted(
    [f[:-3] for f in os.listdir(SRC)
     if f.endswith(".py") and f not in ("main.py", "__init__.py")]
    + ["generator"])


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
    """Le graphe de dépendance d'un module du projet, generator compris."""
    dossier = os.path.join(SRC, "generator")
    if module == "generator":
        vus = set()
        for nom in os.listdir(dossier):
            if nom.endswith(".py"):
                vus |= _imports_du_projet(os.path.join(dossier, nom), profondeur=1)
        return vus - {"generator"}
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
