"""Taking back control of an account whose password is lost.

Without email, a lost password made the account AND its projects permanently
inaccessible. It was written in the terms of use, which makes it honest but
not acceptable: the first person it happens to loses all their work.

The rejected path deserves to be known. "We send you a link" assumes a mail
server, a domain with a reputation and a network dependency in a service that
has none — and the privacy policy promises no email is sent. The recovery
code moves the safekeeping to the person: they get eight codes once, they
store them where they like. It is the contract already made for API keys, so
neither a new promise nor a new storage mode.

Everything is tested against a real server: it is the only way to check that
a code really presented on the wire really resets a password, and that open
sessions do fall with it.
"""

import os

import requests

from monl_platform.identity import IdentityStore
from tests.support.server import uvicorn_server
from tests.support.sqlite import sqlite_db

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OLD = "MotDePasse-Ancien-2026"
NEW = "MotDePasse-Nouveau-2026"


def _server(folder):
    env = os.environ.copy()
    env["PYTHONPATH"] = os.path.join(RACINE, "src")
    return uvicorn_server(str(folder), env=env,
                          module="monl_platform.app:app", ready_path="/health")


def _register(base, address, password=OLD):
    session = requests.Session()
    response = session.post(f"{base}/api/auth/register", timeout=30,
                           json={"email": address, "password": password})
    assert response.status_code == 201, response.text
    return session, response.json()


def _space(tmp_path):
    candidate = tmp_path / "platform-projects"
    return candidate if candidate.exists() else tmp_path


# ---------------------------------------------------------------------------
# What registration hands over
# ---------------------------------------------------------------------------

def test_registration_hands_over_eight_codes_only_once(tmp_path):
    with _server(tmp_path) as base:
        session, body = _register(base, "codes@exemple.test")
        codes = body["recovery_codes"]
        assert len(codes) == 8
        assert len(set(codes)) == 8, "two identical codes halve the chances"
        assert all(len(c) >= 16 for c in codes), "un code court se devine"

        # They come out NOWHERE else — like an API key.
        state = session.get(f"{base}/api/auth/recovery-codes", timeout=30).json()
        assert state == {"remaining": 8}
        me = session.get(f"{base}/api/auth/me", timeout=30).text
        for code in codes:
            assert code not in me, "a code comes out of a read route"


def test_codes_are_never_stored_in_clear(tmp_path):
    """The privacy policy's promise, checked IN THE DATABASE.

    A code readable in the database would cancel the whole point: whoever reads
    the file gets into any account without knowing any password.
    """
    with _server(tmp_path) as base:
        _, body = _register(base, "clair@exemple.test")
        codes = body["recovery_codes"]

    store = IdentityStore(_space(tmp_path))
    with sqlite_db(store.path) as db:
        stored = [r[0] for r in db.execute("SELECT code_hash FROM recovery_codes")]
    assert len(stored) == 8
    for code in codes:
        assert code not in stored
        assert not any(code in valeur for valeur in stored)


# ---------------------------------------------------------------------------
# Taking back control
# ---------------------------------------------------------------------------

def test_a_code_restores_the_account_and_drops_the_sessions(tmp_path):
    with _server(tmp_path) as base:
        session, body = _register(base, "reprise@exemple.test")
        code = body["recovery_codes"][0]
        assert session.get(f"{base}/api/auth/me", timeout=30).status_code == 200

        reprise = requests.post(f"{base}/api/auth/recover", timeout=30, json={
            "email": "reprise@exemple.test", "code": code, "password": NEW})
        assert reprise.status_code == 204, reprise.text

        # The old password is worth nothing any more…
        assert requests.post(f"{base}/api/auth/login", timeout=30, json={
            "email": "reprise@exemple.test", "password": OLD}).status_code == 401
        # …the new one opens…
        assert requests.post(f"{base}/api/auth/login", timeout=30, json={
            "email": "reprise@exemple.test", "password": NEW}).status_code == 200
        # …and the session from BEFORE is dead. Without this, resetting would
        # be useless in the only case that counts: someone already got in.
        assert session.get(f"{base}/api/auth/me", timeout=30).status_code == 401


def test_a_code_works_only_once(tmp_path):
    with _server(tmp_path) as base:
        _, body = _register(base, "unefois@exemple.test")
        code = body["recovery_codes"][0]
        for _ in range(1):
            assert requests.post(f"{base}/api/auth/recover", timeout=30, json={
                "email": "unefois@exemple.test", "code": code,
                "password": NEW}).status_code == 204
        replayed = requests.post(f"{base}/api/auth/recover", timeout=30, json={
            "email": "unefois@exemple.test", "code": code,
            "password": "Encore-Un-Autre-2026"})
        assert replayed.status_code == 401
        # The password set by the FIRST use still holds.
        assert requests.post(f"{base}/api/auth/login", timeout=30, json={
            "email": "unefois@exemple.test", "password": NEW}).status_code == 200


def test_another_accounts_code_does_not_work(tmp_path):
    """The single-account test trap: without the second, "does this code work?"
    would pass even if anyone's code opened any account."""
    with _server(tmp_path) as base:
        _, first = _register(base, "alice@exemple.test")
        _register(base, "bob@exemple.test")
        vole = requests.post(f"{base}/api/auth/recover", timeout=30, json={
            "email": "bob@exemple.test", "code": first["recovery_codes"][0],
            "password": NEW})
        assert vole.status_code == 401
        assert requests.post(f"{base}/api/auth/login", timeout=30, json={
            "email": "bob@exemple.test", "password": OLD}).status_code == 200


def test_an_invented_code_is_refused(tmp_path):
    with _server(tmp_path) as base:
        _register(base, "invente@exemple.test")
        assert requests.post(f"{base}/api/auth/recover", timeout=30, json={
            "email": "invente@exemple.test", "code": "pas-un-vrai-code",
            "password": NEW}).status_code == 401


def test_the_refusal_does_not_distinguish_causes(tmp_path):
    """Telling "unknown address" from "wrong code" would teach an attacker which
    of the two they already hold."""
    with _server(tmp_path) as base:
        _, body = _register(base, "muet@exemple.test")
        responses = [
            requests.post(f"{base}/api/auth/recover", timeout=30, json={
                "email": "personne@exemple.test", "code": body["recovery_codes"][0],
                "password": NEW}),
            requests.post(f"{base}/api/auth/recover", timeout=30, json={
                "email": "muet@exemple.test", "code": "faux", "password": NEW}),
        ]
        assert {r.status_code for r in responses} == {401}
        assert len({r.json()["detail"] for r in responses}) == 1


def test_recovery_is_rate_limited(tmp_path):
    """Eight live codes per account make eight chances per try: without a cap,
    the only protection would be the attacker's patience."""
    with _server(tmp_path) as base:
        _register(base, "borne@exemple.test")
        codes_received = [
            requests.post(f"{base}/api/auth/recover", timeout=30, json={
                "email": "borne@exemple.test", "code": f"essai-{number}",
                "password": NEW}).status_code
            for number in range(8)
        ]
        assert 429 in codes_received, f"no ceiling reached: {codes_received}"


# ---------------------------------------------------------------------------
# Regenerating
# ---------------------------------------------------------------------------

def test_a_new_series_invalidates_the_old_one(tmp_path):
    """One often regenerates because one fears a leak. Accumulating series would
    keep alive exactly what one wants to get rid of."""
    with _server(tmp_path) as base:
        session, body = _register(base, "renouvelle@exemple.test")
        old = body["recovery_codes"]

        new = session.post(f"{base}/api/auth/recovery-codes", timeout=30,
                             json={"password": OLD})
        assert new.status_code == 201
        new = new.json()["recovery_codes"]
        assert len(new) == 8
        assert not set(old) & set(new)
        assert session.get(f"{base}/api/auth/recovery-codes",
                           timeout=30).json() == {"remaining": 8}

        assert requests.post(f"{base}/api/auth/recover", timeout=30, json={
            "email": "renouvelle@exemple.test", "code": old[0],
            "password": NEW}).status_code == 401
        assert requests.post(f"{base}/api/auth/recover", timeout=30, json={
            "email": "renouvelle@exemple.test", "code": new[0],
            "password": NEW}).status_code == 204


def test_regenerating_requires_a_session(tmp_path):
    with _server(tmp_path) as base:
        _register(base, "anonyme@exemple.test")
        assert requests.post(f"{base}/api/auth/recovery-codes",
                             timeout=30).status_code == 401
        assert requests.get(f"{base}/api/auth/recovery-codes",
                            timeout=30).status_code == 401


def test_deleting_the_account_takes_its_codes(tmp_path):
    """Orphan codes would be keys to an account that no longer exists."""
    with _server(tmp_path) as base:
        session, _ = _register(base, "efface@exemple.test")
        assert session.request("DELETE", f"{base}/api/auth/account", timeout=30,
                               json={"password": OLD}).status_code == 204

    store = IdentityStore(_space(tmp_path))
    with sqlite_db(store.path) as db:
        assert db.execute("SELECT COUNT(*) FROM recovery_codes").fetchone()[0] == 0


def test_earlier_accounts_are_counted_not_converted(tmp_path):
    """The additive migration catches up a table, never its content (point 89).

    Making codes at startup for existing accounts would be worse: they would have
    to be shown to them, and nobody would read them. They are NAMED.
    """
    store = IdentityStore(tmp_path)
    store.register("ancien@exemple.test", OLD)
    assert store.accounts_without_codes() == 1

    store.create_recovery_codes(
        store.authenticate("ancien@exemple.test", OLD)["id"])
    assert store.accounts_without_codes() == 0
