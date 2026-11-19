"""Launching and relaying the applications produced by monl."""

import http.client
import socket
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from .hosting_admission import eviction_candidate, hosting_limits
from .hosting_control import stop_distant
from .paths import ProjectPathError, project_directory


class SiteHostingError(RuntimeError):
    """The site cannot be launched or relayed."""


class SiteNotCompiledError(SiteHostingError):
    """The project does not have a compiled backend yet.

    POINT 162. Before the refocus, "hosting" meant serving the SNAPSHOT of a
    successful AI build: without a build in the database, nothing ever
    started. With the builder removed, what we start is the backend COMPILED
    by the dialogue — deterministic, present as soon as 'monl compile' runs.
    The frontend stays OPTIONAL: it is the serve.py wrapper that says so ("the
    API answers, /site will return 404"), and seeing the API run is precisely
    the use this module keeps."""


SITE_LOG_FILENAME = "site.log"
SITE_LOG_MAX_BYTES = 1_048_576
# The file is allowed to grow up to twice the bound before compacting:
# compacting at every chunk would reread the whole log eight thousand times per
# megabyte. The disk stays bounded, by 2 MiB rather than 1.
SITE_LOG_COMPACT_BYTES = SITE_LOG_MAX_BYTES * 2


def site_log_path(workspace_root, project):
    """Returns a project's log after the same path check."""
    try:
        return project_directory(
            workspace_root,
            project["user_id"],
            project["project_id"],
            create=False,
        ) / SITE_LOG_FILENAME
    except ProjectPathError as exc:
        raise SiteHostingError(str(exc)) from exc


@dataclass
class _RunningSite:
    project_id: str
    user_id: str
    host: str
    port: int
    process: subprocess.Popen
    log_path: Path
    output_thread: threading.Thread
    last_activity: float


class SiteManager:
    """Maps a project host to a local ``serve.py`` process."""

    def __init__(
        self, store, workspace_root, domain="localhost", *, startup_timeout=5,
        clock=time.monotonic,
    ):
        domain = str(domain).strip().lower().strip(".")
        if not domain or "/" in domain or "\\" in domain:
            raise ValueError("invalid platform domain")
        self.store = store
        self.workspace_root = workspace_root
        self.domain = domain
        self.startup_timeout = startup_timeout
        self._clock = clock
        self._global_limit, self._account_limit = hosting_limits()
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

    def site_log_path(self, project):
        """The project's private output file, readable by the CLI only."""
        return site_log_path(self.workspace_root, project)

    def _require_site(self, project):
        directory = self._project_directory(project)
        for file in ("app.py", "serve.py"):
            if not (directory / file).is_file():
                raise SiteNotCompiledError(
                    f"the backend of project {project['project_id']} is not "
                    f"compiled: {file} missing"
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

    @staticmethod
    def _capture_output(stream, log_path):
        """Copies the child's output keeping the END, never the beginning.

        The first version stopped writing once the bound was reached. The bound
        was therefore held — and the log kept the least useful megabyte: measured,
        a site that chatters then crashes entirely lost the trace of its crash,
        because it comes LAST. A test that only checks the file's size passes in
        both cases; that is why one must measure what is KEPT, not what is thrown
        away."""
        try:
            with log_path.open("a+b") as log:
                read = getattr(stream, "read1", stream.read)
                log.seek(0, 2)
                size = log.tell()
                if size > SITE_LOG_COMPACT_BYTES:
                    size = SiteManager._compact_log(log)
                while True:
                    block = read(8192)
                    if not block:
                        break
                    # Compact BEFORE writing, never after. Compacting after
                    # lets the file EXCEED the bound for the whole duration of
                    # the compaction — which rereads the whole log, truncates
                    # and rewrites. Measured: 2,101,261 bytes on disk for an
                    # announced bound of 2,097,152, and it is exactly the
                    # instant CI captured. A disk bound is a promise about what
                    # is OCCUPIED: it must hold at every instant, not only when
                    # the thread has finished its work.
                    if size + len(block) > SITE_LOG_COMPACT_BYTES:
                        size = SiteManager._compact_log(log)
                    log.write(block)
                    log.flush()
                    size += len(block)
        finally:
            stream.close()

    @staticmethod
    def _compact_log(log):
        """Keep only the end, cut on a whole line."""
        log.seek(0)
        guard = log.read()[-SITE_LOG_MAX_BYTES:]
        # The cut falls in the middle of a line: dropping it avoids an
        # unreadable fragment at the top of the log, which would be taken for a
        # message truncated by the site itself.
        coupe = guard.find(b"\n")
        if 0 <= coupe < len(guard) - 1:
            guard = guard[coupe + 1:]
        log.truncate(0)
        log.seek(0)
        log.write(guard)
        log.flush()
        return len(guard)

    @staticmethod
    def _join_output(output_thread):
        output_thread.join(timeout=5)

    def _stop_running(self, running):
        self._stop_process(running.process)
        self._join_output(running.output_thread)

    def start_project(self, project):
        with self._lock:
            current = self._running.get(project["project_id"])
            if current is not None and current.process.poll() is None:
                current.last_activity = self._clock()
                return current
            if current is not None:
                self._running.pop(project["project_id"], None)
                self._stop_running(current)
            stopped = [
                item for item in self._running.values()
                if item.process.poll() is not None
            ]
            for item in stopped:
                self._running.pop(item.project_id, None)
                self._join_output(item.output_thread)
            now = self._clock()
            candidate, limit_reached = eviction_candidate(
                self._running,
                project["user_id"],
                now,
                self._global_limit,
                self._account_limit,
            )
            if candidate is not None:
                self._running.pop(candidate.project_id, None)
                self._stop_running(candidate)
            elif limit_reached:
                raise SiteHostingError(
                    "the active-site limit is reached; try again later"
                )
            directory = self._require_site(project)
            port = self._allocate_port()
            log_path = directory / SITE_LOG_FILENAME
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
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )
            host = self.host_for(project)
            output_thread = threading.Thread(
                target=self._capture_output,
                args=(process.stdout, log_path),
                name=f"monl-site-log-{project['project_id'][:8]}",
                daemon=True,
            )
            output_thread.start()
            running = _RunningSite(
                project["project_id"], project["user_id"], host, port, process,
                log_path, output_thread, now,
            )
            if not self._wait_ready(process, port):
                self._stop_running(running)
                raise SiteHostingError(f"the server for site {host} did not start")
            running.last_activity = self._clock()
            self._running[project["project_id"]] = running
            return running

    def stop_project(self, project_id):
        with self._lock:
            running = self._running.pop(project_id, None)
            if running is None:
                if getattr(self, "control_local", False):
                    return False
                return stop_distant(self.workspace_root, project_id)
            self._stop_running(running)
            return True

    def is_running(self, project_id):
        """Says whether a project's relay is still alive."""
        with self._lock:
            running = self._running.get(project_id)
            if running is None:
                return False
            if running.process.poll() is not None:
                self._running.pop(project_id, None)
                self._join_output(running.output_thread)
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
            self._stop_running(item)

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
            raise SiteHostingError(f"host {name} designates several projects")
        return projects[0]

    def target_for_host(self, host):
        project = self.project_for_host(host)
        if project is None:
            return None
        return self.start_project(project)

    def forward(self, running, method, path, headers, body):
        with self._lock:
            if self._running.get(running.project_id) is running:
                running.last_activity = self._clock()
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
            raise SiteHostingError(f"site {running.host} is unavailable") from exc
        finally:
            connection.close()
        from fastapi.responses import Response

        result = Response(content=payload, status_code=status)
        result.raw_headers = response_headers
        return result
