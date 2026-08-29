"""Lancement et relais des applications produites par monl."""

import http.client
import socket
import subprocess
import sys
import threading
import time
from dataclasses import dataclass

from .paths import ProjectPathError, project_directory


class SiteHostingError(RuntimeError):
    """Le site ne peut pas être lancé ou relayé."""


class SiteNotCompiledError(SiteHostingError):
    """Le projet ne possède pas encore de backend compilé.

    POINT 162. Avant le recentrage, « héberger » voulait dire servir le
    SNAPSHOT d'une construction IA réussie : sans build en base, rien ne
    démarrait jamais. Le constructeur retiré, ce qu'on met en marche est le
    backend COMPILÉ par le dialogue — déterministe, présent dès 'monl compile'.
    Le frontend reste FACULTATIF : c'est le wrapper serve.py qui le dit
    (« l'API répond, /site renverra 404 »), et voir l'API tourner est
    précisément l'usage que ce module garde.
    """


@dataclass
class _RunningSite:
    project_id: str
    host: str
    port: int
    process: subprocess.Popen


class SiteManager:
    """Associe un hôte de projet à un processus ``serve.py`` local."""

    def __init__(self, store, workspace_root, domain="localhost", *, startup_timeout=5):
        domain = str(domain).strip().lower().strip(".")
        if not domain or "/" in domain or "\\" in domain:
            raise ValueError("domaine de plateforme invalide")
        self.store = store
        self.workspace_root = workspace_root
        self.domain = domain
        self.startup_timeout = startup_timeout
        self._running = {}
        self._lock = threading.RLock()

    def host_for(self, project):
        return f"{project['slug']}.{self.domain}"

    def _project_directory(self, project):
        try:
            return project_directory(
                self.workspace_root,
                project["user_id"],
                project["project_id"],
                create=False,
            )
        except ProjectPathError as exc:
            raise SiteHostingError(str(exc)) from exc

    def _require_site(self, project):
        directory = self._project_directory(project)
        for fichier in ("app.py", "serve.py"):
            if not (directory / fichier).is_file():
                raise SiteNotCompiledError(
                    f"le backend du projet {project['project_id']} n'est pas "
                    f"compilé : {fichier} absent"
                )
        return directory

    def _allocate_port(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            return sock.getsockname()[1]

    def _wait_ready(self, process, port):
        deadline = time.monotonic() + self.startup_timeout
        while time.monotonic() < deadline:
            if process.poll() is not None:
                return False
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                    return True
            except OSError:
                time.sleep(0.02)
        return False

    def start_project(self, project):
        with self._lock:
            current = self._running.get(project["project_id"])
            if current is not None and current.process.poll() is None:
                return current
            if current is not None:
                self._running.pop(project["project_id"], None)
            directory = self._require_site(project)
            port = self._allocate_port()
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "serve:app",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(port),
                    "--log-level",
                    "warning",
                ],
                cwd=directory,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            host = self.host_for(project)
            running = _RunningSite(project["project_id"], host, port, process)
            if not self._wait_ready(process, port):
                self._stop_process(process)
                raise SiteHostingError(f"le serveur du site {host} n'a pas démarré")
            self._running[project["project_id"]] = running
            return running

    def stop_project(self, project_id):
        with self._lock:
            running = self._running.pop(project_id, None)
            if running is None:
                return False
            self._stop_process(running.process)
            return True

    def is_running(self, project_id):
        """Indique si le relais d'un projet est encore vivant."""
        with self._lock:
            running = self._running.get(project_id)
            if running is None:
                return False
            if running.process.poll() is not None:
                self._running.pop(project_id, None)
                return False
            return True

    def _stop_process(self, process):
        if process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)

    def stop_all(self):
        with self._lock:
            running = list(self._running.values())
            self._running.clear()
        for item in running:
            self._stop_process(item.process)

    def _host_without_port(self, host):
        host = (host or "").strip().lower()
        if host.startswith("[") and "]" in host:
            return host[1:].split("]", 1)[0]
        if host.count(":") == 1:
            name, port = host.rsplit(":", 1)
            if port.isdigit():
                return name
        return host

    def project_for_host(self, host):
        name = self._host_without_port(host)
        suffix = "." + self.domain
        if not name.endswith(suffix):
            return None
        slug = name[: -len(suffix)]
        if not slug:
            return None
        projects = self.store.list_projects_by_slug(slug)
        if not projects:
            return None
        if len(projects) > 1:
            raise SiteHostingError(f"l'hôte {name} désigne plusieurs projets")
        return projects[0]

    def target_for_host(self, host):
        project = self.project_for_host(host)
        if project is None:
            return None
        return self.start_project(project)

    def forward(self, running, method, path, headers, body):
        forwarded = {
            key: value
            for key, value in headers.items()
            if key.lower()
            not in {"host", "connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te", "trailers", "transfer-encoding", "upgrade"}
        }
        forwarded["Host"] = running.host
        connection = http.client.HTTPConnection(
            "127.0.0.1", running.port, timeout=self.startup_timeout
        )
        try:
            connection.request(method, path, body=body, headers=forwarded)
            response = connection.getresponse()
            payload = response.read()
            response_headers = [
                (name.lower().encode("latin-1"), value.encode("latin-1"))
                for name, value in response.getheaders()
                if name.lower()
                not in {"connection", "keep-alive", "proxy-authenticate", "proxy-authentication", "te", "trailers", "transfer-encoding", "upgrade"}
            ]
            status = response.status
        except (OSError, http.client.HTTPException) as exc:
            raise SiteHostingError(f"le site {running.host} est indisponible") from exc
        finally:
            connection.close()
        from fastapi.responses import Response

        result = Response(content=payload, status_code=status)
        result.raw_headers = response_headers
        return result
