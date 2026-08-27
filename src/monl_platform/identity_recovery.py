"""Recovery-code creation and password recovery transactions."""

from __future__ import annotations

import secrets
import time
from typing import Any

from .identity_primitives import IdentityError


class IdentityRecoveryMixin:
    # ------------------------------------------------------------------
    # Codes de secours
    # ------------------------------------------------------------------
    #
    # Sans courriel, un mot de passe perdu rendait le compte et ses projets
    # définitivement inaccessibles. Le remède ne peut pas être « on vous
    # envoie un lien » : monl n'envoie rien, et une brique « savoir envoyer un
    # message » ouvrirait un serveur SMTP, un domaine à réputation et une
    # dépendance réseau dans un service qui n'en a aucune.
    #
    # Un code de secours déplace la garde chez la personne : elle reçoit des
    # codes UNE fois, elle les range où elle veut. C'est exactement le contrat
    # déjà passé pour les clés d'API — montrées une fois, hachées ensuite —
    # donc ni une nouvelle promesse, ni un nouveau mode de stockage.

    NB_CODES = 8

    def create_recovery_codes(self, user_id: str, /) -> list[str]:
        """Remplace TOUS les codes du compte et rend les nouveaux, en clair.

        Remplacer plutôt qu'ajouter : quelqu'un qui régénère ses codes le fait
        souvent parce qu'il craint que les anciens aient fuité. Les cumuler
        laisserait vivre exactement ce dont il veut se débarrasser.
        """
        codes = [secrets.token_urlsafe(12) for _ in range(self.NB_CODES)]
        maintenant = int(time.time())
        with self._connect() as db:
            db.execute("DELETE FROM recovery_codes WHERE user_id = ?", (user_id,))
            db.executemany(
                "INSERT INTO recovery_codes VALUES (?, ?, ?)",
                [(self._token_hash(code), user_id, maintenant) for code in codes])
        return codes

    def count_recovery_codes(self, user_id: str, /) -> int:
        with self._connect() as db:
            return db.execute(
                "SELECT COUNT(*) FROM recovery_codes WHERE user_id = ?",
                (user_id,)).fetchone()[0]

    def consume_recovery_code(self, email: Any, code: Any, password: Any
                              ) -> dict[str, str] | None:
        """Vérifie un code, change le mot de passe, et rend le compte.

        Le code est CONSOMMÉ dans la même transaction que le changement de mot
        de passe : hors d'elle, un échec de l'écriture laisserait un code
        brûlé pour rien, et la personne aurait perdu une chance sur huit sans
        rien obtenir.

        Toutes les sessions tombent. Une réinitialisation de mot de passe qui
        laisserait vivre les sessions ouvertes ne servirait à rien dans le cas
        qui compte — celui où quelqu'un d'autre est déjà entré.
        """
        try:
            normalise = self._email(email)
            secret = self._password(password)
        except IdentityError:
            return None
        empreinte = self._token_hash(str(code or ""))
        with self._connect() as db:
            ligne = db.execute(
                "SELECT users.id AS user_id, users.email FROM recovery_codes "
                "JOIN users ON users.id = recovery_codes.user_id "
                "WHERE recovery_codes.code_hash = ? AND users.email = ?",
                (empreinte, normalise)).fetchone()
            if not ligne:
                return None
            sel = secrets.token_bytes(16)
            db.execute("UPDATE users SET password_hash = ?, password_salt = ? "
                       "WHERE id = ?",
                       (self._password_hash(secret, sel), sel, ligne["user_id"]))
            db.execute("DELETE FROM recovery_codes WHERE code_hash = ?", (empreinte,))
            db.execute("DELETE FROM sessions WHERE user_id = ?", (ligne["user_id"],))
        return {"id": ligne["user_id"], "email": ligne["email"]}




