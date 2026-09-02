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
        # Le slug est choisi LIBRE, sous le verrou, et l'écriture suit
        # immédiatement : une vérification faite hors du verrou laisserait deux
        # appels simultanés lire « libre » tous les deux. L'index global de
        # `store_core` refuse la collision même si ce chemin est contourné.
        with self._lock, self._connect() as db:
            slug = self._slug_libre(db, slug)
            db.execute(
                "INSERT INTO builder_projects(project_id, user_id, slug, created_at, "
                "model_routes, generate_images) VALUES (?, ?, ?, ?, ?, ?)",
                (project_id, user_id, slug, _now(), json.dumps(routes, sort_keys=True),
                 int(generate_images)),
            )
            return slug

    #: Au-delà, on refuse plutôt que de boucler : un nom qui a déjà cent
    #: homonymes est le signe d'autre chose qu'un usage normal.
    HOMONYMES_MAX = 100

    @staticmethod
    def _slug_libre(db, base):
        """La première adresse libre : `nom`, puis `nom-2`, `nom-3`…

        Le PREMIER projet garde l'adresse que son nom annonce — c'est celui
        qui était déjà en ligne, et la lui retirer casserait un site qui
        marche. Ce sont les suivants qui portent le suffixe.

        L'adresse est un sous-domaine, donc l'unicité est GLOBALE et non par
        compte : sans cela, un inconnu qui nomme son projet comme le vôtre
        rendait les deux injoignables (`project_for_host` refuse de servir
        quand deux projets répondent au même hôte, et il a raison de refuser).
        """
        # `.lower()` n'est pas redondant avec le `COLLATE NOCASE` : celui-ci
        # gouverne la SÉLECTION, le repli ci-dessous gouverne la COMPARAISON en
        # Python. Sans lui, une ligne ANTÉRIEURE écrite « myOwn » — du temps où
        # le slug gardait sa casse — était bien remontée par la requête, puis
        # jugée différente de « myown » : deux projets pour un seul hôte, donc
        # `project_for_host` refusant de servir les deux. C'est le défaut (b)
        # survivant sur les bases déjà en service, trouvé par un témoin et non
        # par relecture. Replier d'un seul côté d'une comparaison ne replie rien.
        prise = {ligne["slug"].lower() for ligne in db.execute(
            "SELECT slug FROM builder_projects WHERE slug = ? COLLATE NOCASE "
            "OR slug LIKE ? COLLATE NOCASE", (base, f"{base}-%"))}
        if base not in prise:
            return base
        for rang in range(2, StoreProjectsMixin.HOMONYMES_MAX + 1):
            candidat = f"{base}-{rang}"
            if candidat not in prise:
                return candidat
        raise ValueError(
            f"trop de projets portent l'adresse '{base}' "
            f"({StoreProjectsMixin.HOMONYMES_MAX} au plus)")

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
            # POINT 162 : plus rien n'écrit dans 'builds'. La table et ce
            # garde-fou survivent pour les bases ANTÉRIEURES, qui portent de
            # vraies lignes : une migration additive rattrape une colonne,
            # jamais un contenu (points 32 et 89). Sur une base neuve, la
            # table reste vide et cette lecture ne refuse jamais rien.
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



