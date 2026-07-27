"""AJOUT (roadmap long terme, rate limiting multi-workers) : vérifie que la
limitation de débit est partagée entre plusieurs workers uvicorn — le quota
(5 tentatives / 60 s / IP) s'applique GLOBALEMENT, pas par worker.

Avec l'ancien compteur en mémoire de processus, deux workers auraient
autorisé 2×5 = 10 tentatives avant de bloquer. Le compteur étant désormais
en base (partagée), le 6e échec est bloqué (429) quel que soit le nombre de
workers.
"""
import os
import socket
import subprocess
import sys
import tempfile
import time

import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../src"))

from ast_validator import MonlAST
from generator import MonlSecureGenerator
from parser import parse_monl_string

SPEC = """app RL

entity User
    name: String

actor User selfRegister

workflow W for User
    Read User
"""


def _find_free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait(port, timeout=20):
    start = time.time()
    while time.time() - start < timeout:
        try:
            requests.get(f"http://127.0.0.1:{port}/docs", timeout=1)
            return True
        except requests.exceptions.ConnectionError:
            time.sleep(0.3)
    return False


def test_rate_limit_is_shared_across_workers():
    with tempfile.TemporaryDirectory() as workdir:
        ast = MonlAST(parse_monl_string(SPEC)).validate_and_audit()
        MonlSecureGenerator(ast, output_dir=workdir).generate_all()

        port = _find_free_port()
        proc = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app:app", "--port", str(port), "--workers", "2"],
            cwd=workdir, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        try:
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
