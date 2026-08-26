"""Snapshots immuables des constructions de plateforme."""

import json

import pytest

from monl_platform.revisions import SnapshotError, create_snapshot


def test_snapshot_est_complet_hashé_et_n_imbrique_pas_les_anciens(tmp_path):
    project = tmp_path / "project"
    (project / "frontend").mkdir(parents=True)
    (project / "assets").mkdir()
    (project / "frontend" / "index.html").write_text(
        "<h1>version 1</h1>", encoding="utf-8"
    )
    (project / "assets" / "hero.svg").write_text(
        "<svg></svg>", encoding="utf-8"
    )
    (project / "revisions" / "build-1").mkdir(parents=True)
    (project / "revisions" / "build-1" / "SNAPSHOT.json").write_text(
        "ancienne version", encoding="utf-8"
    )

    snapshot = create_snapshot(project, 2)
    destination = project / snapshot["path"]
    metadata = json.loads(
        (destination / "SNAPSHOT.json").read_text(encoding="utf-8")
    )

    assert destination.is_dir()
    assert (destination / "frontend" / "index.html").read_text(encoding="utf-8") == (
        "<h1>version 1</h1>"
    )
    assert not (destination / "revisions").exists()
    assert metadata["build_id"] == 2
    assert metadata["artifact_sha256"] == snapshot["sha256"]
    assert metadata["bytes"] == snapshot["bytes"]
    assert metadata["file_count"] == snapshot["file_count"]


def test_snapshot_refuse_un_lien_symbolique(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    target = tmp_path / "outside.txt"
    target.write_text("secret", encoding="utf-8")
    (project / "outside.txt").symlink_to(target)

    with pytest.raises(SnapshotError, match="lien symbolique"):
        create_snapshot(project, 1)


def test_snapshot_refuse_deux_fois_le_meme_build(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    create_snapshot(project, 1)

    with pytest.raises(SnapshotError, match="déjà présent"):
        create_snapshot(project, 1)
