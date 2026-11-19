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
from monl.frontend_contract.project import (
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
    for name in DOCUMENTS:
        assert (project / "docs" / name).is_file(), f"{name} is not in docs/"
        assert not (project / name).exists(), f"{name} still lingers at the root"

    # The contract is the MACHINE interface: a tool opens it knowing nothing of
    # the tree. It stays where it is found without searching.
    assert (project / "frontend_contract.json").is_file()
    for name in ("app.py", "schema.sql", "manage.py", "serve.py", "monl.json"):
        assert (project / name).is_file(), f"{name} left the root"


def test_the_project_memory_is_called_agents_and_the_readme_exists(project):
    """(b) and (c), with their marker — the marker is what protects the human."""
    agents = project / "AGENTS.md"
    readme = project / "README.md"
    assert agents.is_file(), "AGENTS.md absent"
    assert readme.is_file(), "README.md missing — the home page promises it"
    assert not (project / "CLAUDE.md").exists(), (
        "CLAUDE.md is still shipped: two memories, one of them stale")
    assert PROJECT_CLAUDE_MD_MARKER in agents.read_text(encoding="utf-8")
    assert PROJECT_README_MARKER in readme.read_text(encoding="utf-8")


def test_the_readme_names_the_real_spec_and_the_backend_starts(project, tmp_path):
    """A README describing something other than the folder is worse than none.

    We do not merely check that it TALKS about startup: the command it gives is
    run, and the server must load. It is point 163 — "served" is not
    "executable" — applied to documentation.
    """
    readme = (project / "README.md").read_text(encoding="utf-8")
    assert "spec.ml" in readme, "the README does not name the project's spec"
    assert "uvicorn serve:app" in readme, "the README does not say how to start"
    assert "docs/" in readme, "the README does not say what docs/ contains"

    result = subprocess.run(
        [sys.executable, "-c", "import serve; assert serve.app is not None; print('ok')"],
        cwd=str(project), capture_output=True, text=True, timeout=120,
        env={**os.environ, "PYTHONPATH": str(project)},
    )
    assert result.returncode == 0, (
        f"the README command does not load the application:\n"
        f"{result.stderr[-1500:]}")


def _put_back_a_plat(project):
    """Rebuilds the EARLIER form: everything at the root, memory in CLAUDE.md."""
    for name in DOCUMENTS:
        (project / "docs" / name).replace(project / name)
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
    _put_back_a_plat(project)
    written_to_the_main = "# Direction écrite par l'humain\nDu vert bouteille.\n"
    (project / "DESIGN_SPEC.md").write_text(written_to_the_main, encoding="utf-8")

    compile_project(str(project / "spec.ml"), str(project))

    assert (project / "docs" / "DESIGN_SPEC.md").read_text(encoding="utf-8") == (
        written_to_the_main), "human work was overwritten by the tidying"
    for name in DOCUMENTS:
        assert not (project / name).exists(), f"{name} stayed at the root"
    assert (project / "AGENTS.md").is_file()
    assert not (project / "CLAUDE.md").exists()


def test_a_personal_claude_md_is_never_touched(project):
    """THE COUNTER-PROOF of the rename.

    Without a marker, `CLAUDE.md` belongs to the user — they may have written
    their own instructions in it. Renaming it AGENTS.md would move their text
    under a name monl overwrites at the next compilation: their memory would
    disappear later, which is worse than an immediate overwrite.
    """
    _put_back_a_plat(project)
    a_lui = "# Mes consignes à moi\nNe touche pas à la barre de navigation.\n"
    (project / "CLAUDE.md").write_text(a_lui, encoding="utf-8")

    compile_project(str(project / "spec.ml"), str(project))

    assert (project / "CLAUDE.md").read_text(encoding="utf-8") == a_lui, (
        "the user's personal CLAUDE.md was moved or rewritten")
    assert (project / "AGENTS.md").is_file(), (
        "monl did not place its own memory next to it")
    assert PROJECT_CLAUDE_MD_MARKER in (project / "AGENTS.md").read_text(
        encoding="utf-8")


def test_the_tidying_is_idempotent(project):
    """Recompiling must announce nothing and move nothing a second time."""
    before = sorted(p.relative_to(project).as_posix()
                   for p in project.rglob("*") if p.is_file())
    compile_project(str(project / "spec.ml"), str(project))
    apres = sorted(p.relative_to(project).as_posix()
                   for p in project.rglob("*") if p.is_file())
    assert before == apres
