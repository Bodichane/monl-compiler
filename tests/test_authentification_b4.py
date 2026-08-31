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

# Le banc garde deux fenêtres délibérément différentes. Le serveur principal
# éprouve la réouverture spontanée avec la fenêtre courte ; le serveur de
# mesure doit pouvoir contenir l'escalade complète (135 paires, soit 270
# appels) sans transformer le verrou en variable cachée de la mesure.
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


# Nombre de tours de départ des mesures de temps. Le compteur de messages plus
# bas en dépend : la voie « adresse connue » envoie un courriel à CHAQUE tour.
# Le témoin de bruit peut acheter de la résolution, sans dépasser la borne
# déclarée ci-dessous.
TOURS_MESURE = 15
TOURS_ESCALADE = (TOURS_MESURE, TOURS_MESURE * 3, TOURS_MESURE * 9)

# La tolérance vient d'un TÉMOIN mesuré juste avant chaque comparaison : deux
# appels du même chemin, avec des IP distinctes. Leur écart ne peut pas porter
# une fuite applicative ; il mesure le bruit du runner à cet instant. Deux fois
# ce bruit couvrent les deux médianes comparées, et le plancher protège la
# machine assez rapide pour laquelle un témoin nul ne signifie pas une horloge
# parfaite.
#
# Le bruit n'est PAS autorisé à désarmer l'oracle. Le témoin doit rester sous
# 7,5 ms, ce qui borne la marge dérivée à 15 ms et laisse une fuite de l'ordre
# de 20 ms détectable. S'il dépasse cette borne, on dépense d'abord plus de
# mesure (15 → 45 → 135) ; s'il reste trop grand, le test échoue explicitement.
#
# Ces deux constantes expriment une exigence de résolution, pas un étalonnage
# de machine : la fuite de 20 ms est la contre-épreuve du point 160.
FACTEUR_MARGE_BRUIT = 2.0
BRUIT_MAX_RESOLUBLE = 0.0075
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


def _mesurer_bruit(appel_a, appel_b, *, nom):
    """Mesure le bruit pur, puis augmente la dépense si nécessaire.

    `appel_a` et `appel_b` doivent représenter le même chemin. Le décalage
    transmis aux callbacks rend les IP uniques même si une escalade rejoue la
    mesure : le limiteur ne doit jamais devenir le signal observé.
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
    """La marge dérivée du témoin, avec une borne de résolution."""
    return max(FACTEUR_MARGE_BRUIT * abs(ecart_bruit), PLANCHER_ECART)


def _mesurer_ecart_corrige(appel_a, appel_b, *, bruit, tours_depart,
                           statut_attendu, nom):
    """Mesure l'écart réel, en rendant un sursaut isolé indécis explicite.

    Le témoin choisit un premier nombre de paires. Si la mesure réelle reste
    au-delà de sa marge, on achète la même résolution supplémentaire (45 puis
    135 paires) ; le banc long garantit que le compte verrouillé reste fermé
    pendant cette reprise. Une fuite réelle reste présente à chaque palier et
    échoue donc encore à la fin.
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
    base, directory, dsn, smtp, mesure_base = b4_application
    alice = "alice-b4@example.invalid"
    bob = "bob-b4@example.invalid"
    _register(base, alice)
    _register(base, bob)

    # La fenêtre courte est éprouvée sur le serveur principal. Le sommeil est
    # volontaire : il prouve la réouverture spontanée, sans écriture SQL.
    for index in range(3):
        failed = _login(base, alice, "mauvais-pass", ip=f"lock-fail-{index}")
        assert failed.status_code == 401
        assert failed.json()["detail"] == "Identifiants invalides."
    locked = _login(base, alice, "motdepasse8", ip="lock-correct")
    assert locked.status_code == 401
    assert locked.json()["detail"] == "Identifiants invalides."
    bob_token = _token(_login(base, bob, "motdepasse8", ip="bob-before-totp"))
    assert _login(base, alice, "motdepasse8", ip="lock-still-closed").status_code == 401
    time.sleep(10.5)
    alice_token = _token(_login(base, alice, "motdepasse8", ip="lock-expired"))

    # Le témoin et la mesure vivent sur le second serveur : son `3 in 300`
    # n'est pas une valeur de production, mais la configuration de banc qui
    # rend la résolution indépendante du temps dépensé par l'escalade.
    mesure_alice = "alice-lock-mesure@example.invalid"
    _register(mesure_base, mesure_alice)
    # 1. Compteur par compte, réponse générique et durée comparable à
    # l'identifiant absent. Les IP changent pour ne pas confondre ce test avec
    # la limitation historique par IP.
    for index in range(3):
        failed = _login(mesure_base, mesure_alice, "mauvais-pass",
                        ip=f"mesure-lock-fail-{index}")
        assert failed.status_code == 401
        assert failed.json()["detail"] == "Identifiants invalides."
    locked = _login(mesure_base, mesure_alice, "motdepasse8", ip="mesure-lock-correct")
    assert locked.status_code == 401
    assert locked.json()["detail"] == "Identifiants invalides."

    # Le témoin est pris immédiatement AVANT la mesure, mais APRÈS avoir posé
    # le verrou : sur le banc long, même l'escalade complète ne peut plus le
    # faire expirer. Le bruit et la comparaison subissent ainsi la même charge
    # du serveur, au lieu de comparer deux instants éloignés.
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
    # Un compte VERROUILLÉ et un compte INEXISTANT doivent être
    # indiscernables : les distinguer, fût-ce par le temps de réponse,
    # apprendrait à un attaquant quelles adresses existent.
    ecart_corrige = ecart_verrou - bruit_verrou
    tolerance = _tolerance_ecart(bruit_verrou)
    assert abs(ecart_corrige) < tolerance, (
        f"ecart median {ecart_verrou*1000:.2f} ms, témoin "
        f"{bruit_verrou*1000:.2f} ms, pour un appel de "
        f"{duree_verrou*1000:.2f} ms — au-dela de "
        f"{tolerance*1000:.2f} ms ({tours_verrou_reel} tours)")
    # 2. Réinitialisation réellement livrée par la brique de messages, sans
    # différence de réponse entre une adresse connue et une adresse absente.
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
    # La voie « adresse connue » a envoyé un courriel par tour : le jeton
    # utilisable est celui du DERNIER, les précédents ayant pu être invalidés.
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
