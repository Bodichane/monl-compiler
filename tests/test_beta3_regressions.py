"""Non-régression des correctifs de sécurité de la bêta 0.9.0-beta.3.

Chaque test rejoue une faille réelle constatée sur la bêta 2 :

1. auto-attribution d'un rôle privilégié à l'inscription (élévation de
   privilège complète en deux appels HTTP anonymes) ;
2. énumération des comptes par le temps de réponse de /login ;
3. quota de tentatives contournable en parallèle (TOCTOU) ;
4. secret de signature lisible par tout compte local ;
5. liste noire de jetons jamais purgée ;
6. sortie de compilation non reproductible d'une exécution à l'autre.
"""
import json
import os
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
    """Efface le compteur de tentatives de l'application (point 67).

    Le quota (5 / 60 s / IP) est persisté en base — c'est tout l'objet du
    point 33. Un test qui veut plus de cinq mesures n'a donc pas à dormir une
    minute : il lui suffit de vider la table, ce qui n'affaiblit rien du
    produit et ne concerne que le banc d'essai."""
    import sqlite3
    with sqlite3.connect(os.path.join(workdir, "app.db")) as cnx:
        cnx.execute("DELETE FROM _monl_rate_limit")


def _login(base, username, password="motdepasse123"):
    """Se connecte en tolérant le quota partagé par les tests de ce module."""
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


# --------------------------------------------------------------------------
# 1. Élévation de privilège par l'inscription
# --------------------------------------------------------------------------

def test_role_provisionne_refuse_a_inscription(app_server):
    """Un client ne peut pas s'attribuer un rôle absent de 'selfRegister'."""
    r = requests.post(app_server.base + "/register",
                      json={"username": "pirate", "password": "motdepasse123", "actor": "Admin"})
    assert r.status_code == 403, r.text
    # ...et le compte ne doit pas exister : la connexion échoue aussi.
    assert _login(app_server.base, "pirate").status_code == 401


def test_role_ouvert_accepte_puis_reste_confine(app_server):
    """Le rôle 'selfRegister' s'inscrit, mais n'obtient pas les droits d'Admin."""
    requests.post(app_server.base + "/register",
                  json={"username": "membre", "password": "motdepasse123", "actor": "Member"})
    token = _login(app_server.base, "membre").json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    assert requests.post(app_server.base + "/note", headers=headers,
                         json={"title": "à moi"}).status_code == 200
    assert requests.post(app_server.base + "/product", headers=headers,
                         json={"label": "interdit"}).status_code == 403


def test_role_provisionne_par_manage_py(app_server):
    """Le chemin légitime : création du compte privilégié sur le serveur."""
    proc = subprocess.run(
        [sys.executable, "manage.py", "adduser", "patron", "Admin"],
        cwd=app_server.workdir, input="motdepasse123\nmotdepasse123\n",
        capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    token = _login(app_server.base, "patron").json()["access_token"]
    r = requests.post(app_server.base + "/product",
                      headers={"Authorization": f"Bearer {token}"}, json={"label": "légitime"})
    assert r.status_code == 200, r.text


# --------------------------------------------------------------------------
# 2. Énumération de comptes par canal temporel
# --------------------------------------------------------------------------

def test_login_ne_revele_pas_l_existence_du_compte():
    """Le temps de réponse ne doit pas trahir l'existence d'un identifiant.

    Le compte 'membre' existe (créé plus haut), 'fantome' non. Sans le
    hachage factice, /login répondait sans dérouler les 100 000 itérations
    PBKDF2 quand le compte était inconnu : l'écart (~50-100 ms) suffisait à
    énumérer les comptes. On compare donc au coût d'un hachage réel, mesuré
    sur la machine courante — seule référence stable d'une machine à l'autre.

    Contrainte : le quota est de 5 tentatives / 60 s / IP. On le vide entre
    les mesures (voir _vider_quota) plutôt que de s'y limiter, et on retient
    le MINIMUM de chaque groupe — le plus proche du coût réel du traitement,
    le bruit ne pouvant qu'ajouter du temps.

    POINT 67 : ce test échouait par intermittence en CI, jamais en local. Un
    runner partagé est une machine bruyante ; deux mesures suffisaient à ce
    qu'une préemption fasse exploser l'écart. Deux corrections, aucune ne
    touchant à ce qui est prouvé : cinq échantillons par groupe au lieu de
    deux, et la mesure entière rejouée jusqu'à trois fois. Une vraie fuite
    temporelle est SYSTÉMATIQUE — elle se reproduit à chaque tour ; le bruit,
    non. Élargir le seuil aurait au contraire rendu le test aveugle à la
    fuite qu'il surveille.
    """

    # Serveur dédié : les mesures consomment le quota de tentatives, elles ne
    # peuvent pas partager l'instance des autres tests.
    #
    # POINT 67 : le serveur était démarré à la main et arrêté par une ligne
    # placée APRÈS les mesures — un échec d'assertion laissait donc un uvicorn
    # orphelin et un dossier temporaire derrière lui, sur une machine qui
    # allait enchaîner d'autres serveurs. Un test instable qui fuit un
    # processus contamine ceux d'après : l'échec suivant n'a plus rien à voir
    # avec sa cause.
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

    mesure("echauffement")  # première requête : coûts de démarrage, écartée

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


# --------------------------------------------------------------------------
# 3. Quota de tentatives : atomicité
# --------------------------------------------------------------------------

def test_quota_non_contournable_en_parallele():
    """20 connexions simultanées ne doivent pas toutes passer le quota de 5."""
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


# --------------------------------------------------------------------------
# 4 & 5. Hygiène du secret et purge de la liste noire
# --------------------------------------------------------------------------

def test_secret_jwt_lisible_par_le_seul_proprietaire():
    with tempfile.TemporaryDirectory() as workdir:
        _compile(workdir)
        mode = os.stat(os.path.join(workdir, ".jwt_secret")).st_mode & 0o777
        assert mode == 0o600, f"permissions {oct(mode)} : le secret est lisible par d'autres comptes"


def test_liste_noire_des_jetons_purgeable():
    """La table des jetons révoqués porte la date d'expiration nécessaire à sa purge."""
    with tempfile.TemporaryDirectory() as workdir:
        _compile(workdir)
        schema = open(os.path.join(workdir, "schema.sql"), encoding="utf-8").read()
        assert "expires_at" in schema
        app = open(os.path.join(workdir, "app.py"), encoding="utf-8").read()
        assert "DELETE FROM _monl_revoked_tokens WHERE expires_at" in app


def test_logout_revoque_le_jeton(app_server):
    requests.post(app_server.base + "/register",
                  json={"username": "sortant", "password": "motdepasse123", "actor": "Member"})
    token = _login(app_server.base, "sortant").json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    assert requests.get(app_server.base + "/note", headers=headers).status_code == 200
    assert requests.post(app_server.base + "/logout", headers=headers).status_code == 200
    assert requests.get(app_server.base + "/note", headers=headers).status_code == 401


# --------------------------------------------------------------------------
# 6. Déterminisme de la compilation
# --------------------------------------------------------------------------

def test_compilation_reproductible_entre_processus():
    """Deux compilations de la même spec doivent produire les mêmes octets.

    L'ordre d'itération des ensembles Python varie d'un processus à l'autre
    (PYTHONHASHSEED) : le test compile dans deux sous-processus aux graines
    de hachage opposées, ce qu'une compilation dans le processus courant ne
    pourrait pas détecter.
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
                name: open(os.path.join(workdir, name), encoding="utf-8").read()
                for name in ("app.py", "schema.sql", "manage.py")
            }
    for name in sources["0"]:
        assert sources["0"][name] == sources["1"][name], (
            f"{name} diffère entre deux compilations de la même spec : "
            "la sortie dépend de l'ordre d'itération d'un ensemble Python")


# --------------------------------------------------------------------------
# 7. Contrat frontend : périmètre d'inscription publié
# --------------------------------------------------------------------------

def test_contrat_publie_le_perimetre_d_inscription():
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
    json.dumps(contract)  # le contrat doit rester sérialisable
