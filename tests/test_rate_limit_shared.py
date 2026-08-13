"""AJOUT (roadmap long terme, rate limiting multi-workers) : vérifie que la
limitation de débit est partagée entre plusieurs workers uvicorn — le quota
(5 tentatives / 60 s / IP) s'applique GLOBALEMENT, pas par worker.

Avec l'ancien compteur en mémoire de processus, deux workers auraient
autorisé 2×5 = 10 tentatives avant de bloquer. Le compteur étant désormais
en base (partagée), le 6e échec est bloqué (429) quel que soit le nombre de
workers.
"""
import os
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time

import requests

from monl.ast_validator import MonlAST
from monl.generator import MonlSecureGenerator
from monl.parser import parse_monl_string
from tests.support.server import free_port as _find_free_port

SPEC = """app RL

entity User
    name: String

actor User selfRegister

workflow W for User
    Read User
"""


MARQUEUR_PRET = "Application startup complete"


def _wait(port, timeout=20):
    start = time.time()
    while time.time() - start < timeout:
        try:
            requests.get(f"http://127.0.0.1:{port}/docs", timeout=1)
            return True
        except requests.exceptions.ConnectionError:
            time.sleep(0.3)
    return False


def _attendre_les_deux_workers(proc, journal, attendus=2, timeout=40):
    """Attendre que CHAQUE worker ait démarré, pas seulement le premier.

    Une sonde HTTP ne prouve rien ici : avec `--workers N`, c'est le
    superviseur uvicorn qui ouvre la socket, puis il fork. Un GET réussi
    prouve donc que la socket accepte — pas qu'il y a quelqu'un derrière
    chaque worker. Les connexions distribuées à un worker encore en train de
    démarrer sont RÉINITIALISÉES, et c'est exactement ce que la CI a montré :
    `ConnectionResetError(104)` au milieu de la rafale, sur du code serveur
    parfaitement correct.

    uvicorn écrit `Application startup complete` UNE FOIS PAR WORKER : on
    compte ces lignes plutôt que de deviner. Le tuyau doit être vidé dans un
    fil séparé — laissé plein, il finirait par bloquer le serveur qu'on
    observe.
    """
    debut = time.time()
    while time.time() - debut < timeout:
        if sum(MARQUEUR_PRET in ligne for ligne in list(journal)) >= attendus:
            return True
        if proc.poll() is not None:
            return False
        time.sleep(0.2)
    return False


def _journaliser(proc):
    journal = []

    def _vider():
        for ligne in proc.stderr:
            journal.append(ligne)

    threading.Thread(target=_vider, daemon=True).start()
    return journal


def test_rate_limit_is_shared_across_workers():
    with tempfile.TemporaryDirectory() as workdir:
        ast = MonlAST(parse_monl_string(SPEC)).validate_and_audit()
        MonlSecureGenerator(ast, output_dir=workdir).generate_all()

        port = _find_free_port()
        proc = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app:app", "--port", str(port), "--workers", "2"],
            cwd=workdir, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
            text=True,
        )
        journal = _journaliser(proc)
        try:
            assert _attendre_les_deux_workers(proc, journal), (
                "les deux workers n'ont pas signale leur demarrage :\n"
                + "".join(journal[-20:]))
            assert _wait(port), "le serveur multi-workers n'a pas démarré"
            base = f"http://127.0.0.1:{port}"
            codes = []
            for _ in range(7):
                r = requests.post(f"{base}/login",
                                  json={"username": "inconnu", "password": "mauvais123"})
                codes.append(r.status_code)

            # Les 5 premières tentatives sont autorisées (401 : identifiants
            # invalides), la 6e et au-delà sont bloquées (429), même avec
            # 2 workers — preuve que le quota est global, pas par worker.
            assert codes[:5] == [401] * 5, codes
            assert codes[5] == 429, codes
            assert codes[6] == 429, codes
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()


def test_le_demarrage_survit_a_une_base_deja_verrouillee():
    """Un worker ne doit pas MOURIR parce qu'un autre écrit au même instant.

    Trouvé par la CI, sur du code vieux de plusieurs mois : démarré avec
    `--workers 2`, un worker écrivait le schéma pendant que l'autre exécutait
    `PRAGMA journal_mode = WAL`, et ce pragma est le SEUL endroit du socle que
    `busy_timeout` ne protège pas — mesuré : face à une transaction de lecture
    il attend le délai entier puis échoue quand même, face à une transaction
    d'écriture il échoue en 0,00 s. Le worker mourait, et uvicorn arrêtait le
    serveur entier.

    Le test ne COURSE pas : il tient lui-même le verrou d'écriture le temps
    que le serveur démarre, puis le relâche. Sans la correction, le démarrage
    échoue à tous les coups ; avec, il attend et démarre.
    """
    with tempfile.TemporaryDirectory() as workdir:
        ast = MonlAST(parse_monl_string(SPEC)).validate_and_audit()
        MonlSecureGenerator(ast, output_dir=workdir).generate_all()

        # Une base qui existe déjà et qu'un AUTRE processus est en train
        # d'écrire — exactement l'état où se trouve le second worker.
        chemin = os.path.join(workdir, "app.db")
        rival = sqlite3.connect(chemin, timeout=10.0)
        rival.execute("CREATE TABLE IF NOT EXISTS _verrou_essai (x INTEGER)")
        rival.commit()
        rival.execute("BEGIN IMMEDIATE")
        rival.execute("INSERT INTO _verrou_essai VALUES (1)")

        port = _find_free_port()
        proc = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app:app", "--port", str(port)],
            cwd=workdir, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
            text=True,
        )
        journal = _journaliser(proc)
        try:
            # Relâché APRÈS que le pragma et le premier essai de schéma ont
            # eu lieu : c'est la fenêtre que vit un vrai second worker. Depuis
            # le fil PRINCIPAL — une connexion SQLite n'appartient qu'au fil
            # qui l'a ouverte, et un `threading.Timer` échouait donc en
            # silence, laissant le verrou posé pour toujours.
            time.sleep(3.0)
            rival.rollback()
            rival.close()
            assert _attendre_les_deux_workers(proc, journal, attendus=1), (
                "le serveur est mort sur une base verrouillée :\n"
                + "".join(journal[-20:]))
            assert _wait(port), "le serveur n'a pas démarré"
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
