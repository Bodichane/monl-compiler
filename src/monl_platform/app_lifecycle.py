"""Application lifecycle and periodic project cleanup."""

from __future__ import annotations

import contextlib
import os
import threading

from .builder_runtime import create_runtime
from .deletion import supprimer_projet
from .identity import IdentityStore
from .journal import evenement, panne
from .service import CompilationService


def _purger(service: CompilationService, identities: IdentityStore, runtime=None) -> int:
    """Erases the expired projects, in the database AND on disk.

    Single source: startup and the periodic loop call the same function. Two
    copies would have ended up diverging, and the cleanup would have lost."""
    runtime = runtime or create_runtime(service, identities)
    efface = 0
    for expired_id in identities.expired_projects():
        with identities._connect() as db:
            projet = db.execute("SELECT user_id FROM projects WHERE project_id = ?",
                                (expired_id,)).fetchone()
        if projet:
            supprimer_projet(runtime, projet["user_id"], expired_id)
            efface += 1
    return efface


def create_lifespan(service: CompilationService, identities: IdentityStore, builder_runtime):
    @contextlib.asynccontextmanager
    async def _cycle_de_vie(_app):
        """The purge runs AS LONG AS the server runs.

        It only ran when the application was mounted: on a container that lives
        three months, `MONL_PROJECT_RETENTION_DAYS` was only honored on restart,
        that is, never. The thread lives in the life cycle and not in
        `create_app`, so that building the application in a test starts none."""
        arret = threading.Event()
        intervalle = max(1, int(os.environ.get("MONL_PURGE_INTERVAL_SECONDS", "3600")))

        def boucle():
            while not arret.wait(intervalle):
                try:
                    efface = _purger(service, identities, builder_runtime)
                    if efface:
                        evenement("purge", projets=efface)
                except Exception as exc:
                    # A failed cleanup must never kill the server: it is NAMED
                    # and the loop goes on.
                    panne("purge_impossible", cause=type(exc).__name__)

        fil = threading.Thread(target=boucle, name="monl-purge", daemon=True)
        fil.start()
        builder_runtime.start()
        try:
            yield
        finally:
            arret.set()
            fil.join(timeout=5)
            builder_runtime.stop()

    return _cycle_de_vie
