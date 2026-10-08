"""Témoins HTTP de remplacement, partagés avec les contre-épreuves."""

from tests.test_verification_email import (
    ACCOUNTS,
    PASSWORD,
    _confirm,
    _login,
    _messages,
    _post,
    _sql,
    _token,
)

NEW_PASSWORD = 'nouveau-secret-456'


def register(base, account=ACCOUNTS[0], password=NEW_PASSWORD, actor='User'):
    return _post(base, '/register', username=account, password=password, actor=actor)


def replacement(base, smtp, tokens, directory):
    from tests.test_verification_email import _register_two
    original = _register_two.responses[0]
    response = register(base, ACCOUNTS[0].upper())
    assert response.status_code == 200, 'remplacement désarmé'
    assert {k: type(v) for k, v in response.json().items()} == {k: type(v) for k, v in original.items()}
    assert response.json()['status'] == original['status'] == 'pending'
    latest = _token(smtp, ACCOUNTS[0], 3)
    assert _login(base, ACCOUNTS[0], PASSWORD).status_code == 401
    assert _login(base, ACCOUNTS[0], NEW_PASSWORD).status_code == 403
    assert _confirm(base, ACCOUNTS[0], tokens[0]).status_code == 400
    assert _confirm(base, ACCOUNTS[0], latest).status_code == 200
    assert _login(base, ACCOUNTS[0], NEW_PASSWORD).status_code == 200
    assert _login(base, ACCOUNTS[0], PASSWORD).status_code == 401
    assert _login(base, ACCOUNTS[1], PASSWORD).status_code == 403


def confirmed(base, smtp, tokens, directory):
    for account, token in zip(ACCOUNTS, tokens, strict=True):
        assert _confirm(base, account, token).status_code == 200
    for account in ACCOUNTS:
        response = register(base, account)
        assert _login(base, account, PASSWORD).status_code == 200, 'garde confirmé désarmée : mot de passe pris'
        assert response.status_code == 409, 'garde confirmé désarmée'
        assert _login(base, account, NEW_PASSWORD).status_code == 401
    assert _sql(directory, 'SELECT COUNT(*) FROM _monl_verify_email_tokens') == [(2,)]
    _messages(smtp, 2)


def quota(base, smtp, tokens, directory):
    for _ in range(3):
        assert _post(base, '/verify-email/resend', username=ACCOUNTS[0]).status_code == 200
    latest = _token(smtp, ACCOUNTS[0], 5)
    response = register(base, ACCOUNTS[0].upper())
    assert response.status_code == 200 and response.json()['status'] == 'pending'
    assert _login(base, ACCOUNTS[0], PASSWORD).status_code == 403, 'quota remplacement désarmé'
    assert _login(base, ACCOUNTS[0], NEW_PASSWORD).status_code == 401
    assert _sql(directory, 'SELECT COUNT(*) FROM _monl_verify_email_tokens') == [(5,)]
    _messages(smtp, 5)
    assert _confirm(base, ACCOUNTS[0], latest).status_code == 200


def lockout(base, smtp, tokens, directory):
    for _ in range(3):
        assert _login(base, ACCOUNTS[0], 'incorrect-secret').status_code == 401
    assert _login(base, ACCOUNTS[0], PASSWORD).status_code == 401
    _sql(directory, 'INSERT INTO _monl_refresh_tokens (token_hash, user_id, issued_at, expires_at) VALUES (?, 1, 0, 9999999999)', ('stale',))
    assert register(base, actor='Admin').status_code == 403
    assert _login(base, ACCOUNTS[0], PASSWORD).status_code == 401
    assert register(base, actor='Reader').status_code == 200
    assert _sql(directory, 'SELECT actor, token_version FROM _monl_users WHERE id = 1') == [('Reader', 1)]
    assert _sql(directory, 'SELECT COUNT(*) FROM _monl_refresh_tokens WHERE user_id = 1') == [(0,)]
    assert _sql(directory, 'SELECT actor, token_version FROM _monl_users WHERE id = 2') == [('User', 0)]
    _messages(smtp, 3)
    assert _login(base, ACCOUNTS[0], NEW_PASSWORD).status_code == 403
    assert _login(base, ACCOUNTS[1], PASSWORD).status_code == 403


def shared_quota(base, smtp, tokens, directory):
    for attempt in range(3):
        assert register(base).status_code == 200
        _messages(smtp, 3 + attempt)
    assert _post(base, '/verify-email/resend', username=ACCOUNTS[0]).status_code == 200
    assert register(base, password='autre-secret-789').status_code == 200
    assert _login(base, ACCOUNTS[0], NEW_PASSWORD).status_code == 403
    assert _login(base, ACCOUNTS[0], 'autre-secret-789').status_code == 401
    assert _sql(directory, 'SELECT COUNT(*) FROM _monl_verify_email_tokens') == [(5,)]
    _messages(smtp, 5)


WITNESSES = {'replacement': replacement, 'confirmed': confirmed, 'quota': quota,
             'lockout': lockout, 'shared_quota': shared_quota}
MUTATIONS = {
    'confirmed': ('if row and row[1]:', 'if False:'),
    'replacement': ('if row and row[1]:', 'if row:'),
    'quota': ('if not _verification_quota(cursor, identifier):', 'if False:'),
}
ERRORS = {'confirmed': 'garde confirmé désarmée', 'replacement': 'remplacement désarmé',
          'quota': 'quota remplacement désarmé'}
