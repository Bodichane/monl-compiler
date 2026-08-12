"""B4 : authentification complète contre un vrai serveur, SQLite et PostgreSQL.

Chaque paramètre démarre son propre uvicorn séquentiellement. Les assertions
portent sur les réponses HTTP et, pour la réinitialisation, sur le message
effectivement reçu par un faux SMTP.
"""

from __future__ import annotations

import base64
import contextlib
import hashlib
import hmac
import io
import os
import re
import socketserver
import sqlite3
import struct
import subprocess
import sys
import threading
import time
from email import policy
from email.parser import BytesParser
from pathlib import Path
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit
from uuid import uuid4

import pytest
import requests

from monl.cli import compile_project
from monl.smoke_test import run_smoke_test
from tests.support.server import uvicorn_server

SPEC_B4 = """app CompleteAuth

entity Note
    body: String

actor User selfRegister

capability auth
    identifier: email
    lockout: 3 in 2
    password_reset: 60
    refresh_tokens: 3600
    totp

workflow Main for User
    Create Note
    Read Note
"""

SPEC_LEGACY = """app CompleteAuth

entity Note
    body: String

actor User selfRegister

capability auth
    identifier: email

workflow Main for User
    Create Note
    Read Note
"""


class _SMTPHandler(socketserver.StreamRequestHandler):
    def _reply(self, text):
        self.wfile.write(text.encode("ascii") + b"\r\n")
        self.wfile.flush()

    def handle(self):
        self._reply("220 b4-smtp.example.invalid ESMTP")
        while True:
            line = self.rfile.readline()
            if not line:
                return
            command = line.decode("ascii", "replace").strip().upper()
            if command.startswith(("EHLO", "HELO")):
                self.wfile.write(b"250-b4-smtp.example.invalid\r\n250 SIZE 10485760\r\n")
                self.wfile.flush()
            elif command.startswith(("MAIL FROM", "RCPT TO")):
                self._reply("250 2.1.0 OK")
            elif command == "DATA":
                self._reply("354 End data with <CR><LF>.<CR><LF>")
                data = []
                while True:
                    line = self.rfile.readline()
                    if line in (b"", b".\r\n", b".\n"):
                        break
                    data.append(line[1:] if line.startswith(b"..") else line)
                self.server.messages.append(
                    BytesParser(policy=policy.default).parsebytes(b"".join(data)))
                self._reply("250 2.0.0 accepted")
            elif command == "QUIT":
                self._reply("221 2.0.0 bye")
                return
            else:
                self._reply("250 2.0.0 ok")


@pytest.fixture
def faux_smtp():
    server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), _SMTPHandler)
    server.daemon_threads = True
    server.messages = []
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.fixture(params=["sqlite", "postgres"], ids=["sqlite", "postgres"])
def b4_application(request, tmp_path, faux_smtp):
    dsn = None
    admin = None
    schema = None
    if request.param == "postgres":
        raw_dsn = os.environ.get("MONL_TEST_DATABASE_URL", "").strip()
        if not raw_dsn:
            pytest.skip("MONL_TEST_DATABASE_URL absent")
        try:
            import psycopg
        except ImportError:
            pytest.skip("psycopg absent")
        schema = f"monl_b4_{uuid4().hex[:12]}"
        admin = psycopg.connect(raw_dsn)
        admin.execute(f'CREATE SCHEMA "{schema}"')
        admin.commit()
        parts = urlsplit(raw_dsn)
        params = dict(parse_qsl(parts.query, keep_blank_values=True))
        params["options"] = f"-c search_path={schema}"
        dsn = urlunsplit(parts._replace(query=urlencode(params, quote_via=quote)))

    spec_path = tmp_path / "spec.ml"
    spec_path.write_text(SPEC_B4, encoding="utf-8")
    with contextlib.redirect_stdout(io.StringIO()):
        compile_project(str(spec_path), str(tmp_path))

    env = os.environ.copy()
    env.pop("MONL_DATABASE_URL", None)
    env.update({
        "MONL_JWT_SECRET": "b4-integration-secret-32-bytes-min",
        "MONL_TRUST_PROXY": "1",
        "MONL_TOKEN_TTL_SECONDS": "1",
        "MONL_SMTP_HOST": faux_smtp.server_address[0],
        "MONL_SMTP_PORT": str(faux_smtp.server_address[1]),
        "MONL_SMTP_FROM": "no-reply@example.invalid",
    })
    if dsn:
        env["MONL_DATABASE_URL"] = dsn
    try:
        with uvicorn_server(str(tmp_path), env=env) as base:
            yield base, Path(tmp_path), dsn, faux_smtp
    finally:
        if admin is not None:
            admin.close()
            import psycopg
            cleanup = psycopg.connect(os.environ["MONL_TEST_DATABASE_URL"])
            try:
                cleanup.execute(f'DROP SCHEMA "{schema}" CASCADE')
                cleanup.commit()
            finally:
                cleanup.close()


@pytest.fixture(params=["sqlite", "postgres"], ids=["sqlite-legacy", "postgres-legacy"])
def legacy_b4_application(request, tmp_path, faux_smtp):
    dsn = None
    schema = None
    if request.param == "postgres":
        raw_dsn = os.environ.get("MONL_TEST_DATABASE_URL", "").strip()
        if not raw_dsn:
            pytest.skip("MONL_TEST_DATABASE_URL absent")
        try:
            import psycopg
        except ImportError:
            pytest.skip("psycopg absent")
        schema = f"monl_b4_legacy_{uuid4().hex[:12]}"
        admin = psycopg.connect(raw_dsn)
        admin.execute(f'CREATE SCHEMA "{schema}"')
        admin.commit()
        admin.close()
        parts = urlsplit(raw_dsn)
        params = dict(parse_qsl(parts.query, keep_blank_values=True))
        params["options"] = f"-c search_path={schema}"
        dsn = urlunsplit(parts._replace(query=urlencode(params, quote_via=quote)))

    spec_path = tmp_path / "spec.ml"
    spec_path.write_text(SPEC_LEGACY, encoding="utf-8")
    with contextlib.redirect_stdout(io.StringIO()):
        compile_project(str(spec_path), str(tmp_path))
    env = os.environ.copy()
    env.pop("MONL_DATABASE_URL", None)
    env["MONL_JWT_SECRET"] = "b4-legacy-secret-32-bytes-min"
    if dsn:
        env["MONL_DATABASE_URL"] = dsn
    try:
        with uvicorn_server(str(tmp_path), env=env) as old_base:
            _register(old_base, "legacy-b4@example.invalid")

        spec_path.write_text(SPEC_B4, encoding="utf-8")
        with contextlib.redirect_stdout(io.StringIO()):
            compile_project(str(spec_path), str(tmp_path))
        env["MONL_SMTP_HOST"] = faux_smtp.server_address[0]
        env["MONL_SMTP_PORT"] = str(faux_smtp.server_address[1])
        env["MONL_SMTP_FROM"] = "no-reply@example.invalid"
        with uvicorn_server(str(tmp_path), env=env) as base:
            yield base, Path(tmp_path), dsn
    finally:
        if schema:
            import psycopg
            cleanup = psycopg.connect(os.environ["MONL_TEST_DATABASE_URL"])
            try:
                cleanup.execute(f'DROP SCHEMA "{schema}" CASCADE')
                cleanup.commit()
            finally:
                cleanup.close()


def _call(method, base, path, *, body=None, token=None, ip="b4"):
    headers = {"X-Forwarded-For": ip}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return requests.request(method, base + path, json=body, headers=headers, timeout=10)


def _register(base, username, password="motdepasse8", ip=None):
    response = _call("POST", base, "/register",
                     body={"username": username, "password": password, "actor": "User"},
                     ip=ip or username)
    assert response.status_code == 200, response.text


def _login(base, username, password, *, ip, code=None):
    body = {"username": username, "password": password}
    if code is not None:
        body["totp_code"] = code
    return _call("POST", base, "/login", body=body, ip=ip)


def _token(response):
    assert response.status_code == 200, response.text
    value = response.json().get("access_token")
    assert value
    return value


def _wait_for_message(smtp, count):
    deadline = time.monotonic() + 5
    while len(smtp.messages) < count and time.monotonic() < deadline:
        time.sleep(0.02)
    assert len(smtp.messages) >= count
    body = smtp.messages[count - 1].get_body(
        preferencelist=("plain",)).get_content()
    match = re.search(r"réinitialisation\s*:\s*([A-Za-z0-9_-]+)", body,
                      re.IGNORECASE)
    assert match, body
    return match.group(1)


def _expire_reset_token(directory, dsn, raw_token):
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    if dsn:
        import psycopg
        conn = psycopg.connect(dsn)
        try:
            conn.execute("UPDATE _monl_password_reset_tokens SET expires_at = 0 "
                         "WHERE token_hash = %s", (token_hash,))
            conn.commit()
        finally:
            conn.close()
    else:
        conn = sqlite3.connect(directory / "app.db")
        try:
            conn.execute("UPDATE _monl_password_reset_tokens SET expires_at = 0 "
                         "WHERE token_hash = ?", (token_hash,))
            conn.commit()
        finally:
            conn.close()


def _totp_code(secret, step=None):
    step = int(time.time()) // 30 if step is None else step
    padded = secret + "=" * ((8 - len(secret) % 8) % 8)
    key = base64.b32decode(padded, casefold=True)
    digest = hmac.new(key, struct.pack(">Q", step), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    number = ((digest[offset] & 0x7F) << 24
              | digest[offset + 1] << 16
              | digest[offset + 2] << 8
              | digest[offset + 3])
    return f"{number % 1_000_000:06d}"


def test_authentification_b4_complete_sur_les_deux_moteurs(b4_application):
    base, directory, dsn, smtp = b4_application
    alice = "alice-b4@example.invalid"
    bob = "bob-b4@example.invalid"
    _register(base, alice)
    _register(base, bob)

    # 1. Compteur par compte, réponse générique et durée comparable à
    # l'identifiant absent. Les IP changent pour ne pas confondre ce test avec
    # la limitation historique par IP.
    for index in range(3):
        failed = _login(base, alice, "mauvais-pass", ip=f"lock-fail-{index}")
        assert failed.status_code == 401
        assert failed.json()["detail"] == "Identifiants invalides."
    locked = _login(base, alice, "motdepasse8", ip="lock-correct")
    assert locked.status_code == 401
    assert locked.json()["detail"] == "Identifiants invalides."
    bob_token = _token(_login(base, bob, "motdepasse8", ip="bob-before-totp"))

    started = time.perf_counter()
    locked_probe = _login(base, alice, "motdepasse8", ip="lock-timing")
    locked_duration = time.perf_counter() - started
    started = time.perf_counter()
    missing_probe = _login(base, "absent-b4@example.invalid",
                           "motdepasse8", ip="missing-timing")
    missing_duration = time.perf_counter() - started
    assert locked_probe.status_code == missing_probe.status_code == 401
    assert locked_probe.json() == missing_probe.json()
    assert abs(locked_duration - missing_duration) < 0.20
    assert _login(base, alice, "motdepasse8", ip="lock-still-closed").status_code == 401
    time.sleep(2.2)
    alice_token = _token(_login(base, alice, "motdepasse8", ip="lock-expired"))

    # 2. Réinitialisation réellement livrée par la brique de messages, sans
    # différence de réponse entre une adresse connue et une adresse absente.
    started = time.perf_counter()
    known = _call("POST", base, "/password-reset/request",
                  body={"username": alice}, ip="reset-known")
    known_duration = time.perf_counter() - started
    started = time.perf_counter()
    unknown = _call("POST", base, "/password-reset/request",
                    body={"username": "nobody-b4@example.invalid"}, ip="reset-unknown")
    unknown_duration = time.perf_counter() - started
    assert known.status_code == unknown.status_code == 200
    assert known.json() == unknown.json()
    assert abs(known_duration - unknown_duration) < 0.20
    alice_reset = _wait_for_message(smtp, 1)

    _call("POST", base, "/password-reset/request",
          body={"username": bob}, ip="reset-bob")
    bob_reset = _wait_for_message(smtp, 2)
    assert bob_reset != alice_reset
    wrong_account = _call(
        "POST", base, "/password-reset/confirm",
        body={"username": bob, "token": alice_reset, "password": "nouveau-alice-8"},
        ip="reset-wrong-account")
    assert wrong_account.status_code == 400

    _call("POST", base, "/password-reset/request",
          body={"username": alice}, ip="reset-expired-request")
    expired = _wait_for_message(smtp, 3)
    _expire_reset_token(directory, dsn, expired)
    assert _call(
        "POST", base, "/password-reset/confirm",
        body={"username": alice, "token": expired, "password": "nouveau-alice-8"},
        ip="reset-expired").status_code == 400

    _call("POST", base, "/password-reset/request",
          body={"username": alice}, ip="reset-success-request")
    fresh = _wait_for_message(smtp, 4)
    confirmed = _call(
        "POST", base, "/password-reset/confirm",
        body={"username": alice, "token": fresh, "password": "nouveau-alice-8"},
        ip="reset-confirm")
    assert confirmed.status_code == 200
    replay = _call(
        "POST", base, "/password-reset/confirm",
        body={"username": alice, "token": fresh, "password": "autre-alice-8"},
        ip="reset-replay")
    assert replay.status_code == 400
    assert _token(_login(base, alice, "nouveau-alice-8",
                         ip="login-after-reset"))
    assert _login(base, alice, "motdepasse8", ip="login-old-password").status_code == 401

    # 3. Le JWT d'accès expire, le jeton opaque tourne, et il n'est pas
    # interchangeable avec un Bearer JWT.
    time.sleep(1.3)
    assert _call("GET", base, "/note", token=alice_token,
                 ip="expired-access").status_code == 401
    refresh = _login(base, alice, "nouveau-alice-8", ip="refresh-login").json()
    old_refresh = refresh["refresh_token"]
    refreshed = _call("POST", base, "/refresh",
                      body={"refresh_token": old_refresh}, ip="refresh-rotate")
    assert refreshed.status_code == 200
    rotated = refreshed.json()
    assert rotated["refresh_token"] != old_refresh
    assert _call("GET", base, "/note", token=rotated["refresh_token"],
                 ip="refresh-as-access").status_code == 401
    assert _call("POST", base, "/refresh",
                 body={"refresh_token": old_refresh}, ip="refresh-replay").status_code == 401
    assert _call("GET", base, "/note", token=rotated["access_token"],
                 ip="refresh-access").status_code == 200
    assert _call("POST", base, "/logout", token=rotated["access_token"],
                 ip="refresh-logout").status_code == 200
    assert _call("POST", base, "/refresh",
                 body={"refresh_token": rotated["refresh_token"]},
                 ip="refresh-revoked").status_code == 401

    # 4. TOTP hors ligne : activation, code courant, fenêtre précédente et
    # rejeu. Le compte Alice, sans TOTP activé, est resté connectable ci-dessus.
    bob_token = _token(_login(base, bob, "motdepasse8", ip="totp-session"))
    setup = _call("POST", base, "/totp/setup", token=bob_token, ip="totp-setup")
    assert setup.status_code == 200, setup.text
    secret = setup.json()["secret"]
    assert setup.json()["otpauth_uri"].startswith("otpauth://totp/")
    enabled = _call("POST", base, "/totp/enable", token=bob_token,
                    body={"code": _totp_code(secret)}, ip="totp-enable")
    assert enabled.status_code == 200, enabled.text
    valid = _login(base, bob, "motdepasse8", ip="totp-valid",
                   code=_totp_code(secret))
    assert valid.status_code == 200, valid.text
    assert _login(base, bob, "motdepasse8", ip="totp-other-window",
                  code=_totp_code(secret, int(time.time()) // 30 - 1)).status_code == 401
    assert _login(base, bob, "motdepasse8", ip="totp-replay",
                  code=_totp_code(secret)).status_code == 401
    assert _login(base, bob, "motdepasse8", ip="totp-missing").status_code == 401

    contract = (directory / "frontend_contract.json").read_text(encoding="utf-8")
    assert "secret" not in contract.lower()
    smoke_ok, smoke_errors, _smoke_warnings = run_smoke_test(
        str(directory), say=lambda *_args: None)
    assert smoke_ok, smoke_errors
    manage_env = os.environ.copy()
    manage_env["MONL_JWT_SECRET"] = "b4-integration-secret-32-bytes-min"
    if dsn:
        manage_env["MONL_DATABASE_URL"] = dsn
    manage = subprocess.run(
        [sys.executable, str(directory / "manage.py"), "users"],
        cwd="/tmp", env=manage_env, capture_output=True, text=True, timeout=10)
    assert manage.returncode == 0, manage.stderr
    assert alice in manage.stdout and bob in manage.stdout


def test_b4_ne_casse_pas_un_compte_historique(legacy_b4_application):
    base, directory, dsn = legacy_b4_application
    legacy = _login(base, "legacy-b4@example.invalid", "motdepasse8",
                    ip="legacy-login")
    assert legacy.status_code == 200, legacy.text

    if dsn:
        import psycopg
        conn = psycopg.connect(dsn)
        try:
            columns = {
                row[0] for row in conn.execute(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = '_monl_users'")}
            row = conn.execute(
                "SELECT totp_secret, totp_enabled, totp_last_step "
                "FROM _monl_users WHERE username = %s",
                ("legacy-b4@example.invalid",)).fetchone()
        finally:
            conn.close()
    else:
        conn = sqlite3.connect(directory / "app.db")
        try:
            columns = {row[1] for row in conn.execute(
                "PRAGMA table_info(_monl_users)")}
            row = conn.execute(
                "SELECT totp_secret, totp_enabled, totp_last_step "
                "FROM _monl_users WHERE username = ?",
                ("legacy-b4@example.invalid",)).fetchone()
        finally:
            conn.close()
    assert {"totp_secret", "totp_enabled", "totp_last_step"} <= columns
    assert row == (None, None, None)
