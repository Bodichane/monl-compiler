"""Brick 22: the number a human reads and dictates — point 102.

Why the brick. `exemples/02_boutique.ml` declared `Order.reference: UUID` — a
field the CLIENT filled, and which since point 101 requires a UUID's canonical
form. But nobody dictates `3f2504e0-4f89-41d3-9a0c-0305e82c3301` over the
phone. An order book wants "CMD-2026-0001", and that number is not the
client's data: the seller assigns it.

    rule Order.reference numbered "CMD-{YYYY}-{NNNN}"

What the brick decides, and what did not go without saying:

* **the counter lives in a SYSTEM table.** `MAX(...) + 1` over the business
  table would give back a deleted record's number — two invoices with the
  same reference — and would go wrong as soon as two creations cross.
  `test_the_number_does_not_go_back_after_a_deletion` proves it;
* **assignment lives IN the creation transaction.** Outside it, a refused
  insertion would leave the counter advanced;
* **the keyword is not `reference`.** It would be confused with the field name
  it is almost always given: `rule Order.reference reference "…"` does not
  read;
* **earlier records stay WITHOUT a number.** Numbering them at startup would
  claim an arrival order the server did not observe — and on an order book, an
  invented number ends up on an invoice. It is point 89's lesson, word for
  word.
"""
import json
import sqlite3
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

import pytest

from monl.ast_validator import ASTValidationError, MonlAST
from monl.cli import compile_project
from monl.parser import parse_monl_string
from tests.support.process import close_tubes, stop_process
from tests.support.server import free_port as _port_free

SPEC = """app BancNumero

entity Commande
    reference: String
    libelle: String

actor Client selfRegister

relation Client hasMany Commande

rule Commande.Read ownedBy Client
rule Commande.reference numbered "CMD-{YYYY}-{NNNN}"

workflow Acheter for Client
    Create Commande
    Read Commande
    Update Commande
    Delete Commande
"""


def _valid(spec):
    return MonlAST(parse_monl_string(spec)).validate_and_audit()


# --------------------------------------------------------------------------
# What compilation must refuse
# --------------------------------------------------------------------------

def test_the_bench_spec_compiles(capsys):
    ast = _valid(SPEC)
    rule = ast["security"]["numbered_fields"][0]
    assert rule == {"entity": "Commande", "field": "reference",
                     "format": "CMD-{YYYY}-{NNNN}", "periode": "YYYY"}
    capsys.readouterr()


def test_a_nonexistent_field_is_refused(capsys):
    with pytest.raises(ASTValidationError) as refusal:
        _valid(SPEC.replace("Commande.reference numbered",
                             "Commande.fantome numbered"))
    assert "field does not exist" in str(refusal.value)
    capsys.readouterr()


def test_a_non_text_field_is_refused(capsys):
    spec = SPEC.replace("    reference: String", "    reference: Integer")
    with pytest.raises(ASTValidationError) as refusal:
        _valid(spec)
    assert "String" in str(refusal.value)
    capsys.readouterr()


def test_a_uuid_field_is_refused_by_name(capsys):
    """POINT 101: it is the type one is tempted to choose for a reference, and
    since that point it checks its form — a readable number would never fit. The
    message must SAY so, otherwise the author tries and does not understand."""
    spec = SPEC.replace("    reference: String", "    reference: UUID")
    with pytest.raises(ASTValidationError) as refusal:
        _valid(spec)
    assert "point 101" in str(refusal.value)
    capsys.readouterr()


def test_a_hidden_field_is_refused(capsys):
    spec = SPEC.replace("rule Commande.reference numbered",
                        "rule Commande.reference hidden\nrule Commande.reference numbered")
    with pytest.raises(ASTValidationError) as refusal:
        _valid(spec)
    assert "hidden" in str(refusal.value)
    capsys.readouterr()


def test_two_rules_on_the_same_field_are_refused(capsys):
    spec = SPEC.replace('rule Commande.reference numbered "CMD-{YYYY}-{NNNN}"',
                        'rule Commande.reference numbered "CMD-{YYYY}-{NNNN}"\n'
                        'rule Commande.reference numbered "AUTRE-{NNNN}"')
    with pytest.raises(ASTValidationError) as refusal:
        _valid(spec)
    assert "only one is allowed" in str(refusal.value)
    capsys.readouterr()


def test_a_template_without_sequence_is_refused(capsys):
    """THE refusal that carries the brick: without a sequence, all records would
    carry the same number — which is not one (point 85)."""
    with pytest.raises(ASTValidationError) as refusal:
        _valid(SPEC.replace('"CMD-{YYYY}-{NNNN}"', '"CMD-{YYYY}"'))
    assert "has no sequence" in str(refusal.value)
    capsys.readouterr()


def test_two_sequences_are_refused(capsys):
    with pytest.raises(ASTValidationError) as refusal:
        _valid(SPEC.replace('"CMD-{YYYY}-{NNNN}"', '"CMD-{NN}-{NNNN}"'))
    assert "which one to increment" in str(refusal.value)
    capsys.readouterr()


def test_an_unknown_milestone_is_refused(capsys):
    with pytest.raises(ASTValidationError) as refusal:
        _valid(SPEC.replace('"CMD-{YYYY}-{NNNN}"', '"CMD-{MOIS}-{NNNN}"'))
    assert "which has no meaning" in str(refusal.value)
    capsys.readouterr()


def test_an_orphan_brace_is_refused(capsys):
    with pytest.raises(ASTValidationError) as refusal:
        _valid(SPEC.replace('"CMD-{YYYY}-{NNNN}"', '"CMD-{YYYY-{NNNN}"'))
    assert "unmatched brace" in str(refusal.value)
    capsys.readouterr()


def test_a_month_without_year_is_refused(capsys):
    """'CMD-{MM}-{NNNN}' gives 'CMD-03-0001' again every March. The unique index
    would catch it — a year later, and in production."""
    with pytest.raises(ASTValidationError) as refusal:
        _valid(SPEC.replace('"CMD-{YYYY}-{NNNN}"', '"CMD-{MM}-{NNNN}"'))
    assert "without '{YYYY}'" in str(refusal.value)
    capsys.readouterr()


def test_a_bound_on_a_numbered_field_is_refused(capsys):
    """Inherited from point 85's cross-check without one more line: the field is
    not in the input schema, a bound would have nowhere to live."""
    with pytest.raises(ASTValidationError) as refusal:
        _valid(SPEC + "rule Commande.reference max 10\n")
    assert "reference" in str(refusal.value)
    capsys.readouterr()


# --------------------------------------------------------------------------
# What generation must write
# --------------------------------------------------------------------------

def _compile(tmp_path, spec=SPEC, name="p"):
    (tmp_path / f"{name}.ml").write_text(spec, encoding="utf-8")
    contract = compile_project(str(tmp_path / f"{name}.ml"), str(tmp_path / name))
    return contract, (tmp_path / name / "app.py").read_text(encoding="utf-8")


def test_the_field_leaves_the_input_schema(tmp_path, capsys):
    _, generated = _compile(tmp_path)
    capsys.readouterr()
    debut = generated.index("class CommandeSchema")
    assert "reference" not in generated[debut:debut + 300]


def test_the_field_leaves_the_update_set(tmp_path, capsys):
    """An order number that changes is no longer a reference: the customer wrote
    it down, so did the seller."""
    _, generated = _compile(tmp_path)
    capsys.readouterr()
    line = next(li for li in generated.splitlines() if 'UPDATE "commande" SET' in li)
    assert '"reference"' not in line
    assert '"libelle"' in line


def test_a_unique_index_is_created_without_declaring_it(tmp_path, capsys):
    """A duplicate number is not a number. Requiring 'unique' in the spec would
    make the guarantee depend on a line one can forget to write."""
    _, generated = _compile(tmp_path)
    capsys.readouterr()
    assert "idx_unique_commande_reference" in generated


def test_the_output_differs_without_the_rule(tmp_path, capsys):
    """POINT 85: the test forbidding a rule that produces nothing."""
    _, with_ = _compile(tmp_path, SPEC, "avec")
    _, sans = _compile(
        tmp_path, SPEC.replace('rule Commande.reference numbered "CMD-{YYYY}-{NNNN}"\n', ""),
        "sans")
    capsys.readouterr()
    assert with_ != sans


def test_the_contract_announces_a_read_only_field(tmp_path, capsys):
    contract, _ = _compile(tmp_path)
    capsys.readouterr()
    field = next(f for f in contract["entities"]["Commande"]["fields"]
                 if f["name"] == "reference")
    assert field["server_generated"] is True
    assert field["numbered_as"] == "CMD-{YYYY}-{NNNN}"
    assert "Do not send it" in field["note"]
    route = next(r for r in contract["routes"]
                 if r["method"] == "POST" and r["path"] == "/commande")
    assert "reference" not in route["request_fields"]


# --------------------------------------------------------------------------
# Le comportement, contre un vrai serveur
# --------------------------------------------------------------------------

def _call(url, body=None, token=None, method=None):
    donnees = json.dumps(body).encode() if body is not None else None
    query = urllib.request.Request(url, data=donnees, method=method)
    query.add_header("Content-Type", "application/json")
    if token:
        query.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(query, timeout=20) as response:
            return response.status, json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as err:
        with err:
            return err.code, {}


def _start(folder, port):
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app:app", "--host", "127.0.0.1",
         "--port", str(port)],
        cwd=str(folder), stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    base = f"http://127.0.0.1:{port}"
    for _ in range(120):
        if process.poll() is not None:
            output = process.stdout.read().decode("utf-8", "replace")[-2000:]
            close_tubes(process)
            pytest.fail(output)
        try:
            with urllib.request.urlopen(base + "/docs", timeout=5) as response:
                response.read()
            return process, base
        except OSError:
            time.sleep(0.25)
    stop_process(process)
    pytest.fail("the server never answered")


def _stop(process):
    process.terminate()
    try:
        # communicate() reads to the end AND closes the pipes.
        return process.communicate(timeout=10)[0].decode("utf-8", "replace")
    except subprocess.TimeoutExpired:
        stop_process(process)
        return ""


@pytest.fixture
def book(tmp_path):
    (tmp_path / "spec.ml").write_text(SPEC, encoding="utf-8")
    compile_project(str(tmp_path / "spec.ml"), str(tmp_path))
    process, base = _start(tmp_path, _port_free())
    try:
        _call(base + "/register", {"username": "zoe", "password": "motdepasse1",
                                    "actor": "Client"})
        _, token = _call(base + "/login", {"username": "zoe",
                                            "password": "motdepasse1"})
        yield base, token["access_token"], tmp_path
    finally:
        _stop(process)


def _number(base, identifier, token):
    _, response = _call(f"{base}/commande/{identifier}", token=token)
    return response["data"]["reference"]


def test_the_numbers_follow_each_other(book):
    base, token, _ = book
    numbers = []
    for i in range(3):
        _, created = _call(base + "/commande", {"libelle": f"achat {i}"}, token)
        numbers.append(_number(base, created["id"], token))
    year = time.gmtime().tm_year
    assert numbers == [f"CMD-{year}-0001", f"CMD-{year}-0002", f"CMD-{year}-0003"]


def test_the_client_cannot_choose_its_number(book):
    """The field is not in the schema: sending it does nothing. It is the
    behavior of the whole family of server-filled fields."""
    base, token, _ = book
    _, created = _call(base + "/commande",
                     {"libelle": "triche", "reference": "CMD-1999-0001"}, token)
    assert _number(base, created["id"], token) != "CMD-1999-0001"


def test_the_number_does_not_move_on_update(book):
    base, token, _ = book
    _, created = _call(base + "/commande", {"libelle": "achat"}, token)
    before = _number(base, created["id"], token)
    code, _ = _call(f"{base}/commande/{created['id']}",
                     {"libelle": "renommé", "reference": "CMD-1999-9999"},
                     token, method="PUT")
    assert code == 200
    assert _number(base, created["id"], token) == before


def test_the_number_does_not_go_back_after_a_deletion(book):
    """THE system table's reason for being. With `MAX(...) + 1`, deleting the
    last order would REASSIGN its number — two invoices, one reference."""
    base, token, _ = book
    _, premiere = _call(base + "/commande", {"libelle": "a"}, token)
    _, seconde = _call(base + "/commande", {"libelle": "b"}, token)
    second_number = _number(base, seconde["id"], token)
    _call(f"{base}/commande/{seconde['id']}", token=token, method="DELETE")
    _, third = _call(base + "/commande", {"libelle": "c"}, token)
    assert _number(base, third["id"], token) != second_number
    assert _number(base, premiere["id"], token).endswith("0001")


def test_two_simultaneous_creations_do_not_share_a_number(book):
    """Eight concurrent creations: eight distinct numbers, and no failure.

    What this test REALLY proves, and no more: that contention produces neither
    collision, nor "database is locked", nor 500. It does not by itself settle
    between an atomic counter and a `MAX(...) + 1` — SQLite serializes writes,
    and that serialization would hide the difference under such a modest load.
    `test_the_number_does_not_go_back_after_a_deletion` settles between the two
    designs."""
    base, token, _ = book
    obtained, lock = [], threading.Lock()

    def commander(rang):
        code, created = _call(base + "/commande", {"libelle": f"lot {rang}"}, token)
        with lock:
            obtained.append((code, created.get("id")))

    fils = [threading.Thread(target=commander, args=(i,)) for i in range(8)]
    for f in fils:
        f.start()
    for f in fils:
        f.join(timeout=30)

    assert all(code == 200 for code, _ in obtained), obtained
    numbers = [_number(base, identifier, token) for _, identifier in obtained]
    assert len(set(numbers)) == 8, numbers


def test_an_earlier_period_does_not_shift_the_sequence(book):
    """The sequence restarts at 1 every year: a counter left by last year must
    not be picked up."""
    base, token, folder = book
    login = sqlite3.connect(str(folder / "app.db"))
    login.execute(
        "INSERT INTO _monl_sequences (entite, champ, periode, dernier) "
        "VALUES ('Commande', 'reference', '2019', 41)")
    login.commit()
    login.close()
    _, created = _call(base + "/commande", {"libelle": "cette année"}, token)
    assert _number(base, created["id"], token).endswith("0001")


def test_earlier_records_stay_without_number(tmp_path):
    """POINT 89, word for word: the additive migration catches up a column, never
    its content. Numbering afterwards would invent an arrival order."""
    sans = SPEC.replace('rule Commande.reference numbered "CMD-{YYYY}-{NNNN}"\n', "")
    (tmp_path / "spec.ml").write_text(sans, encoding="utf-8")
    compile_project(str(tmp_path / "spec.ml"), str(tmp_path))
    process, base = _start(tmp_path, _port_free())
    _call(base + "/register", {"username": "zoe", "password": "motdepasse1",
                                "actor": "Client"})
    _, token = _call(base + "/login", {"username": "zoe", "password": "motdepasse1"})
    token = token["access_token"]
    _call(base + "/commande", {"libelle": "avant la règle", "reference": ""}, token)
    _stop(process)

    # The rule arrives now, on the already populated database.
    (tmp_path / "spec.ml").write_text(SPEC, encoding="utf-8")
    compile_project(str(tmp_path / "spec.ml"), str(tmp_path))
    process, base = _start(tmp_path, _port_free())
    _, nouvelle = _call(base + "/commande", {"libelle": "après"}, token)
    log = _stop(process)

    login = sqlite3.connect(str(tmp_path / "app.db"))
    try:
        refs = [r[0] for r in login.execute(
            'SELECT "reference" FROM "commande" ORDER BY id').fetchall()]
    finally:
        login.close()
    # The old one keeps what it had, the new one starts again from 1.
    assert refs[-1].endswith("0001")
    assert refs[0] != refs[-1]
    assert "remain unnumbered" in log or refs[0] == ""


def test_a_duplicate_number_returns_409_never_a_success(book):
    """WORKSTREAM A1, defect found in review. Classifying integrity errors by
    SQLSTATE had left the `except` ending WITHOUT `raise`: an integrity violation
    of an unnamed kind left the block raising nothing, and the route went on to
    its `return {'status': 'success'}` — after a `rollback`. Measured here: the
    duplicate reference returned 500 (`UnboundLocalError` on `row_id`) instead
    of a 409, and the same hole would have announced as written what had just
    been undone as soon as `row_id` was already bound.

    The reset counter is not a textbook hypothesis: it is what restoring a
    partial backup produces. An `except` that does not end in a `raise` is an
    `except` that lies."""
    base, token, folder = book
    code, _ = _call(base + "/commande", {"libelle": "premiere"}, token)
    assert code == 200

    conn = sqlite3.connect(str(folder / "app.db"))
    conn.execute("UPDATE _monl_sequences SET dernier = 0")
    conn.commit()
    conn.close()

    code, response = _call(base + "/commande", {"libelle": "doublon"}, token)
    assert code == 409, f"expected 409, got {code}: {response}"
    assert "status" not in response or response.get("status") != "success"

    conn = sqlite3.connect(str(folder / "app.db"))
    lines = conn.execute("SELECT COUNT(*) FROM commande").fetchone()[0]
    conn.close()
    assert lines == 1, "the refused write must have left nothing in the database"


def test_no_integrity_except_ends_without_raise(tmp_path):
    """The previous test's structural witness: it holds for ALL routes, not only
    the one the bench exercises. An integrity block not ending with a `raise` lets
    a cancelled write pass for a success."""
    (tmp_path / "spec.ml").write_text(SPEC, encoding="utf-8")
    compile_project(str(tmp_path / "spec.ml"), str(tmp_path))
    lines = (tmp_path / "app.py").read_text(encoding="utf-8").splitlines()

    # `init_db`'s integrity block is EXCLUDED, on purpose: on a database
    # already containing duplicates, it NAMES the field and lets the server run
    # (point 85). Forcing a `raise` on it would immobilize an existing project
    # at startup. The witness is therefore only about the routes, hence the cut
    # at the first decorator.
    premiere_route = next(i for i, line in enumerate(lines)
                          if line.startswith("@app."))
    blocks = [i for i, line in enumerate(lines)
             if "except _DATABASE_INTEGRITY_ERRORS" in line and i > premiere_route]
    assert blocks, "no integrity block generated: the witness would prove nothing"
    for start in blocks:
        indentation = len(lines[start]) - len(lines[start].lstrip())
        last = None
        for line in lines[start + 1:]:
            if not line.strip():
                continue
            if len(line) - len(line.lstrip()) <= indentation:
                break
            last = line.strip()
        assert last is not None
        assert last.startswith("raise") or last.endswith("))"), (
            f"the integrity block at line {start + 1} ends with {last!r}: "
            "it must end in a raise")
