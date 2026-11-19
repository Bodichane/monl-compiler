"""Proof of reauthentication before an irreversible deletion."""

import time

from fastapi import HTTPException

from .log import anomaly, short


def check_deletion(identities, user, token, payload):
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
    anomaly("suppression_compte_refusee", compte=short(user["id"]))
    raise HTTPException(status_code=403, detail=message)
