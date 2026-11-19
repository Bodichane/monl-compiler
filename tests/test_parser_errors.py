"""ADDED (roadmap, readable errors): checks that the parser reports
located syntax errors (MonlSyntaxError with file, line, column, excerpt)
instead of raw Lark exceptions, and that line numbering stays the ORIGINAL
FILE's even when the spec contains comment lines (removed before Lark —
see parser.py)."""

import pytest

from monl.parser import MonlSyntaxError, parse_monl_string


def test_syntax_error_is_localized():
    spec = "app Demo\n\nentity User\n    name String\n"
    with pytest.raises(MonlSyntaxError) as exc:
        parse_monl_string(spec, file_path="demo.ml")
    err = exc.value
    assert err.line == 4
    assert "demo.ml:4" in str(err)
    assert "name String" in str(err)  # excerpt of the faulty line
    assert "^" in str(err)            # caret under the column


def test_line_numbers_survive_comment_stripping():
    # Line 2 is a comment alone: it is removed before Lark, but the error (line
    # 5 of the original file) must stay at line 5.
    spec = "app Demo\n# commentaire seul\n\nentity User\n    name String\n"
    with pytest.raises(MonlSyntaxError) as exc:
        parse_monl_string(spec)
    assert exc.value.line == 5


def test_error_suggests_expected_tokens():
    spec = "app Demo\n\nentity User\n    name String\n"
    with pytest.raises(MonlSyntaxError) as exc:
        parse_monl_string(spec)
    assert "Expected here" in str(exc.value)
