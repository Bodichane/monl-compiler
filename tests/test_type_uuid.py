"""The `UUID` type finally checks its form — point 101.

Point 91 had set the reasoning for `Email`: "a type that names an address and
checks none is exactly what point 85 refuses, a rule that produces nothing".
Its SIBLING type stayed standing ten more points.

`UUID` only set a length of 255. `exemples/02_boutique.ml` declares
`Order.reference: UUID`, and the server accepted `CMD-1`, `smoke-reference`,
or the empty string, under a name promising a universally unique identifier —
two orders could therefore carry the same "reference".

What the point decides:

* **the canonical form, and nothing more.** Neither version digit nor
  variant: requiring them would reject the nil UUID and future versions,
  while they are well formed. monl checks the FORM, it does not judge the
  origin;
* **the counter-proof counts as much as the refusal.** A too strict pattern
  would make the rejection tests pass while breaking real identifiers — it is
  point 91's lesson, taken as is;
* **the checker is a client like any other, a THIRD time.** The smoke test
  sent `smoke-reference` and would have declared a healthy shop broken, after
  `'smoke'` (point 95) and `'smoke-status'` (point 96).

This point converts NO existing data: a database already holding malformed
references keeps returning them. The rule only applies to future writes, as
at point 95.
"""
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request

import pytest

from monl.cli import compile_project
from monl.smoke_test import _sample_value, run_smoke_test
from tests.support.cas import verifier_chaque_cas
from tests.support.processus import arreter_processus
from tests.support.server import free_port as _port_libre

SPEC = """app BancUUID

entity Commande
    reference: UUID
    libelle: String

actor Client selfRegister

rule Commande.Read ownedBy Client

relation Client hasMany Commande

workflow Acheter for Client
    Create Commande
    Read Commande
"""

MAL_FORMES = [
    "smoke-reference",                        # what the smoke test sent
    "CMD-1",                                  # a "business" reference
    "3f2504e0-4f89-41d3-9a0c",                # truncated
    "3f2504e04f8941d39a0c0305e82c3301",       # without dashes
    "3f2504e0-4f89-41d3-9a0c-0305e82c330g",   # 'g' is not hexadecimal
    "3f2504e0-4f89-41d3-9a0c-0305e82c33011",  # one character too many
    "",
]

BIEN_FORMES = [
    "3f2504e0-4f89-41d3-9a0c-0305e82c3301",
    # The nil UUID is well FORMED: refusing it would require judging the value,
    # not its form — and monl only checks the form.
    "00000000-0000-0000-0000-000000000000",
    # Capitals: hexadecimal case is free in the canonical form.
    "3F2504E0-4F89-41D3-9A0C-0305E82C3302",
]


# --------------------------------------------------------------------------
# What generation must write
# --------------------------------------------------------------------------

def test_the_pattern_is_written_for_a_uuid_field(tmp_path, capsys):
    (tmp_path / "spec.ml").write_text(SPEC, encoding="utf-8")
    compile_project(str(tmp_path / "spec.ml"), str(tmp_path))
    capsys.readouterr()
    genere = (tmp_path / "app.py").read_text(encoding="utf-8")
    ligne = next(li for li in genere.splitlines() if li.strip().startswith("reference:"))
    assert "pattern=" in ligne
    assert "max_length=36" in ligne


def test_an_ordinary_text_field_gains_no_pattern(tmp_path, capsys):
    """The witness: without it, a pattern put on every text field would pass the
    previous test."""
    (tmp_path / "spec.ml").write_text(SPEC, encoding="utf-8")
    compile_project(str(tmp_path / "spec.ml"), str(tmp_path))
    capsys.readouterr()
    genere = (tmp_path / "app.py").read_text(encoding="utf-8")
    ligne = next(li for li in genere.splitlines() if li.strip().startswith("libelle:"))
    assert "pattern=" not in ligne


def test_the_output_differs_from_a_string_field(tmp_path, capsys):
    """POINT 85: a rule that produces nothing is a lie. Declaring a `UUID` field
    rather than `String` must therefore change the produced code."""
    (tmp_path / "a.ml").write_text(SPEC, encoding="utf-8")
    (tmp_path / "b.ml").write_text(SPEC.replace("reference: UUID",
                                                "reference: String"),
                                   encoding="utf-8")
    compile_project(str(tmp_path / "a.ml"), str(tmp_path / "avec"))
    compile_project(str(tmp_path / "b.ml"), str(tmp_path / "sans"))
    capsys.readouterr()
    assert ((tmp_path / "avec" / "app.py").read_text(encoding="utf-8")
            != (tmp_path / "sans" / "app.py").read_text(encoding="utf-8"))


# --------------------------------------------------------------------------
# The checker, which is a client like any other
# --------------------------------------------------------------------------

def test_the_smoke_test_value_is_a_valid_uuid():
    """THIRD occurrence of the lesson of points 95 and 96, taken in advance this
    time rather than after a false diagnosis."""
    import re
    valeur = _sample_value("UUID", "reference")
    assert re.fullmatch(
        r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
        r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}", valeur)


def test_the_smoke_test_passes_on_a_uuid_spec(tmp_path, capsys):
    """End-to-end proof: the checker must turn GREEN a healthy application that
    declares a `UUID` field."""
    (tmp_path / "spec.ml").write_text(SPEC, encoding="utf-8")
    compile_project(str(tmp_path / "spec.ml"), str(tmp_path))
    ok, erreurs, _avertissements = run_smoke_test(str(tmp_path), say=lambda *a, **k: None)
    capsys.readouterr()
    assert ok, erreurs
    assert erreurs == []


# --------------------------------------------------------------------------
# Le comportement, contre un vrai serveur
# --------------------------------------------------------------------------

def _appel(url, corps=None, jeton=None):
    donnees = json.dumps(corps).encode() if corps is not None else None
    requete = urllib.request.Request(url, data=donnees)
    requete.add_header("Content-Type", "application/json")
    if jeton:
        requete.add_header("Authorization", f"Bearer {jeton}")
    try:
        with urllib.request.urlopen(requete, timeout=10) as reponse:
            return reponse.status, json.loads(reponse.read() or b"{}")
    except urllib.error.HTTPError as err:
        with err:
            return err.code, {}


@pytest.fixture(scope="module")
def application(tmp_path_factory):
    dossier = tmp_path_factory.mktemp("uuid")
    (dossier / "spec.ml").write_text(SPEC, encoding="utf-8")
    compile_project(str(dossier / "spec.ml"), str(dossier))
    port = _port_libre()
    processus = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app:app", "--host", "127.0.0.1",
         "--port", str(port)],
        cwd=str(dossier), stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(120):
            if processus.poll() is not None:
                pytest.fail(processus.stdout.read().decode("utf-8", "replace")[-2000:])
            try:
                with urllib.request.urlopen(base + "/docs", timeout=5) as reponse:
                    reponse.read()
                break
            except OSError:
                time.sleep(0.25)
        else:
            pytest.fail("le serveur n'a jamais répondu")
        _appel(base + "/register", {"username": "zoe", "password": "motdepasse1",
                                    "actor": "Client"})
        _, jeton = _appel(base + "/login", {"username": "zoe",
                                            "password": "motdepasse1"})
        yield base, jeton["access_token"]
    finally:
        arreter_processus(processus, delai=10)


def test_a_malformed_reference_is_refused(application):
    table = MAL_FORMES

    def cas(valeur):
        base, jeton = application
        code, _ = _appel(base + "/commande",
                         {"reference": valeur, "libelle": "essai"}, jeton)
        assert code == 422

    verifier_chaque_cas([(valeur,) for valeur in table], cas)


def test_a_well_formed_reference_stays_accepted(application):
    """The refusal's counter-proof: a too strict pattern would make the previous
    test pass while also rejecting real identifiers."""
    table = BIEN_FORMES

    def cas(valeur):
        base, jeton = application
        code, _ = _appel(base + "/commande",
                         {"reference": valeur, "libelle": "essai"}, jeton)
        assert code == 200

    verifier_chaque_cas([(valeur,) for valeur in table], cas)
