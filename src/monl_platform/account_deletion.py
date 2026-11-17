"""Preuve de réauthentification avant suppression irréversible."""

import time

from fastapi import HTTPException

from .journal import anomalie, court


def verifier_suppression(identities, user, token, payload):
    session = identities.session_proof(token)
    if session and session.get("auth_provider"):
        age = time.time() - session["session_created_at"]
        if 0 <= age < 600:
            return
        message = "Sign in again with your OAuth provider, then retry: the sign-in must be less than ten minutes old."
    elif identities.authenticate(user["email"], payload.get("password")):
        return
    else:
        message = "Incorrect password: the account was not deleted."
    anomalie("suppression_compte_refusee", compte=court(user["id"]))
    raise HTTPException(status_code=403, detail=message)
