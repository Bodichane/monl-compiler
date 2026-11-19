"""Non-regression of the security fixes of beta 0.9.0-beta.3.

Each test replays a real flaw observed on beta 2:

1. self-assignment of a privileged role at registration (full privilege
   escalation in two anonymous HTTP calls);
2. account enumeration through /login's response time;
3. attempt quota bypassable in parallel (TOCTOU);
4. signing secret readable by any local account;
5. token blacklist never purged;
6. compilation output not reproducible from one run to the next.
"""
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
import requests

from monl.ast_validator import MonlAST
from monl.generator import MonlSecureGenerator
from monl.parser import parse_monl_file

SPEC = """app PrivApp

entity Note
    title: String

entity Product
    label: String

actor Member selfRegister
actor Admin

rule Note.Update ownedBy Member

relation Member hasMany Note

workflow Notes for Member
    Create Note
    Read Note
    Update Note

workflow Catalog for Admin
    Create Product
    Read Product
    Delete Product
"""


def _compile(workdir, spec=SPEC):
    spec_path = os.path.join(workdir, "spec.ml")
    with open(spec_path, "w", encoding="utf-8") as f:
        f.write(spec)
    ast = MonlAST(parse_monl_file(spec_path)).validate_and_audit()
    MonlSecureGenerator(ast, output_dir=workdir).generate_all()
    return workdir


def _free_port():
    import socket
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class _Server:
    def __init__(self, workdir):
        self.workdir = workdir
        self.port = _free_port()
        self.base = f"http://127.0.0.1:{self.port}"

    def __enter__(self):
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app:app", "--port", str(self.port)],
            cwd=self.workdir, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(100):
            try:
                requests.get(self.base + "/docs", timeout=1)
                return self
            except requests.RequestException:
                time.sleep(0.2)
        raise RuntimeError("le serveur éphémère n'a jamais répondu")

    def __exit__(self, *exc):
        self.proc.terminate()
        self.proc.wait(timeout=10)


def _vider_quota(workdir):
    """Clears the application's attempt counter (point 67).

    The quota (5 / 60 s / IP) is persisted in the database — that is the whole
    point of point 33. A test wanting more than five measurements therefore need
    not sleep a minute: it just empties the table, which weakens nothing in the
    product and only concerns the test bench."""
    import sqlite3
    cnx = sqlite3.connect(os.path.join(workdir, "app.db"))
    try:
        with cnx:
            cnx.execute("DELETE FROM _monl_rate_limit")
    finally:
        # `with sqlite3.connect(...)` commits the transaction but does not
        # CLOSE the connection: without this close, the suite leaks one
        # descriptor per call and reports it as a ResourceWarning.
        cnx.close()


def _login(base, username, password="motdepasse123"):
    """Logs in while tolerating the quota shared by this module's tests."""
    for tentative in range(3):
        reponse = requests.post(base + "/login", json={"username": username, "password": password})
        if reponse.status_code != 429:
            return reponse
        time.sleep(21)
    return reponse


@pytest.fixture(scope="module")
def app_server():
    with tempfile.TemporaryDirectory() as workdir:
        _compile(workdir)
        with _Server(workdir) as server:
            yield server


# -------------------------------------------------------------------------- 1.
# Privilege escalation through registration
# --------------------------------------------------------------------------

def test_role_provisionne_refuse_a_inscription(app_server):
    """A client cannot assign itself a role absent from 'selfRegister'."""
    r = requests.post(app_server.base + "/register",
                      json={"username": "pirate", "password": "motdepasse123", "actor": "Admin"})
    assert r.status_code == 403, r.text
    # ...and the account must not exist: login fails too.
    assert _login(app_server.base, "pirate").status_code == 401


def test_role_ouvert_accepte_puis_reste_confine(app_server):
    """The 'selfRegister' role registers, but does not get Admin rights."""
    requests.post(app_server.base + "/register",
                  json={"username": "membre", "password": "motdepasse123", "actor": "Member"})
    token = _login(app_server.base, "membre").json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    assert requests.post(app_server.base + "/note", headers=headers,
                         json={"title": "à moi"}).status_code == 200
    assert requests.post(app_server.base + "/product", headers=headers,
                         json={"label": "interdit"}).status_code == 403


def test_role_provisionne_par_manage_py(app_server):
    """The legitimate path: creating the privileged account on the server."""
    proc = subprocess.run(
        [sys.executable, "manage.py", "adduser", "patron", "Admin"],
        cwd=app_server.workdir, input="motdepasse123\nmotdepasse123\n",
        capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    token = _login(app_server.base, "patron").json()["access_token"]
    r = requests.post(app_server.base + "/product",
                      headers={"Authorization": f"Bearer {token}"}, json={"label": "légitime"})
    assert r.status_code == 200, r.text


# -------------------------------------------------------------------------- 2.
# Account enumeration through a timing channel
# --------------------------------------------------------------------------

def test_login_does_not_reveal_whether_the_account_exists():
    """Response time must not betray whether an identifier exists.

    The 'membre' account exists (created above), 'fantome' does not. Without the
    dummy hash, /login answered without running the 100,000 PBKDF2 iterations
    when the account was unknown: the gap (~50-100 ms) was enough to enumerate
    accounts. We therefore compare with the cost of a real hash, measured on the
    current machine — the only stable reference from one machine to another.

    Constraint: the quota is 5 attempts / 60 s / IP. We empty it between
    measurements (see _vider_quota) rather than staying within it, and keep each
    group's MINIMUM — the closest to the real processing cost, noise only being
    able to add time.

    POINT 67: this test failed intermittently in CI, never locally. A shared
    runner is a noisy machine; two measurements were enough for a preemption to
    blow up the gap. Two fixes, neither touching what is proven: five samples per
    group instead of two, and the whole measurement replayed up to three times. A
    real timing leak is SYSTEMATIC — it reproduces on every round; noise does
    not. Widening the threshold would instead have made the test blind to the
    leak it watches.
    """

    # Dedicated server: the measurements consume the attempt quota, they cannot
    # share the other tests' instance.
    #
    # POINT 67: the server was started by hand and stopped by a line placed
    # AFTER the measurements — an assertion failure therefore left an orphan
    # uvicorn and a temporary folder behind, on a machine about to chain other
    # servers. A flaky test leaking a process contaminates the following ones:
    # the next failure has nothing to do with its cause any more.
    workdir = tempfile.mkdtemp()
    _compile(workdir)
    server = _Server(workdir).__enter__()
    try:
        _mesurer_canal_temporel(server, workdir)
    finally:
        server.__exit__()
        shutil.rmtree(workdir, ignore_errors=True)


def _mesurer_canal_temporel(server, workdir):
    import hashlib

    requests.post(server.base + "/register",
                  json={"username": "membre", "password": "motdepasse123", "actor": "Member"})

    start = time.perf_counter()
    hashlib.pbkdf2_hmac("sha256", b"x", b"y" * 16, 100_000)
    hash_cost = time.perf_counter() - start

    def mesure(username):
        t0 = time.perf_counter()
        reponse = requests.post(server.base + "/login",
                                json={"username": username, "password": "mauvais-mot-de-passe"})
        assert reponse.status_code == 401, f"quota atteint pendant la mesure ({reponse.status_code})"
        return time.perf_counter() - t0

    def groupe(username, echantillons=5):
        _vider_quota(workdir)
        return min(mesure(username) for _ in range(echantillons))

    mesure("echauffement")  # first request: startup costs, discarded

    ecarts = []
    for _tour in range(3):
        ecart = abs(groupe("membre") - groupe("fantome"))
        ecarts.append(ecart)
        if ecart < hash_cost / 2:
            break

    assert min(ecarts) < hash_cost / 2, (
        f"écart de {min(ecarts) * 1000:.0f} ms entre compte existant et inexistant "
        f"sur {len(ecarts)} mesures indépendantes (coût d'un hachage : "
        f"{hash_cost * 1000:.0f} ms) — canal temporel exploitable")


# -------------------------------------------------------------------------- 3.
# Attempt quota: atomicity
# --------------------------------------------------------------------------

def test_quota_non_contournable_en_parallele():
    """20 simultaneous logins must not all pass the quota of 5."""
    with tempfile.TemporaryDirectory() as workdir:
        _compile(workdir)
        with _Server(workdir) as server:
            def tentative(_i):
                return requests.post(server.base + "/login",
                                     json={"username": "inconnu", "password": "peu-importe"}).status_code

            with ThreadPoolExecutor(max_workers=20) as pool:
                codes = list(pool.map(tentative, range(20)))

            acceptees = sum(1 for c in codes if c != 429)
            assert acceptees <= 5, (
                f"{acceptees} tentatives ont franchi un quota fixé à 5 : le comptage "
                "et l'enregistrement ne sont pas atomiques")


# -------------------------------------------------------------------------- 4
# & 5. Secret hygiene and blacklist purge
# --------------------------------------------------------------------------

def test_jwt_secret_readable_only_by_its_owner():
    with tempfile.TemporaryDirectory() as workdir:
        _compile(workdir)
        mode = os.stat(os.path.join(workdir, ".jwt_secret")).st_mode & 0o777
        assert mode == 0o600, f"permissions {oct(mode)} : le secret est lisible par d'autres comptes"


def test_token_blacklist_is_purgeable():
    """The revoked token table carries the expiry date its purge needs."""
    with tempfile.TemporaryDirectory() as workdir:
        _compile(workdir)
        with open(os.path.join(workdir, "schema.sql"), encoding="utf-8") as fh:
            schema = fh.read()
        assert "expires_at" in schema
        with open(os.path.join(workdir, "app.py"), encoding="utf-8") as fh:
            app = fh.read()
        assert "DELETE FROM _monl_revoked_tokens WHERE expires_at" in app


def test_logout_revokes_the_token(app_server):
    requests.post(app_server.base + "/register",
                  json={"username": "sortant", "password": "motdepasse123", "actor": "Member"})
    token = _login(app_server.base, "sortant").json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    assert requests.get(app_server.base + "/note", headers=headers).status_code == 200
    assert requests.post(app_server.base + "/logout", headers=headers).status_code == 200
    assert requests.get(app_server.base + "/note", headers=headers).status_code == 401


# -------------------------------------------------------------------------- 6.
# Compilation determinism
# --------------------------------------------------------------------------

def test_compilation_reproductible_entre_processus():
    """Two compilations of the same spec must produce the same bytes.

    Python set iteration order varies from one process to another
    (PYTHONHASHSEED): the test compiles in two subprocesses with opposite hash
    seeds, which a compilation in the current process could not detect.
    """
    sources = {}
    for seed in ("0", "1"):
        with tempfile.TemporaryDirectory() as workdir:
            spec_path = os.path.join(workdir, "spec.ml")
            with open(spec_path, "w", encoding="utf-8") as f:
                f.write(SPEC)
            code = (
                "import sys; sys.path.insert(0, %r)\n"
                "from monl.parser import parse_monl_file\n"
                "from monl.ast_validator import MonlAST\n"
                "from monl.generator import MonlSecureGenerator\n"
                "ast = MonlAST(parse_monl_file(%r)).validate_and_audit()\n"
                "MonlSecureGenerator(ast, output_dir=%r).generate_all()\n"
                % (os.path.join(os.path.dirname(__file__), "..", "src"), spec_path, workdir)
            )
            env = {**os.environ, "PYTHONHASHSEED": seed}
            subprocess.run([sys.executable, "-c", code], check=True, capture_output=True, env=env)
            sources[seed] = {
                name: pathlib.Path(workdir, name).read_text(encoding="utf-8")
                for name in ("app.py", "schema.sql", "manage.py")
            }
    for name in sources["0"]:
        assert sources["0"][name] == sources["1"][name], (
            f"{name} diffère entre deux compilations de la même spec : "
            "la sortie dépend de l'ordre d'itération d'un ensemble Python")


# -------------------------------------------------------------------------- 7.
# Frontend contract: published registration scope
# --------------------------------------------------------------------------

def test_contract_publishes_the_registration_scope():
    from monl.frontend_contract import build_contract
    with tempfile.TemporaryDirectory() as workdir:
        spec_path = os.path.join(workdir, "spec.ml")
        with open(spec_path, "w", encoding="utf-8") as f:
            f.write(SPEC)
        ast = MonlAST(parse_monl_file(spec_path)).validate_and_audit()
        generator = MonlSecureGenerator(ast, output_dir=workdir)
        contract = build_contract(ast, generator)
    assert contract["self_register_actors"] == ["Member"]
    assert contract["api"]["auth"]["register"]["self_register_actors"] == ["Member"]
    assert "Admin" in contract["actors"]
    json.dumps(contract)  # the contract must stay serializable
