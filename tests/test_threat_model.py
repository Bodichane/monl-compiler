"""Keep the threat model's test evidence real and nonempty."""

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEST_REFERENCE = re.compile(r"\b(tests/[\w/.-]+\.py)::(test_\w+)\b")


def test_threat_model_test_references_exist():
    document = (ROOT / "docs/THREAT_MODEL.md").read_text(encoding="utf-8")
    references = set(TEST_REFERENCE.findall(document))
    assert references, "THREAT_MODEL.md contains no test references"
    errors = []
    for filename, function in sorted(references):
        path = ROOT / filename
        if not path.is_file():
            errors.append(f"{filename}::{function}: file does not exist")
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=filename)
        # References use module-level pytest functions, not nested helpers.
        functions = {
            node.name for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        if function not in functions:
            errors.append(f"{filename}::{function}: function does not exist")
    assert not errors, "\n".join(errors)
