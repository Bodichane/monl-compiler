"""Un compte non confirmé est un résultat attendu, pas une application cassée."""

from . import fondations


def verifier_connexion(base, contract, status, body, errors, warnings):
    """Éprouve le refus et la présence des deux POST sans consommer de lien."""
    if not contract.get('api', {}).get('auth', {}).get('features', {}).get('verify_email'):
        token = body.get('token') or body.get('access_token')
        if status != 200 or not token:
            errors.append(f'/login returned {status} without a usable token')
            return None
        return token
    if status != 403 or body.get('detail', {}).get('code') != 'email_not_verified':
        errors.append(f'/login returned {status} (expected 403 email_not_verified)')
    if body.get('access_token') or body.get('token') or body.get('refresh_token'):
        errors.append('/login issued a session before confirmation')
    code, openapi = fondations._http('GET', base + '/openapi.json')
    paths = openapi.get('paths', {})
    for path in ('/verify-email', '/verify-email/resend'):
        if code != 200 or 'post' not in paths.get(path, {}):
            errors.append(f'POST {path} missing from server')
    warnings.append('Email confirmation required: expected 403 verified; login and authenticated creation after confirmation not tested.')
    return None


def acteur_connecte(actor, contract):
    if contract.get('api', {}).get('auth', {}).get('features', {}).get('verify_email'):
        return None
    return actor
