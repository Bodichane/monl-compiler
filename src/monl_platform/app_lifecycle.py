"""Application lifecycle and periodic project cleanup."""

from __future__ import annotations

import contextlib
import os
import threading

from .builder_runtime import create_runtime
from .deletion import delete_project
from .identity import IdentityStore
from .log import event, failure
from .service import CompilationService


def _purge(service: CompilationService, identities: IdentityStore, runtime=None) -> int:
    """Erases the expired projects, in the database AND on disk.

    Single source: startup and the periodic loop call the same function. Two
    copies would have ended up diverging, and the cleanup would have lost."""
    runtime = runtime or create_runtime(service, identities)
    efface = 0
    for expired_id in identities.expired_projects():
        with identities._connect() as db:
            project = db.execute("SELECT user_id FROM projects WHERE project_id = ?",
                                (expired_id,)).fetchone()
        if project:
            delete_project(runtime, project["user_id"], expired_id)
            efface += 1
    return efface


def create_lifespan(service: CompilationService, identities: IdentityStore, builder_runtime):
    @contextlib.asynccontextmanager
    async def _cycle_of_vie(_app):
        """The purge runs AS LONG AS the server runs.

        It only ran when the application was mounted: on a container that lives
        three months, `MONL_PROJECT_RETENTION_DAYS` was only honored on restart,
        that is, never. The thread lives in the life cycle and not in
        `create_app`, so that building the application in a test starts none."""
        stop = threading.Event()
        interval = max(1, int(os.environ.get("MONL_PURGE_INTERVAL_SECONDS", "3600")))

        def loop():
            while not stop.wait(interval):
                try:
                    efface = _purge(service, identities, builder_runtime)
                    if efface:
                        event("purge", projets=efface)
                except Exception as exc:
                    # A failed cleanup must never kill the server: it is NAMED
                    # and the loop goes on.
                    failure("purge_impossible", cause=type(exc).__name__)

        fil = threading.Thread(target=loop, name="monl-purge", daemon=True)
        fil.start()
        builder_runtime.start()
        try:
            yield
        finally:
            stop.set()
            fil.join(timeout=5)
            builder_runtime.stop()

    return _cycle_of_vie
