"""B4: full authentication against a real server, SQLite and PostgreSQL.

Each parameter starts its own uvicorn sequentially. The assertions are about
the HTTP responses and, for reset, about the message actually received by a
fake SMTP.
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
import statistics
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
    lockout: 3 in 10
    password_reset: 60
    refresh_tokens: 3600
    totp

workflow Main for User
    Create Note
    Read Note
"""

# The bench keeps two deliberately different windows. The main server tests
# spontaneous reopening with the short window; the measurement server must be
# able to hold the full escalation (135 pairs, i.e. 270 calls) without turning
# the lock into a hidden variable of the measurement.
SPEC_B4_MESURE = SPEC_B4.replace("lockout: 3 in 10", "lockout: 3 in 300")

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
    mesure_dir = tmp_path / "mesure-verrou"
    mesure_dir.mkdir()
    mesure_spec = mesure_dir / "spec.ml"
    mesure_spec.write_text(SPEC_B4_MESURE, encoding="utf-8")
    with contextlib.redirect_stdout(io.StringIO()):
        compile_project(str(mesure_spec), str(mesure_dir))

    env = os.environ.copy()
    env.pop("MONL_DATABASE_URL", None)
    env.update({
        "MONL_JWT_SECRET": "b4-integration-secret-32-bytes-min",
        "MONL_TRUST_PROXY": "1",
        # Short, to PROVE the access token expires — but not so short that a
        # plain HTTP round trip makes it stale. At 1 second, the TOTP phase
        # failed intermittently under the full suite's load: the token obtained
        # at login was already expired at the next call, and the test then
        # denounced a healthy application. It is the complaint beta 4 had
        # already addressed on the timing channel test: a test must not depend
        # on the machine's load.
        "MONL_TOKEN_TTL_SECONDS": ("3" if "complete_sur" in request.node.name else "120"),
        "MONL_SMTP_HOST": faux_smtp.server_address[0],
        "MONL_SMTP_PORT": str(faux_smtp.server_address[1]),
        "MONL_SMTP_FROM": "no-reply@example.invalid",
    })
    if dsn:
        env["MONL_DATABASE_URL"] = dsn
    try:
        with (uvicorn_server(str(tmp_path), env=env) as base,
              uvicorn_server(str(mesure_dir), env=env) as mesure_base):
            yield base, Path(tmp_path), dsn, faux_smtp, mesure_base
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
            old_token = _token(_login(old_base, "legacy-b4@example.invalid",
                                      "motdepasse8", ip="avant-migration"))

        spec_path.write_text(SPEC_B4, encoding="utf-8")
        with contextlib.redirect_stdout(io.StringIO()):
            compile_project(str(spec_path), str(tmp_path))
        env["MONL_SMTP_HOST"] = faux_smtp.server_address[0]
        env["MONL_SMTP_PORT"] = str(faux_smtp.server_address[1])
        env["MONL_SMTP_FROM"] = "no-reply@example.invalid"
        with uvicorn_server(str(tmp_path), env=env) as base:
            yield base, Path(tmp_path), dsn, old_token
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


# Starting number of rounds of the time measurements. The message counter below
# depends on it: the "known address" path sends an email on EVERY round. The
# noise witness can buy resolution, without exceeding the bound declared below.
TOURS_MESURE = 15
TOURS_ESCALADE = (TOURS_MESURE, TOURS_MESURE * 3, TOURS_MESURE * 9)

# The tolerance comes from a WITNESS measured just before each comparison: two
# calls of the same path, with distinct IPs. Their gap cannot carry an
# application leak; it measures the runner's noise at that moment. Twice that
# noise covers the two compared medians, and the floor protects the machine
# fast enough that a zero witness does not mean a perfect clock.
#
# Noise is NOT allowed to disarm the oracle. The witness must stay below 7.5
# ms, which bounds the derived margin at 15 ms and leaves a leak of about 20 ms
# detectable. If it exceeds that bound, more measurement is spent first (15 →
# 45 → 135); if it stays too large, the test fails explicitly.
#
# These two constants express a resolution requirement, not a machine
# calibration: the 20 ms leak is point 160's counter-proof.
FACTEUR_MARGE_BRUIT = 2.0
BRUIT_MAX_RESOLUBLE = 0.0075
PLANCHER_ECART = 0.005


def _ecart_apparie(appel_a, appel_b, tours=TOURS_MESURE):
    """Median gap between two paths, measured ALTERNATELY and in pairs.

    A timing oracle is a TREND, not an instant. Measured with a single draw on a
    shared runner, one spike (scheduler, garbage collector, noisy neighbor) is
    enough to make the comparison fail: CI fell exactly that way, by 0.4 ms on a
    200 ms threshold, while the same test passed on the other run of the same
    Python version. A security test that is wrong one time out of two teaches
    people to stop reading failures — point 57's ruling.

    Two fixes, and the second is the one that was missing. The MEDIAN discards an
    isolated spike without hiding anything: a real timing leak shifts ALL
    measurements, not one. But measuring one path entirely THEN the other leaves
    all of the machine's drift in the gap: under eight saturated cores, the first
    series rose from 0.20 to 0.37 s while the second stayed flat — a 130 ms gap
    attributed to locking, while it belonged only to the ORDER of the
    measurements. The two paths are therefore called ALTERNATELY and the gap is
    computed PAIR BY PAIR: a spike hits both members of a pair and cancels out in
    their difference, while a real leak is present in every pair.

    The IP changes at every round: otherwise per-IP limiting (5 / 60 s, points 13
    and 33) would answer 429 on the sixth call and measure the limiter's refusal
    instead of the authentication path.
    """
    ecarts, durees = [], []
    reponse_a = reponse_b = None
    for tour in range(tours):
        depart = time.perf_counter()
        reponse_a = appel_a(tour)
        duree_a = time.perf_counter() - depart
        depart = time.perf_counter()
        reponse_b = appel_b(tour)
        duree_b = time.perf_counter() - depart
        ecarts.append(duree_a - duree_b)
        durees += [duree_a, duree_b]
    # The median duration goes with the gap: it is the SCALE at which the gap
    # must be judged. Without it, the caller could only compare with a number
    # of seconds written in advance, which does not mean the same thing from
    # one machine to another.
    return (statistics.median(ecarts), statistics.median(durees),
            reponse_a, reponse_b)


def _mesurer_bruit(appel_a, appel_b, *, nom):
    """Measures pure noise, then increases the spend if needed.

    `appel_a` and `appel_b` must represent the same path. The offset passed to
    the callbacks makes the IPs unique even if an escalation replays the
    measurement: the limiter must never become the observed signal.
    """
    offset = 0
    dernier_ecart = 0.0
    for tours in TOURS_ESCALADE:
        ecart, duree, reponse_a, reponse_b = _ecart_apparie(
            lambda tour, offset=offset: appel_a(offset + tour),
            lambda tour, offset=offset: appel_b(offset + tour),
            tours=tours)
        dernier_ecart = ecart
        if abs(ecart) <= BRUIT_MAX_RESOLUBLE:
            return ecart, duree, tours, reponse_a, reponse_b
        offset += tours
    raise AssertionError(
        f"machine trop bruyante pour {nom}: témoin médian "
        f"{abs(dernier_ecart) * 1000:.2f} ms après {TOURS_ESCALADE[-1]} "
        f"tours, au-delà de {BRUIT_MAX_RESOLUBLE * 1000:.2f} ms; "
        "impossible de conclure sur une fuite de 20 ms")


def _tolerance_ecart(ecart_bruit):
    """The margin derived from the witness, with a resolution bound."""
    return max(FACTEUR_MARGE_BRUIT * abs(ecart_bruit), PLANCHER_ECART)


def _mesurer_ecart_corrige(appel_a, appel_b, *, bruit, tours_depart,
                           statut_attendu, nom):
    """Measures the real gap, making an isolated undecided spike explicit.

    The witness chooses a first number of pairs. If the real measurement stays
    beyond its margin, the same extra resolution is bought (45 then 135 pairs);
    the long bench guarantees the locked account stays closed during this
    retry. A real leak stays present at every step and therefore still fails at
    the end.
    """
    tolerance = _tolerance_ecart(bruit)
    candidats = TOURS_ESCALADE[TOURS_ESCALADE.index(tours_depart):]
    total_appels_a = 0
    offset = 0
    dernier = None
    for tours in candidats:
        mesure = _ecart_apparie(
            lambda tour, offset=offset: appel_a(offset + tour),
            lambda tour, offset=offset: appel_b(offset + tour),
            tours=tours)
        total_appels_a += tours
        offset += tours
        ecart, duree, reponse_a, reponse_b = mesure
        if not (reponse_a.status_code == reponse_b.status_code == statut_attendu):
            raise AssertionError(
                f"mesure {nom} non concluante : réponses "
                f"{reponse_a.status_code} et {reponse_b.status_code} après "
                f"{total_appels_a} appels du premier chemin")
        dernier = (*mesure, tours, total_appels_a)
        if abs(ecart - bruit) < tolerance:
            return dernier
    return dernier


def _wait_for_message(smtp, count):
    deadline = time.monotonic() + 5
    while len(smtp.messages) < count and time.monotonic() < deadline:
        time.sleep(0.02)
    assert len(smtp.messages) >= count
    body = smtp.messages[count - 1].get_body(
        preferencelist=("plain",)).get_content()
    match = re.search(r"reset token\s*:\s*([A-Za-z0-9_-]+)", body,
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


# Margin required before using a TOTP step: enough to hold the few HTTP round
# trips that follow, even under the full suite's load.
MARGE_FENETRE_TOTP = 10.0


def _pas_totp_stable(marge=MARGE_FENETRE_TOTP):
    """The current TOTP step, with the guarantee it stays so for `marge` seconds.

    Without this wait, the 30 s window can flip between computing a code and the
    server checking it: the test then measures something other than what it
    announces. That is what made the replay assertion fail in CI (run
    33136766014, `assert 200 == 401`) — the code recomputed after the flip was a
    NEW code, never consumed, which the server rightly accepted. Waiting for the
    start of the next window is the only way to write a replay assertion that is
    really about a replay.
    """
    reste = 30 - time.time() % 30
    if reste < marge:
        time.sleep(reste)
    return int(time.time()) // 30


def _totp_code(secret, step):
    """The code of the REQUESTED step. The step is mandatory: deducing it here
    from the clock is precisely what let a replay assertion be about a new code
    (see `_pas_totp_stable`)."""
    padded = secret + "=" * ((8 - len(secret) % 8) % 8)
    key = base64.b32decode(padded, casefold=True)
    digest = hmac.new(key, struct.pack(">Q", step), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    number = ((digest[offset] & 0x7F) << 24
              | digest[offset + 1] << 16
              | digest[offset + 2] << 8
              | digest[offset + 3])
    return f"{number % 1_000_000:06d}"


def test_full_b4_authentication_on_both_engines(b4_application):
    base, directory, dsn, smtp, mesure_base = b4_application
    alice = "alice-b4@example.invalid"
    bob = "bob-b4@example.invalid"
    _register(base, alice)
    _register(base, bob)

    # The short window is tested on the main server. The sleep is deliberate:
    # it proves spontaneous reopening, without an SQL write.
    for index in range(3):
        failed = _login(base, alice, "mauvais-pass", ip=f"lock-fail-{index}")
        assert failed.status_code == 401
        assert failed.json()["detail"] == "Invalid credentials."
    locked = _login(base, alice, "motdepasse8", ip="lock-correct")
    assert locked.status_code == 401
    assert locked.json()["detail"] == "Invalid credentials."
    bob_token = _token(_login(base, bob, "motdepasse8", ip="bob-before-totp"))
    assert _login(base, alice, "motdepasse8", ip="lock-still-closed").status_code == 401
    time.sleep(10.5)
    alice_token = _token(_login(base, alice, "motdepasse8", ip="lock-expired"))

    # The witness and the measurement live on the second server: its `3 in 300`
    # is not a production value, but the bench configuration that makes
    # resolution independent of the time spent by the escalation.
    mesure_alice = "alice-lock-mesure@example.invalid"
    _register(mesure_base, mesure_alice)
    # 1. Per-account counter, generic response and duration comparable to the
    # missing identifier. The IPs change so as not to confuse this test with
    # the historical per-IP limiting.
    for index in range(3):
        failed = _login(mesure_base, mesure_alice, "mauvais-pass",
                        ip=f"mesure-lock-fail-{index}")
        assert failed.status_code == 401
        assert failed.json()["detail"] == "Invalid credentials."
    locked = _login(mesure_base, mesure_alice, "motdepasse8", ip="mesure-lock-correct")
    assert locked.status_code == 401
    assert locked.json()["detail"] == "Invalid credentials."

    # The witness is taken right BEFORE the measurement, but AFTER setting the
    # lock: on the long bench, even the full escalation can no longer make it
    # expire. Noise and comparison thus undergo the same server load, instead
    # of comparing two distant moments.
    bruit_verrou, _, tours_verrou, control_a, control_b = _mesurer_bruit(
        lambda tour: _login(mesure_base, f"absent-lock-a-{tour}@example.invalid",
                            "motdepasse8", ip=f"lock-noise-a-{tour}"),
        lambda tour: _login(mesure_base, f"absent-lock-b-{tour}@example.invalid",
                            "motdepasse8", ip=f"lock-noise-b-{tour}"),
        nom="verrouillage")
    assert control_a.status_code == control_b.status_code == 401
    assert control_a.json() == control_b.json()

    (ecart_verrou, duree_verrou, locked_probe, missing_probe,
     tours_verrou_reel, _verrou_appels) = _mesurer_ecart_corrige(
        lambda tour: _login(mesure_base, mesure_alice, "motdepasse8",
                            ip=f"mesure-lock-timing-{tour}"),
        lambda tour: _login(mesure_base, "absent-b4@example.invalid", "motdepasse8",
                            ip=f"mesure-missing-timing-{tour}"),
        bruit=bruit_verrou, tours_depart=tours_verrou,
        statut_attendu=401, nom="verrouillage")
    assert locked_probe.status_code == missing_probe.status_code == 401
    assert locked_probe.json() == missing_probe.json()
    # A LOCKED account and a NONEXISTENT account must be indistinguishable:
    # telling them apart, even through response time, would teach an attacker
    # which addresses exist.
    ecart_corrige = ecart_verrou - bruit_verrou
    tolerance = _tolerance_ecart(bruit_verrou)
    assert abs(ecart_corrige) < tolerance, (
        f"ecart median {ecart_verrou*1000:.2f} ms, témoin "
        f"{bruit_verrou*1000:.2f} ms, pour un appel de "
        f"{duree_verrou*1000:.2f} ms — au-dela de "
        f"{tolerance*1000:.2f} ms ({tours_verrou_reel} tours)")
    # 2. Reset really delivered by the message brick, with no response
    # difference between a known address and a missing one.
    bruit_reset, _, tours_reset, reset_control_a, reset_control_b = _mesurer_bruit(
        lambda tour: _call("POST", base, "/password-reset/request",
                           body={"username": f"reset-noise-a-{tour}@example.invalid"},
                           ip=f"reset-noise-a-{tour}"),
        lambda tour: _call("POST", base, "/password-reset/request",
                           body={"username": f"reset-noise-b-{tour}@example.invalid"},
                           ip=f"reset-noise-b-{tour}"),
        nom="réinitialisation")
    assert reset_control_a.status_code == reset_control_b.status_code == 200
    assert reset_control_a.json() == reset_control_b.json()
    (ecart_reset, duree_reset, known, unknown,
     tours_reset_reel, reset_known_count) = _mesurer_ecart_corrige(
        lambda tour: _call("POST", base, "/password-reset/request",
                           body={"username": alice}, ip=f"reset-known-{tour}"),
        lambda tour: _call("POST", base, "/password-reset/request",
                           body={"username": "nobody-b4@example.invalid"},
                           ip=f"reset-unknown-{tour}"),
        bruit=bruit_reset, tours_depart=tours_reset,
        statut_attendu=200, nom="réinitialisation")
    assert known.status_code == unknown.status_code == 200
    assert known.json() == unknown.json()
    ecart_corrige = ecart_reset - bruit_reset
    tolerance = _tolerance_ecart(bruit_reset)
    assert abs(ecart_corrige) < tolerance, (
        f"ecart median {ecart_reset*1000:.2f} ms, témoin "
        f"{bruit_reset*1000:.2f} ms, pour un appel de "
        f"{duree_reset*1000:.2f} ms — au-dela de "
        f"{tolerance*1000:.2f} ms ({tours_reset_reel} tours)")
    # The "known address" path sent one email per round: the usable token is
    # the LAST one's, the previous ones possibly having been invalidated.
    alice_reset = _wait_for_message(smtp, reset_known_count)

    _call("POST", base, "/password-reset/request",
          body={"username": bob}, ip="reset-bob")
    bob_reset = _wait_for_message(smtp, reset_known_count + 1)
    assert bob_reset != alice_reset
    wrong_account = _call(
        "POST", base, "/password-reset/confirm",
        body={"username": bob, "token": alice_reset, "password": "nouveau-alice-8"},
        ip="reset-wrong-account")
    assert wrong_account.status_code == 400

    _call("POST", base, "/password-reset/request",
          body={"username": alice}, ip="reset-expired-request")
    expired = _wait_for_message(smtp, reset_known_count + 2)
    _expire_reset_token(directory, dsn, expired)
    assert _call(
        "POST", base, "/password-reset/confirm",
        body={"username": alice, "token": expired, "password": "nouveau-alice-8"},
        ip="reset-expired").status_code == 400

    _call("POST", base, "/password-reset/request",
          body={"username": alice}, ip="reset-success-request")
    fresh = _wait_for_message(smtp, reset_known_count + 3)
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

    # 3. The access JWT expires, the opaque token rotates, and it is not
    # interchangeable with a Bearer JWT.
    time.sleep(3.3)  # beyond MONL_TOKEN_TTL_SECONDS, set to 3
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

    # 4. Offline TOTP: activation, current code, previous window and replay.
    # The Alice account, without TOTP enabled, stayed able to log in above.
    bob_token = _token(_login(base, bob, "motdepasse8", ip="totp-session"))
    setup = _call("POST", base, "/totp/setup", token=bob_token, ip="totp-setup")
    assert setup.status_code == 200, setup.text
    secret = setup.json()["secret"]
    assert setup.json()["otpauth_uri"].startswith("otpauth://totp/")
    # The step is fixed BEFORE login: `_pas_totp_stable` may wait for the start
    # of the next window, and that wait would make the access token stale if it
    # happened after its issuance.
    pas_activation = _pas_totp_stable()
    # FRESH token: 'setup' and 'enable' are two calls, and the access token is
    # deliberately short. Reusing it would make the test sensitive to the first
    # call's duration rather than to the measured behavior.
    enabled = _call("POST", base, "/totp/enable",
                    token=_token(_login(base, bob, "motdepasse8",
                                        ip="totp-enable-session")),
                    body={"code": _totp_code(secret, pas_activation), "password": "motdepasse8"},
                    ip="totp-enable")
    assert enabled.status_code == 200, enabled.text
    # The step is fixed ONCE: the three logins that follow therefore all fall
    # in the same window, and the "previous" window is indeed the one right
    # before the accepted code.
    pas = _pas_totp_stable()
    code_courant = _totp_code(secret, pas)
    # The PREVIOUS window is tested BEFORE the valid login. After it, the
    # current step is consumed and replay protection refuses this code whatever
    # happens: the assertion would stay green while measuring nothing. Checked
    # by giving the server a ±1 window tolerance — placed after, it passed;
    # placed here, it turns red.
    assert _login(base, bob, "motdepasse8", ip="totp-other-window",
                  code=_totp_code(secret, pas - 1)).status_code == 401
    valid = _login(base, bob, "motdepasse8", ip="totp-valid", code=code_courant)
    assert valid.status_code == 200, valid.text
    # The SAME code, replayed: recomputing here would prove nothing as soon as
    # the window flipped between the two calls — the variable, and only it,
    # makes this line a replay assertion.
    assert _login(base, bob, "motdepasse8", ip="totp-replay",
                  code=code_courant).status_code == 401
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


def test_b4_does_not_break_a_historical_account(legacy_b4_application):
    base, directory, dsn, old_token = legacy_b4_application
    assert _call("GET", base, "/note", token=old_token).status_code == 200, (
        "La migration doit préserver le jeton ancien du compte inchangé")
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
    assert {"totp_secret", "totp_enabled", "totp_last_step", "token_version"} <= columns
    assert row == (None, None, None)



def _session_b4(base, username):
    _register(base, username)
    response = _login(base, username, "motdepasse8", ip=username)
    _token(response)
    return response.json()


def _activation_b4(base, session, password="motdepasse8"):
    pas = _pas_totp_stable()
    setup = _call("POST", base, "/totp/setup", token=session["access_token"])
    assert setup.status_code == 200, setup.text
    secret = setup.json()["secret"]
    enabled = _call("POST", base, "/totp/enable", token=session["access_token"],
                    body={"password": password, "code": _totp_code(secret, pas)})
    assert enabled.status_code == 200, enabled.text
    return secret, pas


def _manage_b4(directory, dsn, command, username, password=None):
    env = os.environ.copy()
    env.pop("MONL_DATABASE_URL", None)
    env["MONL_JWT_SECRET"] = "b4-integration-secret-32-bytes-min"
    if dsn:
        env["MONL_DATABASE_URL"] = dsn
    # getpass is replaced in the child process, without modifying manage.py.
    script = ("import getpass, runpy, sys; "
              f"getpass.getpass = lambda *a, **k: {password!r}; "
              f"sys.argv = ['manage.py', {command!r}, {username!r}]; "
              f"runpy.run_path({str(directory / 'manage.py')!r}, run_name='__main__')")
    result = subprocess.run([sys.executable, "-c", script], cwd="/tmp", env=env,
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    return result


def test_b4_activation_requires_the_password(b4_application):
    base, _, _, _, _ = b4_application
    username = "victime@example.invalid"
    session = _session_b4(base, username)
    pas = _pas_totp_stable()
    setup = _call("POST", base, "/totp/setup", token=session["access_token"])
    code = _totp_code(setup.json()["secret"], pas)
    absent = _call("POST", base, "/totp/enable", token=session["access_token"],
                   body={"code": code})
    assert absent.status_code >= 400, "Activation TOTP acceptée sans mot de passe"
    wrong = _call("POST", base, "/totp/enable", token=session["access_token"],
                  body={"code": code, "password": "incorrect"})
    assert wrong.status_code == 401, "Activation TOTP acceptée avec un mot de passe incorrect"
    bad_code = _call("POST", base, "/totp/enable", token=session["access_token"],
                     body={"code": "invalide", "password": "motdepasse8"})
    assert wrong.json() == bad_code.json() == {"detail": "Invalid credentials."}, (
        "Le code et le mot de passe incorrects doivent partager le refus générique")
    assert _login(base, username, "motdepasse8", ip="victime-intacte").status_code == 200


@pytest.mark.parametrize("jeton", ["refresh", "access"])
def test_b4_activation_revokes_the_tokens(b4_application, jeton):
    base, _, _, _, _ = b4_application
    username = "activation@example.invalid"
    session = _session_b4(base, username)
    temoin = _session_b4(base, "temoin@example.invalid")
    secret, pas = _activation_b4(base, session)
    if jeton == "refresh":
        response = _call("POST", base, "/refresh",
                         body={"refresh_token": session["refresh_token"]})
    else:
        response = _call("GET", base, "/note", token=session["access_token"])
    assert response.status_code == 401, f"Ancien jeton {jeton} accepté après activation TOTP"
    assert _call("GET", base, "/note", token=temoin["access_token"]).status_code == 200
    assert _login(base, username, "motdepasse8", ip="activation-sans-code").status_code == 401
    fresh = _login(base, username, "motdepasse8", ip="activation-legitime",
                   code=_totp_code(secret, pas))
    assert _call("GET", base, "/note", token=_token(fresh)).status_code == 200


@pytest.mark.parametrize("changement", ["reset", "passwd", "totp-reset"])
def test_b4_change_revokes_the_sessions(b4_application, changement):
    base, directory, dsn, smtp, _ = b4_application
    username = "recuperation@example.invalid"
    session = _session_b4(base, username)
    temoin = _session_b4(base, "intact@example.invalid")
    password = "nouveau-motdepasse8"
    if changement == "totp-reset":
        secret, pas = _activation_b4(base, session)
        session = _login(base, username, "motdepasse8", ip="avant-recuperation",
                         code=_totp_code(secret, pas)).json()
        _manage_b4(directory, dsn, "totp-reset", username)
        password = "motdepasse8"
    elif changement == "passwd":
        _manage_b4(directory, dsn, "passwd", username, password)
    else:
        _call("POST", base, "/password-reset/request", body={"username": username})
        reset = _wait_for_message(smtp, 1)
        response = _call("POST", base, "/password-reset/confirm",
                         body={"username": username, "token": reset, "password": password})
        assert response.status_code == 200, response.text
    assert _call("GET", base, "/note", token=session["access_token"]).status_code == 401, (
        f"Ancien accès accepté après {changement}")
    assert _call("POST", base, "/refresh", body={"refresh_token": session["refresh_token"]}).status_code == 401, (
        f"Ancien rafraîchissement accepté après {changement}")
    assert _call("GET", base, "/note", token=temoin["access_token"]).status_code == 200
    fresh = _login(base, username, password, ip="apres-recuperation")
    assert fresh.status_code == 200, (
        f"Connexion légitime refusée après {changement} : {fresh.text}")
    assert _call("GET", base, "/note", token=_token(fresh)).status_code == 200
    assert _call("POST", base, "/refresh", body={
        "refresh_token": fresh.json()["refresh_token"]}).status_code == 200, (
        f"Rafraîchissement légitime refusé après {changement}")


def test_b4_reset_email_preserve_totp_et_signature(b4_application):
    import copy
    import json

    from monl.cli import _contract_signature

    base, directory, _, smtp, _ = b4_application
    username = "double-facteur@example.invalid"
    session = _session_b4(base, username)
    secret, pas = _activation_b4(base, session)
    _call("POST", base, "/password-reset/request", body={"username": username})
    reset = _wait_for_message(smtp, 1)
    assert _call("POST", base, "/password-reset/confirm", body={
        "username": username, "token": reset, "password": "nouveau-motdepasse8"}).status_code == 200
    assert _login(base, username, "nouveau-motdepasse8", ip="reset-sans-code").status_code == 401, (
        "La réinitialisation par e-mail a supprimé le double facteur")
    assert _token(_login(base, username, "nouveau-motdepasse8", ip="reset-avec-code",
                         code=_totp_code(secret, pas)))
    contract = json.loads((directory / "frontend_contract.json").read_text())
    enable_route = next(route for route in contract["routes"]
                        if route["path"] == "/totp/enable")
    assert "password" in enable_route["request_fields"], (
        "Le contrat oublie le mot de passe requis à l'activation TOTP")
    old = copy.deepcopy(contract)
    del old["api"]["auth"]["features"]["totp"]["enable_body"]["password"]
    assert _contract_signature(old) != _contract_signature(contract), (
        "La signature ignore le mot de passe requis à l'activation TOTP")
