"""`monl content export/import` works only on local files."""
import csv
import os
import pathlib
import tempfile

import pytest

from monl.content_tool import ContentToolError, exporter_content, importer_content

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
    temporary = tempfile.TemporaryDirectory()
    racine = temporary.name
    path = os.path.join(racine, "spec.ml")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(spec)
    return temporary, path


def _rows(racine, entity="Produit"):
    path = os.path.join(racine, "content", f"{entity}.csv")
    with open(path, encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        return reader.fieldnames, list(reader)


def _write_rows(racine, fields, rows, entity="Produit"):
    path = os.path.join(racine, "content", f"{entity}.csv")
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def test_round_trip_without_change_is_byte_stable():
    temporary, spec = _project()
    with temporary:
        before = pathlib.Path(spec).read_text(encoding="utf-8")
        exporter_content(spec, temporary.name)
        rapport = importer_content(spec, temporary.name)
        assert pathlib.Path(spec).read_text(encoding="utf-8") == before
        assert rapport["spec_changee"] is False


def test_changing_a_value_does_not_touch_the_rest_of_the_spec():
    temporary, spec = _project()
    with temporary:
        exporter_content(spec, temporary.name)
        fields, rows = _rows(temporary.name)
        rows[1]["nom"] = "Grande table"
        _write_rows(temporary.name, fields, rows)
        importer_content(spec, temporary.name)
        text = pathlib.Path(spec).read_text(encoding="utf-8")
        assert 'nom: "Grande table", prix: 20, etat: "occasion"' in text
        assert "entity Page\n    titre: String" in text


def test_missing_image_names_the_file_and_csv_row():
    temporary, spec = _project()
    with temporary:
        exporter_content(spec, temporary.name)
        fields, rows = _rows(temporary.name)
        rows[0]["photo"] = "absente.jpg"
        _write_rows(temporary.name, fields, rows)
        with pytest.raises(ContentToolError, match=r"row 2.*absente\.jpg.*not found"):
            importer_content(spec, temporary.name)


def test_image_refuses_a_path_with_the_csv_row():
    temporary, spec = _project()
    with temporary:
        exporter_content(spec, temporary.name)
        fields, rows = _rows(temporary.name)
        rows[0]["photo"] = "sous-dossier/photo.jpg"
        _write_rows(temporary.name, fields, rows)
        with pytest.raises(ContentToolError, match=r"row 2.*filename"):
            importer_content(spec, temporary.name)


def test_invalid_number_is_refused_with_the_csv_row():
    temporary, spec = _project()
    with temporary:
        exporter_content(spec, temporary.name)
        fields, rows = _rows(temporary.name)
        rows[0]["prix"] = "douze"
        _write_rows(temporary.name, fields, rows)
        with pytest.raises(ContentToolError, match=r"row 2.*douze"):
            importer_content(spec, temporary.name)


def test_non_contiguous_blocks_of_one_entity_are_refused():
    spec_ = SPEC.replace(
        '    nom: "Table", prix: 20, etat: "occasion"',
        'seed Page\n    titre: "Accueil"\n\nseed Produit\n'
        '    nom: "Table", prix: 20, etat: "occasion"')
    temporary, spec = _project(spec_)
    with temporary:
        exporter_content(spec, temporary.name)
        fields, rows = _rows(temporary.name)
        rows[0]["nom"] = "Fauteuil"
        _write_rows(temporary.name, fields, rows)
        with pytest.raises(ContentToolError, match="are not contiguous"):
            importer_content(spec, temporary.name)


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
    temporary, spec = _project(spec_)
    with temporary:
        exporter_content(spec, temporary.name)
        fields, rows = _rows(temporary.name, "Variante")
        assert fields[0] == "_parent"
        rows.append({"_parent": "Table", "nom": "Blanc"})
        _write_rows(temporary.name, fields, rows, "Variante")
        importer_content(spec, temporary.name)
        text = pathlib.Path(spec).read_text(encoding="utf-8")
        assert text.count('seed Variante for Produit.nom "Table"') == 1
        assert '    nom: "Noir"\n    nom: "Blanc"' in text


def test_entity_without_seed_is_reported_without_blocking_others():
    temporary, spec = _project()
    with temporary:
        rapport = exporter_content(spec, temporary.name)
        assert "Produit" in rapport["entites"]
        assert "Page" in rapport["ignorees"]
        assert not os.path.exists(os.path.join(temporary.name, "content", "Page.csv"))


def test_readme_lists_the_oneof_values():
    temporary, spec = _project()
    with temporary:
        exporter_content(spec, temporary.name)
        text = pathlib.Path(os.path.join(temporary.name, "content", "LISEZMOI.txt")).read_text(encoding="utf-8")
        assert "allowed values: neuf, occasion" in text


def test_export_excludes_server_fields_and_booleans():
    spec_ = SPEC.replace(
        "    etat: String",
        "    etat: String\n    cree: DateTime\n    publie: Boolean",
    ).replace(
        "rule Produit.nom required",
        "rule Produit.nom required\nrule Produit.cree timestamp",
    )
    temporary, spec = _project(spec_)
    with temporary:
        exporter_content(spec, temporary.name)
        fields, _rows_ = _rows(temporary.name)
        assert "cree" not in fields
        assert "publie" not in fields
        text = pathlib.Path(os.path.join(temporary.name, "content", "LISEZMOI.txt")).read_text(encoding="utf-8")
        assert "publie" in text
        assert "true/false literal" in text
