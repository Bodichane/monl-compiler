"""Accounts, OAuth identities and browser sessions."""

from __future__ import annotations

import hmac
import secrets
import sqlite3
import time
import uuid
from typing import Any

from .identity_primitives import SESSION_TTL, IdentityError


class IdentityAuthMixin:
    def register(self, email: Any, password: Any) -> dict[str, str]:
        normalized = self._email(email)
        secret = self._password(password)
        user_id, salt = uuid.uuid4().hex, secrets.token_bytes(16)
        try:
            with self._connect() as db:
                db.execute(
                    "INSERT INTO users "
                    "(id, email, password_hash, password_salt, created_at, auth_provider) "
                    "VALUES (?, ?, ?, ?, ?, NULL)",
                    (user_id, normalized, self._password_hash(secret, salt), salt,
                     int(time.time())),
                )
        except sqlite3.IntegrityError:
            raise IdentityError("Un compte existe déjà pour cette adresse.") from None
        return {"id": user_id, "email": normalized}

    def authenticate(self, email: Any, password: Any) -> dict[str, str] | None:
        normalized = self._login_identifier(email)
        if normalized is None:
            return None
        with self._connect() as db:
            row = db.execute(
                "SELECT id, email, password_hash, password_salt, auth_provider "
                "FROM users WHERE email = ?", (normalized,)
            ).fetchone()
        if not row:
            # Coût similaire pour limiter la distinction compte absent / mauvais secret.
            self._password_hash(str(password or ""), b"monl-missing-user")
            return None
        # Un compte OAuth possède volontairement un hash et un sel aléatoires
        # pour respecter NOT NULL. Ils ne sont pas un mot de passe de secours :
        # le refus doit arriver AVANT tout calcul et être exactement celui d'un
        # mauvais mot de passe.
        if row["auth_provider"] is not None:
            return None
        candidate = self._password_hash(str(password or ""), row["password_salt"])
        if not hmac.compare_digest(candidate, row["password_hash"]):
            return None
        return {"id": row["id"], "email": row["email"]}

    def upsert_oauth_account(self, identifier, provider, display_name=None):
        """Crée ou retrouve une identité OAuth sans fabriquer de mot de passe.

        ``identifier`` appartient à l'espace de noms du fournisseur
        (``github:4242`` ou ``google:...``). La colonne ``email`` conserve cet
        identifiant de connexion ; le libellé vérifié est consommé par la couche
        OAuth qui prépare la session, car le schéma d'identité ne porte pas de
        nom d'affichage séparé.

        ``display_name`` reste un argument accepté pour que la migration de
        l'ancien appelant ne perde pas le libellé vérifié, mais il n'est jamais
        utilisé comme identifiant : rattacher ce libellé à un compte mot de
        passe serait précisément la prise de contrôle écartée.
        """
        del display_name
        identifier = str(identifier).strip()
        provider = str(provider).strip()
        if not identifier or "\x00" in identifier:
            raise IdentityError("identifiant OAuth vide ou invalide")
        if not provider or "\x00" in provider:
            raise IdentityError("fournisseur OAuth vide ou invalide")
        with self._connect() as db:
            row = db.execute(
                "SELECT id, auth_provider FROM users WHERE email = ?", (identifier,)
            ).fetchone()
            if row is not None:
                if row["auth_provider"] != provider:
                    raise IdentityError("identité OAuth déjà attachée à un autre fournisseur")
                return row["id"], False
            user_id = uuid.uuid4().hex
            # Ces octets ne sont pas un digest calculé depuis un secret connu.
            # Ils existent uniquement pour satisfaire les NOT NULL du registre.
            password_hash = secrets.token_bytes(32)
            password_salt = secrets.token_bytes(16)
            db.execute(
                "INSERT INTO users "
                "(id, email, password_hash, password_salt, created_at, auth_provider) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (user_id, identifier, password_hash, password_salt, int(time.time()), provider),
            )
            return user_id, True

    def create_session(self, user_id: str) -> str:
        token = secrets.token_urlsafe(32)
        now = int(time.time())
        with self._connect() as db:
            db.execute("DELETE FROM sessions WHERE expires_at <= ?", (now,))
            db.execute("INSERT INTO sessions VALUES (?, ?, ?, ?)",
                       (self._token_hash(token), user_id, now + SESSION_TTL, now))
        return token

    def session_user(self, token: str | None) -> dict[str, str] | None:
        if not token:
            return None
        now = int(time.time())
        with self._connect() as db:
            row = db.execute(
                "SELECT users.id, users.email FROM sessions JOIN users "
                "ON users.id = sessions.user_id WHERE token_hash = ? AND expires_at > ?",
                (self._token_hash(token), now),
            ).fetchone()
        return {"id": row["id"], "email": row["email"]} if row else None

    def revoke_session(self, token: str | None) -> None:
        if token:
            with self._connect() as db:
                db.execute("DELETE FROM sessions WHERE token_hash = ?", (self._token_hash(token),))



