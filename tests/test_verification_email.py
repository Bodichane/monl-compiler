"""Point 209: two accounts, real uvicorn, messages really received over SMTP.

The counter-proofs only mutate the throwaway compiled application, then run
the SAME witness: a red test is required for each guard.
"""

import contextlib
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import pytest
import requests

from monl.ast_validator import ASTValidationError
from monl.cli import _contract_signature, compile_project
from monl.cli.delta import cmd_update
from tests.support.server import uvicorn_server
from tests.support.sqlite import sqlite_db
from tests.test_authentification_b4 import faux_smtp as faux_smtp
from tests.test_messages import _uvicorn_with_output

LEGACY = '''app Verification

entity Note
    body: String

actor User selfRegister
actor Admin

capability auth
    identifier: email

workflow Main for User
    Create Note
    Read Note
'''
SETTINGS = '    verify_email: 86400\n    verify_resend: 3 in 3600\n'
SPEC = LEGACY.replace('    identifier: email\n', '    identifier: email\n' + SETTINGS)
PASSWORD = 'mot-de-passe-123'
ACCOUNTS = ('alice@example.test', 'bob@example.test')

def _compile(directory, spec=SPEC):
    directory.mkdir(parents=True, exist_ok=True)
    source = directory / 'spec.ml'
    source.write_text(spec)
    with contextlib.redirect_stdout(io.StringIO()):
        return compile_project(str(source), str(directory))

def _env(smtp):
    env = os.environ.copy()
    env.pop('MONL_DATABASE_URL', None)
    env.update(MONL_JWT_SECRET='verification-integration-secret-32-bytes',
               MONL_TRUST_PROXY='1', PYTHONUNBUFFERED='1',
               MONL_SMTP_HOST=smtp.server_address[0],
               MONL_SMTP_PORT=str(smtp.server_address[1]),
               MONL_SMTP_FROM='monl@example.test',
               MONL_PASSWORD_RESET_URL='https://example.test/site/confirmation')
    return env

def _post(base, path, **data):
    # Do not let the historical IP limiter hide the measured guard.
    _post.sequence += 1
    return requests.post(base + path, json=data, timeout=10,
                         headers={'X-Forwarded-For': f'192.0.2.{_post.sequence}'})

_post.sequence = 0

def _login(base, account, password=PASSWORD):
    return _post(base, '/login', username=account, password=password)

def _sql(directory, statement, parameters=()):
    with sqlite_db(directory / 'app.db') as conn:
        return conn.execute(statement, parameters).fetchall()

def _messages(smtp, count):
    deadline = time.monotonic() + 10
    while len(smtp.messages) < count and time.monotonic() < deadline:
        time.sleep(0.02)
    assert len(smtp.messages) == count, 'SMTP message not received'

def _token(smtp, account, count):
    _messages(smtp, count)
    messages = [message for message in smtp.messages if message['To'] == account]
    assert messages
    body = messages[-1].get_content()
    assert 'https://example.test/site/confirmation?token=' in body
    assert messages[-1]['Subject'] == 'Confirm your email address'
    return re.search(r'token: ([A-Za-z0-9_-]+)', body)[1]

def _register_two(base, smtp, actor="User"):
    _register_two.responses = []
    for account in ACCOUNTS:
        response = _post(base, '/register', username=account, password=PASSWORD, actor=actor)
        assert response.status_code == 200
        _register_two.responses.append(response.json())
        assert response.json()['status'] == 'pending'
        assert not {'access_token', 'refresh_token', 'token'} & response.json().keys()
    return [_token(smtp, account, 2) for account in ACCOUNTS]

@contextlib.contextmanager
def _application(directory, smtp, mutation=None, spec=SPEC):
    contract = _compile(directory, spec)
    if mutation:
        path = directory / 'app.py'
        original = path.read_text()
        before, after = mutation
        assert before in original, 'counter-proof without target'
        path.write_text(original.replace(before, after))
    with uvicorn_server(directory, env=_env(smtp)) as base:
        tokens = _register_two(base, smtp, contract["self_register_actors"][0])
        yield base, tokens

def _assert_login(base):
    for account in ACCOUNTS:
        good = _login(base, account)
        assert good.status_code == 403, '403 guard disarmed'
        assert good.json()['detail']['code'] == 'email_not_verified'
        assert not {'access_token', 'refresh_token', 'token'} & good.json().keys()
        wrong = _login(base, account, 'mot-de-passe-faux')
        missing = _login(base, 'absent@example.test', 'mot-de-passe-faux')
        assert wrong.status_code == missing.status_code == 401
        assert wrong.json() == missing.json() == {'detail': 'Invalid credentials.'}

def _confirm(base, account, token):
    return _post(base, '/verify-email', username=account, token=token)

def _assert_replay(base, tokens):
    assert _confirm(base, ACCOUNTS[0], tokens[0]).status_code == 200
    assert _confirm(base, ACCOUNTS[0], tokens[0]).status_code == 400, 'consumption disarmed'
    assert _login(base, ACCOUNTS[0]).status_code == 200
    assert _login(base, ACCOUNTS[1]).status_code == 403

def _assert_expiration(base, tokens, directory):
    _sql(directory, 'UPDATE _monl_verify_email_tokens SET expires_at = 0 WHERE token_hash = ?',
         (hashlib.sha256(tokens[0].encode()).hexdigest(),))
    assert _confirm(base, ACCOUNTS[0], tokens[0]).status_code == 400, 'expiration disarmed'
    assert _login(base, ACCOUNTS[0]).status_code == 403
    assert _confirm(base, ACCOUNTS[1], tokens[1]).status_code == 200
    assert _login(base, ACCOUNTS[1]).status_code == 200

def _assert_limit(base, smtp, directory):
    expected = {'status': 'accepted', 'detail': 'If the account exists, a message has been sent.'}
    for attempt in range(4):
        for account in (ACCOUNTS[0], 'absent@example.test'):
            started = time.perf_counter()
            response = _post(base, '/verify-email/resend', username=account)
            assert response.status_code == 200
            assert response.json() == expected
            assert time.perf_counter() - started >= 0.045
        if attempt < 3:
            _messages(smtp, 3 + attempt)
    count = _sql(directory, 'SELECT COUNT(*) FROM _monl_verify_email_tokens WHERE user_id = 1')[0][0]
    assert count == 4, 'resend limit disarmed'  # inscription + trois renvois
    _messages(smtp, 5)
    assert _login(base, ACCOUNTS[0]).status_code == 403
    assert _login(base, ACCOUNTS[1]).status_code == 403

def test_registration_confirmation_and_replay(tmp_path, faux_smtp):
    with _application(tmp_path, faux_smtp) as (base, tokens):
        _assert_login(base)
        hashes = _sql(tmp_path, 'SELECT token_hash FROM _monl_verify_email_tokens')
        assert {row[0] for row in hashes} == {hashlib.sha256(t.encode()).hexdigest() for t in tokens}
        _assert_replay(base, tokens)
        assert _confirm(base, ACCOUNTS[1], tokens[1]).status_code == 200
        assert _login(base, ACCOUNTS[1]).status_code == 200
        assert requests.get(base + '/verify-email', timeout=10).status_code == 405


def test_expired_token(tmp_path, faux_smtp):
    with _application(tmp_path, faux_smtp) as (base, tokens):
        _assert_expiration(base, tokens, tmp_path)


def test_token_of_another_account(tmp_path, faux_smtp):
    with _application(tmp_path, faux_smtp) as (base, tokens):
        assert _confirm(base, ACCOUNTS[1], tokens[0]).status_code == 400
        assert _confirm(base, 'étranger@example.test', tokens[0]).status_code == 400
        assert all(_login(base, a).status_code == 403 for a in ACCOUNTS)
        assert _confirm(base, ACCOUNTS[0], tokens[0]).status_code == 200
        assert _login(base, ACCOUNTS[1]).status_code == 403
        assert _confirm(base, ACCOUNTS[1], tokens[1]).status_code == 200


def test_generic_resend_limit_and_invalidation(tmp_path, faux_smtp):
    with _application(tmp_path, faux_smtp) as (base, tokens):
        _assert_limit(base, faux_smtp, tmp_path)
        assert _confirm(base, ACCOUNTS[0], tokens[0]).status_code == 400
        assert _confirm(base, ACCOUNTS[1], tokens[1]).status_code == 200
        latest = _token(faux_smtp, ACCOUNTS[0], 5)
        assert _confirm(base, ACCOUNTS[0], latest).status_code == 200
        assert all(_login(base, a).status_code == 200 for a in ACCOUNTS)


MUTATIONS = {
    '403': ('    if not _confirmed:', '    if False:'),
    'consommation': ('AND used_at IS NULL AND expires_at > ?', 'AND expires_at > ?'),
    'expiration': ('AND expires_at > ?', 'AND ? >= 0'),
    'limite': ('if recent >= VERIFY_RESEND_MAX:', 'if False:'),
}


@pytest.mark.parametrize('guard', MUTATIONS)
def test_contre_epreuves(guard, tmp_path, faux_smtp):
    with _application(tmp_path, faux_smtp, MUTATIONS[guard]) as (base, tokens):
        with pytest.raises(AssertionError, match={
                '403': '403 guard disarmed', 'consommation': 'consumption disarmed',
                'expiration': 'expiration disarmed', 'limite': 'resend limit disarmed'}[guard]) as red:
            if guard == '403':
                _assert_login(base)
            elif guard == 'consommation':
                _assert_replay(base, tokens)
            elif guard == 'expiration':
                _assert_expiration(base, tokens, tmp_path)
            else:
                _assert_limit(base, faux_smtp, tmp_path)
        print(f'CONTRE-ÉPREUVE {guard} : témoin ROUGE : {red.value}')


@pytest.mark.parametrize('settings', [
    '    verify_email: 86400\n', '    verify_resend: 3 in 3600\n',
    '    verify_email: 0\n    verify_resend: 3 in 3600\n',
    '    verify_email: 1\n    verify_resend: 0 in 3600\n',
    '    verify_email: 1\n    verify_resend: 3 in 0\n',
])
def test_incomplete_or_invalid_settings_refused(settings, tmp_path):
    with pytest.raises(ASTValidationError):
        _compile(tmp_path, LEGACY.replace('    identifier: email\n', '    identifier: email\n' + settings))


@pytest.mark.parametrize('identifier', ['', '    identifier: phone\n', '    identifier: email, phone\n'])
def test_refused_without_email_identifier(identifier, tmp_path):
    with pytest.raises(ASTValidationError, match='identifier: email'):
        _compile(tmp_path, SPEC.replace('    identifier: email\n', identifier))


def test_earlier_accounts_and_manage_stay_confirmed(tmp_path, faux_smtp):
    _compile(tmp_path, LEGACY)
    env = _env(faux_smtp)
    with uvicorn_server(tmp_path, env=env) as base:
        for account in ACCOUNTS:
            assert _post(base, '/register', username=account, password=PASSWORD, actor='User').status_code == 200
            assert _login(base, account).status_code == 200
    _compile(tmp_path)
    with _uvicorn_with_output(tmp_path, env) as server:
        server.attendre('2 older account(s) remain confirmed')
        assert all(_login(server.base, a).status_code == 200 for a in ACCOUNTS)
        result = subprocess.run([sys.executable, 'manage.py', 'adduser', 'service', 'Admin'],
                                cwd=tmp_path, env=env, input=PASSWORD + '\n' + PASSWORD + '\n', capture_output=True, text=True)
        assert result.returncode == 0, result.stdout + result.stderr
        login = _login(server.base, 'service')
        assert login.status_code == 200
        changed = subprocess.run([sys.executable, 'manage.py', 'passwd', 'service'],
                                 cwd=tmp_path, env=env, input='nouveau-secret-123\n' * 2,
                                 capture_output=True, text=True)
        assert changed.returncode == 0, changed.stdout + changed.stderr
        assert _login(server.base, 'service', 'nouveau-secret-123').status_code == 200
        old_session = requests.post(server.base + '/logout', timeout=10,
                                    headers={'Authorization': 'Bearer ' + login.json()['access_token']})
        assert old_session.status_code == 401
        assert _post(server.base, '/register', username='admin@example.test', password=PASSWORD, actor='Admin').status_code == 403
        assert not faux_smtp.messages


def test_contract_signature_and_monl_update(tmp_path, capsys):
    previous = _compile(tmp_path, LEGACY)
    (tmp_path / 'spec.ml').write_text(SPEC)
    cmd_update(str(tmp_path))
    output = capsys.readouterr().out
    current = json.loads((tmp_path / 'frontend_contract.json').read_text())
    assert _contract_signature(previous) != _contract_signature(current)
    assert '/verify-email' in output and '/verify-email/resend' in output
    assert 'authentification B4' in output
    auth = current['api']['auth']
    import copy
    before = copy.deepcopy(current)
    del before['api']['auth']['features']['verify_email']['unconfirmed_registration']
    assert _contract_signature(before) != _contract_signature(current)
    assert 'replaces the password' in (tmp_path / 'docs' / 'FRONTEND_PROMPT.md').read_text()
    assert auth['login']['errors']['403']['code'] == 'email_not_verified'
    assert auth['features']['verify_email']['resend'] == {'max_attempts': 3, 'window_seconds': 3600}


def test_monl_run_check(tmp_path):
    _compile(tmp_path)
    result = subprocess.run([sys.executable, '-m', 'monl.cli', 'run', str(tmp_path), '--check'],
                            capture_output=True, text=True, timeout=60,
                            env={**os.environ, 'PYTHONPATH': str(Path('src').resolve())})
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'confirmation' in result.stdout.lower(), result.stdout


def test_dialogue_email_to_server(tmp_path, faux_smtp):
    from tests.test_app_templates import _run_template
    spec = _run_template(1, 'n', False, account_answers=['2', 'o', '86400', '3', '3600'])
    assert SETTINGS.strip() in spec
    with _application(tmp_path, faux_smtp, spec=spec) as (base, tokens):
        _assert_login(base)
        _assert_replay(base, tokens)


def test_dialogue_refused_confirmation_writes_nothing(monkeypatch):
    from monl.dialogue_engine.accounts import ComptesMixin
    from tests.test_app_templates import TEMPLATES, _run_template
    # The only dialogue delta is the confirmation offer: compare the real
    # journey that refuses it with the same journey without this question.
    refused = {}
    for index in range(1, len(TEMPLATES) + 1):
        for answer in ('n', 'o'):
            refused[index, answer] = _run_template(
                index, answer, answer == 'o', account_answers=['2', 'n'])
    monkeypatch.setattr(ComptesMixin, '_ask_email_verification', lambda self: {})
    baseline = {}
    for index in range(1, len(TEMPLATES) + 1):
        for answer in ('n', 'o'):
            baseline[index, answer] = _run_template(
                index, answer, answer == 'o', account_answers=['2'])
    assert len(refused) == len(baseline) == 20
    assert refused == baseline
    assert all('verify_email' not in spec for spec in refused.values())


def test_dialogue_asks_only_for_online_email():
    from monl.dialogue_engine import GuidedDialogue
    for answers, self_register in [([], None), (['0'], 'User'),
                                    (['1', '+229'], 'User'), (['3', '+229'], 'User')]:
        prompts = []
        it = iter(answers)
        engine = GuidedDialogue(ask=lambda prompt, prompts=prompts, it=it: (prompts.append(prompt), next(it))[1])
        engine._ask_account_identifier(self_register)
        assert not any('confirmation' in prompt for prompt in prompts)
    prompts = []
    answers = iter(['2', 'n'])
    engine = GuidedDialogue(ask=lambda prompt: (prompts.append(prompt), next(answers))[1])
    engine._ask_account_identifier('User')
    assert sum('confirmation' in prompt for prompt in prompts) == 1


def test_transport_failure_breaks_neither_registration_nor_resend(tmp_path, faux_smtp):
    _compile(tmp_path)
    env = _env(faux_smtp)
    env['MONL_SMTP_PORT'] = '0'
    with _uvicorn_with_output(tmp_path, env) as server:
        for account in ACCOUNTS:
            response = _post(server.base, '/register', username=account, password=PASSWORD, actor='User')
            assert response.status_code == 200
            assert _login(server.base, account).status_code == 403
        assert _post(server.base, '/verify-email/resend', username=ACCOUNTS[0]).status_code == 200
        server.attendre('[MONL_PASSWORD_RESET] message not sent')
        assert _sql(tmp_path, 'SELECT COUNT(*) FROM _monl_users WHERE email_verified = 0') == [(2,)]
        assert not faux_smtp.messages


def test_verification_combined_with_b4(tmp_path, faux_smtp):
    spec = SPEC.replace(SETTINGS, SETTINGS + '    lockout: 3 in 3600\n    password_reset: 60\n    refresh_tokens: 3600\n    totp\n')
    with _application(tmp_path, faux_smtp, spec=spec) as (base, tokens):
        _assert_login(base)
        # The dummy salt must never turn absence into an account.
        assert _login(base, 'absent@example.test', 'monl-dummy-password').status_code == 401
        _assert_replay(base, tokens)
        response = _login(base, ACCOUNTS[0])
        assert response.status_code == 200
        assert response.json()['access_token'] and response.json()['refresh_token']
        assert _login(base, ACCOUNTS[1]).status_code == 403


def test_lockout_takes_precedence_over_unconfirmed_account(tmp_path, faux_smtp):
    # A locked account answers 401 even with the RIGHT password: the "not
    # confirmed" 403 must never bypass the point 124 lockout.
    spec = SPEC.replace(SETTINGS, SETTINGS + '    lockout: 3 in 3600\n')
    with _application(tmp_path, faux_smtp, spec=spec) as (base, tokens):
        assert _login(base, ACCOUNTS[0]).status_code == 403
        for _ in range(3):
            assert _login(base, ACCOUNTS[0], 'mot-de-passe-faux').status_code == 401
        assert _login(base, ACCOUNTS[0]).status_code == 401


@pytest.mark.parametrize('scenario,counterproof', [(s, c) for c in (False, True) for s in
    ('replacement', 'confirmed', 'quota', 'lockout', 'shared_quota') if not c or s in ('replacement', 'confirmed', 'quota')])
def test_preinscription(scenario, counterproof, tmp_path, faux_smtp):
    from tests.support.preregistration import ERRORS, MUTATIONS, WITNESSES
    mutation = MUTATIONS[scenario] if counterproof else None
    spec = SPEC.replace(SETTINGS, SETTINGS + '    lockout: 3 in 3600\n    refresh_tokens: 3600\n').replace('actor Admin', 'actor Reader selfRegister\nactor Admin') if scenario == 'lockout' else SPEC
    with _application(tmp_path, faux_smtp, mutation, spec) as (base, tokens):
        if counterproof:
            with pytest.raises(AssertionError, match=ERRORS[scenario]) as red:
                WITNESSES[scenario](base, faux_smtp, tokens, tmp_path)
            print(f'CONTRE-ÉPREUVE pré-inscription {scenario} : témoin ROUGE : {red.value}')
        else:
            WITNESSES[scenario](base, faux_smtp, tokens, tmp_path)
