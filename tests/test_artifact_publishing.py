from pathlib import Path

import pytest

from monl import artifacts
from monl.cli import compile_project


def _write(directory: Path, name: str, value: str) -> None:
    (directory / name).write_text(value, encoding="utf-8")


def test_publication_remplace_le_jeu_complet_sans_toucher_les_autres_fichiers(tmp_path):
    target = tmp_path / "projet"
    staging = tmp_path / "stage"
    target.mkdir()
    staging.mkdir()
    _write(target, "app.py", "ancienne app")
    _write(target, "frontend.txt", "créé par l'utilisateur")
    _write(staging, "app.py", "nouvelle app")
    _write(staging, "schema.sql", "nouveau schema")

    artifacts.publish_files(staging, target, ("app.py", "schema.sql"))

    assert (target / "app.py").read_text(encoding="utf-8") == "nouvelle app"
    assert (target / "schema.sql").read_text(encoding="utf-8") == "nouveau schema"
    assert (target / "frontend.txt").read_text(encoding="utf-8") == "créé par l'utilisateur"


def test_publication_restaure_tous_les_anciens_fichiers_si_un_remplacement_echoue(
    tmp_path, monkeypatch
):
    target = tmp_path / "projet"
    staging = tmp_path / "stage"
    target.mkdir()
    staging.mkdir()
    _write(target, "app.py", "ancienne app")
    _write(target, "schema.sql", "ancien schema")
    _write(staging, "app.py", "nouvelle app")
    _write(staging, "schema.sql", "nouveau schema")

    real_replace = artifacts._replace
    calls = 0

    def fail_on_second_replace(source, destination):
        nonlocal calls
        calls += 1
        if calls == 3:
            raise OSError("disque plein simulé")
        real_replace(source, destination)

    monkeypatch.setattr(artifacts, "_replace", fail_on_second_replace)

    with pytest.raises(artifacts.ArtifactPublicationError):
        artifacts.publish_files(staging, target, ("app.py", "schema.sql"))

    assert (target / "app.py").read_text(encoding="utf-8") == "ancienne app"
    assert (target / "schema.sql").read_text(encoding="utf-8") == "ancien schema"


def test_publication_refuse_un_staging_incomplet(tmp_path):
    target = tmp_path / "projet"
    staging = tmp_path / "stage"
    target.mkdir()
    staging.mkdir()
    _write(staging, "app.py", "app")

    with pytest.raises(artifacts.ArtifactPublicationError, match=r"schema\.sql"):
        artifacts.publish_files(staging, target, ("app.py", "schema.sql"))

    assert not (target / "app.py").exists()


def test_compile_project_ne_publie_rien_si_la_transaction_finale_echoue(
    tmp_path, monkeypatch
):
    spec = tmp_path / "spec.ml"
    spec.write_text(
        """app Transaction

entity Note
    title: String

actor Admin selfRegister

rule Note.Read public

workflow Gerer for Admin
    Create Note
    Read Note
""",
        encoding="utf-8",
    )
    (tmp_path / "app.py").write_text("ancienne version", encoding="utf-8")
    (tmp_path / "frontend").mkdir()
    (tmp_path / "frontend" / "index.html").write_text("<h1>user</h1>", encoding="utf-8")

    def fail_publish(*args, **kwargs):
        raise artifacts.ArtifactPublicationError("publication simulée")

    monkeypatch.setattr("monl.cli.publish_files", fail_publish)

    with pytest.raises(artifacts.ArtifactPublicationError):
        compile_project(str(spec), str(tmp_path))

    assert (tmp_path / "app.py").read_text(encoding="utf-8") == "ancienne version"
    assert (tmp_path / "frontend" / "index.html").read_text(encoding="utf-8") == "<h1>user</h1>"
    assert not (tmp_path / "frontend_contract.json").exists()
    assert not (tmp_path / "monl.json").exists()
