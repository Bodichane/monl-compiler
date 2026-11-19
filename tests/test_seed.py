"""ADDED (frontend roadmap, 'seed' block): checks the demo data —
validation at compile time, idempotent insertion at startup (no duplicates
on restart, real data preserved), and synthetic filling of 'generated'
fields (anonymous pseudonym).
"""
import subprocess
import sys
import tempfile
import time

import pytest
import requests

from monl.ast_validator import ASTValidationError, MonlAST
from monl.generator import MonlSecureGenerator
from monl.parser import parse_monl_string
from tests.support.server import free_port as _find_free_port

SEED_SPEC = """app Boutique

entity Product
    name: String
    price: Money
    stock: Integer

actor Customer selfRegister

rule Product.Read public

workflow Browse for Customer
    Read Product

seed Product
    name: "Chaise", price: 249.90, stock: 12
    name: "Lampe", price: 89.00, stock: 3
"""


def _validate(spec):
    return MonlAST(parse_monl_string(spec)).validate_and_audit()


def test_seed_is_parsed_and_exported():
    ast = _validate(SEED_SPEC)
    seeds = ast["seeds"]
    assert len(seeds) == 1
    assert seeds[0]["entity"] == "Product"
    assert len(seeds[0]["rows"]) == 2
    assert seeds[0]["rows"][0]["name"] == "Chaise"
    assert seeds[0]["rows"][0]["price"] == 249.90


def test_seed_unknown_entity_is_rejected():
    spec = SEED_SPEC.replace("seed Product", "seed Ghost")
    with pytest.raises(ASTValidationError, match="does not exist"):
        _validate(spec)


def test_seed_unknown_field_is_rejected():
    spec = SEED_SPEC.replace('name: "Chaise", price: 249.90, stock: 12',
                             'name: "Chaise", couleur: "rouge"')
    with pytest.raises(ASTValidationError, match="is not declared on"):
        _validate(spec)


def test_seed_type_mismatch_is_rejected():
    # price (Money) expects a number, not a string.
    spec = SEED_SPEC.replace('name: "Chaise", price: 249.90, stock: 12',
                             'name: "Chaise", price: "cher", stock: 12')
    with pytest.raises(ASTValidationError, match="expects a number"):
        _validate(spec)


def test_generated_field_is_filled_in_seed():
    # A 'generated' field not provided in the seed gets a synthetic pseudonym
    # (as on a real creation, assigned by the server).
    spec = """app S

entity Post
    content: Text
    author: String

actor Member selfRegister

rule Post.Read public
rule Post.author generated

workflow W for Member
    Create Post
    Read Post

seed Post
    content: "Bonjour"
    content: "Deuxième"
"""
    ast = _validate(spec)
    with tempfile.TemporaryDirectory() as workdir:
        gen = MonlSecureGenerator(ast, output_dir=workdir)
        seed_data = gen._compute_seed_data()
    # BRICK 21 (point 100): each entry is now a pair {"values": …, "parent": …}
    # — a child's attachment cannot live in the row itself, the column carrying
    # it not being a declared field. A seed without a parent leaves it at None,
    # and the values are unchanged.
    rows = [entree["values"] for entree in seed_data["post"]]
    assert all(entree["parent"] is None for entree in seed_data["post"])
    assert len(rows) == 2
    assert all(r["author"].startswith("Anon#") for r in rows)
    assert rows[0]["author"] != rows[1]["author"]  # uniques


# --- Idempotent insertion at startup (real server) ---

def _wait(port, timeout=15):
    start = time.time()
    while time.time() - start < timeout:
        try:
            requests.get(f"http://127.0.0.1:{port}/docs", timeout=1)
            return True
        except requests.exceptions.ConnectionError:
            time.sleep(0.3)
    return False


def _serve(workdir, port):
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app:app", "--port", str(port)],
        cwd=workdir, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    assert _wait(port), "le serveur n'a pas démarré"
    return proc


def _stop(proc):
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


def test_seed_populates_on_startup_and_is_idempotent():
    ast = _validate(SEED_SPEC)
    with tempfile.TemporaryDirectory() as workdir:
        MonlSecureGenerator(ast, output_dir=workdir).generate_all()

        # 1st start: the public showcase is already populated.
        port = _find_free_port()
        proc = _serve(workdir, port)
        try:
            data = requests.get(f"http://127.0.0.1:{port}/product?limit=10").json()
            assert data["total"] == 2
        finally:
            _stop(proc)

        # 2nd start: no duplicates (idempotent insertion).
        port = _find_free_port()
        proc = _serve(workdir, port)
        try:
            data = requests.get(f"http://127.0.0.1:{port}/product?limit=10").json()
            assert data["total"] == 2, "le seed a été réinséré (doublons)"
        finally:
            _stop(proc)
