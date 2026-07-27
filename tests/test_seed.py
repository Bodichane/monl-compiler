"""AJOUT (roadmap frontend, bloc 'seed') : vérifie les données de
démonstration — validation à la compilation, insertion idempotente au
démarrage (pas de doublons au redémarrage, données réelles préservées), et
remplissage synthétique des champs 'generated' (pseudonyme anonyme).
"""
import os
import socket
import subprocess
import sys
import tempfile
import time

import pytest
import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../src"))

from ast_validator import ASTValidationError, MonlAST
from generator import MonlSecureGenerator
from parser import parse_monl_string

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
    with pytest.raises(ASTValidationError, match="n'existe pas"):
        _validate(spec)


def test_seed_unknown_field_is_rejected():
    spec = SEED_SPEC.replace('name: "Chaise", price: 249.90, stock: 12',
                             'name: "Chaise", couleur: "rouge"')
    with pytest.raises(ASTValidationError, match="n'est pas déclaré"):
        _validate(spec)


def test_seed_type_mismatch_is_rejected():
    # price (Money) attend un nombre, pas une chaîne.
    spec = SEED_SPEC.replace('name: "Chaise", price: 249.90, stock: 12',
                             'name: "Chaise", price: "cher", stock: 12')
    with pytest.raises(ASTValidationError, match="attend un nombre"):
        _validate(spec)


def test_generated_field_is_filled_in_seed():
    # Un champ 'generated' non fourni dans le seed reçoit un pseudonyme
    # synthétique (comme à la création réelle, assigné par le serveur).
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
    rows = seed_data["post"]
    assert len(rows) == 2
    assert all(r["author"].startswith("Anon#") for r in rows)
    assert rows[0]["author"] != rows[1]["author"]  # uniques


# --- Insertion idempotente au démarrage (serveur réel) ---

def _find_free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


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

        # 1er démarrage : la vitrine publique est déjà peuplée.
        port = _find_free_port()
        proc = _serve(workdir, port)
        try:
            data = requests.get(f"http://127.0.0.1:{port}/product?limit=10").json()
            assert data["total"] == 2
        finally:
            _stop(proc)

        # 2e démarrage : pas de doublons (insertion idempotente).
        port = _find_free_port()
        proc = _serve(workdir, port)
        try:
            data = requests.get(f"http://127.0.0.1:{port}/product?limit=10").json()
            assert data["total"] == 2, "le seed a été réinséré (doublons)"
        finally:
            _stop(proc)
