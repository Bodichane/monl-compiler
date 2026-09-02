"""L'archive livrée se lit : `docs/` pour les documents, la racine pour le code.

TROIS DÉFAUTS CONSTATÉS SUR UNE ARCHIVE RÉELLEMENT TÉLÉCHARGÉE.

  (a) Quinze fichiers à plat, sans rien pour distinguer ce qu'on LANCE de ce
      qu'on LIT. Les quatre documents destinés à l'IA d'interface — brief et
      direction visuelle — partent dans `docs/` ; le contrat JSON reste à la
      racine, c'est l'interface MACHINE du projet.

  (b) La mémoire du projet s'appelait `CLAUDE.md`, quand le frontend peut être
      écrit par claude-code, codex ou gemini (point 69). Un fichier nommé
      d'après un seul agent est un fichier que les autres ne lisent pas :
      c'est `AGENTS.md`.

  (c) Aucun `README.md`, alors que la page d'accueil de la plateforme en
      promet un dans son aperçu d'arborescence depuis toujours.

CE QUI SE JOUE DANS LE DÉPLACEMENT. Écrire au nouvel emplacement sans bouger
l'ancien fichier produirait DEUX vérités, dont une périmée — et c'est la
périmée qu'un agent lirait, puisqu'elle est à la racine. On déplace donc. Mais
un `DESIGN_SPEC.md` retouché à la main est du travail humain : le déplacement
doit le préserver, sans quoi la copie préservée irait le chercher là où il
n'est plus et le remplacerait par un document tout neuf.
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
def projet(tmp_path):
    """Un projet réellement compilé, pas un dossier fabriqué à la main."""
    spec = tmp_path / "spec.ml"
    spec.write_text(SPEC, encoding="utf-8")
    compile_project(str(spec), str(tmp_path))
    return tmp_path


def test_les_documents_vivent_dans_docs_et_le_code_a_la_racine(projet):
    """(a) La règle en une phrase : `docs/` se lit, la racine s'exécute."""
    for nom in DOCUMENTS:
        assert (projet / "docs" / nom).is_file(), f"{nom} n'est pas dans docs/"
        assert not (projet / nom).exists(), f"{nom} traîne encore à la racine"

    # Le contrat est l'interface MACHINE : un outil l'ouvre sans rien connaître
    # de l'arborescence. Il reste où on le trouve sans chercher.
    assert (projet / "frontend_contract.json").is_file()
    for nom in ("app.py", "schema.sql", "manage.py", "serve.py", "monl.json"):
        assert (projet / nom).is_file(), f"{nom} a quitté la racine"


def test_la_memoire_du_projet_sappelle_agents_et_le_readme_existe(projet):
    """(b) et (c), avec leur marqueur — c'est lui qui protège l'humain."""
    agents = projet / "AGENTS.md"
    readme = projet / "README.md"
    assert agents.is_file(), "AGENTS.md absent"
    assert readme.is_file(), "README.md absent — la page d'accueil le promet"
    assert not (projet / "CLAUDE.md").exists(), (
        "CLAUDE.md est encore livré : deux mémoires, dont une périmée")
    assert PROJECT_CLAUDE_MD_MARKER in agents.read_text(encoding="utf-8")
    assert PROJECT_README_MARKER in readme.read_text(encoding="utf-8")


def test_le_readme_nomme_la_vraie_spec_et_le_backend_demarre(projet, tmp_path):
    """Un README qui décrit autre chose que le dossier est pire qu'absent.

    On ne se contente pas de vérifier qu'il PARLE de démarrage : la commande
    qu'il donne est exécutée, et le serveur doit se charger. C'est le point 163
    — « servi » n'est pas « exécutable » — appliqué à de la documentation.
    """
    readme = (projet / "README.md").read_text(encoding="utf-8")
    assert "spec.ml" in readme, "le README ne nomme pas la spec du projet"
    assert "uvicorn serve:app" in readme, "le README ne dit pas comment démarrer"
    assert "docs/" in readme, "le README ne dit pas ce que contient docs/"

    resultat = subprocess.run(
        [sys.executable, "-c", "import serve; assert serve.app is not None; print('ok')"],
        cwd=str(projet), capture_output=True, text=True, timeout=120,
        env={**os.environ, "PYTHONPATH": str(projet)},
    )
    assert resultat.returncode == 0, (
        f"la commande du README ne charge pas l'application :\n"
        f"{resultat.stderr[-1500:]}")


def _remettre_a_plat(projet):
    """Refabrique la forme d'AVANT : tout à la racine, mémoire en CLAUDE.md."""
    for nom in DOCUMENTS:
        (projet / "docs" / nom).replace(projet / nom)
    (projet / "docs").rmdir()
    (projet / "AGENTS.md").replace(projet / "CLAUDE.md")
    (projet / "README.md").unlink()


def test_un_projet_deja_compile_est_range_sans_rien_perdre(projet):
    """LE CAS QUI COMPTE : la personnalisation humaine survit au déplacement.

    Un `DESIGN_SPEC.md` sans marqueur a été écrit par quelqu'un. Le déplacer
    en le remplaçant par un document neuf effacerait son travail en silence —
    et c'est ce qui arriverait si on écrivait dans `docs/` sans déménager la
    racine : la copie préservée ne trouverait rien à préserver.
    """
    _remettre_a_plat(projet)
    ecrit_a_la_main = "# Direction écrite par l'humain\nDu vert bouteille.\n"
    (projet / "DESIGN_SPEC.md").write_text(ecrit_a_la_main, encoding="utf-8")

    compile_project(str(projet / "spec.ml"), str(projet))

    assert (projet / "docs" / "DESIGN_SPEC.md").read_text(encoding="utf-8") == (
        ecrit_a_la_main), "le travail humain a été écrasé par le rangement"
    for nom in DOCUMENTS:
        assert not (projet / nom).exists(), f"{nom} est resté à la racine"
    assert (projet / "AGENTS.md").is_file()
    assert not (projet / "CLAUDE.md").exists()


def test_un_claude_md_personnel_nest_jamais_touche(projet):
    """LA CONTRE-ÉPREUVE du renommage.

    Sans marqueur, `CLAUDE.md` appartient à l'utilisateur — il a pu y écrire
    ses propres consignes. Le renommer en AGENTS.md déplacerait son texte sous
    un nom que monl écrase à la compilation suivante : sa mémoire disparaîtrait
    à retardement, ce qui est pire qu'un écrasement immédiat.
    """
    _remettre_a_plat(projet)
    a_lui = "# Mes consignes à moi\nNe touche pas à la barre de navigation.\n"
    (projet / "CLAUDE.md").write_text(a_lui, encoding="utf-8")

    compile_project(str(projet / "spec.ml"), str(projet))

    assert (projet / "CLAUDE.md").read_text(encoding="utf-8") == a_lui, (
        "le CLAUDE.md personnel de l'utilisateur a été déplacé ou réécrit")
    assert (projet / "AGENTS.md").is_file(), (
        "monl n'a pas déposé sa propre mémoire à côté")
    assert PROJECT_CLAUDE_MD_MARKER in (projet / "AGENTS.md").read_text(
        encoding="utf-8")


def test_le_rangement_est_idempotent(projet):
    """Recompiler ne doit rien annoncer ni rien déplacer une seconde fois."""
    avant = sorted(p.relative_to(projet).as_posix()
                   for p in projet.rglob("*") if p.is_file())
    compile_project(str(projet / "spec.ml"), str(projet))
    apres = sorted(p.relative_to(projet).as_posix()
                   for p in projet.rglob("*") if p.is_file())
    assert avant == apres
