"""Credential validation and password/token primitives."""

from __future__ import annotations

import hashlib
import re
from typing import Any

from .identity_primitives import EMAIL, IdentityError


class IdentityCredentialsMixin:
    @staticmethod
    def _email(value: Any) -> str:
        email = str(value or "").strip().lower()
        if len(email) > 254 or not EMAIL.fullmatch(email):
            raise IdentityError("Saisissez une adresse email valide.")
        return email

    @classmethod
    def _login_identifier(cls, value: Any) -> str | None:
        """Accepte l'email humain ou l'identifiant OAuth namespace."""
        raw = str(value or "").strip().lower()
        try:
            return cls._email(raw)
        except IdentityError:
            if re.fullmatch(r"[a-z][a-z0-9_-]*:[^\s:]+", raw):
                return raw
            return None

    @staticmethod
    def _password(value: Any) -> str:
        password = str(value or "")
        if len(password) < 10:
            raise IdentityError("Le mot de passe doit contenir au moins 10 caractères.")
        if len(password.encode("utf-8")) > 1024:
            raise IdentityError("Le mot de passe est trop long.")
        return password

    @staticmethod
    def _password_hash(password: str, salt: bytes) -> bytes:
        return hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)

    @staticmethod
    def _token_hash(token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()




