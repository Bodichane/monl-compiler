"""Offline administration reads, backups and expiry handling."""

from __future__ import annotations

import os
import sqlite3
import time
from pathlib import Path
from typing import Any

from .identity_primitives import IdentityError


class IdentityAdminMixin:
    def comptes_sans_codes(self) -> int:
        """Combien de comptes n'ont aucun code de secours.

        Les comptes ANTÉRIEURS n'en ont pas : la migration additive rattrape
        une table, jamais son contenu (point 89, mot pour mot). Leur en
        fabriquer au démarrage serait pire — il faudrait les afficher, et
        personne ne les lirait. Ils sont donc COMPTÉS et nommés, et la page du
        compte propose d'en générer.
        """
        with self._connect() as db:
            return db.execute(
                "SELECT COUNT(*) FROM users WHERE id NOT IN "
                "(SELECT DISTINCT user_id FROM recovery_codes)").fetchone()[0]

    def comptes_herites(self) -> int:
        """Compte les anciennes lignes ``accounts`` sans les convertir.

        L'ancien registre utilisait un autre hachage et des identifiants
        entiers. Aucun mot de passe ne peut être deviné ou fabriqué pour le
        transférer honnêtement dans ``users`` ; la table reste donc intacte et
        le démarrage nomme seulement le nombre de comptes non repris.
        """
        with self._connect() as db:
            existe = db.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'accounts'"
            ).fetchone()
            if existe is None:
                return 0
            return db.execute("SELECT COUNT(*) FROM accounts").fetchone()[0]

    count_legacy_accounts = comptes_herites

    # ------------------------------------------------------------------
    # Lectures et gestes d'exploitation
    # ------------------------------------------------------------------
    #
    # Ces méthodes n'ont AUCUNE route HTTP. Toute intervention sur un compte
    # passait par `sqlite3` à la main, serveur arrêté : tenable à dix comptes,
    # pas à cent, et chaque geste risquait une requête tapée de travers sans
    # trace de qui l'avait faite.
    #
    # Le choix d'une ligne de commande plutôt que d'un panneau web n'est pas
    # de la paresse. Un panneau demanderait sa propre authentification et une
    # colonne de privilège, et deviendrait la cible la plus intéressante du
    # service. Qui possède le shell possède déjà la base : la ligne de
    # commande n'ajoute donc AUCUNE surface d'attaque, elle rend seulement
    # sûrs et traçables des gestes qu'on faisait déjà.

    def comptes(self) -> list[dict[str, Any]]:
        """Tous les comptes, avec de quoi décider sans requête de plus."""
        with self._connect() as db:
            lignes = db.execute("""
                SELECT users.id, users.email, users.created_at,
                       (SELECT COUNT(*) FROM projects WHERE user_id = users.id) AS projets,
                       (SELECT COUNT(*) FROM api_keys
                        WHERE user_id = users.id AND revoked_at IS NULL) AS cles,
                       (SELECT COUNT(*) FROM recovery_codes
                        WHERE user_id = users.id) AS codes
                FROM users ORDER BY users.created_at DESC
            """).fetchall()
        return [dict(ligne) for ligne in lignes]

    def compte_par_adresse(self, email: Any) -> dict[str, str] | None:
        """Retrouve un compte par son adresse, sans mot de passe.

        L'adresse est NORMALISÉE comme à l'inscription : sans ça, l'exploitant
        taperait l'adresse telle qu'on la lui a dictée et ne trouverait rien,
        alors que le compte existe.
        """
        try:
            normalise = self._email(email)
        except IdentityError:
            return None
        with self._connect() as db:
            ligne = db.execute("SELECT id, email FROM users WHERE email = ?",
                               (normalise,)).fetchone()
        return {"id": ligne["id"], "email": ligne["email"]} if ligne else None

    def tous_les_projets(self, user_id: str | None = None) -> list[dict[str, Any]]:
        requete = ("SELECT projects.*, users.email FROM projects "
                   "JOIN users ON users.id = projects.user_id ")
        parametres: tuple = ()
        if user_id:
            requete += "WHERE projects.user_id = ? "
            parametres = (user_id,)
        with self._connect() as db:
            lignes = db.execute(requete + "ORDER BY projects.created_at DESC",
                                parametres).fetchall()
        return [dict(ligne) for ligne in lignes]

    def deplacer_echeance(self, project_id: str, secondes: int | None) -> bool:
        """Repousse (ou avance) l'expiration d'un projet. `None` = jamais.

        Compté depuis MAINTENANT et non depuis l'échéance actuelle : « garde-le
        trente jours de plus » se dit après coup, souvent sur un projet déjà
        échu, et repartir de l'ancienne date ne prolongerait rien.
        """
        echeance = None if secondes is None else int(time.time()) + secondes
        with self._connect() as db:
            curseur = db.execute("UPDATE projects SET expires_at = ? WHERE project_id = ?",
                                 (echeance, project_id))
        return curseur.rowcount == 1

    def revoquer_cle_par_id(self, key_id: str) -> dict[str, str] | None:
        """Révoque une clé sans connaître son propriétaire.

        `revoke_api_key` exige l'identifiant du compte, parce qu'une route HTTP
        ne doit toucher que les clés de l'appelant. L'exploitant, lui, a devant
        lui un préfixe de clé lu dans un journal et pas grand-chose d'autre.
        """
        with self._connect() as db:
            ligne = db.execute(
                "SELECT api_keys.id, api_keys.name, users.email FROM api_keys "
                "JOIN users ON users.id = api_keys.user_id "
                "WHERE api_keys.id = ? AND api_keys.revoked_at IS NULL",
                (key_id,)).fetchone()
            if not ligne:
                return None
            db.execute("UPDATE api_keys SET revoked_at = ? WHERE id = ?",
                       (int(time.time()), key_id))
        return dict(ligne)

    def cles_du_compte(self, user_id: str) -> list[dict[str, Any]]:
        return self.api_keys(user_id)

    def sauvegarder(self, destination: str | os.PathLike[str]) -> Path:
        """Copie la base par l'API de sauvegarde en ligne de SQLite.

        Un `cp` sur une base ouverte peut rendre un fichier DÉCHIRÉ : la
        plateforme écrit en WAL, donc le `.sqlite3` seul ne contient pas les
        transactions encore dans le journal. `Connection.backup()` prend une
        copie cohérente pendant que le serveur continue de servir — c'est la
        seule raison d'être de cette méthode plutôt que d'une ligne de shell.
        """
        cible = Path(destination).resolve()
        cible.parent.mkdir(parents=True, exist_ok=True)
        source = sqlite3.connect(self.path, timeout=30)
        copie = sqlite3.connect(cible)
        try:
            source.backup(copie)
        finally:
            copie.close()
            source.close()
        return cible

    def expired_projects(self) -> list[str]:
        now = int(time.time())
        with self._connect() as db:
            rows = db.execute("SELECT project_id FROM projects "
                              "WHERE expires_at IS NOT NULL AND expires_at <= ?", (now,)).fetchall()
            db.executemany("DELETE FROM projects WHERE project_id = ?",
                           [(row["project_id"],) for row in rows])
        return [row["project_id"] for row in rows]



