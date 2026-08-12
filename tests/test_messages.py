"""B2 : envoi e-mail réel contre un faux SMTP, jamais vers une vraie boîte.

Le serveur monl est un vrai processus uvicorn. Le faux SMTP parle le minimum
du protocole nécessaire à smtplib et conserve le message effectivement reçu :
le test ne se contente donc pas de vérifier que le thread a été lancé.
"""
import contextlib
import io
import os
import socketserver
import sqlite3
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

from monl.ast_validator import ASTValidationError, MonlAST
from monl.cli import _contract_signature, compile_project
from monl.parser import parse_monl_string
from tests.support.server import free_port

SPEC = """app Notifications

entity Order
    label: String
    status: String

relation Customer hasMany Order

actor Customer selfRegister

rule Order.Read ownedBy Customer
rule Order.Update ownedBy Customer
rule Order.Create sends "Commande reçue" "Votre commande¶est prise en compte"

capability auth
    identifier: email

workflow Buy for Customer
    Create Order
    Read Order
    Update Order
"""


class _SMTPHandler(socketserver.StreamRequestHandler):
    def _reply(self, text):
        self.wfile.write(text.encode("ascii") + b"\r\n")
        self.wfile.flush()

    def handle(self):
        self._reply("220 faux-smtp.example.invalid ESMTP")
        while True:
            line = self.rfile.readline()
            if not line:
                return
            command = line.decode("ascii", "replace").strip()
            upper = command.upper()
            if upper.startswith(("EHLO", "HELO")):
                self.wfile.write(b"250-faux-smtp.example.invalid\r\n250 SIZE 10485760\r\n")
                self.wfile.flush()
            elif upper.startswith("MAIL FROM") or upper.startswith("RCPT TO"):
                self._reply("250 2.1.0 OK")
            elif upper == "DATA":
                self._reply("354 End data with <CR><LF>.<CR><LF>")
                raw = []
                while True:
                    data_line = self.rfile.readline()
                    if data_line in (b"", b".\r\n", b".\n"):
                        break
                    raw.append(data_line[1:] if data_line.startswith(b"..") else data_line)
                message = BytesParser(policy=policy.default).parsebytes(b"".join(raw))
                self.server.messages.append(message)
                self._reply("250 2.0.0 accepted")
            elif upper == "RSET":
                self._reply("250 2.0.0 reset")
            elif upper == "NOOP":
                self._reply("250 2.0.0 ok")
            elif upper == "QUIT":
                self._reply("221 2.0.0 bye")
                return
            else:
                self._reply("250 2.0.0 ok")


@pytest.fixture(scope="module")
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


class _RunningServer:
    def __init__(self, process, base):
        self.process = process
        self.base = base
        self.output = ""

    def stop(self):
        if self.process.poll() is None:
            self.process.terminate()
        try:
            self.output, _ = self.process.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.output, _ = self.process.communicate()


@contextlib.contextmanager
def _uvicorn_with_output(directory, env):
    port = free_port()
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app:app", "--host", "127.0.0.1",
         "--port", str(port)],
        cwd=directory,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    running = _RunningServer(process, f"http://127.0.0.1:{port}")
    try:
        for _ in range(100):
            if process.poll() is not None:
                output, _ = process.communicate()
                pytest.fail(f"serveur arrêté au démarrage : {output[-3000:]}")
            try:
                response = requests.get(running.base + "/health", timeout=1)
                if response.status_code == 200:
                    break
            except requests.RequestException:
                time.sleep(0.1)
        else:
            pytest.fail("serveur uvicorn non démarré")
        yield running
    finally:
        running.stop()


@pytest.fixture(params=["sqlite", "postgres"], ids=["sqlite", "postgres"])
def database_kind(request):
    if request.param == "postgres":
        if not os.environ.get("MONL_TEST_DATABASE_URL"):
            pytest.skip("MONL_TEST_DATABASE_URL absent")
        try:
            import psycopg
        except ImportError:
            pytest.skip("psycopg absent")
        return ("postgres", psycopg)
    return ("sqlite", None)


@contextlib.contextmanager
def _application(tmp_path, faux_smtp, database_kind, smtp_mode="working"):
    kind, psycopg = database_kind
    admin = None
    dsn = None
    schema = None
    if kind == "postgres":
        base_dsn = os.environ["MONL_TEST_DATABASE_URL"]
        schema = f"monl_message_{uuid4().hex[:12]}"
        admin = psycopg.connect(base_dsn)
        admin.execute(f'CREATE SCHEMA "{schema}"')
        admin.commit()
        parts = urlsplit(base_dsn)
        query = dict(parse_qsl(parts.query, keep_blank_values=True))
        query["options"] = f"-c search_path={schema}"
        dsn = urlunsplit(parts._replace(
            query=urlencode(query, quote_via=quote)))

    spec_path = tmp_path / "spec.ml"
    spec_path.write_text(SPEC, encoding="utf-8")
    with contextlib.redirect_stdout(io.StringIO()):
        compile_project(str(spec_path), str(tmp_path))

    env = os.environ.copy()
    env.pop("MONL_DATABASE_URL", None)
    env.pop("MONL_SMTP_HOST", None)
    env.pop("MONL_SMTP_PORT", None)
    env.pop("MONL_SMTP_FROM", None)
    if dsn:
        env["MONL_DATABASE_URL"] = dsn
    if smtp_mode == "working":
        host, port = faux_smtp.server_address[:2]
        env.update({
            "MONL_SMTP_HOST": host,
            "MONL_SMTP_PORT": str(port),
            "MONL_SMTP_FROM": "no-reply@example.invalid",
        })
    elif smtp_mode == "unreachable":
        env.update({
            "MONL_SMTP_HOST": "127.0.0.1",
            "MONL_SMTP_PORT": str(free_port()),
            "MONL_SMTP_FROM": "no-reply@example.invalid",
        })
    else:
        env["MONL_SMTP_FROM"] = "no-reply@example.invalid"

    try:
        with _uvicorn_with_output(str(tmp_path), env) as running:
            yield running, Path(tmp_path), dsn
    finally:
        if admin is not None:
            admin.close()
        if schema:
            cleanup = psycopg.connect(os.environ["MONL_TEST_DATABASE_URL"])
            try:
                cleanup.execute(f'DROP SCHEMA "{schema}" CASCADE')
                cleanup.commit()
            finally:
                cleanup.close()


def _wait_for_messages(server, count, timeout=5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if len(server.messages) >= count:
            return
        time.sleep(0.05)
    pytest.fail(f"faux SMTP : {len(server.messages)} message(s), {count} attendu(s)")


def _register_and_login(base, username):
    password = "motdepasse-b2"
    register = requests.post(
        f"{base}/register",
        json={"username": username, "password": password, "actor": "Customer"},
        timeout=10,
    )
    assert register.status_code == 200, register.text
    login = requests.post(
        f"{base}/login",
        json={"username": username, "password": password},
        timeout=10,
    )
    assert login.status_code == 200, login.text
    return (
        {"Authorization": f"Bearer {login.json()['access_token']}"},
        register.json()["user_id"],
    )


def _update_username(directory, dsn, user_id, username):
    if dsn:
        import psycopg
        conn = psycopg.connect(dsn)
        try:
            conn.execute("UPDATE _monl_users SET username = %s WHERE id = %s",
                         (username, user_id))
            conn.commit()
        finally:
            conn.close()
        return
    conn = sqlite3.connect(directory / "app.db")
    try:
        conn.execute("UPDATE _monl_users SET username = ? WHERE id = ?",
                     (username, user_id))
        conn.commit()
    finally:
        conn.close()


def test_un_create_declenche_un_seul_message_reel_et_le_contenu(database_kind,
                                                                  faux_smtp,
                                                                  tmp_path):
    faux_smtp.messages.clear()
    with _application(tmp_path, faux_smtp, database_kind) as (server, _directory, _dsn):
        username = f"client-{uuid4().hex[:8]}@example.invalid"
        headers, _user_id = _register_and_login(server.base, username)
        created = requests.post(
            f"{server.base}/order",
            headers=headers,
            json={"label": "commande de test", "status": "nouvelle"},
            timeout=10,
        )
        assert created.status_code == 200, created.text
        _wait_for_messages(faux_smtp, 1)

        message = faux_smtp.messages[0]
        assert message["To"] == username
        assert message["From"] == "no-reply@example.invalid"
        assert message["Subject"] == "Commande reçue"
        assert "Votre commande" in message.get_body(preferencelist=("plain",)).get_content()
        assert "est prise en compte" in message.get_body(
            preferencelist=("plain",)).get_content()

        for label in ("modification 1", "modification 2"):
            updated = requests.put(
                f"{server.base}/order/{created.json()['id']}",
                headers=headers,
                json={"label": label, "status": "nouvelle"},
                timeout=10,
            )
            assert updated.status_code == 200, updated.text
        time.sleep(0.25)
        assert len(faux_smtp.messages) == 1


def test_saut_de_ligne_dans_le_sujet_est_refuse_a_la_compilation(capsys):
    spec = SPEC.replace(
        '"Commande reçue"', '"Sujet\\nBcc: hidden@example.invalid"')
    with pytest.raises(ASTValidationError) as refusal:
        MonlAST(parse_monl_string(spec)).validate_and_audit()
    assert "injection d'en-têtes SMTP" in str(refusal.value)
    capsys.readouterr()


def test_sans_identifier_email_la_regle_est_refusee(capsys):
    spec = SPEC.replace("capability auth\n    identifier: email\n", "capability auth\n")
    with pytest.raises(ASTValidationError) as refusal:
        MonlAST(parse_monl_string(spec)).validate_and_audit()
    assert "identifier: email" in str(refusal.value)
    assert "champ texte libre" in str(refusal.value)
    capsys.readouterr()


def test_un_champ_email_libre_ne_suffit_pas(capsys):
    spec = SPEC.replace(
        "entity Order\n    label: String\n    status: String",
        "entity Order\n    label: String\n    status: String\n    email: String",
    ).replace("capability auth\n    identifier: email\n", "capability auth\n")
    with pytest.raises(ASTValidationError) as refusal:
        MonlAST(parse_monl_string(spec)).validate_and_audit()
    assert "champ texte libre" in str(refusal.value)
    capsys.readouterr()


def test_un_saut_de_ligne_dans_le_corps_doit_passer_par_le_separateur(capsys):
    spec = SPEC.replace(
        '"Votre commande¶est prise en compte"',
        '"Votre commande\\nest prise en compte"',
    )
    with pytest.raises(ASTValidationError) as refusal:
        MonlAST(parse_monl_string(spec)).validate_and_audit()
    assert "séparateur '¶'" in str(refusal.value)
    capsys.readouterr()


def test_le_destinataire_crlf_n_est_jamais_envoye(database_kind, faux_smtp,
                                                   tmp_path):
    faux_smtp.messages.clear()
    with _application(tmp_path, faux_smtp, database_kind) as (server, directory, dsn):
        username = f"client-{uuid4().hex[:8]}@example.invalid"
        headers, user_id = _register_and_login(server.base, username)
        hostile = username + "\r\nBcc: hidden@example.invalid"
        _update_username(directory, dsn, user_id, hostile)
        response = requests.post(
            f"{server.base}/order",
            headers=headers,
            json={"label": "ligne hostile", "status": "nouvelle"},
            timeout=10,
        )
        assert response.status_code == 200, response.text
        time.sleep(0.4)
        assert not faux_smtp.messages
        assert requests.get(f"{server.base}/health", timeout=10).status_code == 200
    assert "[MONL_MESSAGE]" in server.output


def test_smtp_injoignable_ne_defait_pas_la_route_et_nomme_la_variable(
        database_kind, faux_smtp, tmp_path):
    with _application(tmp_path, faux_smtp, database_kind,
                      smtp_mode="unreachable") as (server, directory, _dsn):
        username = f"client-{uuid4().hex[:8]}@example.invalid"
        headers, _user_id = _register_and_login(server.base, username)
        started = time.monotonic()
        response = requests.post(
            f"{server.base}/order",
            headers=headers,
            json={"label": "SMTP indisponible", "status": "nouvelle"},
            timeout=10,
        )
        elapsed = time.monotonic() - started
        assert response.status_code == 200, response.text
        assert elapsed < 2, f"la route attend le SMTP ({elapsed:.3f}s)"
        assert requests.get(f"{server.base}/health", timeout=10).status_code == 200
    assert "[MONL_MESSAGE]" in server.output


def test_variable_smtp_absente_est_nommee(database_kind, faux_smtp, tmp_path):
    with _application(tmp_path, faux_smtp, database_kind,
                      smtp_mode="missing") as (server, _directory, _dsn):
        username = f"client-{uuid4().hex[:8]}@example.invalid"
        headers, _user_id = _register_and_login(server.base, username)
        response = requests.post(
            f"{server.base}/order",
            headers=headers,
            json={"label": "SMTP non configuré", "status": "nouvelle"},
            timeout=10,
        )
        assert response.status_code == 200, response.text
    assert "MONL_SMTP_HOST" in server.output


def test_contrat_et_delta_voient_un_message(tmp_path, capsys):
    spec = tmp_path / "spec.ml"
    spec.write_text(SPEC, encoding="utf-8")
    with contextlib.redirect_stdout(io.StringIO()):
        contract = compile_project(str(spec), str(tmp_path))
    assert contract["business_rules"]["messages"][0]["body"] == (
        "Votre commande\n\nest prise en compte")
    create_route = next(
        route for route in contract["routes"]
        if route["method"] == "POST" and route["path"] == "/order")
    assert "NOTIFICATION" in create_route["note"]

    changed = dict(contract)
    changed["business_rules"] = dict(contract["business_rules"])
    changed["business_rules"]["messages"] = [
        dict(contract["business_rules"]["messages"][0], body="Autre texte")
    ]
    assert _contract_signature(contract)[6] != _contract_signature(changed)[6]
    capsys.readouterr()
