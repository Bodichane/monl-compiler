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
        # Court, pour PROUVER que le jeton d'accès expire — mais pas au point
        # qu'un simple aller-retour HTTP le périme. À 1 seconde, la phase TOTP
        # échouait par intermittence sous la charge de la suite complète : le
        # jeton obtenu à la connexion était déjà expiré à l'appel suivant, et
        # le test dénonçait alors une application saine. C'est le reproche que
        # la bêta 4 avait déjà traité sur le test du canal temporel : un test
        # ne doit pas dépendre de la charge de la machine.
        "MONL_TOKEN_TTL_SECONDS": "3",
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


# Nombre de tours des mesures de temps. Le compteur de messages plus bas en
# dépend : la voie « adresse connue » envoie un courriel à CHAQUE tour.
#
# Cinq tours ne suffisaient pas. La médiane de CINQ écarts appariés reste
# sensible à un blocage isolé : mesuré sur douze répétitions, elle montait à
# 9,70 ms au repos et 6,29 ms sous charge, là où la médiane de QUINZE restait
# sous 1,54 ms et 2,95 ms. Et c'est bien l'estimateur qui a lâché en CI, avec
# une médiane de 0,1016 s pour un seuil de 0,10 — 1,6 ms de trop.
TOURS_MESURE = 15

# La tolérance est RELATIVE au temps de réponse observé, avec un plancher.
# Cent millisecondes en absolu ne veulent pas dire la même chose sur un runner
# partagé où un appel prend 300 ms et sur cette machine où il en prend 66 : le
# seuil était tantôt impossible à tenir, tantôt trop large pour rien dire.
# Ce qui compte pour un attaquant est le SIGNAL par rapport au BRUIT.
#
# Les chiffres, mesurés sur 36 répétitions de quinze tours (au repos et sous
# charge) : l'écart médian vaut 0,1 à 3,8 ms pour un appel de 48 à 85 ms, soit
# un rapport d'au plus 4,4 %. Vingt pour cent laissent donc 4,5 fois la marge
# du pire cas observé.
#
# CE QUE LE SEUIL ATTRAPE, mesuré en injectant une vraie fuite dans la branche
# « compte verrouillé » du serveur généré : 10 ms passent, 20 ms sont refusées
# (19,83 ms mesurées pour une tolérance de 16,45), 30 ms aussi. Le plancher de
# détection est donc d'une vingtaine de millisecondes sur cette machine — cinq
# fois plus fin que les 100 ms absolues d'avant, qui laissaient passer tout ce
# qui était en dessous. Le seuil relatif est à la fois plus SENSIBLE et plus
# ROBUSTE ; ce n'est pas un assouplissement.
#
# Une différence RÉELLE et petite subsiste, et il faut la connaître : le chemin
# verrouillé coûte 1,6 à 1,8 ms de plus que le chemin absent, dans 19 mesures
# sur 24. Ce n'est pas un artefact de l'ordre des appels — mesuré en inversant
# l'ordre à l'intérieur de chaque paire, le biais ne bouge pas (+1,81 ms contre
# +1,63 ms). Le test BORNE cette différence, il n'exige pas zéro : exiger zéro
# d'une mesure de temps serait une promesse qu'aucune machine ne tient.
#
# Le plancher existe pour la machine RAPIDE : à 5 ms par appel, 20 % feraient
# 1 ms, sous le bruit de mesure. Un seuil qu'aucune machine ne peut tenir ne
# mesure plus rien, il apprend à ignorer l'échec (point 57).
PART_ECART_TOLEREE = 0.20
PLANCHER_ECART = 0.005


def _ecart_apparie(appel_a, appel_b, tours=TOURS_MESURE):
    """Écart médian entre deux chemins, mesuré en ALTERNANCE et par paires.

    Un oracle temporel est une TENDANCE, pas un instant. Mesuré à un seul
    tirage sur un runner partagé, il suffit d'un sursaut (ordonnanceur,
    ramasse-miettes, voisin bruyant) pour faire échouer la comparaison : la CI
    est tombée exactement comme ça, à 0,4 ms près sur un seuil de 200 ms,
    pendant que le même test passait sur l'autre exécution de la même version
    de Python. Un test de sécurité qui se trompe une fois sur deux apprend à
    ne plus lire les échecs — c'est l'arbitrage du point 57.

    Deux corrections, et la seconde est celle qui manquait. La MÉDIANE écarte
    un sursaut isolé sans rien masquer : une vraie fuite de temps déplace
    TOUTES les mesures, pas une seule. Mais mesurer un chemin en entier PUIS
    l'autre laisse toute la dérive de la machine dans l'écart : sous huit
    cœurs saturés, la première série montait de 0,20 à 0,37 s pendant que la
    seconde restait plate — un écart de 130 ms attribué au verrouillage, alors
    qu'il n'appartenait qu'à l'ORDRE des mesures. Les deux chemins sont donc
    appelés en ALTERNANCE et l'écart est calculé PAIRE PAR PAIRE : un sursaut
    frappe les deux membres d'une même paire et s'annule dans leur différence,
    là où une vraie fuite, elle, est présente dans chaque paire.

    L'IP change à chaque tour : sans quoi la limitation par IP (5 / 60 s,
    points 13 et 33) répondrait 429 au sixième appel et mesurerait le refus du
    limiteur au lieu du chemin d'authentification.
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
    # La durée médiane accompagne l'écart : c'est l'ÉCHELLE à laquelle il doit
    # être jugé. Sans elle, l'appelant ne pourrait comparer qu'à un nombre de
    # secondes écrit d'avance, qui ne veut pas dire la même chose d'une machine
    # à l'autre.
    return (statistics.median(ecarts), statistics.median(durees),
            reponse_a, reponse_b)


def _tolerance_ecart(duree_mediane):
    """La marge admise pour un écart de temps, à l'échelle de la machine."""
    return max(PART_ECART_TOLEREE * duree_mediane, PLANCHER_ECART)


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


# Marge exigée avant d'employer un pas TOTP : de quoi tenir les quelques
# allers-retours HTTP qui suivent, même sous la charge de la suite complète.
MARGE_FENETRE_TOTP = 10.0


def _pas_totp_stable(marge=MARGE_FENETRE_TOTP):
    """Le pas TOTP courant, avec la garantie qu'il le reste `marge` secondes.

    Sans cette attente, la fenêtre de 30 s peut basculer entre le calcul d'un
    code et sa vérification par le serveur : le test mesure alors autre chose
    que ce qu'il annonce. C'est ce qui faisait échouer l'assertion de rejeu en
    CI (run 33136766014, `assert 200 == 401`) — le code recalculé après la
    bascule était un code NEUF, jamais consommé, que le serveur acceptait à
    juste titre. Attendre le début de la fenêtre suivante est le seul moyen
    d'écrire une assertion de rejeu qui porte réellement sur un rejeu.
    """
    reste = 30 - time.time() % 30
    if reste < marge:
        time.sleep(reste)
    return int(time.time()) // 30


def _totp_code(secret, step):
    """Le code du pas DEMANDÉ. Le pas est obligatoire : le déduire ici de
    l'horloge est précisément ce qui laissait une assertion de rejeu porter
    sur un code neuf (voir `_pas_totp_stable`)."""
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

    ecart_verrou, duree_verrou, locked_probe, missing_probe = _ecart_apparie(
        lambda tour: _login(base, alice, "motdepasse8",
                            ip=f"lock-timing-{tour}"),
        lambda tour: _login(base, "absent-b4@example.invalid", "motdepasse8",
                            ip=f"missing-timing-{tour}"))
    assert locked_probe.status_code == missing_probe.status_code == 401
    assert locked_probe.json() == missing_probe.json()
    # Un compte VERROUILLÉ et un compte INEXISTANT doivent être
    # indiscernables : les distinguer, fût-ce par le temps de réponse,
    # apprendrait à un attaquant quelles adresses existent.
    tolerance = _tolerance_ecart(duree_verrou)
    assert abs(ecart_verrou) < tolerance, (
        f"ecart median {ecart_verrou*1000:.2f} ms pour un appel de "
        f"{duree_verrou*1000:.2f} ms — au-dela de {tolerance*1000:.2f} ms")
    assert _login(base, alice, "motdepasse8", ip="lock-still-closed").status_code == 401
    # La fenêtre de verrouillage est passée de 2 à 10 secondes, et ce n'est
    # pas du confort : la mesure d'oracle ci-dessus fait DIX appels, et avec
    # une fenêtre de 2 s elle expirait le verrou avant l'assertion « toujours
    # fermé » — le test échouait alors sous charge en accusant le mauvais
    # coupable. Le `sleep` reste, parce qu'il prouve ce qu'aucune écriture en
    # base ne prouverait : que le verrou se rouvre TOUT SEUL, au bout du temps
    # déclaré.
    time.sleep(10.5)
    alice_token = _token(_login(base, alice, "motdepasse8", ip="lock-expired"))

    # 2. Réinitialisation réellement livrée par la brique de messages, sans
    # différence de réponse entre une adresse connue et une adresse absente.
    ecart_reset, duree_reset, known, unknown = _ecart_apparie(
        lambda tour: _call("POST", base, "/password-reset/request",
                           body={"username": alice}, ip=f"reset-known-{tour}"),
        lambda tour: _call("POST", base, "/password-reset/request",
                           body={"username": "nobody-b4@example.invalid"},
                           ip=f"reset-unknown-{tour}"))
    assert known.status_code == unknown.status_code == 200
    assert known.json() == unknown.json()
    tolerance = _tolerance_ecart(duree_reset)
    assert abs(ecart_reset) < tolerance, (
        f"ecart median {ecart_reset*1000:.2f} ms pour un appel de "
        f"{duree_reset*1000:.2f} ms — au-dela de {tolerance*1000:.2f} ms")
    # La voie « adresse connue » a envoyé un courriel par tour : le jeton
    # utilisable est celui du DERNIER, les précédents ayant pu être invalidés.
    alice_reset = _wait_for_message(smtp, TOURS_MESURE)

    _call("POST", base, "/password-reset/request",
          body={"username": bob}, ip="reset-bob")
    bob_reset = _wait_for_message(smtp, TOURS_MESURE + 1)
    assert bob_reset != alice_reset
    wrong_account = _call(
        "POST", base, "/password-reset/confirm",
        body={"username": bob, "token": alice_reset, "password": "nouveau-alice-8"},
        ip="reset-wrong-account")
    assert wrong_account.status_code == 400

    _call("POST", base, "/password-reset/request",
          body={"username": alice}, ip="reset-expired-request")
    expired = _wait_for_message(smtp, TOURS_MESURE + 2)
    _expire_reset_token(directory, dsn, expired)
    assert _call(
        "POST", base, "/password-reset/confirm",
        body={"username": alice, "token": expired, "password": "nouveau-alice-8"},
        ip="reset-expired").status_code == 400

    _call("POST", base, "/password-reset/request",
          body={"username": alice}, ip="reset-success-request")
    fresh = _wait_for_message(smtp, TOURS_MESURE + 3)
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
    time.sleep(3.3)  # au-delà de MONL_TOKEN_TTL_SECONDS, réglé à 3
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
    # Le pas est arrêté AVANT la connexion : `_pas_totp_stable` peut attendre
    # le début de la fenêtre suivante, et cette attente périmerait le jeton
    # d'accès si elle avait lieu après son émission.
    pas_activation = _pas_totp_stable()
    # Jeton NEUF : 'setup' et 'enable' sont deux appels, et le jeton d'accès
    # est volontairement court. Le réutiliser rendrait le test sensible à la
    # durée du premier appel plutôt qu'au comportement mesuré.
    enabled = _call("POST", base, "/totp/enable",
                    token=_token(_login(base, bob, "motdepasse8",
                                        ip="totp-enable-session")),
                    body={"code": _totp_code(secret, pas_activation)},
                    ip="totp-enable")
    assert enabled.status_code == 200, enabled.text
    # Le pas est arrêté UNE fois : les trois connexions qui suivent portent
    # donc toutes sur la même fenêtre, et la fenêtre « précédente » est bien
    # celle qui précède immédiatement le code accepté.
    pas = _pas_totp_stable()
    code_courant = _totp_code(secret, pas)
    # La fenêtre PRÉCÉDENTE s'éprouve AVANT la connexion valide. Après elle,
    # le pas courant est consommé et l'anti-rejeu refuse ce code quoi qu'il
    # arrive : l'assertion resterait verte sans plus rien mesurer. Vérifié en
    # donnant au serveur une tolérance de ±1 fenêtre — placée après, elle
    # passait ; placée ici, elle devient rouge.
    assert _login(base, bob, "motdepasse8", ip="totp-other-window",
                  code=_totp_code(secret, pas - 1)).status_code == 401
    valid = _login(base, bob, "motdepasse8", ip="totp-valid", code=code_courant)
    assert valid.status_code == 200, valid.text
    # Le MÊME code, rejoué : recalculer ici ne prouverait rien dès que la
    # fenêtre a basculé entre les deux appels — c'est la variable, et elle
    # seule, qui fait de cette ligne une assertion de rejeu.
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
