"""AJOUT (roadmap long terme, rate limiting multi-workers) : vérifie que la
limitation de débit est partagée entre plusieurs workers uvicorn — le quota
(5 tentatives / 60 s / IP) s'applique GLOBALEMENT, pas par worker.

Avec l'ancien compteur en mémoire de processus, deux workers auraient
autorisé 2×5 = 10 tentatives avant de bloquer. Le compteur étant désormais
en base (partagée), le 6e échec est bloqué (429) quel que soit le nombre de
workers.
"""
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
