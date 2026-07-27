# Les frontières d'architecture, rendues EXÉCUTABLES (point 63).
#
# CLAUDE.md les énonce depuis longtemps — « le compilateur ignore
# l'orchestrateur », « aucune logique de dialogue dans tui.py », « le
# catalogue est de la donnée, pas du code ». Elles tenaient parce qu'on
# s'en souvenait. Une clause que rien ne vérifie n'est pas une clause
# (point 48) : ce fichier les vérifie.
#
# Pourquoi un test et pas import-linter : l'outil (comme grimp, son moteur)
# exige des PAQUETS, or src/ est délibérément plat pendant la bêta — le
# passage à un vrai paquet Python est un chantier GA assumé (pyproject.toml,
# docs/BETA.md). Plutôt que de tordre l'arborescence pour un outil, la même
# garantie est obtenue en 60 lignes de stdlib, et elle tourne dans la suite
# existante au lieu d'une étape de CI séparée.
#
# Les imports DANS les fonctions comptent autant que ceux en tête de
# fichier : c'est précisément là que les dépendances interdites se cachent.
import ast
import os

SRC = os.path.join(os.path.dirname(__file__), "..", "src")

# Les modules du projet (le package generator compte pour un seul nœud :
# son découpage interne est une affaire de couches, pas de frontières).
MODULES = sorted(
    [f[:-3] for f in os.listdir(SRC) if f.endswith(".py") and f != "main.py"]
    + ["generator"])


def _imports_du_projet(chemin):
    """Tous les modules du projet importés par un fichier, où que l'import
    se trouve — en tête, dans une fonction, dans une méthode."""
    with open(chemin, encoding="utf-8") as fh:
        arbre = ast.parse(fh.read(), filename=chemin)
    trouves = set()
    for noeud in ast.walk(arbre):
        if isinstance(noeud, ast.Import):
            for alias in noeud.names:
                trouves.add(alias.name.split(".")[0])
        elif isinstance(noeud, ast.ImportFrom):
            if noeud.level:            # import relatif : reste dans generator
                continue
            if noeud.module:
                trouves.add(noeud.module.split(".")[0])
    return {m for m in trouves if m in MODULES}


def _depend_de(module):
    """Le graphe de dépendance d'un module du projet, generator compris."""
    dossier = os.path.join(SRC, "generator")
    if module == "generator":
        vus = set()
        for nom in os.listdir(dossier):
            if nom.endswith(".py"):
                vus |= _imports_du_projet(os.path.join(dossier, nom))
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
