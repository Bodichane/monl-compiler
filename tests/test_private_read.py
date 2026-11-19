"""Reads are sealed between accounts (beta 3).

Defect fixed: 'ownedBy' only protected writes. On an expense-tracking
application, two distinct accounts read each other's data — 'GET /expense'
returned everything, and 'GET /expense/{id}' answered 200 on someone else's
record. Only 'PUT' was refused.

The test starts a real generated application and replays the whole scenario.
"""
import subprocess
import sys
import tempfile

import pytest
import requests

from monl.ast_validator import MonlAST
from monl.generator import MonlSecureGenerator
from monl.parser import parse_monl_string
from tests.support.server import uvicorn_server

SPEC_PRIVATE = """app Depenses

entity Expense
    label: String
    amount: Money

entity User
    displayName: String

relation User hasMany Expense

actor User selfRegister
actor Auditor

rule Expense.Read ownedBy User
rule Expense.Update ownedBy User
rule Expense.Delete ownedBy User

workflow MesDepenses for User
    Create Expense
    Read Expense
    Update Expense
    Delete Expense

workflow Controle for Auditor
    Read Expense
"""


def _account(base, name):
    requests.post(f"{base}/register",
                  json={"username": name, "password": "motdepasse123", "actor": "User"})
    token = requests.post(f"{base}/login",
                          json={"username": name, "password": "motdepasse123"}).json()
    return {"Authorization": "Bearer " + token["access_token"]}


@pytest.fixture(scope="module")
def application():
    """Compiles the spec, starts the server, hands it to the caller."""
    with tempfile.TemporaryDirectory() as folder:
        ast = MonlAST(parse_monl_string(SPEC_PRIVATE)).validate_and_audit()
        MonlSecureGenerator(ast, output_dir=folder).generate_all()
        with uvicorn_server(folder) as base:
            yield base, folder


def test_an_account_does_not_read_another_accounts_data(application):
    base, folder = application
    alice, bob = _account(base, "alice"), _account(base, "bob")
    created = requests.post(f"{base}/expense", headers=alice,
                         json={"label": "Consultation", "amount": 120.0})
    assert created.status_code == 200
    id_alice = created.json()["id"]
    requests.post(f"{base}/expense", headers=bob, json={"label": "Courses", "amount": 42.0})

    # List: Bob only sees his own, and the total only counts his own.
    view_bob = requests.get(f"{base}/expense", headers=bob).json()
    assert view_bob["total"] == 1, view_bob
    assert [d["label"] for d in view_bob["data"]] == ["Courses"]

    # Direct access: 404 and not 403 — a 403 would confirm that someone else's
    # record exists, hence allow counting it by enumeration.
    assert requests.get(f"{base}/expense/{id_alice}", headers=bob).status_code == 404
    # Writing stays refused too (historical behavior kept).
    assert requests.put(f"{base}/expense/{id_alice}", headers=bob,
                        json={"label": "x", "amount": 1.0}).status_code in (403, 404)
    # The owner does reach their own.
    assert requests.get(f"{base}/expense/{id_alice}", headers=alice).status_code == 200


def test_an_allowed_third_role_still_sees_everything(application):
    """The filter targets the owning actor, not the other allowed roles.

    Without this nuance, a shop's manager would see no order and the ownership
    check would break the applications it is meant to protect.
    """
    base, folder = application
    subprocess.run([sys.executable, "manage.py", "adduser", "inspecteur", "Auditor"],
                   cwd=folder, input="motdepasse123\nmotdepasse123\n",
                   capture_output=True, text=True)
    token = requests.post(f"{base}/login",
                          json={"username": "inspecteur", "password": "motdepasse123"}).json()
    auditor = {"Authorization": "Bearer " + token["access_token"]}
    view = requests.get(f"{base}/expense", headers=auditor).json()
    assert view["total"] >= 2, view


def test_ownedby_on_create_is_refused_at_compile_time():
    """A rule without effect must fail, not be silently ignored."""
    from monl.ast_validator import ASTValidationError
    spec = SPEC_PRIVATE.replace("rule Expense.Read ownedBy User",
                               "rule Expense.Create ownedBy User")
    with pytest.raises(ASTValidationError, match="Create"):
        MonlAST(parse_monl_string(spec)).validate_and_audit()
