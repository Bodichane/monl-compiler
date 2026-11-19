"""The Claude Code plugin does not drift silently (point 198).

The plugin lives in `plugin/`, as ORDINARY files: Anthropic's directory
refuses a symbolic link in what a plugin loads. Its skills really live
there; the examples and the grammar, which stay in place in the repository,
are COPIED there — and a copy drifts, hence the byte identity witness. What
can still break silently: a version no longer following the package, a skill
pinning a version never published, a cited path that no longer exists. Each
is guarded here, with its non-emptiness.
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
# Copy in the plugin -> original in the repository.
COPIES = {
    PLUGIN / "reference" / "grammar.py": RACINE / "src" / "monl" / "parser" / "lark_grammar.py",
    PLUGIN / "reference" / "exemples" / "README.md": RACINE / "exemples" / "README.md",
    **{PLUGIN / "reference" / "exemples" / p.name: p
       for p in sorted((RACINE / "exemples").glob("*.ml"))},
    **{PLUGIN / "reference" / "exemples" / "assets" / p.relative_to(RACINE / "exemples" / "assets"): p
       for p in sorted((RACINE / "exemples" / "assets").rglob("*")) if p.is_file()},
}


def test_the_plugin_never_gets_ahead_of_the_package():
    """The plugin pins a PUBLISHED version: Anthropic's directory rereads main,
    and a pin to a version absent from PyPI would break every installation. It
    therefore follows the package one step behind — never ahead — and catches up
    after publishing."""
    assert Version(monl.__version__) == VERSION_PAQUET
    assert Version(MANIFESTE["version"]) <= VERSION_PAQUET


def test_each_version_pinned_by_the_plugin_is_its_manifests():
    textes = [*COMPETENCES, PLUGIN / "README.md"]
    epinglees = [Version(v) for chemin in textes
                 for v in re.findall(r"monl-compiler==([0-9][^\s`\"']*)",
                                     chemin.read_text(encoding="utf-8"))]
    # Without a pin found, the rule would look at nothing.
    assert len(epinglees) >= 2, "pinned versions not found"
    assert set(epinglees) == {Version(MANIFESTE["version"])}, epinglees


def test_the_catalog_names_the_plugin_with_the_same_name():
    entrees = CATALOGUE["plugins"]
    assert [e["name"] for e in entrees] == [MANIFESTE["name"]]
    source = (RACINE / entrees[0]["source"]).resolve()
    assert source == PLUGIN.resolve()
    assert (source / ".claude-plugin" / "plugin.json").is_file()


def test_the_plugin_contains_no_symbolic_link():
    fichiers = list(PLUGIN.rglob("*"))
    assert len(fichiers) >= 20, fichiers
    liens = [str(p.relative_to(PLUGIN)) for p in fichiers if p.is_symlink()]
    assert not liens, f"Anthropic's directory refuses a link: {liens}"


def test_the_plugin_copies_are_identical_to_their_original():
    assert len(COPIES) >= 15, COPIES
    assert sum(p.parent.name == "assets" for p in COPIES) >= 8, "assets introuvables"
    divergentes = [str(copie.relative_to(RACINE)) for copie, original in COPIES.items()
                   if not copie.is_file() or copie.read_bytes() != original.read_bytes()]
    assert not divergentes, (
        "copies absentes ou divergentes : " + ", ".join(divergentes)
        + " — copy the original (exemples/, src/monl/parser/lark_grammar.py)")


def test_the_plugin_icon_is_the_platforms():
    # A single source for the brand: the platform favicon (dark disc, cream
    # sign — readable outside any page, point 157), enlarged to 256 px because
    # the directory asks for a square of at least 128 px.
    from monl_platform.theme import FAVICON

    icone = (PLUGIN / ".claude-plugin" / "icon.svg").read_text(encoding="utf-8").strip()
    assert 'width="256" height="256"' in icone
    assert icone == FAVICON.replace("<svg ", '<svg width="256" height="256" ', 1)


def test_the_plugin_readme_satisfies_the_directory():
    texte = (PLUGIN / "README.md").read_text(encoding="utf-8")
    sans_code = re.sub(r"```.*?```", "", texte, flags=re.DOTALL)
    # Portal threshold: 40 words outside code blocks, otherwise the submission
    # blocks.
    assert len(sans_code.split()) >= 40


def test_each_skill_is_named_like_its_folder():
    # The EXACT list: an "at least N" threshold would have let through the
    # disappearance of a skill as well as the addition of an unreviewed one.
    assert sorted(c.parent.name for c in COMPETENCES) == ["monl-frontend", "monl-spec"]
    for chemin in COMPETENCES:
        entete = chemin.read_text(encoding="utf-8").split("---")[1]
        champs = dict(ligne.split(":", 1) for ligne in entete.strip().splitlines()
                      if ":" in ligne and not ligne.startswith(" "))
        assert champs["name"].strip() == chemin.parent.name, chemin
        assert champs["description"].strip(), chemin


def test_each_plugin_path_cited_by_a_skill_exists():
    cites = [(chemin.parent.name, cite) for chemin in COMPETENCES
             for cite in re.findall(r"\$\{CLAUDE_PLUGIN_ROOT\}/([^\s`)]+)",
                                    chemin.read_text(encoding="utf-8"))]
    assert cites, "no ${CLAUDE_PLUGIN_ROOT} path found: the rule would look at nothing"
    for competence, cite in cites:
        trouves = list(PLUGIN.glob(cite)) if "*" in cite else [PLUGIN / cite]
        assert trouves and all(t.exists() for t in trouves), f"{competence} : {cite}"


def test_each_verb_cited_by_the_entry_skill_exists():
    from monl.cli.dispatch import build_parser

    sous = next(a for a in build_parser()._actions if a.dest == "command")
    texte = (PLUGIN / "skills" / "monl-spec" / "SKILL.md").read_text(encoding="utf-8")
    # A COMMAND (start of a code block line, or after a backtick), never prose:
    # "why does monl reject my spec" is not one.
    verbes = set(re.findall(r"(?:^|`)monl (\w+)", texte, flags=re.MULTILINE))
    assert {"compile", "run", "diff", "update"} <= verbes, verbes
    assert verbes <= set(sous.choices), verbes - set(sous.choices)
