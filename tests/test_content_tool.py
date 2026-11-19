"""`monl content export/import` works only on local files."""
import csv
import os
import pathlib
import tempfile

import pytest

from monl.content_tool import ContentToolError, exporter_contenu, importer_contenu

SPEC = """app Contenu
entity Produit
    nom: String
    prix: Integer
    photo: Image
    etat: String

entity Page
    titre: String

actor Admin
rule Produit.nom required
rule Produit.etat oneOf "neuf", "occasion"
rule Produit.Read public
workflow Voir for Admin
    Read Produit

seed Produit
    nom: "Chaise", prix: 12, etat: "neuf"
    nom: "Table", prix: 20, etat: "occasion"
"""


def _project(spec=SPEC):
    temporaire = tempfile.TemporaryDirectory()
    racine = temporaire.name
    chemin = os.path.join(racine, "spec.ml")
    with open(chemin, "w", encoding="utf-8") as fh:
        fh.write(spec)
    return temporaire, chemin


def _rows(racine, entite="Produit"):
    chemin = os.path.join(racine, "content", f"{entite}.csv")
    with open(chemin, encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        return reader.fieldnames, list(reader)


def _write_rows(racine, champs, rows, entite="Produit"):
    chemin = os.path.join(racine, "content", f"{entite}.csv")
    with open(chemin, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=champs)
        writer.writeheader()
        writer.writerows(rows)


def test_round_trip_without_change_is_byte_stable():
    temporaire, spec = _project()
    with temporaire:
        avant = pathlib.Path(spec).read_text(encoding="utf-8")
        exporter_contenu(spec, temporaire.name)
        rapport = importer_contenu(spec, temporaire.name)
        assert pathlib.Path(spec).read_text(encoding="utf-8") == avant
        assert rapport["spec_changee"] is False


def test_changing_a_value_does_not_touch_the_rest_of_the_spec():
    temporaire, spec = _project()
    with temporaire:
        exporter_contenu(spec, temporaire.name)
        champs, rows = _rows(temporaire.name)
        rows[1]["nom"] = "Grande table"
        _write_rows(temporaire.name, champs, rows)
        importer_contenu(spec, temporaire.name)
        texte = pathlib.Path(spec).read_text(encoding="utf-8")
        assert 'nom: "Grande table", prix: 20, etat: "occasion"' in texte
        assert "entity Page\n    titre: String" in texte


def test_missing_image_names_the_file_and_csv_row():
    temporaire, spec = _project()
    with temporaire:
        exporter_contenu(spec, temporaire.name)
        champs, rows = _rows(temporaire.name)
        rows[0]["photo"] = "absente.jpg"
        _write_rows(temporaire.name, champs, rows)
        with pytest.raises(ContentToolError, match=r"row 2.*absente\.jpg.*not found"):
            importer_contenu(spec, temporaire.name)


def test_image_refuses_a_path_with_the_csv_row():
    temporaire, spec = _project()
    with temporaire:
        exporter_contenu(spec, temporaire.name)
        champs, rows = _rows(temporaire.name)
        rows[0]["photo"] = "sous-dossier/photo.jpg"
        _write_rows(temporaire.name, champs, rows)
        with pytest.raises(ContentToolError, match=r"row 2.*filename"):
            importer_contenu(spec, temporaire.name)


def test_invalid_number_is_refused_with_the_csv_row():
    temporaire, spec = _project()
    with temporaire:
        exporter_contenu(spec, temporaire.name)
        champs, rows = _rows(temporaire.name)
        rows[0]["prix"] = "douze"
        _write_rows(temporaire.name, champs, rows)
        with pytest.raises(ContentToolError, match=r"row 2.*douze"):
            importer_contenu(spec, temporaire.name)


def test_non_contiguous_blocks_of_one_entity_are_refused():
    spec_ = SPEC.replace(
        '    nom: "Table", prix: 20, etat: "occasion"',
        'seed Page\n    titre: "Accueil"\n\nseed Produit\n'
        '    nom: "Table", prix: 20, etat: "occasion"')
    temporaire, spec = _project(spec_)
    with temporaire:
        exporter_contenu(spec, temporaire.name)
        champs, rows = _rows(temporaire.name)
        rows[0]["nom"] = "Fauteuil"
        _write_rows(temporaire.name, champs, rows)
        with pytest.raises(ContentToolError, match="are not contiguous"):
            importer_contenu(spec, temporaire.name)


def test_parent_is_exported_and_grouped_in_the_headers():
    spec_ = """app Variantes
entity Produit
    nom: String
entity Variante
    nom: String
relation Produit hasMany Variante
actor Admin
rule Produit.Read public
rule Variante.Read public
workflow Voir for Admin
    Read Produit
    Read Variante
seed Produit
    nom: "Chaise"
    nom: "Table"
seed Variante for Produit.nom "Chaise"
    nom: "Bois"
seed Variante for Produit.nom "Table"
    nom: "Noir"
"""
    temporaire, spec = _project(spec_)
    with temporaire:
        exporter_contenu(spec, temporaire.name)
        champs, rows = _rows(temporaire.name, "Variante")
        assert champs[0] == "_parent"
        rows.append({"_parent": "Table", "nom": "Blanc"})
        _write_rows(temporaire.name, champs, rows, "Variante")
        importer_contenu(spec, temporaire.name)
        texte = pathlib.Path(spec).read_text(encoding="utf-8")
        assert texte.count('seed Variante for Produit.nom "Table"') == 1
        assert '    nom: "Noir"\n    nom: "Blanc"' in texte


def test_entity_without_seed_is_reported_without_blocking_others():
    temporaire, spec = _project()
    with temporaire:
        rapport = exporter_contenu(spec, temporaire.name)
        assert "Produit" in rapport["entites"]
        assert "Page" in rapport["ignorees"]
        assert not os.path.exists(os.path.join(temporaire.name, "content", "Page.csv"))


def test_readme_lists_the_oneof_values():
    temporaire, spec = _project()
    with temporaire:
        exporter_contenu(spec, temporaire.name)
        texte = pathlib.Path(os.path.join(temporaire.name, "content", "LISEZMOI.txt")).read_text(encoding="utf-8")
        assert "allowed values: neuf, occasion" in texte


def test_export_excludes_server_fields_and_booleans():
    spec_ = SPEC.replace(
        "    etat: String",
        "    etat: String\n    cree: DateTime\n    publie: Boolean",
    ).replace(
        "rule Produit.nom required",
        "rule Produit.nom required\nrule Produit.cree timestamp",
    )
    temporaire, spec = _project(spec_)
    with temporaire:
        exporter_contenu(spec, temporaire.name)
        champs, _rows_ = _rows(temporaire.name)
        assert "cree" not in champs
        assert "publie" not in champs
        texte = pathlib.Path(os.path.join(temporaire.name, "content", "LISEZMOI.txt")).read_text(encoding="utf-8")
        assert "publie" in texte
        assert "true/false literal" in texte
