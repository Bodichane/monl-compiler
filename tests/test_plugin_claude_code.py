"""Le plugin Claude Code ne dérive pas en silence (point 198).

Le plugin vit dans `plugin/` et ne contient que des liens vers ce qui sert
(`skills/`, `exemples/`, la grammaire) : Claude Code les remplace par leur
contenu en copiant depuis un marketplace git. Ce qui peut casser sans bruit :
une version qui ne suit plus le paquet, une compétence qui épingle une version
jamais publiée, un lien vers un fichier déplacé, un chemin cité qui n'existe
plus. Chacun est gardé ici, avec sa non-vacuité.
"""
import json
import pathlib
import re

from packaging.version import Version

import monl

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib

RACINE = pathlib.Path(__file__).resolve().parents[1]
PLUGIN = RACINE / "plugin"
MANIFESTE = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
CATALOGUE = json.loads((RACINE / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))
VERSION_PAQUET = Version(tomllib.loads(
    (RACINE / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"])
COMPETENCES = sorted((RACINE / "skills").glob("*/SKILL.md"))


def test_le_plugin_suit_la_version_du_paquet():
    assert Version(MANIFESTE["version"]) == VERSION_PAQUET == Version(monl.__version__)


def test_chaque_version_epinglee_par_une_competence_est_celle_du_paquet():
    epinglees = [Version(v) for chemin in COMPETENCES
                 for v in re.findall(r"monl-compiler==([0-9][^\s`\"']*)",
                                     chemin.read_text(encoding="utf-8"))]
    # Sans épinglage trouvé, la règle ne regarderait rien.
    assert epinglees, "aucune version épinglée trouvée dans les compétences"
    assert set(epinglees) == {VERSION_PAQUET}, epinglees


def test_le_catalogue_designe_le_plugin_sous_le_meme_nom():
    entrees = CATALOGUE["plugins"]
    assert [e["name"] for e in entrees] == [MANIFESTE["name"]]
    source = (RACINE / entrees[0]["source"]).resolve()
    assert source == PLUGIN.resolve()
    assert (source / ".claude-plugin" / "plugin.json").is_file()


def test_les_liens_du_plugin_menent_dans_le_depot():
    liens = [p for p in PLUGIN.iterdir() if p.is_symlink()]
    assert len(liens) >= 3, liens
    for lien in liens:
        cible = lien.resolve()
        assert cible.exists(), f"{lien.name} -> {cible} n'existe pas"
        assert RACINE.resolve() in cible.parents, f"{lien.name} sort du dépôt : {cible}"


def test_chaque_competence_est_nommee_comme_son_dossier():
    assert len(COMPETENCES) >= 6, COMPETENCES
    for chemin in COMPETENCES:
        entete = chemin.read_text(encoding="utf-8").split("---")[1]
        champs = dict(ligne.split(":", 1) for ligne in entete.strip().splitlines()
                      if ":" in ligne and not ligne.startswith(" "))
        assert champs["name"].strip() == chemin.parent.name, chemin
        assert champs["description"].strip(), chemin


def test_chaque_chemin_du_plugin_cite_par_une_competence_existe():
    cites = [(chemin.parent.name, cite) for chemin in COMPETENCES
             for cite in re.findall(r"\$\{CLAUDE_PLUGIN_ROOT\}/([^\s`)]+)",
                                    chemin.read_text(encoding="utf-8"))]
    assert cites, "aucun chemin ${CLAUDE_PLUGIN_ROOT} trouvé : la règle ne regarderait rien"
    for competence, cite in cites:
        motif = cite.replace("*", "")
        trouves = list(PLUGIN.glob(cite)) if "*" in cite else [PLUGIN / motif]
        assert trouves and all(t.exists() for t in trouves), f"{competence} : {cite}"


def test_chaque_verbe_cite_par_la_competence_d_entree_existe():
    from monl.cli.dispatch import build_parser

    sous = next(a for a in build_parser()._actions if a.dest == "command")
    texte = (RACINE / "skills" / "monl-spec" / "SKILL.md").read_text(encoding="utf-8")
    # Une COMMANDE (début de ligne d'un bloc de code, ou après un accent
    # grave), jamais la prose : « pourquoi monl refuse ma spec » n'en est pas.
    verbes = set(re.findall(r"(?:^|`)monl (\w+)", texte, flags=re.MULTILINE))
    assert {"compile", "run", "diff", "update"} <= verbes, verbes
    assert verbes <= set(sous.choices), verbes - set(sous.choices)
