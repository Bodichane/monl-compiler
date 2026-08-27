"""Application lifecycle and periodic project cleanup."""

from __future__ import annotations

import contextlib
import os
import threading

from .identity import IdentityStore
from .journal import evenement, panne
from .service import CompilationService, PlatformNotFoundError


def _purger(service: CompilationService, identities: IdentityStore) -> int:
    """Efface les projets échus, en base ET sur le disque.

    Source unique : le démarrage et la boucle périodique appellent la même
    fonction. Deux copies auraient fini par diverger, et c'est le nettoyage
    qui aurait perdu.
    """
    efface = 0
    for expired_id in identities.expired_projects():
        try:
            service.delete(expired_id)
        except PlatformNotFoundError:
            pass
        efface += 1
    return efface


def create_lifespan(service: CompilationService, identities: IdentityStore, builder_runtime):
    @contextlib.asynccontextmanager
    async def _cycle_de_vie(_app):
        """La purge tourne TANT QUE le serveur tourne.

        Elle ne s'exécutait qu'au montage de l'application : sur un conteneur
        qui vit trois mois, `MONL_PROJECT_RETENTION_DAYS` n'était honoré
        qu'au redémarrage, donc jamais. Le fil vit dans le cycle de vie et non
        dans `create_app`, pour que construire l'application dans un test n'en
        démarre aucun.
        """
        arret = threading.Event()
        intervalle = max(1, int(os.environ.get("MONL_PURGE_INTERVAL_SECONDS", "3600")))

        def boucle():
            while not arret.wait(intervalle):
                try:
                    efface = _purger(service, identities)
                    if efface:
                        evenement("purge", projets=efface)
                except Exception as exc:
                    # Un ménage raté ne doit jamais tuer le serveur :
                    # on le NOMME et la boucle continue.
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
