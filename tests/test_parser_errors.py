"""AJOUT (roadmap, erreurs lisibles) : vérifie que le parseur remonte des
erreurs de syntaxe localisées (MonlSyntaxError avec fichier, ligne,
colonne, extrait) au lieu des exceptions Lark brutes, et que la numérotation
des lignes reste celle du FICHIER ORIGINAL même quand la spec contient des
lignes de commentaire (retirées avant Lark — voir parser.py)."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../src"))

from parser import MonlSyntaxError, parse_monl_string


def test_syntax_error_is_localized():
    spec = "app Demo\n\nentity User\n    name String\n"
    with pytest.raises(MonlSyntaxError) as exc:
        parse_monl_string(spec, file_path="demo.ml")
    err = exc.value
    assert err.line == 4
    assert "demo.ml:4" in str(err)
    assert "name String" in str(err)  # extrait de la ligne fautive
    assert "^" in str(err)            # curseur sous la colonne


def test_line_numbers_survive_comment_stripping():
    # La ligne 2 est un commentaire seul : elle est retirée avant Lark,
    # mais l'erreur (ligne 5 du fichier original) doit rester à la ligne 5.
    spec = "app Demo\n# commentaire seul\n\nentity User\n    name String\n"
    with pytest.raises(MonlSyntaxError) as exc:
        parse_monl_string(spec)
    assert exc.value.line == 5


def test_error_suggests_expected_tokens():
    spec = "app Demo\n\nentity User\n    name String\n"
    with pytest.raises(MonlSyntaxError) as exc:
        parse_monl_string(spec)
    assert "Attendu ici" in str(exc.value)
