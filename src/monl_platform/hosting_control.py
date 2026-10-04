"""Relais local des arrêts demandés par la CLI au gestionnaire vivant."""

import hashlib
import os
import socket
import struct
import threading
from pathlib import Path


def _prefixe(workspace):
    empreinte = hashlib.sha256(str(Path(workspace).resolve()).encode()).hexdigest()
    return "@monl-sites-" + empreinte + "-"


def _adresse(workspace):
    return "\0" + _prefixe(workspace)[1:] + str(os.getpid())


def _adresses(workspace):
    prefixe = _prefixe(workspace)
    with Path("/proc/net/unix").open() as flux:
        return {"\0" + champs[7][1:] for ligne in flux
                if len(champs := ligne.split()) == 8 and champs[7].startswith(prefixe)}


def arreter_distant(workspace, project_id):
    confirme = False
    for adresse in _adresses(workspace):
        if _arreter_worker(adresse, project_id):
            confirme = True
    return confirme


def _arreter_worker(adresse, project_id):
    with socket.socket(socket.AF_UNIX) as canal:
        canal.settimeout(15)
        try:
            canal.connect(adresse)
        except ConnectionRefusedError:
            return False
        canal.sendall(project_id.encode())
        canal.shutdown(socket.SHUT_WR)
        if canal.recv(1) != b"1":
            raise RuntimeError("Le gestionnaire n'a pas confirmé l'arrêt du site.")
    return True


class ControleSites:
    def __init__(self, sites):
        self.sites = sites
        sites.controle_local = True
        self.arret = threading.Event()
        self.canal = socket.socket(socket.AF_UNIX)
        self.canal.bind(_adresse(sites.workspace_root))
        self.canal.settimeout(0.2)
        self.fil = threading.Thread(target=self._boucle, daemon=True)

    def start(self):
        self.canal.listen()
        self.fil.start()

    def _boucle(self):
        while not self.arret.is_set():
            try:
                canal, _ = self.canal.accept()
            except TimeoutError:
                continue
            with canal:
                canal.settimeout(2)
                _, uid, _ = struct.unpack("3i", canal.getsockopt(
                    socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
                if uid != os.getuid():
                    continue
                try:
                    with canal.makefile("rb") as flux:
                        projet = flux.read(256).decode()
                    self.sites.stop_project(projet)
                    canal.sendall(b"1")
                except (OSError, UnicodeError):
                    continue

    def stop(self):
        self.arret.set()
        self.fil.join(timeout=5)
        self.canal.close()
