"""Worker persistant des constructions de plateforme."""

import threading
from time import monotonic

from .builder import build_project


class _UnavailableProvider:
    provider_name = "indisponible"
    model = "indisponible"
    last_usage = None

    def __call__(self, _prompt):
        raise RuntimeError("aucun fournisseur IA n'est configuré pour la plateforme")


class _UnavailableImageProvider:
    provider_name = "image-indisponible"
    model = "image-indisponible"
    last_usage = None

    def __init__(self, error):
        self.error = str(error)

    def __call__(self, _prompt):
        raise RuntimeError(self.error)


class BuildWorker:
    """Traite les constructions SQLite avec une boucle contrôlable.

    ``run_once`` est la sonde et le mode de test : il réserve une construction
    et la traite sans lancer de thread. ``start`` utilise la même opération
    dans une boucle arrêtée par ``stop``. Les constructions déjà ``en_cours``
    sont marquées échouées avant toute nouvelle réservation, ce qui rend le
    redémarrage honnête après une interruption.
    """

    def __init__(
        self,
        store,
        workspace_root,
        quota,
        *,
        provider_factory=None,
        provider=None,
        model_provider_factory=None,
        image_provider_factory=None,
        image_provider=None,
        prices_path=None,
        on_success=None,
        poll_interval=0.25,
        wait=None,
    ):
        if provider_factory is not None and provider is not None:
            raise ValueError("fournir provider_factory ou provider, pas les deux")
        if provider_factory is None:
            if provider is None:
                provider = _UnavailableProvider()

            def provider_factory(_project, _build):
                return provider
        if image_provider_factory is not None and image_provider is not None:
            raise ValueError("fournir image_provider_factory ou image_provider, pas les deux")
        if image_provider_factory is None:

            def image_provider_factory(_project, _build):
                return image_provider
        if poll_interval < 0:
            raise ValueError("poll_interval doit être positif ou nul")
        self.store = store
        self.workspace_root = workspace_root
        self.quota = quota
        self.provider_factory = provider_factory
        self.model_provider_factory = model_provider_factory
        self.image_provider_factory = image_provider_factory
        self.prices_path = prices_path
        self.on_success = on_success
        self.poll_interval = poll_interval
        self._wait = wait or self._default_wait
        self._stop_event = threading.Event()
        self._thread = None

    def _default_wait(self, seconds):
        self._stop_event.wait(seconds)

    def recover_in_progress(self):
        return self.store.recover_in_progress_builds()

    def run_once(self):
        build = self.store.claim_next_build()
        if build is None:
            return None
        project = self.store.get_project(build["project_id"])
        if project is None:
            self.store.finish_build(
                build["id"],
                "echouee",
                error_message="projet de construction introuvable",
            )
            return self.store.get_build(build["id"])
        try:
            provider = self.provider_factory(project, build)
            image_provider = None
            if project.get("generate_images"):
                try:
                    image_provider = self.image_provider_factory(project, build)
                except Exception as exc:
                    # Une image est une amélioration optionnelle : conserver
                    # l'erreur pour que le builder puisse continuer en texte
                    # seul, sans transformer une panne d'images en panne du site.
                    image_provider = _UnavailableImageProvider(exc)
            result = build_project(
                project["project_id"],
                self._spec_for(project),
                provider,
                account_id=project["user_id"],
                store=self.store,
                workspace_root=self.workspace_root,
                quota=self.quota,
                prices_path=self.prices_path,
                build_id=build["id"],
                model_routes=project.get("model_routes"),
                provider_factory=self.model_provider_factory,
                generate_images=bool(project.get("generate_images")),
                image_provider=image_provider,
            )
        except Exception as exc:
            current = self.store.get_build(build["id"])
            if current is not None and current["state"] not in {"reussie", "echouee"}:
                self.store.finish_build(build["id"], "echouee", error_message=str(exc))
            result = self.store.get_build(build["id"])
        if result and result["state"] == "reussie" and self.on_success is not None:
            try:
                self.on_success(project, result)
            except Exception:
                # La construction reste réussie : le site peut être démarré
                # par la route /start et l'erreur de service sera explicite.
                pass
        return result

    def _spec_for(self, project):
        from .paths import project_directory

        directory = project_directory(
            self.workspace_root, project["user_id"], project["project_id"], create=False
        )
        spec_path = directory / "spec.ml"
        if not spec_path.is_file():
            raise RuntimeError("spec.ml absent du projet")
        return spec_path.read_text(encoding="utf-8")

    def _loop(self):
        while not self._stop_event.is_set():
            if self.run_once() is None:
                self._wait(self.poll_interval)

    def start(self):
        if self._thread is not None and self._thread.is_alive():
            return False
        self.recover_in_progress()
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._loop, name="monl-platform-build-worker", daemon=True
        )
        self._thread.start()
        return True

    def stop(self, timeout=None):
        self._stop_event.set()
        thread = self._thread
        if thread is None:
            return True
        deadline = None if timeout is None else monotonic() + timeout
        remaining = None if deadline is None else max(0, deadline - monotonic())
        thread.join(remaining)
        return not thread.is_alive()

    @property
    def alive(self):
        return self._thread is not None and self._thread.is_alive()
