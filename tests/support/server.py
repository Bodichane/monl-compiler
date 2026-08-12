"""Cycle de vie commun des applications uvicorn générées pendant les tests."""

import contextlib
import os
import socket
import subprocess
import sys
import time

import pytest
import requests


def free_port():
    """Réserve brièvement un port local libre et renvoie son numéro."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@contextlib.contextmanager
def uvicorn_server(directory, *, env=None, module="app:app",
                   ready_path="/openapi.json", attempts=80):
    """Lance une application générée, attend qu'elle réponde, puis l'arrête.

    Les scénarios métier restent responsables de compiler leur spec et de
    préparer leur base. Cet utilitaire ne porte que la mécanique de processus
    répétée dans les tests d'intégration.
    """
    port = free_port()
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", module, "--port", str(port)],
        cwd=directory,
        env=env or os.environ.copy(),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    base_url = f"http://127.0.0.1:{port}"
    try:
        for _ in range(attempts):
            if process.poll() is not None:
                pytest.skip(
                    f"serveur uvicorn arrêté avant de répondre (code {process.returncode})")
            try:
                response = requests.get(base_url + ready_path, timeout=1)
                if response.status_code < 500:
                    break
            except requests.RequestException:
                time.sleep(0.25)
        else:
            pytest.skip("serveur non démarré")
        yield base_url
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
