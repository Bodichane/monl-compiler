"""Corpus intégral déterministe ; régénération explicite depuis la racine."""

import contextlib
import hashlib
import io
import json
import tempfile
from pathlib import Path

from monl.app_templates import TEMPLATES
from monl.cli import compile_project
from tests.test_app_templates import _run_template
from tests.test_authentification_b4 import SPEC_B4
from tests.test_bloc_custom_absent import AVEC_CUSTOM
from tests.test_generated_specs import generated_spec
from tests.test_golden_artifacts import SPEC, SPEC_LOOKUP_SOURCES
from tests.test_messages import SPEC as SPEC_MESSAGES

ROOT = Path(__file__).resolve().parents[2]
BASELINE = ROOT / "tests/data/corpus_octets.json"


def corpus_specs():
    cases = {path.relative_to(ROOT).as_posix(): path.read_text(encoding="utf-8")
             for path in sorted((ROOT / "exemples").glob("*.ml"))}
    cases["demo/spec.ml"] = (ROOT / "demo/spec.ml").read_text(encoding="utf-8")
    cases.update(golden=SPEC, golden_lookup=SPEC_LOOKUP_SOURCES, golden_b4=SPEC_B4,
                 benchmark=generated_spec(20))
    for index in range(1, len(TEMPLATES) + 1):
        for answer in ("n", "o"):
            cases[f"dialogue_{index}_{answer}"] = _run_template(
                index, answer, want_seed=answer == "o")
    cases["auth_complete"] = SPEC_B4.replace(
        "    totp\n", "    totp\n    verify_email: 86400\n    verify_resend: 3 in 3600\n")
    for name, option in {
        "lockout": "lockout: 3 in 10",
        "password_reset": "password_reset: 60",
        "refresh_tokens": "refresh_tokens: 3600",
        "totp": "totp",
        "verify_email": "verify_email: 86400\n    verify_resend: 3 in 3600",
    }.items():
        cases[f"auth_{name}"] = SPEC.replace(
            "workflow", f"capability auth\n    identifier: email\n    {option}\n\nworkflow")
    cases["messages"] = SPEC_MESSAGES
    cases["custom"] = AVEC_CUSTOM
    cases["migration"] = '''app MigrationCorpus
entity User
    name: String
entity Note
    heading: String
    priority: Integer
relation User hasMany Note
actor User selfRegister
workflow W for User
    Create Note
    Read Note
migration note_fields
    rename Note.title to heading
    alter Note.priority from String to Integer
    drop Note.legacy
'''
    assert cases, "Corpus vide"
    return cases


def corpus_hashes():
    result = {}
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        with contextlib.redirect_stdout(io.StringIO()):
            specs = corpus_specs()
        for index, (name, source) in enumerate(specs.items()):
            output = root / f"output_{index}"
            output.mkdir()
            spec = output / "spec.ml"
            spec.write_text(source, encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()):
                reference = ROOT / name
                base = reference.parent if reference.is_file() else root
                compile_project(str(spec), str(output), base_dir=str(base))
            files = {path.relative_to(output).as_posix():
                     hashlib.sha256(path.read_bytes()).hexdigest()
                     for path in sorted(output.rglob("*")) if path.is_file()
                     and path.name not in {"monl.json", ".jwt_secret", "spec.ml"}
                     and path.suffix not in {".db", ".sqlite", ".sqlite3"}}
            assert files, f"Aucun fichier : {name}"
            result[name] = files
    assert result, "Corpus vide"
    return result


if __name__ == "__main__":
    first = corpus_hashes()
    assert first == corpus_hashes(), "Compilation non déterministe"
    BASELINE.write_text(json.dumps(first, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
