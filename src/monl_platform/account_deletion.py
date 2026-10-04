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
        message = "Reconnectez-vous avec votre fournisseur OAuth puis réessayez : la connexion doit dater de moins de dix minutes."
    elif identities.authenticate(user["email"], payload.get("password")):
        return
    else:
        message = "Mot de passe incorrect : le compte n'a pas été supprimé."
    anomalie("suppression_compte_refusee", compte=court(user["id"]))
    raise HTTPException(status_code=403, detail=message)
