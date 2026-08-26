"""Cycle de vie commun des applications uvicorn générées pendant les tests."""

import contextlib
import os
import socket
import subprocess
import sys
import tempfile
import time

import pytest
import requests


def free_port():
    """Réserve brièvement un port local libre et renvoie son numéro.

    **Ce port est RELÂCHÉ avant d'être utilisé**, et rien ne le retient entre
    les deux : l'OS peut le redonner à n'importe qui, y compris à une connexion
    sortante de la suite elle-même — `bind(0)` et les sockets clientes puisent
    dans la MÊME plage éphémère (`/proc/sys/net/ipv4/ip_local_port_range`, ici
    32768-60999). D'où un `uvicorn` qui meurt sur « address already in use »
    seulement sous charge, jamais quand on lance le fichier seul.

    `uvicorn_server` ne s'en sert plus : il lie sa socket et la passe à
    l'enfant, ce qui supprime la fenêtre au lieu de la retenter. Les tests qui
    montent leur serveur eux-mêmes l'appellent encore ; ils échouent
    franchement si le port leur échappe, ce qui est bruyant mais honnête.
    """
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _diagnostic(entete, journal, module, directory):
    """Ce qu'uvicorn a écrit avant de mourir.

    Cette sortie partait dans `DEVNULL` : c'est la raison pour laquelle
    personne n'a jamais su POURQUOI le serveur s'arrêtait. Un message qui ne
    dit pas la cause envoie chercher au mauvais endroit.
    """
    try:
        journal.seek(0)
        sortie = journal.read().strip()
    except (OSError, ValueError):  # pragma: no cover - journal déjà fermé
        sortie = ""
    return (f"{entete}\n"
            f"module={module!r} dossier={directory!r}\n"
            f"--- sortie d'uvicorn ---\n"
            f"{sortie or '(le serveur n a rien ecrit)'}")


@contextlib.contextmanager
def uvicorn_server(directory, *, env=None, module="app:app",
                   ready_path="/openapi.json", attempts=80):
    """Lance une application générée, attend qu'elle réponde, puis l'arrête.

    Les scénarios métier restent responsables de compiler leur spec et de
    préparer leur base. Cet utilitaire ne porte que la mécanique de processus
    répétée dans les tests d'intégration.

    Deux décisions à ne pas défaire.

    **La socket est liée ICI et passée à l'enfant** (`uvicorn --fd`), au lieu
    de lui transmettre un numéro de port qu'on vient de relâcher. Le port ne
    redevient jamais disponible entre le choix et l'écoute : la collision est
    rendue IMPOSSIBLE, elle n'est pas retentée. Retenter aurait aussi masqué
    une panne déterministe derrière deux essais de plus.

    **Un serveur qui ne démarre pas fait ÉCHOUER le test, jamais sauter.** La
    version précédente appelait `pytest.skip`, donc les vingt et un fichiers
    d'intégration qui passent par ici pouvaient ne rien vérifier en rendant du
    vert. C'est exactement le faux vert que CLAUDE.md interdit.
    """
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    sock.listen(128)
    port = sock.getsockname()[1]
    fd = sock.fileno()
    os.set_inheritable(fd, True)

    journal = tempfile.TemporaryFile(mode="w+", encoding="utf-8", errors="replace")
    try:
        try:
            process = subprocess.Popen(
                [sys.executable, "-m", "uvicorn", module, "--fd", str(fd)],
                cwd=directory,
                env=env or os.environ.copy(),
                pass_fds=(fd,),
                stdout=journal,
                stderr=subprocess.STDOUT,
            )
        finally:
            # L'enfant a sa propre copie du descripteur. Garder la nôtre
            # ouverte ferait accepter par le noyau des connexions que plus
            # personne ne sert si le serveur meurt : une panne deviendrait une
            # attente jusqu'au délai, au lieu d'un refus immédiat.
            sock.close()

        base_url = f"http://127.0.0.1:{port}"
        try:
            for _ in range(attempts):
                if process.poll() is not None:
                    pytest.fail(_diagnostic(
                        "le serveur uvicorn s'est arrêté avant de répondre "
                        f"(code {process.returncode})",
                        journal, module, directory))
                try:
                    response = requests.get(base_url + ready_path, timeout=1)
                    if response.status_code < 500:
                        break
                except requests.RequestException:
                    pass
                time.sleep(0.25)
            else:
                pytest.fail(_diagnostic(
                    f"le serveur uvicorn n'a jamais répondu sur {ready_path} "
                    f"après {attempts} essais",
                    journal, module, directory))
            yield base_url
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
    finally:
        journal.close()
