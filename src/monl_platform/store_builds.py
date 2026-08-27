"""Build queue and build-result operations."""

from __future__ import annotations

from .store_core import _now


class StoreBuildsMixin:
    def create_build(self, project_id):
        if isinstance(project_id, bool):
            raise ValueError("identifiant de projet invalide")
        with self._lock, self._connect() as db:
            if self._row(
                db, "SELECT project_id FROM builder_projects WHERE project_id = ?",
                (project_id,),
            ) is None:
                raise KeyError(f"projet introuvable : {project_id}")
            cursor = db.execute(
                "INSERT INTO builds(project_id, state, created_at) VALUES (?, ?, ?)",
                (project_id, "en_attente", _now()),
            )
            return cursor.lastrowid

    def start_build(self, build_id):
        with self._lock, self._connect() as db:
            db.execute(
                "UPDATE builds SET state = ?, started_at = ? WHERE id = ?",
                ("en_cours", _now(), build_id),
            )

    def claim_next_build(self):
        """Réserve atomiquement la prochaine construction en attente."""
        with self._lock, self._connect() as db:
            build = self._row(
                db,
                "SELECT * FROM builds WHERE state = 'en_attente' ORDER BY id LIMIT 1"
            )
            if build is None:
                return None
            updated = db.execute(
                "UPDATE builds SET state = ?, started_at = ? "
                "WHERE id = ? AND state = 'en_attente'",
                ("en_cours", _now(), build["id"]),
            )
            if updated.rowcount != 1:
                return None
            build["state"] = "en_cours"
            build["started_at"] = self._row(
                db,
                "SELECT started_at FROM builds WHERE id = ?", (build["id"],)
            )["started_at"]
            return build

    def recover_in_progress_builds(self, message="construction interrompue au redémarrage"):
        """Ne laisse jamais une construction abandonnée mentir en ``en_cours``."""
        with self._lock, self._connect() as db:
            cursor = db.execute(
                "UPDATE builds SET state = ?, finished_at = ?, error_message = ?, "
                "warning_message = NULL "
                "WHERE state = 'en_cours'",
                ("echouee", _now(), message),
            )
            return cursor.rowcount

    def finish_build(
        self,
        build_id,
        state,
        *,
        run_id=None,
        tokens_consumed=None,
        input_tokens=None,
        output_tokens=None,
        cost=None,
        currency=None,
        price_status=None,
        error_message=None,
        warning_message=None,
        snapshot_path=None,
        snapshot_sha256=None,
        snapshot_bytes=None,
    ):
        if state not in {"reussie", "echouee"}:
            raise ValueError(f"état terminal invalide : {state}")
        with self._lock, self._connect() as db:
            db.execute(
                """UPDATE builds SET state = ?, run_id = ?, tokens_consumed = ?,
                   input_tokens = ?, output_tokens = ?, cost = ?, currency = ?,
                   price_status = ?, finished_at = ?, error_message = ?,
                   warning_message = ?, snapshot_path = ?, snapshot_sha256 = ?,
                   snapshot_bytes = ? WHERE id = ?""",
                (
                    state,
                    run_id,
                    tokens_consumed,
                    input_tokens,
                    output_tokens,
                    cost,
                    currency,
                    price_status,
                    _now(),
                    error_message,
                    warning_message,
                    snapshot_path,
                    snapshot_sha256,
                    snapshot_bytes,
                    build_id,
                ),
            )

    def get_build(self, build_id):
        with self._lock, self._connect() as db:
            build = self._row(db, "SELECT * FROM builds WHERE id = ?", (build_id,))
            if build is not None:
                build["total_tokens"] = build["tokens_consumed"]
            return build

    def get_build_for_project(self, project_id, build_id):
        with self._lock, self._connect() as db:
            build = self._row(
                db,
                "SELECT * FROM builds WHERE id = ? AND project_id = ?",
                (build_id, project_id),
            )
            if build is not None:
                build["total_tokens"] = build["tokens_consumed"]
            return build

    def list_builds(self, project_id):
        with self._lock, self._connect() as db:
            builds = self._rows(
                db,
                "SELECT * FROM builds WHERE project_id = ? ORDER BY id", (project_id,)
            )
            for build in builds:
                build["total_tokens"] = build["tokens_consumed"]
            return builds

