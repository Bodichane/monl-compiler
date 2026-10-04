"""Issue #99 : la vraie CLI interrompt le dialogue sans trace ni écriture."""

import os
import selectors
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest


def _commande(tmp_path, dossier):
    env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1] / "src"))
    return [sys.executable, "-m", "monl.cli", "init", "--dir", dossier], env


@pytest.mark.parametrize("existant", [False, True])
@pytest.mark.parametrize("entree,dossier,message", [
    ("3\n1\n", "p1", "Entrée interrompue"),
    ("3\n2\nMaBoutique\n" + "n\n" * 80, "p2", "Réponse invalide après 3 tentatives"),
])
def test_init_interrompu_en_sous_processus(tmp_path, existant, entree, dossier, message):
    if existant:
        (tmp_path / dossier).mkdir()
    commande, env = _commande(tmp_path, dossier)
    resultat = subprocess.run(commande, input=entree, text=True, capture_output=True,
                              cwd=tmp_path, env=env, timeout=20)
    assert resultat.returncode == 2
    assert resultat.stderr == f"{message} : rien n'a été écrit, relancez `monl init`.\n"
    assert "Traceback" not in resultat.stdout + resultat.stderr
    assert sorted(p.name for p in tmp_path.iterdir()) == ([dossier] if existant else [])
    assert not (tmp_path / dossier).exists() or not list((tmp_path / dossier).iterdir())


def test_init_ctrl_c_en_sous_processus(tmp_path):
    commande, env = _commande(tmp_path, "p3")
    with subprocess.Popen(commande, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, cwd=tmp_path, env=env) as processus:
        try:
            # Attendre le vrai input(), sans dépendre de la vitesse de démarrage.
            sortie = b""
            echeance = time.monotonic() + 20
            with selectors.DefaultSelector() as selecteur:
                selecteur.register(processus.stdout, selectors.EVENT_READ)
                while not sortie.endswith(b"\n> "):
                    restant = echeance - time.monotonic()
                    assert restant > 0 and selecteur.select(restant), sortie
                    bloc = os.read(processus.stdout.fileno(), 4096)
                    assert bloc, sortie
                    sortie += bloc
            processus.send_signal(signal.SIGINT)
            stdout, stderr = processus.communicate(timeout=20)
        finally:
            if processus.poll() is None:
                processus.kill()
                processus.communicate()
    assert processus.returncode == 130
    assert stderr.decode() == "Entrée interrompue : rien n'a été écrit, relancez `monl init`.\n"
    assert b"Traceback" not in sortie + stdout + stderr
    assert not list(tmp_path.iterdir())
