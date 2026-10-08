"""Un compte non confirmé est un résultat attendu, pas une application cassée."""

from . import fondations


def verifier_connexion(base, contract, status, body, errors, warnings):
    """Éprouve le refus et la présence des deux POST sans consommer de lien."""
    if not contract.get('api', {}).get('auth', {}).get('features', {}).get('verify_email'):
        token = body.get('token') or body.get('access_token')
        if status != 200 or not token:
            errors.append(f'/login a répondu {status} sans jeton exploitable')
            return None
        return token
    if status != 403 or body.get('detail', {}).get('code') != 'email_not_verified':
        errors.append(f'/login a répondu {status} (403 email_not_verified attendu)')
    if body.get('access_token') or body.get('token') or body.get('refresh_token'):
        errors.append('/login a émis une session avant confirmation')
    code, openapi = fondations._http('GET', base + '/openapi.json')
    paths = openapi.get('paths', {})
    for path in ('/verify-email', '/verify-email/resend'):
        if code != 200 or 'post' not in paths.get(path, {}):
            errors.append(f'POST {path} absent du serveur')
    warnings.append('Confirmation e-mail requise : 403 attendu éprouvé ; connexion et création authentifiée après confirmation non éprouvées.')
    return None


def acteur_connecte(actor, contract):
    if contract.get('api', {}).get('auth', {}).get('features', {}).get('verify_email'):
        return None
    return actor
