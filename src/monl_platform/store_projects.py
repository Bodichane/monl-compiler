"""Builder-project metadata operations."""

from __future__ import annotations

import json

from .store_core import _now, normalize_slug


class StoreProjectsMixin:
    def create_project(
        self, user_id, project_id, slug, *, model_routes=None, generate_images=False
    ):
        """Adds the builder metadata of a project that already has an identity.

        The project itself must first be created by
        ``IdentityStore.add_project(user_id, project_id, name)``. The foreign
        keys make this order verifiable and let identity own the cascading
        deletion."""
        if not isinstance(user_id, str) or not user_id or "\x00" in user_id:
            raise ValueError("invalid user identifier")
        if not isinstance(project_id, str) or not project_id or "\x00" in project_id:
            raise ValueError("invalid project identifier")
        slug = normalize_slug(slug)
        if not slug or slug in {".", ".."} or "/" in slug or "\\" in slug:
            raise ValueError("invalid project slug: path traversal refused")
        if not isinstance(generate_images, bool):
            raise ValueError("generate_images must be a boolean")
        routes = self._normalize_model_routes(model_routes)
        # The slug is chosen FREE, under the lock, and the write follows
        # immediately: a check made outside the lock would let two simultaneous
        # calls both read "free". The global index of `store_core` refuses the
        # collision even if this path is bypassed.
        with self._lock, self._connect() as db:
            slug = self._slug_free(db, slug)
            db.execute(
                "INSERT INTO builder_projects(project_id, user_id, slug, created_at, "
                "model_routes, generate_images) VALUES (?, ?, ?, ?, ?, ?)",
                (project_id, user_id, slug, _now(), json.dumps(routes, sort_keys=True),
                 int(generate_images)),
            )
            return slug

    #: Beyond that, refuse rather than loop: a name that already has a hundred
    #: namesakes is the sign of something other than normal use.
    NAMESAKES_MAX = 100

    @staticmethod
    def _slug_free(db, base):
        """The first free address: `name`, then `name-2`, `name-3`…

        The FIRST project keeps the address its name announces — it is the one
        that was already online, and taking it away would break a working site.
        It is the following ones that carry the suffix.

        The address is a subdomain, so uniqueness is GLOBAL and not per account:
        otherwise, a stranger who names their project like yours made both
        unreachable (`project_for_host` refuses to serve when two projects answer
        the same host, and it is right to refuse)."""
        # `.lower()` is not redundant with the `COLLATE NOCASE`: the latter
        # governs the SELECTION, the folding below governs the COMPARISON in
        # Python. Without it, an EARLIER row written "myOwn" — from the time
        # when the slug kept its case — was indeed returned by the query, then
        # judged different from "myown": two projects for a single host, hence
        # `project_for_host` refusing to serve both. It is defect (b) surviving
        # on databases already in service, found by a witness and not by
        # rereading. Folding only one side of a comparison folds nothing.
        prise = {line["slug"].lower() for line in db.execute(
            "SELECT slug FROM builder_projects WHERE slug = ? COLLATE NOCASE "
            "OR slug LIKE ? COLLATE NOCASE", (base, f"{base}-%"))}
        if base not in prise:
            return base
        for rang in range(2, StoreProjectsMixin.NAMESAKES_MAX + 1):
            candidate = f"{base}-{rang}"
            if candidate not in prise:
                return candidate
        raise ValueError(
            f"too many projects use the address '{base}' "
            f"({StoreProjectsMixin.NAMESAKES_MAX} at most)")

    def discard_project(self, user_id, project_id):
        """Deletes a just-created project if its initialization fails.

        This primitive is not a user API: it serves as compensation for writing
        ``spec.ml`` in the same HTTP request. A project that already has a build
        cannot be discarded."""
        if not isinstance(user_id, str) or not isinstance(project_id, str):
            raise ValueError("invalid project identifier")
        with self._lock, self._connect() as db:
            row = self._row(
                db,
                "SELECT project_id FROM builder_projects WHERE project_id = ? AND user_id = ?",
                (project_id, user_id),
            )
            if row is None:
                return False
            # POINT 162: nothing writes to 'builds' anymore. The table and this
            # safeguard survive for EARLIER databases, which carry real rows:
            # an additive migration catches up a column, never content (points
            # 32 and 89). On a new database, the table stays empty and this
            # read never refuses anything.
            build = self._row(
                db,
                "SELECT id FROM builds WHERE project_id = ? LIMIT 1", (project_id,)
            )
            if build is not None:
                raise ValueError("project already built: compensating deletion refused")
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
        # COLLATE NOCASE, and not only a comparison on the canonical form:
        # projects created before normalization still carry their capital
        # letter in the database, and they are sites already built and already
        # paid for. A strict comparison would leave them unreachable.
        with self._lock, self._connect() as db:
            return self._project_rows(
                db,
                "SELECT * FROM builder_projects WHERE slug = ? COLLATE NOCASE "
                "ORDER BY project_id",
                (normalize_slug(slug),),
            )



