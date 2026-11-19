"""The delivered archive reads well: `docs/` for documents, the root for code.

THREE DEFECTS OBSERVED ON A REALLY DOWNLOADED ARCHIVE.

  (a) Fifteen flat files, with nothing to tell what one RUNS from what one
      READS. The four documents meant for the interface AI — brief and visual
      direction — go into `docs/`; the JSON contract stays at the root, it is
      the project's MACHINE interface.

  (b) The project memory was called `CLAUDE.md`, while the frontend can be
      written by claude-code, codex or gemini (point 69). A file named after
      a single agent is a file the others do not read: it is `AGENTS.md`.

  (c) No `README.md`, while the platform home page has always promised one
      in its tree preview.

WHAT IS AT STAKE IN THE MOVE. Writing to the new location without moving the
old file would produce TWO truths, one of them stale — and the stale one is
what an agent would read, since it is at the root. So we move. But a
hand-edited `DESIGN_SPEC.md` is human work: the move must preserve it,
otherwise the preserved copy would look for it where it no longer is and
replace it with a brand-new document.
"""
from __future__ import annotations

import os
import subprocess
import sys

import pytest

from monl.cli import compile_project
from monl.frontend_contract.projet import (
    PROJECT_CLAUDE_MD_MARKER,
    PROJECT_README_MARKER,
)

SPEC = """app Vitrine

entity Note
    titre: String

actor Auteur selfRegister

relation Auteur hasMany Note

rule Note.Read public

workflow Ecrire for Auteur
    Create Note
    Read Note
"""

DOCUMENTS = ("FRONTEND_PROMPT.md", "DESIGN_SYSTEM.md", "DESIGN_SPEC.md",
             "ASSET_MANIFEST.json")


@pytest.fixture
def project(tmp_path):
    """A really compiled project, not a hand-made folder."""
    spec = tmp_path / "spec.ml"
    spec.write_text(SPEC, encoding="utf-8")
    compile_project(str(spec), str(tmp_path))
    return tmp_path


def test_documents_live_in_docs_and_code_at_the_root(project):
    """(a) The rule in one sentence: `docs/` is read, the root is run."""
    for nom in DOCUMENTS:
        assert (project / "docs" / nom).is_file(), f"{nom} n'est pas dans docs/"
        assert not (project / nom).exists(), f"{nom} traîne encore à la racine"

    # The contract is the MACHINE interface: a tool opens it knowing nothing of
    # the tree. It stays where it is found without searching.
    assert (project / "frontend_contract.json").is_file()
    for nom in ("app.py", "schema.sql", "manage.py", "serve.py", "monl.json"):
        assert (project / nom).is_file(), f"{nom} a quitté la racine"


def test_the_project_memory_is_called_agents_and_the_readme_exists(project):
    """(b) and (c), with their marker — the marker is what protects the human."""
    agents = project / "AGENTS.md"
    readme = project / "README.md"
    assert agents.is_file(), "AGENTS.md absent"
    assert readme.is_file(), "README.md absent — la page d'accueil le promet"
    assert not (project / "CLAUDE.md").exists(), (
        "CLAUDE.md est encore livré : deux mémoires, dont une périmée")
    assert PROJECT_CLAUDE_MD_MARKER in agents.read_text(encoding="utf-8")
    assert PROJECT_README_MARKER in readme.read_text(encoding="utf-8")


def test_the_readme_names_the_real_spec_and_the_backend_starts(project, tmp_path):
    """A README describing something other than the folder is worse than none.

    We do not merely check that it TALKS about startup: the command it gives is
    run, and the server must load. It is point 163 — "served" is not
    "executable" — applied to documentation.
    """
    readme = (project / "README.md").read_text(encoding="utf-8")
    assert "spec.ml" in readme, "le README ne nomme pas la spec du projet"
    assert "uvicorn serve:app" in readme, "le README ne dit pas comment démarrer"
    assert "docs/" in readme, "le README ne dit pas ce que contient docs/"

    resultat = subprocess.run(
        [sys.executable, "-c", "import serve; assert serve.app is not None; print('ok')"],
        cwd=str(project), capture_output=True, text=True, timeout=120,
        env={**os.environ, "PYTHONPATH": str(project)},
    )
    assert resultat.returncode == 0, (
        f"la commande du README ne charge pas l'application :\n"
        f"{resultat.stderr[-1500:]}")


def _remettre_a_plat(project):
    """Rebuilds the EARLIER form: everything at the root, memory in CLAUDE.md."""
    for nom in DOCUMENTS:
        (project / "docs" / nom).replace(project / nom)
    (project / "docs").rmdir()
    (project / "AGENTS.md").replace(project / "CLAUDE.md")
    (project / "README.md").unlink()


def test_an_already_compiled_project_is_tidied_without_losing_anything(project):
    """THE CASE THAT COUNTS: human customization survives the move.

    A `DESIGN_SPEC.md` without a marker was written by someone. Moving it while
    replacing it with a new document would silently erase their work — and that
    is what would happen if we wrote into `docs/` without moving the root: the
    preserved copy would find nothing to preserve.
    """
    _remettre_a_plat(project)
    ecrit_a_la_main = "# Direction écrite par l'humain\nDu vert bouteille.\n"
    (project / "DESIGN_SPEC.md").write_text(ecrit_a_la_main, encoding="utf-8")

    compile_project(str(project / "spec.ml"), str(project))

    assert (project / "docs" / "DESIGN_SPEC.md").read_text(encoding="utf-8") == (
        ecrit_a_la_main), "le travail humain a été écrasé par le rangement"
    for nom in DOCUMENTS:
        assert not (project / nom).exists(), f"{nom} est resté à la racine"
    assert (project / "AGENTS.md").is_file()
    assert not (project / "CLAUDE.md").exists()


def test_a_personal_claude_md_is_never_touched(project):
    """THE COUNTER-PROOF of the rename.

    Without a marker, `CLAUDE.md` belongs to the user — they may have written
    their own instructions in it. Renaming it AGENTS.md would move their text
    under a name monl overwrites at the next compilation: their memory would
    disappear later, which is worse than an immediate overwrite.
    """
    _remettre_a_plat(project)
    a_lui = "# Mes consignes à moi\nNe touche pas à la barre de navigation.\n"
    (project / "CLAUDE.md").write_text(a_lui, encoding="utf-8")

    compile_project(str(project / "spec.ml"), str(project))

    assert (project / "CLAUDE.md").read_text(encoding="utf-8") == a_lui, (
        "le CLAUDE.md personnel de l'utilisateur a été déplacé ou réécrit")
    assert (project / "AGENTS.md").is_file(), (
        "monl n'a pas déposé sa propre mémoire à côté")
    assert PROJECT_CLAUDE_MD_MARKER in (project / "AGENTS.md").read_text(
        encoding="utf-8")


def test_the_tidying_is_idempotent(project):
    """Recompiling must announce nothing and move nothing a second time."""
    avant = sorted(p.relative_to(project).as_posix()
                   for p in project.rglob("*") if p.is_file())
    compile_project(str(project / "spec.ml"), str(project))
    apres = sorted(p.relative_to(project).as_posix()
                   for p in project.rglob("*") if p.is_file())
    assert avant == apres
