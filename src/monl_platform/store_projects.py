"""Builder-project metadata operations."""

from __future__ import annotations

import json

from .store_core import _now, normalize_slug


class StoreProjectsMixin:
    def create_project(
        self, user_id, project_id, slug, *, model_routes=None, generate_images=False
    ):
        """Ajoute les métadonnées constructeur d'un projet déjà identitaire.

        Le projet lui-même doit d'abord être créé par
        ``IdentityStore.add_project(user_id, project_id, name)``. Les clés
        étrangères rendent cet ordre vérifiable et laissent l'identité
        posséder la suppression en cascade.
        """
        if not isinstance(user_id, str) or not user_id or "\x00" in user_id:
            raise ValueError("identifiant d'utilisateur invalide")
        if not isinstance(project_id, str) or not project_id or "\x00" in project_id:
            raise ValueError("identifiant de projet invalide")
        slug = normalize_slug(slug)
        if not slug or slug in {".", ".."} or "/" in slug or "\\" in slug:
            raise ValueError("slug de projet invalide : remontée de chemin refusée")
        if not isinstance(generate_images, bool):
            raise ValueError("generate_images doit être un booléen")
        routes = self._normalize_model_routes(model_routes)
        with self._lock, self._connect() as db:
            db.execute(
                "INSERT INTO builder_projects(project_id, user_id, slug, created_at, "
                "model_routes, generate_images) VALUES (?, ?, ?, ?, ?, ?)",
                (project_id, user_id, slug, _now(), json.dumps(routes, sort_keys=True),
                 int(generate_images)),
            )
            return project_id

    def discard_project(self, user_id, project_id):
        """Supprime un projet tout juste créé si son initialisation échoue.

        Cette primitive n'est pas une API utilisateur : elle sert de
        compensation à l'écriture de ``spec.ml`` dans la même requête HTTP.
        Un projet possédant déjà une construction ne peut pas être écarté.
        """
        if not isinstance(user_id, str) or not isinstance(project_id, str):
            raise ValueError("identifiant de projet invalide")
        with self._lock, self._connect() as db:
            row = self._row(
                db,
                "SELECT project_id FROM builder_projects WHERE project_id = ? AND user_id = ?",
                (project_id, user_id),
            )
            if row is None:
                return False
            build = self._row(
                db,
                "SELECT id FROM builds WHERE project_id = ? LIMIT 1", (project_id,)
            )
            if build is not None:
                raise ValueError("projet déjà construit : suppression de compensation refusée")
            deleted = db.execute(
                "DELETE FROM builder_projects WHERE project_id = ? AND user_id = ?",
                (project_id, user_id),
            )
            return deleted.rowcount == 1

    def get_project(self, project_id):
        with self._lock, self._connect() as db:
            return self._project_row(
                db, "SELECT * FROM builder_projects WHERE project_id = ?", (project_id,)
            )

    def get_project_for_user(self, user_id, project_id):
        with self._lock, self._connect() as db:
            return self._project_row(
                db,
                "SELECT * FROM builder_projects WHERE project_id = ? AND user_id = ?",
                (project_id, user_id),
            )

    def list_projects(self, user_id):
        with self._lock, self._connect() as db:
            return self._project_rows(
                db,
                "SELECT * FROM builder_projects WHERE user_id = ? ORDER BY project_id",
                (user_id,),
            )

    def list_all_projects(self):
        with self._lock, self._connect() as db:
            return self._project_rows(
                db, "SELECT * FROM builder_projects ORDER BY project_id"
            )

    def list_projects_by_slug(self, slug):
        # COLLATE NOCASE, et pas seulement une comparaison sur la forme
        # canonique : les projets créés avant la normalisation portent encore
        # leur majuscule en base, et ce sont des sites déjà construits et déjà
        # payés. Une comparaison stricte les laisserait injoignables.
        with self._lock, self._connect() as db:
            return self._project_rows(
                db,
                "SELECT * FROM builder_projects WHERE slug = ? COLLATE NOCASE "
                "ORDER BY project_id",
                (normalize_slug(slug),),
            )



