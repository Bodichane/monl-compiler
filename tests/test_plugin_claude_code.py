"""Le plugin Claude Code ne dérive pas en silence (point 198).

Le plugin vit dans `plugin/`, en fichiers ORDINAIRES : le répertoire
d'Anthropic refuse un lien symbolique dans ce qu'un plugin charge. Ses
compétences y vivent pour de vrai ; les exemples et la grammaire, qui restent
à leur place dans le dépôt, y sont COPIÉS — et une copie dérive, d'où le
témoin d'identité à l'octet. Ce qui peut encore casser sans bruit : une
version qui ne suit plus le paquet, une compétence qui épingle une version
jamais publiée, un chemin cité qui n'existe plus. Chacun est gardé ici, avec
sa non-vacuité.
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
COMPETENCES = sorted((PLUGIN / "skills").glob("*/SKILL.md"))
# Copie dans le plugin -> original dans le dépôt.
COPIES = {
    PLUGIN / "reference" / "grammaire.py": RACINE / "src" / "monl" / "parser" / "grammaire.py",
    PLUGIN / "reference" / "exemples" / "README.md": RACINE / "exemples" / "README.md",
    **{PLUGIN / "reference" / "exemples" / p.name: p
       for p in sorted((RACINE / "exemples").glob("*.ml"))},
    **{PLUGIN / "reference" / "exemples" / "assets" / p.relative_to(RACINE / "exemples" / "assets"): p
       for p in sorted((RACINE / "exemples" / "assets").rglob("*")) if p.is_file()},
}


def test_le_plugin_suit_la_version_du_paquet():
    assert Version(MANIFESTE["version"]) == VERSION_PAQUET == Version(monl.__version__)


def test_chaque_version_epinglee_par_le_plugin_est_celle_du_paquet():
    textes = [*COMPETENCES, PLUGIN / "README.md"]
    epinglees = [Version(v) for chemin in textes
                 for v in re.findall(r"monl-compiler==([0-9][^\s`\"']*)",
                                     chemin.read_text(encoding="utf-8"))]
    # Sans épinglage trouvé, la règle ne regarderait rien.
    assert len(epinglees) >= 2, "versions épinglées introuvables"
    assert set(epinglees) == {VERSION_PAQUET}, epinglees


def test_le_catalogue_designe_le_plugin_sous_le_meme_nom():
    entrees = CATALOGUE["plugins"]
    assert [e["name"] for e in entrees] == [MANIFESTE["name"]]
    source = (RACINE / entrees[0]["source"]).resolve()
    assert source == PLUGIN.resolve()
    assert (source / ".claude-plugin" / "plugin.json").is_file()


def test_le_plugin_ne_contient_aucun_lien_symbolique():
    fichiers = list(PLUGIN.rglob("*"))
    assert len(fichiers) >= 20, fichiers
    liens = [str(p.relative_to(PLUGIN)) for p in fichiers if p.is_symlink()]
    assert not liens, f"le répertoire d'Anthropic refuse un lien : {liens}"


def test_les_copies_du_plugin_sont_identiques_a_leur_original():
    assert len(COPIES) >= 15, COPIES
    assert sum(p.parent.name == "assets" for p in COPIES) >= 8, "assets introuvables"
    divergentes = [str(copie.relative_to(RACINE)) for copie, original in COPIES.items()
                   if not copie.is_file() or copie.read_bytes() != original.read_bytes()]
    assert not divergentes, (
        "copies absentes ou divergentes : " + ", ".join(divergentes)
        + " — recopier l'original (exemples/, src/monl/parser/grammaire.py)")


def test_l_icone_du_plugin_est_celle_de_la_plateforme():
    # Une seule source pour la marque : le favicon de la plateforme (pastille
    # sombre, signe crème — lisible hors de toute page, point 157), agrandi à
    # 256 px parce que le répertoire demande un carré d'au moins 128 px.
    from monl_platform.theme import FAVICON

    icone = (PLUGIN / ".claude-plugin" / "icon.svg").read_text(encoding="utf-8").strip()
    assert 'width="256" height="256"' in icone
    assert icone == FAVICON.replace("<svg ", '<svg width="256" height="256" ', 1)


def test_le_readme_du_plugin_suffit_au_repertoire():
    texte = (PLUGIN / "README.md").read_text(encoding="utf-8")
    sans_code = re.sub(r"```.*?```", "", texte, flags=re.DOTALL)
    # Seuil du portail : 40 mots hors blocs de code, sinon la soumission bloque.
    assert len(sans_code.split()) >= 40


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
        trouves = list(PLUGIN.glob(cite)) if "*" in cite else [PLUGIN / cite]
        assert trouves and all(t.exists() for t in trouves), f"{competence} : {cite}"


def test_chaque_verbe_cite_par_la_competence_d_entree_existe():
    from monl.cli.dispatch import build_parser

    sous = next(a for a in build_parser()._actions if a.dest == "command")
    texte = (PLUGIN / "skills" / "monl-spec" / "SKILL.md").read_text(encoding="utf-8")
    # Une COMMANDE (début de ligne d'un bloc de code, ou après un accent
    # grave), jamais la prose : « pourquoi monl refuse ma spec » n'en est pas.
    verbes = set(re.findall(r"(?:^|`)monl (\w+)", texte, flags=re.MULTILINE))
    assert {"compile", "run", "diff", "update"} <= verbes, verbes
    assert verbes <= set(sous.choices), verbes - set(sous.choices)
