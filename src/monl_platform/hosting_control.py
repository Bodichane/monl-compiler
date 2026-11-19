"""Local relay of the stops the CLI requests from the live manager."""

import hashlib
import os
import socket
import struct
import threading
from pathlib import Path


def _prefix(workspace):
    fingerprint = hashlib.sha256(str(Path(workspace).resolve()).encode()).hexdigest()
    return "@monl-sites-" + fingerprint + "-"


def _address(workspace):
    return "\0" + _prefix(workspace)[1:] + str(os.getpid())


def _addresses(workspace):
    prefix = _prefix(workspace)
    with Path("/proc/net/unix").open() as flux:
        return {"\0" + fields[7][1:] for line in flux
                if len(fields := line.split()) == 8 and fields[7].startswith(prefix)}


def stop_distant(workspace, project_id):
    confirmed = False
    for address in _addresses(workspace):
        if _stop_worker(address, project_id):
            confirmed = True
    return confirmed


def _stop_worker(address, project_id):
    with socket.socket(socket.AF_UNIX) as canal:
        canal.settimeout(15)
        try:
            canal.connect(address)
        except ConnectionRefusedError:
            return False
        canal.sendall(project_id.encode())
        canal.shutdown(socket.SHUT_WR)
        if canal.recv(1) != b"1":
            raise RuntimeError("The manager did not confirm that the site stopped.")
    return True


class ControlSites:
    def __init__(self, sites):
        self.sites = sites
        sites.control_local = True
        self.stop_event = threading.Event()
        self.canal = socket.socket(socket.AF_UNIX)
        self.canal.bind(_address(sites.workspace_root))
        self.canal.settimeout(0.2)
        self.fil = threading.Thread(target=self._loop, daemon=True)

    def start(self):
        self.canal.listen()
        self.fil.start()

    def _loop(self):
        while not self.stop_event.is_set():
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
                        project = flux.read(256).decode()
                    self.sites.stop_project(project)
                    canal.sendall(b"1")
                except (OSError, UnicodeError):
                    continue

    def stop(self):
        self.stop_event.set()
        self.fil.join(timeout=5)
        self.canal.close()
