# The architecture boundaries, made EXECUTABLE (point 63).
#
# CLAUDE.md has stated them for a long time — "the compiler ignores the
# orchestrator", "no dialogue logic in tui.py", "the catalog is data, not
# code". They held because people remembered them. A clause nothing checks is
# not a clause (point 48): this file checks them.
#
# Why this test rather than import-linter: the tool is now usable (src/monl/
# has been a real package since point 65), but it would add a dependency and a
# CI step for what 60 lines of stdlib already achieve — while running in the
# existing suite. It becomes the right choice the day contracts are counted by
# the dozen, not by six.
#
# Imports INSIDE functions count as much as those at the top of the file: that
# is precisely where forbidden dependencies hide.
import ast
import fnmatch
import os
import pathlib
import re
import sys

from monl.parser.grammaire import grammar
from monl.parser.version import LANGUAGE_VERSION

SRC = os.path.join(os.path.dirname(__file__), "..", "src", "monl")


def _grammar_literals():
    """Derives the literal words from the Lark productions, without a copied list.

    Comments and their examples are not productions: removing them before
    extraction prevents a product or illustration name cited in an explanation
    from accidentally becoming a DSL keyword. Like `_terminal` in `coloration.py`,
    this function FAILS if it finds nothing: a mute extractor must not turn the
    guard green.
    """
    productions = "\n".join(
        ligne.split("#", 1)[0] for ligne in grammar.splitlines())
    litteraux = frozenset(
        re.findall(r'"([a-zA-Z][a-zA-Z_]{1,24})"', productions))
    if not litteraux:
        raise AssertionError("la grammaire ne fournit aucun littéral à vérifier")
    return litteraux


def _passages_de_code(texte):
    """Les passages écrits COMME DU CODE : `mot`, et les blocs clôturés.

    Un passage de code ne franchit pas la fin de ligne — `[^`\\n]+` et non
    `[^`]+` : une expression trop large apparie deux backticks de lignes
    différentes et rend un texte qui n'a jamais existé. Mesuré en l'écrivant :
    la version large déclarait `ownedBy` et `sumOf` absents de la mémoire alors
    qu'ils y sont, tous les deux, dans un passage de code.
    """
    return re.findall(r"`([^`\n]+)`", texte) + re.findall(
        r"```.*?```", texte, flags=re.S)


def _written_as_code(texte, mot):
    """The word must be written as a KEYWORD, not met in a sentence.

    It is the only difference that makes the guard useful, and it is MEASURED on
    the real drift fixed here: looking for the word anywhere catches 5 out of 11,
    requiring it in a code passage catches 6 — and on the corrected memory, the
    strict rule wrongly requests nothing.
    """
    motif = rf"(?<![A-Za-z0-9_]){re.escape(mot)}(?![A-Za-z0-9_])"
    return any(re.search(motif, passage) for passage in _passages_de_code(texte))

# The project's modules. A PACKAGE counts as a single node: its internal split
# is a matter of layers, not boundaries.
#
# The list is READ FROM DISK, never written by hand. It named `generator`
# hard-coded, and the day `ast_validator` became a package in turn it vanished
# from MODULES without a word — its contract would have stayed in INTERDITS
# looking at nothing. It is the defect this file's header denounces, arriving
# through the list's door rather than relative imports'.
MODULES = sorted(
    [f[:-3] for f in os.listdir(SRC)
     if f.endswith(".py") and f not in ("main.py", "__init__.py")]
    + [d for d in os.listdir(SRC)
       if os.path.isfile(os.path.join(SRC, d, "__init__.py"))])


def _project_imports(chemin, profondeur=0):
    """All the project modules imported by a file, wherever the import is — at
    the top, in a function, in a method.

    TRAP (point 65): since the move to a package, internal dependencies are
    written RELATIVE (`from .parser import …`). Ignoring them, as the first
    version did, would have made this test mute overnight — it would have kept
    passing while looking at nothing. `profondeur` says at which level of the
    package the file lives: a `from .x` in monl/ designates a top-level module,
    the same written in monl/generator/ designates a neighbor in the subpackage."""
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
                # Walk up to the package root: it is a top-level module. `from
                # . import generator` counts too, through the imported names.
                if noeud.module:
                    trouves.add(noeud.module.split(".")[0])
                else:
                    trouves.update(a.name for a in noeud.names)
    return {m for m in trouves if m in MODULES}


def _depend_de(module):
    """The dependency graph of a project module, its PACKAGES included.

    A package's graph is the union of its modules', minus itself: a submodule
    importing its neighbor (`from .socle import …`) crosses no boundary, and
    `profondeur=1` precisely makes the `..` go up to the first level."""
    dossier = os.path.join(SRC, module)
    if os.path.isdir(dossier):
        vus = set()
        for nom in sorted(os.listdir(dossier)):
            if nom.endswith(".py"):
                vus |= _project_imports(os.path.join(dossier, nom), profondeur=1)
        return vus - {module}
    return _project_imports(os.path.join(SRC, module + ".py"))


# ---- The contracts ---------------------------------------------------
# (source, forbidden, why) — the "why" is displayed on failure.
INTERDITS = [
    ("policies", [module for module in MODULES if module not in ("policies", "ir")],
     "les politiques de champs et d'accès dépendent seulement de l'IR"),
    ("planning", [module for module in MODULES if module not in ("planning", "ir")],
     "l'analyse des routes et relations dépend seulement de l'IR, "
     "jamais du générateur ni de ses consommateurs"),
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


def test_the_architecture_boundaries_hold():
    violations = []
    for source, interdits, pourquoi in INTERDITS:
        for cible in _depend_de(source) & set(interdits):
            violations.append(f"{source} → {cible} : {pourquoi}")
    assert not violations, "frontières franchies :\n  " + "\n  ".join(violations)


def test_the_compiler_stays_usable_alone():
    """Concrete consequence of the contracts above: the compilation chain must
    import without pulling anything from the orchestrator."""
    orchestration = {"cli", "dialogue_engine", "frontend_ai", "tui",
                     "app_templates", "smoke_test"}
    for module in ("parser", "ast_validator", "generator"):
        assert not _depend_de(module) & orchestration, module


def test_no_module_imports_itself_in_a_cycle():
    """A direct cycle (A imports B which imports A) is tolerated nowhere except
    between cli and frontend_ai, where it is known and documented."""
    connu = {("cli", "frontend_ai"), ("frontend_ai", "cli")}
    cycles = set()
    graphe = {m: _depend_de(m) for m in MODULES}
    for source, cibles in graphe.items():
        for cible in cibles:
            if source in graphe.get(cible, set()):
                cycles.add((source, cible))
    assert cycles <= connu, f"nouveaux cycles d'import : {sorted(cycles - connu)}"


def test_the_graph_really_sees_something():
    """The safeguard's safeguard: a boundary test that no longer detects any
    dependency would always pass, and would say nothing any more. The
    repository's known dependencies must therefore appear."""
    assert {"parser", "generator", "frontend_contract"} <= _depend_de("cli")
    assert {"tui", "app_templates", "parser"} <= _depend_de("dialogue_engine")
    assert "frontend_contract" in _depend_de("smoke_test")


def test_monl_never_imports_monl_platform():
    """The platform depends on the compiler, never the reverse."""
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


def test_each_contract_applies_to_a_module_the_graph_knows():
    """A contract whose SOURCE disappeared from MODULES no longer refuses
    anything.

    It happened: `MODULES` named `generator` hard-coded, and the day
    `ast_validator` became a package it left the list — its contract stayed
    written in INTERDITS, entirely mute. Nothing would have turned red. This
    witness is about the LIST, not the imports: it is the other way an
    architecture test stops looking."""
    inconnus = [source for source, _, _ in INTERDITS if source not in MODULES]
    assert not inconnus, (
        "contrat sans module : " + ", ".join(inconnus)
        + " — MODULES est lu sur le disque, un renommage ou un passage en "
          "paquet a dû casser la correspondance")


def test_the_validator_base_reads_nothing_from_its_package():
    """`ast_validator/socle.py` is the LEAF: that is what makes an import cycle
    impossible in the package.

    Its docstring claims it; without this test the claim would rest on
    discipline alone, and the first `from .core import …` slipped into it would
    break the whole compiler's import — at load time, hence everywhere at once."""
    chemin = os.path.join(SRC, "ast_validator", "socle.py")
    with open(chemin, encoding="utf-8") as fh:
        arbre = ast.parse(fh.read(), filename=chemin)
    voisins = [noeud.module or "."
               for noeud in ast.walk(arbre)
               if isinstance(noeud, ast.ImportFrom) and noeud.level == 1]
    assert not voisins, (
        "le socle lit son propre paquet : " + ", ".join(voisins)
        + " — il doit ne dépendre que de la stdlib et de `..errors`")


def test_no_ruff_exception_targets_a_vanished_file():
    """A `per-file-ignores` exception whose path no longer exists excuses
    nothing — it suggests a rule is still relaxed where it no longer is, and
    nobody notices.

    It happened twice at once: `src/monl/parser.py` and `src/monl/frontend_ai.py`
    became PACKAGES, and their two exceptions kept living in `pyproject.toml`
    applying to nothing. Same family as the architecture contract gone mute: what
    stops looking makes no noise."""
    try:
        import tomllib
    except ModuleNotFoundError:      # 3.10 : `tomllib` n'arrive qu'en 3.11
        import tomli as tomllib      # noqa: I001  (declared in the `dev` extra)

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
# FILE AND FUNCTION SIZE (point 155)
#
# Nine compiler files weighed 700 to 2,800 lines, and two functions exceeded
# 900. Splitting them is only worth something if nothing lets them grow back:
# a rule nothing checks is not a rule (point 48, already this file's header
# argument).
#
# The ceiling applies to `src/`, not `tests/`: a test file is a sequence of
# independent cases read one by one, not a component whose complexity grows
# with length. Splitting it would make it harder to find things, not simpler.
#
# Each exception carries ITS REASON, like ruff's in pyproject.toml. Both are
# DATA: a catalog and a grammar. The ceiling targets complexity, and a literal
# has none — cutting it into two arbitrary halves would make the file harder
# to read, exactly the opposite of the goal.
PLAFOND_FICHIER = 400
PLAFOND_FONCTION = 400
EXCEPTIONS_DE_TAILLE = {
    "monl/app_templates.py":
        "TEMPLATES est un littéral de données : les dix modèles du catalogue, "
        "un par entrée. Le couper séparerait des lignes qui se lisent en table.",
    "monl/parser/grammaire.py":
        "La grammaire Lark est UNE chaîne. La couper en deux ferait deux "
        "moitiés dont aucune n'est une grammaire.",
    "monl_platform/console_script.py":
        "402 de ses 405 lignes vivent dans UNE chaîne : le script JavaScript "
        "servi à la console. Le couper en deux constantes Python recollées à "
        "l'émission ne le rendrait pas plus lisible, et multiplierait les "
        "frontières d'échappement — celles qui ont tué deux pages au point 163.",
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


def test_no_src_file_exceeds_the_ceiling():
    trop = {}
    for rel, chemin in _fichiers_de_src():
        with open(chemin, encoding="utf-8") as fh:
            n = len(fh.read().splitlines())
        if n > PLAFOND_FICHIER and rel not in EXCEPTIONS_DE_TAILLE:
            trop[rel] = n
    assert not trop, (
        f"fichiers au-dessus de {PLAFOND_FICHIER} lignes sans exception "
        f"écrite : {trop}")


def test_no_function_exceeds_the_ceiling():
    """A short file made of two 500-line functions has gained nothing."""
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


def test_each_size_exception_targets_a_file_still_over():
    """An exception that no longer exempts anything must DISAPPEAR.

    The exact counterpart of
    `test_no_ruff_exception_targets_a_vanished_file`: a forgotten exemption ends
    up covering a file one believed held."""
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


# ---- Cyclomatic complexity ---------------------------------------------
#
# Ruff usefully measures complexity, but this safeguard must stay runnable
# with the project's minimal suite: it therefore counts its AST itself. The
# ceiling is deliberately 15, the threshold above which the workstream began.
# The exceptions are explicit and carry the observed value; they are
# ratchets, not comfort ceilings.
PLAFOND_COMPLEXITE = 15
EXCEPTIONS_DE_COMPLEXITE = {
}


class _CompteurComplexite(ast.NodeVisitor):
    """Local, deterministic counter, distinct from Ruff's definition.

    The score starts at 1 and adds a point for each ``if`` (hence each ``elif``,
    represented by an ``if`` in the ``orelse``), ``for``/``async for``,
    ``while``, ``except`` handler, ``IfExp`` ternary, boolean ``and``/``or``
    node, comprehension generator and comprehension ``if`` filter, as well as for
    each ``assert``. Nested functions, lambdas and classes are deliberately
    ignored while visiting their parent; ``ast.walk`` measures them separately. A
    comprehension with several generators therefore counts each generator and
    each filter.
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


def test_no_src_function_exceeds_the_complexity_ceiling():
    """The common ceiling also applies to new functions."""
    violations = _violations_de_complexite(
        _fonctions_de_src(), EXCEPTIONS_DE_COMPLEXITE)
    assert not violations, (
        f"fonctions au-dessus de {PLAFOND_COMPLEXITE} sans cliquet valide : "
        f"{violations}")


def test_each_complexity_exception_is_still_needed():
    """An exception back under the ceiling must be removed.

    THIS is where the ratchet lives, in strict equality with the recorded score —
    not in a separate test. A second test replaying `_violations_de_complexite`
    existed under the name "the ratchet forbids any regression": measured, it
    NEVER turned red alone (counter-proof done on the three ways of breaking the
    safeguard), it repeated the ceiling assertion word for word. A witness
    announcing a guarantee carried elsewhere ends up making it look guarded twice
    — point 167bis.
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


def test_the_complexity_counter_counts_the_announced_constructs():
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


def test_the_safeguard_turns_red_for_a_too_complex_function():
    source = "def trop_complexe(value):\n" + "".join(
        "    if value:\n        pass\n" for _ in range(16))
    arbre = ast.parse(source, filename="synthetic.py")
    fonctions = [(f"synthetic.py:{n.name}", _complexite_fonction(n))
                 for n in ast.walk(arbre)
                 if isinstance(n, ast.FunctionDef)]
    assert _violations_de_complexite(fonctions, {}) == {
        "synthetic.py:trop_complexe": {"mesure": 17, "limite": 15}}


def test_the_safeguard_turns_red_when_a_needed_exception_is_removed():
    """The ceiling must bite, even once the exception table is empty.

    Removing an existing exception was the counter-proof while there were
    any. With an empty table that step has nothing left to remove, so a
    synthetic function one decision above the ceiling goes through the REAL
    counter and the REAL guard: it must be reported, and be the only one —
    otherwise an empty table would only prove that nothing is measured."""
    fonctions = list(_fonctions_de_src())
    assert fonctions, "no function read from src/: the guard would measure nothing"
    exceptions = dict(EXCEPTIONS_DE_COMPLEXITE)
    if exceptions:
        retiree = next(iter(exceptions))
        del exceptions[retiree]
        violations = _violations_de_complexite(fonctions, exceptions)
        assert retiree in violations
    source = "def trop_complexe(x):\n" + "".join(
        f"    if x == {i}:\n        x += 1\n" for i in range(PLAFOND_COMPLEXITE))
    score = _complexite_fonction(ast.parse(source).body[0])
    assert score == PLAFOND_COMPLEXITE + 1
    violations = _violations_de_complexite(
        fonctions + [("synthetique:trop_complexe", score)], EXCEPTIONS_DE_COMPLEXITE)
    assert set(violations) == {"synthetique:trop_complexe"}


def test_no_test_skips_for_lack_of_a_library():
    """`pytest.importorskip` returns green without checking anything.

    Found by CI, not locally: Pillow was only declared in the `ai` extra, which CI
    does not install. The JPEG re-encoding test therefore SKIPPED on every run —
    and the only reason we found out is that a neighboring test failed outright.
    The skip would never have spoken.

    It is point 140 through another door: a skip does not say "nothing to check
    here", it says "I did not check". A library a test needs is DECLARED in the
    `dev` extra — the one CI installs — instead of being worked around.

    Conditional `pytest.skip` stays allowed: it keeps an integration one can
    legitimately not require (a real PostgreSQL), and it NAMES it. An installable
    Python library, no.
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


def test_every_platform_static_file_is_shipped_in_the_package():
    """A file not declared in `package-data` is NOT installed.

    Measured, not assumed: `package-data` only declared `static/*.png`, so
    `favicon.ico` stayed in the working tree and never in the package. But
    `theme.py` reads it AT MODULE LEVEL (to derive the cache fingerprint): from a
    normal installation, `import monl_platform.app` raised `FileNotFoundError` —
    **the whole platform was undeployable**.

    Why CI did not see it: its "the package installs and the command answers"
    safeguard runs after a `pip install -e .`, so modules point to the source tree
    where the file IS. Editable installation hides exactly this class of defect.

    This test reads the DISK and not a hand-written list: a `.svg` or `.woff2`
    added tomorrow would silently reopen the same hole.
    """
    try:
        import tomllib
    except ModuleNotFoundError:      # 3.10 : `tomllib` n'arrive qu'en 3.11
        import tomli as tomllib      # noqa: I001  (declared in the `dev` extra)

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


def test_no_test_mounts_the_platform_with_testclient():
    """`starlette.testclient` requires `httpx2`, which CI does not install.

    The decision has long been WRITTEN, at the top of `tests/test_platform_web.py`:
    that file mounted the platform with `TestClient`, the suite stopped at
    COLLECTION on the three Python versions, and everything was redone against an
    ephemeral uvicorn.

    Nothing guarded it. A new test therefore reintroduced `TestClient` and turned
    CI red exactly the same way — green locally with a mere deprecation warning,
    broken where it counts. **A decision written but not guarded is relearned by
    breaking it**; it is point 152 ("a guarantee that stops applying makes no
    noise") applied to a prose instruction.

    The remedy is not to add `httpx2`: an in-process client crosses neither the
    real ASGI layer nor server startup.
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


def _ouvertures_sqlite_nues(source, nom):
    """Lines where `sqlite3.connect(...)` DIRECTLY serves as a `with` manager.

    This `with` commits or rolls back the transaction, it does not CLOSE the
    connection (points 141 and 185). Read by AST: a comment, a docstring or a
    string emitted in generated code that cite the trap do not count.
    """
    lignes = []
    for noeud in ast.walk(ast.parse(source, filename=nom)):
        if not isinstance(noeud, (ast.With, ast.AsyncWith)):
            continue
        for item in noeud.items:
            appel = item.context_expr
            if (isinstance(appel, ast.Call)
                    and isinstance(appel.func, ast.Attribute)
                    and appel.func.attr == "connect"
                    and isinstance(appel.func.value, ast.Name)
                    and appel.func.value.id == "sqlite3"):
                lignes.append(noeud.lineno)
    return lignes


def test_no_sqlite_connection_is_opened_by_a_bare_with():
    """`with sqlite3.connect(...)` leaves the connection to the garbage collector.

    72 `ResourceWarning: unclosed database` under Python 3.14 came from this one
    pattern, 33 times in `tests/`; the shipped code had already left it
    (`identity_database`, `backup_healthcheck`, `store_core`). `pyproject.toml`'s
    `error::ResourceWarning` filter catches a leak WHEN a test produces it; this
    guard refuses the pattern before it is used. Use
    `tests.support.sqlite.base_sqlite` (or `try/finally` + `close`).
    """
    racine = pathlib.Path(__file__).resolve().parent.parent
    fautifs = []
    for arbre in ("tests", "src"):
        for chemin in sorted((racine / arbre).rglob("*.py")):
            source = chemin.read_text(encoding="utf-8")
            fautifs += [f"{chemin.relative_to(racine)}:{ligne}"
                        for ligne in _ouvertures_sqlite_nues(source, str(chemin))]
    assert not fautifs, (
        "`with sqlite3.connect(...)` valide sans fermer — utiliser "
        "tests.support.sqlite.base_sqlite : " + ", ".join(fautifs))


OUVERTURES_A_FERMER = {"open", "io.open", "codecs.open", "urllib.request.urlopen", "urlopen"}


def _ouvertures_hors_with(source, nom):
    """Lines where a file or HTTP response is opened OUTSIDE a `with`.

    `open(p).read()` and `urlopen(u).read()` close whenever the garbage collector
    feels like it: five `frontend_ai` reads and eight server waits in the tests
    did so until `error::ResourceWarning` made them visible. Read by AST: only the
    `with opening(...) as x:` form is allowed.
    """
    arbre = ast.parse(source, filename=nom)
    gerees = {id(item.context_expr) for noeud in ast.walk(arbre)
              if isinstance(noeud, (ast.With, ast.AsyncWith)) for item in noeud.items}
    return sorted(noeud.lineno for noeud in ast.walk(arbre)
                  if isinstance(noeud, ast.Call) and id(noeud) not in gerees
                  and ast.unparse(noeud.func) in OUVERTURES_A_FERMER)


def test_no_file_or_http_response_is_opened_outside_a_with():
    """The `error::ResourceWarning` filter only catches a leak if a test RUNS the
    leaking path; this guard refuses the pattern everywhere, even in a branch no
    test goes through."""
    racine = pathlib.Path(__file__).resolve().parent.parent
    fautifs = []
    for arbre in ("tests", "src"):
        for chemin in sorted((racine / arbre).rglob("*.py")):
            source = chemin.read_text(encoding="utf-8")
            fautifs += [f"{chemin.relative_to(racine)}:{ligne}"
                        for ligne in _ouvertures_hors_with(source, str(chemin))]
    assert not fautifs, (
        "ouverture hors `with` : le fichier ou la réponse ne sera fermé que par "
        "le ramasse-miettes — " + ", ".join(fautifs))


def test_the_outside_with_opening_extractor_sees_the_pattern():
    """Counter-proof of the guard above (point 161)."""
    fautif = (
        "import urllib.request\n"
        "texte = open('a').read()\n"
        "urllib.request.urlopen('http://x').read()\n"
        "f = open('b')\n"
    )
    assert _ouvertures_hors_with(fautif, "fautif.py") == [2, 3, 4]
    sain = (
        "import urllib.request\n"
        "with open('a') as f, urllib.request.urlopen('http://x') as r:\n"
        "    f.read(); r.read()\n"
        "# open('a').read() dans un commentaire ne compte pas\n"
    )
    assert _ouvertures_hors_with(sain, "sain.py") == []


def test_the_bare_connection_extractor_sees_the_pattern():
    """Counter-proof: without it, an extractor that never finds anything would
    turn the guard green without looking at anything (point 161)."""
    fautif = (
        "import sqlite3\n"
        "def f(p):\n"
        "    with sqlite3.connect(p) as db:\n"
        "        db.execute('select 1')\n"
        "    with open(p) as a, sqlite3.connect(p) as b:\n"
        "        pass\n"
    )
    assert _ouvertures_sqlite_nues(fautif, "fautif.py") == [3, 5]
    sain = (
        "import sqlite3\n"
        "from tests.support.sqlite import base_sqlite\n"
        "# with sqlite3.connect(p) as db:  -- un commentaire ne compte pas\n"
        "CODE = 'with sqlite3.connect(p) as db:'\n"
        "def f(p):\n"
        "    with base_sqlite(p) as db:\n"
        "        db.execute('select 1')\n"
    )
    assert _ouvertures_sqlite_nues(sain, "sain.py") == []


# The repository trees the tests exercise. `outils/` is among them because
# Pillow only enters through `outils/fabriquer_images.py`, and `scripts/`
# because the publication safeguard lives there (point 168).
ARBRES_EXERCES = ("tests", "outils", "scripts")


def _normalise_distribution(nom):
    """PEP 503: `PyYAML`, `pyyaml` and `Py_Yaml` are the SAME distribution."""
    return re.sub(r"[-_.]+", "-", nom).lower()


def _module_distributions(module):
    """Returns the distributions providing *module*, or None if unknown.

    None does not mean "none" but "not installed here, hence not measurable": the
    import name → distribution name mapping is carried by the environment, not by
    the code.
    """
    from importlib.metadata import packages_distributions

    fournisseurs = packages_distributions().get(module)
    if fournisseurs is None:
        return None
    return {_normalise_distribution(nom) for nom in fournisseurs}


def _repository_modules():
    """Everything living in the tree: neither to declare nor to install."""
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


def _third_party_modules_imported_by_tests():
    """The THIRD-PARTY modules imported under `tests/`, by AST.

    By AST and not `grep`: a multi-line import or attribute access escapes text
    (point 153). Modules that entered the standard library AFTER the minimum
    version are discarded — on Python 3.10, `tomllib` is not in
    `sys.stdlib_module_names` and would be taken for a third-party dependency.
    """
    interne = _repository_modules()
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


def test_the_libraries_tests_need_are_in_dev():
    """The previous test's counterpart: the declaration, not only the absence of
    workaround.

    Without it, removing Pillow from the `dev` extra would make CI fail without a
    test explaining WHY — and the temptation would be to put a skip back.

    **The list of libraries is DERIVED, never written here.** It used to be, and
    it named `pytest`, `requests` and `pillow` — three of the nine the tests
    really imported. A bound expressed as a list of names stops bounding as soon
    as a name is added, without making noise: it is the defect of point 162bis
    (`OUTILS_QUI_COMPILENT`), point 164 (the `/mcp` page) and point 167 (the
    Python versions). Adding `packaging` and `PyYAML` at point 168 would have
    woken nothing.

    **Its limit is STATED**: mapping a module to its distribution (`PIL` →
    `pillow`, `yaml` → `PyYAML`) requires the module to be INSTALLED, since the
    environment carries that mapping. What cannot be mapped is not judged — it is
    NAMED in the message, rather than guessing a distribution name and refusing a
    correct declaration (same arbitration as at point 83: without `base_dir`, the
    validator stays silent). On CI the question does not arise: a module no
    installation provides makes collection of the importing file fail.
    """
    try:
        import tomllib
    except ModuleNotFoundError:      # 3.10 : `tomllib` n'arrive qu'en 3.11
        import tomli as tomllib      # noqa: I001  (declared in the `dev` extra)

    racine = os.path.join(os.path.dirname(__file__), "..")
    with open(os.path.join(racine, "pyproject.toml"), "rb") as fh:
        config = tomllib.load(fh)

    # What `pip install -e ".[dev,postgres]"` — ci.yml's exact line — really
    # installs. Not only `dev`: a library declared in the package's
    # dependencies is there too.
    requis = list(config["project"].get("dependencies", []))
    for extra in ("dev", "postgres"):
        requis += config["project"]["optional-dependencies"].get(extra, [])
    installees = {_normalise_distribution(re.split(r"[<>=!;\[ ]", ligne.strip())[0])
                  for ligne in requis}

    manquantes, non_mesurables = [], []
    for module, fichiers in sorted(_third_party_modules_imported_by_tests().items()):
        distributions = _module_distributions(module)
        if distributions is None:
            non_mesurables.append(module)      # not installed: see docstring
        elif not (distributions & installees):
            manquantes.append(f"{module} (distribution {sorted(distributions)}, "
                              f"importé par {sorted(fichiers)[0]})")

    assert not manquantes, (
        f"la CI installe `.[dev,postgres]` et n'y trouvera pas : {manquantes}. "
        f"Les tests qui en dépendent échoueront à la collecte, ou sauteront — "
        f"et un saut ne dit pas « rien à vérifier », il dit « je n'ai pas "
        f"vérifié » (point 140). Non mesurables ici : {non_mesurables or 'aucun'}")


# Modules that entered the standard library AFTER the minimum version declared
# by `requires-python` (3.10). Importing them AT THE TOP of a file makes
# COLLECTION fail on the oldest version CI covers — hence the whole file, not
# only the concerned test.
APRES_LA_VERSION_MINIMALE = {
    "tomllib": "3.11",     # lecture de pyproject.toml
    "asyncio.taskgroups": "3.11",
}


def test_no_test_imports_at_top_a_module_missing_from_the_minimum_version():
    """A top-level import kills COLLECTION, not only its test.

    `import tomllib` placed at the top of `test_architecture.py` turned CI red on
    Python 3.10 (`ModuleNotFoundError`) while the suite was green locally: this
    machine runs 3.14, where the module exists. The file ALREADY carried the
    correct fallback twice — a `try/except ModuleNotFoundError` in the function —
    and the top-level import bypassed it.

    The fallback must stay INSIDE the function: there, only the test needing the
    module fails if `tomli` is missing, and it says so. At the top, the whole file
    disappears from collection, which looks like "nothing to check" (point 140).
    """
    dossier = os.path.dirname(os.path.abspath(__file__))
    fichiers = sorted(nom for nom in os.listdir(dossier)
                      if nom.startswith("test_") and nom.endswith(".py"))
    assert fichiers, "aucun fichier de test lu : ce témoin ne garde plus rien"

    fautes = []
    for nom_fichier in fichiers:
        with open(os.path.join(dossier, nom_fichier), encoding="utf-8") as fh:
            arbre = ast.parse(fh.read())
        for noeud in arbre.body:            # the module BODY, not the functions
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


def test_the_keyword_extractor_does_not_look_at_nothing():
    """The safeguard's witness: the extractor finds real productions.

    Testing only that the extractor exists would allow a function always
    returning ``frozenset()``. These three forms cover a block, a rule and a type
    added late: they must all come from the imported grammar, not from a local
    keyword list.
    """
    mots = _grammar_literals()
    assert len(mots) >= 50
    assert {"app", "rule", "Upload"} <= mots


def _paragraphe_de_reference(memoire):
    """The `CLAUDE.md` paragraph that LISTS the DSL keywords."""
    debut = memoire.index("**DSL keyword reference.**")
    fin = memoire.index("none is a standalone brick.", debut)
    return memoire[debut:fin]


def test_the_keyword_reference_names_nothing_that_vanished():
    """The other direction: the memory must not announce a removed keyword.

    The reference paragraph is a HAND-WRITTEN list — the exact form points 164,
    167 and 169 saw stop bounding three times. It cannot be derived, `CLAUDE.md`
    being a document; it can however be CONFRONTED, as point 169 confronts the
    trusted publisher table with `[project.urls]`. A brick removed from the
    grammar therefore fails here, instead of being promised forever.
    """
    racine = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(racine, "CLAUDE.md"), encoding="utf-8") as fh:
        reference = _paragraphe_de_reference(fh.read())
    reels = _grammar_literals()
    annonces = set(re.findall(r"`([a-zA-Z][a-zA-Z_]{1,24})`", reference))
    fantomes = sorted(annonces - reels)
    assert not fantomes, (
        "la référence de CLAUDE.md annonce des mots-clés que la grammaire "
        "n'implémente pas : " + ", ".join(fantomes))


def test_every_grammar_keyword_is_named_in_claude():
    """The memory must not lose a word when the grammar gains one.

    The expected list is computed from the Lark productions. The test therefore
    does not know future bricks; it only copies the linking exceptions, each
    justified and guarded by the neighboring test.
    """
    racine = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(racine, "CLAUDE.md"), encoding="utf-8") as fh:
        memoire = fh.read()
    absents = sorted(
        mot for mot in _grammar_literals()
        if not _written_as_code(memoire, mot))
    assert not absents, (
        "mots-clés de la grammaire absents de CLAUDE.md : "
        + ", ".join(absents))


def test_each_python_test_exercises_an_assertion():
    """A collected test must be able to turn red on its own scenario."""
    racine = pathlib.Path(__file__).resolve().parent
    fonctions = []
    sans_temoin = []
    exemptions_servies = set()
    exemptions = {
        "test_app_templates.py:test_chaque_modele_compile_tout_refuse":
            "la validation complète doit accepter chaque spec tout-refus; toute erreur échoue le test",
        "test_beta3_regressions.py:test_login_does_not_reveal_whether_the_account_exists":
            "ses assertions vivent dans le helper _mesurer_canal_temporel, appelé dans un try/finally qui arrête le serveur",
        "test_cli_commandes.py:test_run_check_passes_on_a_healthy_project":
            "le contrat est précisément que cmd_run termine normalement; une erreur lève SystemExit et échoue",
        "test_platform_couverture.py:test_asgi_routes_cover_responses_and_effects":
            "_dialogue fait des assertions ASGI détaillées pendant son exécution",
        "test_publication.py:test_the_matching_tag_is_accepted":
            "validate_tag_version est un validateur pur qui lève sur toute version refusée",
        "test_publication.py:test_both_spellings_of_one_version_are_accepted":
            "les deux appels au validateur pur doivent terminer sans exception",
    }
    for chemin in sorted(racine.glob("test_*.py")):
        arbre = ast.parse(chemin.read_text(encoding="utf-8"), filename=str(chemin))
        for fonction in (n for n in ast.walk(arbre)
                         if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                         and n.name.startswith("test_")):
            fonctions.append(f"{chemin.name}:{fonction.lineno}")
            noeuds = list(ast.walk(fonction))
            assertion = any(isinstance(n, ast.Assert) for n in noeuds)
            erreur_attendue = any(
                isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                and n.func.attr == "raises" and isinstance(n.func.value, ast.Name)
                and n.func.value.id == "pytest" for n in noeuds)
            helper = any(
                isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                and "assert" in n.func.id.lower() for n in noeuds)
            identifiant = f"{chemin.name}:{fonction.name}"
            if not (assertion or erreur_attendue or helper):
                if identifiant in exemptions:
                    exemptions_servies.add(identifiant)
                else:
                    sans_temoin.append(f"{identifiant}:{fonction.lineno}")
    assert len(fonctions) >= 1000, f"extracteur de tests trop pauvre : {len(fonctions)}"
    assert not sans_temoin, "tests sans assertion : " + ", ".join(sans_temoin)
    # An exemption no longer used (test gone, or now carrying an assertion)
    # makes the test fail: otherwise it would silently excuse the next test
    # taking that name (point 155).
    perimees = sorted(set(exemptions) - exemptions_servies)
    assert not perimees, "exemptions qui ne servent plus : " + ", ".join(perimees)


def test_language_compatibility_ratchet():
    """Keep historical witnesses; additions must be declared in the current one."""
    current = _grammar_literals()
    witnesses = sorted(pathlib.Path(__file__).parent.glob("grammaire_v*.txt"))
    assert witnesses, "no language compatibility witnesses"
    versions = set()
    for witness in witnesses:
        version = int(witness.stem.removeprefix("grammaire_v"))
        versions.add(version)
        declared = frozenset(witness.read_text(encoding="utf-8").splitlines())
        assert declared, f"empty witness: {witness}"
        assert version <= LANGUAGE_VERSION, f"future witness: {witness}"
        if version == LANGUAGE_VERSION:
            assert not declared - current, (
                "language break requires LANGUAGE_VERSION increment: "
                + ", ".join(sorted(declared - current)))
            assert not current - declared, (
                "undeclared language additions: "
                + ", ".join(sorted(current - declared)))
    assert LANGUAGE_VERSION in versions, "current language witness missing"


def test_language_extractor_refuses_empty_grammar(monkeypatch):
    import pytest

    monkeypatch.setitem(globals(), "grammar", "TYPE: /[A-Z]+/")
    with pytest.raises(AssertionError, match="aucun littéral"):
        _grammar_literals()
