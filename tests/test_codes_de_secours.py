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
ANCIEN = "MotDePasse-Ancien-2026"
NOUVEAU = "MotDePasse-Nouveau-2026"


def _server(dossier):
    env = os.environ.copy()
    env["PYTHONPATH"] = os.path.join(RACINE, "src")
    return uvicorn_server(str(dossier), env=env,
                          module="monl_platform.app:app", ready_path="/health")


def _inscrire(base, adresse, mot_de_passe=ANCIEN):
    session = requests.Session()
    reponse = session.post(f"{base}/api/auth/register", timeout=30,
                           json={"email": adresse, "password": mot_de_passe})
    assert reponse.status_code == 201, reponse.text
    return session, reponse.json()


def _espace(tmp_path):
    candidat = tmp_path / "platform-projects"
    return candidat if candidat.exists() else tmp_path


# ---------------------------------------------------------------------------
# What registration hands over
# ---------------------------------------------------------------------------

def test_registration_hands_over_eight_codes_only_once(tmp_path):
    with _server(tmp_path) as base:
        session, corps = _inscrire(base, "codes@exemple.test")
        codes = corps["recovery_codes"]
        assert len(codes) == 8
        assert len(set(codes)) == 8, "two identical codes halve the chances"
        assert all(len(c) >= 16 for c in codes), "un code court se devine"

        # They come out NOWHERE else — like an API key.
        etat = session.get(f"{base}/api/auth/recovery-codes", timeout=30).json()
        assert etat == {"remaining": 8}
        me = session.get(f"{base}/api/auth/me", timeout=30).text
        for code in codes:
            assert code not in me, "a code comes out of a read route"


def test_codes_are_never_stored_in_clear(tmp_path):
    """The privacy policy's promise, checked IN THE DATABASE.

    A code readable in the database would cancel the whole point: whoever reads
    the file gets into any account without knowing any password.
    """
    with _server(tmp_path) as base:
        _, corps = _inscrire(base, "clair@exemple.test")
        codes = corps["recovery_codes"]

    magasin = IdentityStore(_espace(tmp_path))
    with sqlite_db(magasin.path) as db:
        stockes = [r[0] for r in db.execute("SELECT code_hash FROM recovery_codes")]
    assert len(stockes) == 8
    for code in codes:
        assert code not in stockes
        assert not any(code in valeur for valeur in stockes)


# ---------------------------------------------------------------------------
# Taking back control
# ---------------------------------------------------------------------------

def test_a_code_restores_the_account_and_drops_the_sessions(tmp_path):
    with _server(tmp_path) as base:
        session, corps = _inscrire(base, "reprise@exemple.test")
        code = corps["recovery_codes"][0]
        assert session.get(f"{base}/api/auth/me", timeout=30).status_code == 200

        reprise = requests.post(f"{base}/api/auth/recover", timeout=30, json={
            "email": "reprise@exemple.test", "code": code, "password": NOUVEAU})
        assert reprise.status_code == 204, reprise.text

        # The old password is worth nothing any more…
        assert requests.post(f"{base}/api/auth/login", timeout=30, json={
            "email": "reprise@exemple.test", "password": ANCIEN}).status_code == 401
        # …the new one opens…
        assert requests.post(f"{base}/api/auth/login", timeout=30, json={
            "email": "reprise@exemple.test", "password": NOUVEAU}).status_code == 200
        # …and the session from BEFORE is dead. Without this, resetting would
        # be useless in the only case that counts: someone already got in.
        assert session.get(f"{base}/api/auth/me", timeout=30).status_code == 401


def test_a_code_works_only_once(tmp_path):
    with _server(tmp_path) as base:
        _, corps = _inscrire(base, "unefois@exemple.test")
        code = corps["recovery_codes"][0]
        for _ in range(1):
            assert requests.post(f"{base}/api/auth/recover", timeout=30, json={
                "email": "unefois@exemple.test", "code": code,
                "password": NOUVEAU}).status_code == 204
        rejoue = requests.post(f"{base}/api/auth/recover", timeout=30, json={
            "email": "unefois@exemple.test", "code": code,
            "password": "Encore-Un-Autre-2026"})
        assert rejoue.status_code == 401
        # The password set by the FIRST use still holds.
        assert requests.post(f"{base}/api/auth/login", timeout=30, json={
            "email": "unefois@exemple.test", "password": NOUVEAU}).status_code == 200


def test_another_accounts_code_does_not_work(tmp_path):
    """The single-account test trap: without the second, "does this code work?"
    would pass even if anyone's code opened any account."""
    with _server(tmp_path) as base:
        _, premier = _inscrire(base, "alice@exemple.test")
        _inscrire(base, "bob@exemple.test")
        vole = requests.post(f"{base}/api/auth/recover", timeout=30, json={
            "email": "bob@exemple.test", "code": premier["recovery_codes"][0],
            "password": NOUVEAU})
        assert vole.status_code == 401
        assert requests.post(f"{base}/api/auth/login", timeout=30, json={
            "email": "bob@exemple.test", "password": ANCIEN}).status_code == 200


def test_an_invented_code_is_refused(tmp_path):
    with _server(tmp_path) as base:
        _inscrire(base, "invente@exemple.test")
        assert requests.post(f"{base}/api/auth/recover", timeout=30, json={
            "email": "invente@exemple.test", "code": "pas-un-vrai-code",
            "password": NOUVEAU}).status_code == 401


def test_the_refusal_does_not_distinguish_causes(tmp_path):
    """Telling "unknown address" from "wrong code" would teach an attacker which
    of the two they already hold."""
    with _server(tmp_path) as base:
        _, corps = _inscrire(base, "muet@exemple.test")
        reponses = [
            requests.post(f"{base}/api/auth/recover", timeout=30, json={
                "email": "personne@exemple.test", "code": corps["recovery_codes"][0],
                "password": NOUVEAU}),
            requests.post(f"{base}/api/auth/recover", timeout=30, json={
                "email": "muet@exemple.test", "code": "faux", "password": NOUVEAU}),
        ]
        assert {r.status_code for r in reponses} == {401}
        assert len({r.json()["detail"] for r in reponses}) == 1


def test_recovery_is_rate_limited(tmp_path):
    """Eight live codes per account make eight chances per try: without a cap,
    the only protection would be the attacker's patience."""
    with _server(tmp_path) as base:
        _inscrire(base, "borne@exemple.test")
        codes_recus = [
            requests.post(f"{base}/api/auth/recover", timeout=30, json={
                "email": "borne@exemple.test", "code": f"essai-{numero}",
                "password": NOUVEAU}).status_code
            for numero in range(8)
        ]
        assert 429 in codes_recus, f"no ceiling reached: {codes_recus}"


# ---------------------------------------------------------------------------
# Regenerating
# ---------------------------------------------------------------------------

def test_a_new_series_invalidates_the_old_one(tmp_path):
    """One often regenerates because one fears a leak. Accumulating series would
    keep alive exactly what one wants to get rid of."""
    with _server(tmp_path) as base:
        session, corps = _inscrire(base, "renouvelle@exemple.test")
        anciens = corps["recovery_codes"]

        neufs = session.post(f"{base}/api/auth/recovery-codes", timeout=30,
                             json={"password": ANCIEN})
        assert neufs.status_code == 201
        neufs = neufs.json()["recovery_codes"]
        assert len(neufs) == 8
        assert not set(anciens) & set(neufs)
        assert session.get(f"{base}/api/auth/recovery-codes",
                           timeout=30).json() == {"remaining": 8}

        assert requests.post(f"{base}/api/auth/recover", timeout=30, json={
            "email": "renouvelle@exemple.test", "code": anciens[0],
            "password": NOUVEAU}).status_code == 401
        assert requests.post(f"{base}/api/auth/recover", timeout=30, json={
            "email": "renouvelle@exemple.test", "code": neufs[0],
            "password": NOUVEAU}).status_code == 204


def test_regenerating_requires_a_session(tmp_path):
    with _server(tmp_path) as base:
        _inscrire(base, "anonyme@exemple.test")
        assert requests.post(f"{base}/api/auth/recovery-codes",
                             timeout=30).status_code == 401
        assert requests.get(f"{base}/api/auth/recovery-codes",
                            timeout=30).status_code == 401


def test_deleting_the_account_takes_its_codes(tmp_path):
    """Orphan codes would be keys to an account that no longer exists."""
    with _server(tmp_path) as base:
        session, _ = _inscrire(base, "efface@exemple.test")
        assert session.request("DELETE", f"{base}/api/auth/account", timeout=30,
                               json={"password": ANCIEN}).status_code == 204

    magasin = IdentityStore(_espace(tmp_path))
    with sqlite_db(magasin.path) as db:
        assert db.execute("SELECT COUNT(*) FROM recovery_codes").fetchone()[0] == 0


def test_earlier_accounts_are_counted_not_converted(tmp_path):
    """The additive migration catches up a table, never its content (point 89).

    Making codes at startup for existing accounts would be worse: they would have
    to be shown to them, and nobody would read them. They are NAMED.
    """
    magasin = IdentityStore(tmp_path)
    magasin.register("ancien@exemple.test", ANCIEN)
    assert magasin.comptes_sans_codes() == 1

    magasin.create_recovery_codes(
        magasin.authenticate("ancien@exemple.test", ANCIEN)["id"])
    assert magasin.comptes_sans_codes() == 0
