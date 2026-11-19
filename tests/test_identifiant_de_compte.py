"""Registration by email or phone — point 95.

`capability auth` had been declarative since brick 1: the block was parsed,
validated, went through the whole pipeline and changed NOTHING in generation.
This is its first real function — constraining the FORM of the account
identifier.

What the brick decides, and what does not go without saying:

* **the field stays `username` ON THE WIRE.** Renaming it `email` would have
  broken the registration form of every existing project for a cosmetic gain.
  The CONTRACT says which form it expects, and the interface AI labels the
  screen;
* **the substance is not validation, it is NORMALIZATION.** `Jean@Ex.com` and
  `jean@ex.com` are the same mailbox, `06 12 34 56 78` and `+33612345678` the
  same number. Without a canonical form, uniqueness can be bypassed — two
  accounts for one person — and login fails depending on how one types;
* **the same normalization in THREE places**: `/register`, `/login` and
  `manage.py`. A single omission creates accounts one cannot log into;
* **nothing declared = nothing changes.** Every spec written before this point
  compiles identically. Guessing "email by default" would lock every existing
  project at the first recompilation.
"""
import json
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request

import pytest

from monl.ast_validator import ASTValidationError, MonlAST
from monl.cli import compile_project
from monl.parser import parse_monl_string
from tests.support.server import free_port as _port_libre

SPEC = """app BancIdentifiant

entity Note
    texte: String

relation Client hasMany Note

actor Client selfRegister
actor Patron

rule Note.Read ownedBy Client

capability auth
    identifier: email, phone

workflow Ecrire for Client
    Create Note
    Read Note
"""

SANS_FORME = SPEC.replace("capability auth\n    identifier: email, phone\n",
                          "capability auth\n")


def _valide(spec):
    return MonlAST(parse_monl_string(spec)).validate_and_audit()


# --------------------------------------------------------------------------
# What compilation accepts and refuses
# --------------------------------------------------------------------------

def test_declared_forms_go_through_the_ast(capsys):
    ast = _valide(SPEC)
    assert ast["security"]["auth_identifier"] == ["email", "phone"]
    capsys.readouterr()


def test_without_declaration_no_constraint(capsys):
    """None and not []: "nothing declared" is not "no valid form"."""
    assert _valide(SANS_FORME)["security"]["auth_identifier"] is None
    capsys.readouterr()


def test_an_unknown_form_is_refused(capsys):
    with pytest.raises(ASTValidationError) as refus:
        _valide(SPEC.replace("identifier: email, phone", "identifier: pigeon"))
    assert "pigeon" in str(refus.value)
    capsys.readouterr()


def test_libre_combined_with_a_strict_form_is_refused(capsys):
    """'libre' accepts everything: combining it cancels the other without saying
    so. A written rule producing nothing is exactly what point 85 refuses."""
    with pytest.raises(ASTValidationError) as refus:
        _valide(SPEC.replace("identifier: email, phone", "identifier: email, libre"))
    assert "libre" in str(refus.value)
    capsys.readouterr()


def test_identifier_outside_auth_is_refused(capsys):
    """It is registration it constrains: elsewhere, it would mean nothing."""
    spec = SPEC.replace("capability auth\n    identifier: email, phone",
                        "capability auth\ncapability payment\n    identifier: email")
    with pytest.raises(ASTValidationError) as refus:
        _valide(spec)
    assert "auth" in str(refus.value)
    capsys.readouterr()


def test_a_spec_without_indented_block_compiles_as_before(tmp_path, capsys):
    """THE compatibility witness: the indented block is optional, and a dormant
    brick waking up must break nothing of what existed."""
    (tmp_path / "a.ml").write_text(SANS_FORME, encoding="utf-8")
    compile_project(str(tmp_path / "a.ml"), str(tmp_path / "a"))
    genere = (tmp_path / "a" / "app.py").read_text(encoding="utf-8")
    capsys.readouterr()
    assert "AUTH_IDENTIFIER_FORMS = []" in genere
    # The function exists anyway: a single code path, exercised everywhere.
    assert "def _normalize_identifier" in genere


# --------------------------------------------------------------------------
# Le comportement, contre un vrai serveur
# --------------------------------------------------------------------------

def _appel(url, corps=None, jeton=None, methode=None):
    donnees = json.dumps(corps).encode() if corps is not None else None
    requete = urllib.request.Request(url, data=donnees, method=methode)
    requete.add_header("Content-Type", "application/json")
    if jeton:
        requete.add_header("Authorization", f"Bearer {jeton}")
    try:
        with urllib.request.urlopen(requete, timeout=10) as reponse:
            return reponse.status, json.loads(reponse.read() or b"{}")
    except urllib.error.HTTPError as err:
        try:
            brut = err.read()
            return err.code, json.loads(brut or b"{}")
        except ValueError:
            return err.code, {"detail": brut.decode("utf-8", "replace")}
        finally:
            err.close()


@pytest.fixture
def server(tmp_path):
    (tmp_path / "spec.ml").write_text(SPEC, encoding="utf-8")
    compile_project(str(tmp_path / "spec.ml"), str(tmp_path))
    port = _port_libre()
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app:app", "--host", "127.0.0.1",
         "--port", str(port)],
        cwd=str(tmp_path), stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(120):
            if proc.poll() is not None:
                pytest.fail(proc.stdout.read().decode("utf-8", "replace")[-2000:])
            try:
                with urllib.request.urlopen(base + "/docs", timeout=5):
                    pass
                break
            except OSError:
                time.sleep(0.25)
        else:
            pytest.fail("le serveur n'a jamais répondu")
        yield base, tmp_path
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
        if proc.stdout is not None:
            proc.stdout.close()


def _degeler(dossier):
    """Rate limiting (5 tries/minute) would answer instead of the brick: it is not
    what is tested here."""
    conn = sqlite3.connect(str(dossier / "app.db"))
    conn.execute("DELETE FROM _monl_rate_limit")
    conn.commit()
    conn.close()


def _inscrire(base, dossier, login, mdp="motdepasse1"):
    _degeler(dossier)
    return _appel(base + "/register",
                  {"username": login, "password": mdp, "actor": "Client"})


def _connecter(base, dossier, login, mdp="motdepasse1"):
    _degeler(dossier)
    return _appel(base + "/login", {"username": login, "password": mdp})


@pytest.mark.parametrize("bon", ["alice@exemple.fr", "+33 6 12 34 56 78",
                                 "0612345699", "a.b+c@sous.domaine.co.uk"])
def test_declared_forms_are_accepted(server, bon):
    base, dossier = server
    code, reponse = _inscrire(base, dossier, bon)
    assert code == 200, reponse


@pytest.mark.parametrize("mauvais", ["alice", "pas-un-courriel", "alice@",
                                     "@exemple.fr", "12345", "alice exemple.fr"])
def test_other_forms_are_refused(server, mauvais):
    base, dossier = server
    code, reponse = _inscrire(base, dossier, mauvais)
    assert code == 422, reponse


def test_two_spellings_of_the_same_address_are_ONE_account(server):
    """THE heart of the brick. Without a canonical form, the uniqueness check can
    be bypassed by changing a capital letter: two accounts for one person, and
    the second gets the first one's orders."""
    base, dossier = server
    assert _inscrire(base, dossier, "alice@exemple.fr")[0] == 200

    code, reponse = _inscrire(base, dossier, "Alice@Exemple.FR")

    assert code == 409, reponse
    # And the message names what is really in conflict.
    assert "address" in reponse["detail"] or "identifier" in reponse["detail"]


def test_two_spellings_of_the_same_number_are_ONE_account(server):
    """A number is typed with spaces, dots or dashes — never twice the same way."""
    base, dossier = server
    assert _inscrire(base, dossier, "+33 6 12 34 56 78")[0] == 200
    for variante in ["+33612345678", "+33-6-12-34-56-78", "+33 (6) 12.34.56.78"]:
        code, reponse = _inscrire(base, dossier, variante)
        assert code == 409, f"{variante} a créé un second compte : {reponse}"


@pytest.mark.parametrize("variante", ["alice@exemple.fr", "Alice@Exemple.FR",
                                      "  alice@exemple.fr  ", "ALICE@EXEMPLE.FR"])
def test_login_works_however_one_types(server, variante):
    """The OTHER half, and the one people forget: normalizing on one side only
    creates accounts one can no longer log into."""
    base, dossier = server
    _inscrire(base, dossier, "alice@exemple.fr")
    code, reponse = _connecter(base, dossier, variante)
    assert code == 200, reponse


def test_a_malformed_identifier_at_login_reveals_nothing(server):
    """401 and not 422: login must not teach an attacker which form the accounts
    have — a malformed identifier simply does not exist."""
    base, dossier = server
    code, _ = _connecter(base, dossier, "alice")
    assert code == 401


def test_the_token_carries_the_canonical_form(server):
    """`sub` serves as identity throughout the backend: leaving the typed case in
    it would make two identities for one account."""
    import base64
    base, dossier = server
    _inscrire(base, dossier, "alice@exemple.fr")
    _, reponse = _connecter(base, dossier, "Alice@Exemple.FR")
    corps = reponse["access_token"].split(".")[1]
    corps += "=" * (-len(corps) % 4)
    assert json.loads(base64.urlsafe_b64decode(corps))["sub"] == "alice@exemple.fr"


def test_manage_py_normalizes_like_the_server(server):
    """The third place, the one people forget. An account provisioned offline
    with 'Patron@Ex.com' would be stored as is, and login — which normalizes —
    would look for 'patron@ex.com': a brand new account one cannot log into."""
    base, dossier = server
    proc = subprocess.run(
        [sys.executable, "manage.py", "adduser", "Patron@Exemple.FR", "Patron"],
        cwd=str(dossier), input="motdepasse1\nmotdepasse1\n",
        capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stdout + proc.stderr

    connexion = sqlite3.connect(str(dossier / "app.db"))
    try:
        stocke = connexion.execute(
            "SELECT username FROM _monl_users WHERE actor = 'Patron'").fetchone()[0]
    finally:
        connexion.close()
    assert stocke == "patron@exemple.fr", "manage.py a stocké la forme tapée"
    code, reponse = _connecter(base, dossier, "Patron@Exemple.FR")
    assert code == 200, reponse


def test_an_earlier_account_keeps_working(server):
    """The rule only applies to FUTURE registrations. Converting an existing
    account is impossible (an address is not invented) and deleting it would be
    worse — the server counts and names them at startup, as at point 89 for
    missing timestamps."""
    base, dossier = server
    # THE TRAP: without this account, the INSERT ... SELECT below copies
    # NOTHING (empty table), and the test would pass proving the opposite of
    # what it announces — a 401 for a nonexistent account instead of a 401 for
    # a wrong password. Same family of trap as at point 90 ("is there at least
    # one record?" passed as long as only ONE account was used).
    assert _inscrire(base, dossier, "alice@exemple.fr")[0] == 200
    conn = sqlite3.connect(str(dossier / "app.db"))
    # An account as it existed BEFORE the declaration: a nickname, and the hash
    # of a known password (alice's, hence 'motdepasse1').
    copies = conn.execute(
        "INSERT INTO _monl_users (username, password_hash, salt, actor, anon_handle)"
        " SELECT 'ancien_pseudo', password_hash, salt, 'Client', 'Anon#4242'"
        " FROM _monl_users WHERE username = 'alice@exemple.fr'").rowcount
    conn.commit()
    conn.close()
    assert copies == 1, "le compte antérieur n'a pas été créé : le test ne prouverait rien"

    code, reponse = _connecter(base, dossier, "ancien_pseudo")

    assert code == 200, f"un compte antérieur doit continuer de se connecter : {reponse}"


def test_the_smoke_test_respects_the_form_it_enforces(tmp_path, capsys):
    """THE bug found by applying the brick to a real project. The smoke test
    registered an account hard-coded as 'smoke': on any app declaring
    `identifier: email`, it got 422 on its OWN registration and declared the
    application broken. The verifier cannot ignore a rule it otherwise enforces.

    Seen on `projets/SneakerLab`: three errors (`/register` 422, `/login` 401,
    `POST /customer` 401) coming from neither the backend nor the frontend, but
    from monl itself."""
    from monl.smoke_test import run_smoke_test

    (tmp_path / "spec.ml").write_text(SPEC, encoding="utf-8")
    compile_project(str(tmp_path / "spec.ml"), str(tmp_path))
    capsys.readouterr()

    ok, erreurs, _avertissements = run_smoke_test(str(tmp_path), say=lambda *_: None)

    assert ok, erreurs


def test_the_smoke_identifier_follows_the_declared_form():
    """Three forms, three identifiers — and DISTINCT identifiers per rank: the
    privilege escalation loop tries one per provisioned role, and two
    registrations under the same identifier would give a 409 wrongly read as a
    role refusal."""
    from monl.smoke_test import _identifiant_smoke

    def contract(formes):
        return {"api": {"auth": {"register": {"identifier_forms": formes}}}}

    assert _identifiant_smoke(contract(["email"])) == "smoke@monl.test"
    assert _identifiant_smoke(contract(["phone"])).startswith("+336")
    assert _identifiant_smoke(contract([])) == "smoke"
    distincts = {_identifiant_smoke(contract(["email"]), r) for r in (0, 1, 2)}
    assert len(distincts) == 3


# --------------------------------------------------------------------------
# The calling code: '06…' and '+336…' are the same line — if we know from where
# --------------------------------------------------------------------------

SPEC_PREFIXE = SPEC.replace('    identifier: email, phone\n',
                            '    identifier: email, phone\n    phone_prefix: "+33"\n')


def test_a_malformed_calling_code_is_refused(capsys):
    for mauvais in ['"33"', '"+"', '"+abc"', '"+123456"']:
        with pytest.raises(ASTValidationError) as refus:
            _valide(SPEC_PREFIXE.replace('"+33"', mauvais))
        assert "international calling code" in str(refus.value)
    capsys.readouterr()


def test_a_calling_code_without_phone_form_is_refused(capsys):
    """It would apply to nothing: a written rule producing nothing is exactly what
    point 85 refuses."""
    spec = SPEC_PREFIXE.replace("identifier: email, phone", "identifier: email")
    with pytest.raises(ASTValidationError) as refus:
        _valide(spec)
    assert "phone" in str(refus.value)
    capsys.readouterr()


def test_the_contract_passes_the_calling_code_to_the_frontend(tmp_path, capsys):
    (tmp_path / "spec.ml").write_text(SPEC_PREFIXE, encoding="utf-8")
    compile_project(str(tmp_path / "spec.ml"), str(tmp_path))
    contract = json.loads(
        (tmp_path / "frontend_contract.json").read_text(encoding="utf-8")
    )
    inscription = contract["api"]["auth"]["register"]
    assert inscription["identifier_forms"] == ["email", "phone"]
    assert inscription["phone_prefix"] == "+33"
    assert "+33" in inscription["note"]
    assert "+33" in (tmp_path / "docs/FRONTEND_PROMPT.md").read_text(encoding="utf-8")
    capsys.readouterr()


@pytest.fixture
def prefixed_server(tmp_path):
    (tmp_path / "spec.ml").write_text(SPEC_PREFIXE, encoding="utf-8")
    compile_project(str(tmp_path / "spec.ml"), str(tmp_path))
    port = _port_libre()
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app:app", "--host", "127.0.0.1",
         "--port", str(port)],
        cwd=str(tmp_path), stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(120):
            if proc.poll() is not None:
                pytest.fail(proc.stdout.read().decode("utf-8", "replace")[-2000:])
            try:
                with urllib.request.urlopen(base + "/docs", timeout=5):
                    pass
                break
            except OSError:
                time.sleep(0.25)
        else:
            pytest.fail("le serveur n'a jamais répondu")
        yield base, tmp_path
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
        if proc.stdout is not None:
            proc.stdout.close()


def test_national_and_international_are_ONE_account(prefixed_server):
    """THE hole found by testing the brick on the real site: '06 12 34 56 78' and
    '+33612345678' designate the same line and made two accounts. monl cannot
    guess it — the calling code depends on the country — so it has it DECLARED."""
    base, dossier = prefixed_server
    assert _inscrire(base, dossier, "06 12 34 56 78")[0] == 200
    for variante in ["+33612345678", "+33 6 12 34 56 78", "0612345678"]:
        code, reponse = _inscrire(base, dossier, variante)
        assert code == 409, f"{variante} a créé un second compte : {reponse}"


def test_the_stored_form_is_the_international_one(prefixed_server):
    """The canonical form must be the one that does not depend on the country: it
    is the one that will someday be sent to a provider, and it does not get
    reread."""
    base, dossier = prefixed_server
    _inscrire(base, dossier, "06 12 34 56 78")
    connexion = sqlite3.connect(str(dossier / "app.db"))
    try:
        stocke = connexion.execute(
            "SELECT username FROM _monl_users").fetchone()[0]
    finally:
        connexion.close()
    assert stocke == "+33612345678"


@pytest.mark.parametrize("notation", ["06 12 34 56 78", "+33612345678",
                                      "0612345678", "+33 6 12 34 56 78"])
def test_login_works_in_both_notations(prefixed_server, notation):
    base, dossier = prefixed_server
    _inscrire(base, dossier, "06 12 34 56 78")
    code, reponse = _connecter(base, dossier, notation)
    assert code == 200, reponse


def test_without_declared_calling_code_both_notations_stay_distinct(server):
    """The STATED limit, and its witness. Without `phone_prefix`, monl does not
    know which country a '06…' comes from: it attaches it to nothing rather than
    guessing France. The test exists so that this behavior is a visible choice
    and not an oversight — the declaration is what opens it."""
    base, dossier = server
    assert _inscrire(base, dossier, "06 12 34 56 78")[0] == 200
    assert _inscrire(base, dossier, "+33612345678")[0] == 200


# --------------------------------------------------------------------------
# POINT 138 — a country WITHOUT a trunk zero
#
# Everything above tests France, where the national number carries a leading
# `0` that the international form replaces. The rule had been written from this
# example, then generalized without being tested elsewhere: it canonicalized
# ONLY numbers starting with zero.
#
# In Benin — the target market, and `projets/AtelierNaya`'s country — the local
# number is written without a leading zero. `phone_prefix: "+229"` therefore
# produced NOTHING: the person registered as "97 12 34 56" was not recognized
# as "+229 97 12 34 56", exactly the two accounts the calling code exists to
# prevent. A declared rule producing nothing is what point 85 refuses.
# --------------------------------------------------------------------------
SPEC_BENIN = SPEC.replace('    identifier: email, phone\n',
                          '    identifier: phone\n    phone_prefix: "+229"\n')


@pytest.fixture
def benin_server(tmp_path):
    (tmp_path / "spec.ml").write_text(SPEC_BENIN, encoding="utf-8")
    compile_project(str(tmp_path / "spec.ml"), str(tmp_path))
    port = _port_libre()
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app:app", "--host", "127.0.0.1",
         "--port", str(port)],
        cwd=str(tmp_path), stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(120):
            if proc.poll() is not None:
                pytest.fail(proc.stdout.read().decode("utf-8", "replace")[-2000:])
            try:
                with urllib.request.urlopen(base + "/docs", timeout=5):
                    pass
                break
            except OSError:
                time.sleep(0.25)
        else:
            pytest.fail("le serveur n'a jamais répondu")
        yield base, tmp_path
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
        if proc.stdout is not None:
            proc.stdout.close()


def test_a_number_without_leading_zero_is_internationalized(benin_server):
    """The heart of the defect. Before, the STORED form remained "97123456" — a
    number no provider can reach and that cannot be read outside Benin."""
    base, dossier = benin_server
    assert _inscrire(base, dossier, "97 12 34 56")[0] == 200
    connexion = sqlite3.connect(str(dossier / "app.db"))
    try:
        stocke = connexion.execute("SELECT username FROM _monl_users").fetchone()[0]
    finally:
        connexion.close()
    assert stocke == "+22997123456"


@pytest.mark.parametrize("notation", ["97123456", "97 12 34 56", "97-12-34-56",
                                      "+22997123456", "+229 97 12 34 56",
                                      "22997123456"])
def test_every_way_of_writing_a_beninese_number_opens_the_same_account(
        benin_server, notation):
    base, dossier = benin_server
    _inscrire(base, dossier, "97123456")
    code, reponse = _connecter(base, dossier, notation)
    assert code == 200, reponse


def test_an_already_international_number_is_not_prefixed_twice(benin_server):
    """The trap the fix could introduce: "22997123456", typed without the `+`,
    must not become "+22922997123456" — that would be a THIRD account, created by
    the fix itself."""
    base, dossier = benin_server
    assert _inscrire(base, dossier, "22997123456")[0] == 200
    connexion = sqlite3.connect(str(dossier / "app.db"))
    try:
        stocke = connexion.execute("SELECT username FROM _monl_users").fetchone()[0]
    finally:
        connexion.close()
    assert stocke == "+22997123456"
    assert _inscrire(base, dossier, "97123456")[0] == 409


def test_manage_py_normalizes_like_the_server_without_leading_zero(benin_server):
    """Point 95, the third place — the one people forget. Diverging here creates
    an account `manage.py` can write and nobody can open."""
    base, dossier = benin_server
    sortie = subprocess.run(
        [sys.executable, "manage.py", "adduser", "97 99 88 77", "Patron"],
        cwd=str(dossier), input="motdepasse1\nmotdepasse1\n",
        capture_output=True, text=True, timeout=60)
    assert sortie.returncode == 0, sortie.stdout + sortie.stderr
    code, reponse = _connecter(base, dossier, "+22997998877")
    assert code == 200, reponse
