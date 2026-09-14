"""Lire `.github/workflows/ci.yml` — source UNIQUE, pour tous les témoins.

Deux fichiers de tests interrogent désormais ce workflow : celui qui exige que
les sauts se voient (point 161) et celui qui exige qu'une barrière de
couverture porte sur toute la suite. Le repliage YAML et la reconnaissance des
chemins sont assez subtils pour qu'en écrire deux versions les fasse diverger
— c'est le point 146, et il vaut aussi pour l'outillage des tests.

Une règle traverse tout ce module : **rien n'y échoue en silence**. Un
extracteur qui rend un ensemble vide rendrait vertes les garanties qui
l'emploient, sans regarder quoi que ce soit (point 161). Toute cible qu'on ne
sait pas résoudre lève donc, plutôt que de disparaître.
"""

import re
from pathlib import Path

RACINE = Path(__file__).resolve().parents[2]
CI = RACINE / ".github" / "workflows" / "ci.yml"
PYPROJECT = RACINE / "pyproject.toml"

# Un élément de liste YAML (« - name: ... ») ou une clé (« run: ... ») ferme
# la commande en cours. « --cov=... » commence aussi par un tiret : c'est le
# tiret SUIVI D'UNE ESPACE qui fait la liste, et la distinction n'est pas
# cosmétique — sans elle, une commande repliée serait coupée en son milieu.
NOUVEL_ELEMENT = re.compile(r"^\s*-\s")
NOUVELLE_CLE = re.compile(r"^\s*[A-Za-z_][\w -]*:(\s|$)")


def _charger_pyproject():
    try:
        import tomllib
    except ModuleNotFoundError:      # 3.10 : `tomllib` n'arrive qu'en 3.11
        import tomli as tomllib      # noqa: I001  (déclaré dans l'extra `dev`)
    with PYPROJECT.open("rb") as fh:
        return tomllib.load(fh)


def addopts_du_projet():
    """Les options que `pyproject.toml` ajoute à toute invocation de pytest."""
    ini = _charger_pyproject()["tool"]["pytest"]["ini_options"]
    return ini["addopts"].split()


def testpaths_du_projet():
    """Ce que pytest collecte quand la commande ne nomme aucun chemin.

    Lu et non recopié : une commande sans cible sélectionne exactement ça, et
    une seconde liste finirait par ne plus dire la même chose que la première.
    """
    ini = _charger_pyproject()["tool"]["pytest"]["ini_options"]
    return list(ini["testpaths"])


def seuil_de_couverture_du_projet():
    """La barrière déclarée par `pyproject.toml`, jamais recopiée ici.

    Le workflow doit tenir AU MOINS cette exigence ; l'inscrire une seconde
    fois dans un test la ferait diverger le jour où on la déplace.
    """
    return _charger_pyproject()["tool"]["coverage"]["report"]["fail_under"]


def _commandes(texte, marqueur):
    """Les commandes du workflow contenant `marqueur`, recollées sur une ligne.

    Le workflow emploie les deux formes : « run: <commande> » sur une ligne,
    et un scalaire replié « run: >- » dont la commande occupe plusieurs lignes
    de MÊME indentation. Une seule mise en œuvre pour tous les marqueurs :
    deux lectures d'un même repliage divergeraient (point 146).
    """
    commandes, courante = [], None
    for ligne in texte.splitlines():
        if not ligne.strip() or ligne.strip().startswith("#"):
            continue
        if courante is not None:
            suite = (not NOUVEL_ELEMENT.match(ligne)
                     and not NOUVELLE_CLE.match(ligne))
            # Un bloc littéral « run: | » porte PLUSIEURS commandes, une par
            # ligne : une ligne qui reporte le marqueur en ouvre une nouvelle
            # au lieu de prolonger la précédente. Sans cette distinction, deux
            # barrières de couverture successives seraient recollées en une
            # seule, et une règle portant sur « chaque commande » n'en verrait
            # qu'une.
            if suite and marqueur not in ligne:
                courante += " " + ligne.strip()
                continue
            commandes.append(courante)
            courante = None
            if suite:
                courante = ligne.strip()
                continue
        if marqueur in ligne:
            courante = ligne.strip()
    if courante is not None:
        commandes.append(courante)
    return commandes


def commandes_pytest(texte):
    """Les invocations pytest du workflow."""
    return _commandes(texte, "python -m pytest")


def commandes_coverage(texte):
    """Les rapports de couverture du workflow — là où vivent les barrières."""
    return _commandes(texte, "coverage report")


def fichiers_de_tests(racine=RACINE):
    """Les fichiers de tests présents sur le DISQUE, jamais une liste écrite.

    C'est tout l'enjeu du point 169 : une liste tenue à la main cesse de
    garder le jour où quelqu'un range un test sous un autre nom.
    """
    dossiers = [racine / chemin for chemin in testpaths_du_projet()]
    trouves = {f.relative_to(racine) for d in dossiers for f in d.rglob("test_*.py")}
    if not trouves:
        raise AssertionError(
            f"aucun fichier de tests trouvé sous {dossiers} : l'extracteur "
            "rendrait vertes des garanties en ne regardant rien.")
    return trouves


def selection_dune_commande(commande, racine=RACINE):
    """Les fichiers de tests qu'une commande pytest sélectionne réellement.

    Les motifs (`tests/test_platform_*.py`) sont développés, un dossier est
    parcouru comme pytest le parcourt, et une commande sans cible retombe sur
    `testpaths`. Une cible qui ne désigne AUCUN fichier existant lève : c'est
    la seule façon de distinguer « cette commande ne sélectionne rien » de
    « je n'ai pas su lire cette commande ».
    """
    jetons = commande.split()
    if "pytest" not in jetons:
        raise AssertionError(f"commande sans `pytest` : {commande!r}")
    cibles = [j for j in jetons[jetons.index("pytest") + 1:] if not j.startswith("-")]
    if not cibles:
        cibles = testpaths_du_projet()

    selection = set()
    for cible in cibles:
        chemins = sorted(racine.glob(cible)) if "*" in cible else [racine / cible]
        atteints = set()
        for chemin in chemins:
            if chemin.is_dir():
                atteints |= {f.relative_to(racine) for f in chemin.rglob("test_*.py")}
            elif chemin.is_file():
                atteints.add(chemin.relative_to(racine))
        if not atteints:
            raise AssertionError(
                f"la cible {cible!r} de la commande {commande!r} ne désigne "
                "aucun fichier existant : l'extracteur ne sait pas la lire, et "
                "l'ignorer ferait passer une commande pour plus large qu'elle "
                "n'est.")
        selection |= atteints
    return selection


def options_de_couverture(commande):
    """Les options `--cov…` portées par une commande."""
    return [j for j in commande.split() if j.startswith("--cov")]
