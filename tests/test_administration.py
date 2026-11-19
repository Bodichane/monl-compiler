"""`monl-platform admin` — the operating gestures, tested on a real service.

Every intervention on an account went through `sqlite3` by hand, with the
server stopped: bearable at ten accounts, not at a hundred, and each gesture
risked a mistyped query, with no trace of who made it.

**These tests check the EFFECT, never the display.** A command printing "key
revoked" without the key ceasing to work would be worse than absent: people
would believe it done. Every writing gesture is therefore replayed against a
real server, or reread in the database.

The rejected path deserves to be known: a web panel would have needed its own
authentication, a privilege column in `users`, and would have become the
target whose single flaw gives all accounts. Whoever owns the shell already
owns the database — the command line adds no attack surface.
"""

import json
import os
import subprocess
import sys
import time

import pytest
import requests

from monl_platform.hosting import SiteManager
from monl_platform.identity import IdentityStore
from monl_platform.paths import project_directory
from monl_platform.store import PlatformStore
from tests.support.server import uvicorn_server
from tests.support.sqlite import sqlite_db

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PASSWORD = "MotDePasse-Administration-2026"


def _environment(**extra):
    env = os.environ.copy()
    env["PYTHONPATH"] = os.path.join(RACINE, "src")
    env.update(extra)
    return env


def _server(folder, **extra):
    return uvicorn_server(str(folder), env=_environment(**extra),
                          module="monl_platform.app:app", ready_path="/health")


def _space(tmp_path):
    candidate = tmp_path / "platform-projects"
    return candidate if candidate.exists() else tmp_path


def admin(tmp_path, *arguments):
    """Runs the command the way the operator runs it, and returns the process."""
    return subprocess.run(
        [sys.executable, "-m", "monl_platform", "admin", *arguments,
         "--workspace", str(_space(tmp_path))],
        capture_output=True, text=True, env=_environment(), cwd=RACINE, timeout=120)


def _register(base, address):
    session = requests.Session()
    response = session.post(f"{base}/api/auth/register", timeout=30,
                           json={"email": address, "password": PASSWORD})
    assert response.status_code == 201, response.text
    return session, response.json()


# ---------------------------------------------------------------------------
# Lectures
# ---------------------------------------------------------------------------

def test_the_list_shows_accounts_and_what_they_carry(tmp_path):
    with _server(tmp_path) as base:
        session, _ = _register(base, "alice@exemple.test")
        _register(base, "bob@exemple.test")
        assert session.post(f"{base}/api/keys", json={"name": "portable"},
                            timeout=30).status_code == 201

    rendered = admin(tmp_path, "comptes")
    assert rendered.returncode == 0, rendered.stderr
    assert "alice@exemple.test" in rendered.stdout
    assert "bob@exemple.test" in rendered.stdout
    line_alice = next(line for line in rendered.stdout.splitlines()
                       if line.startswith("alice@"))
    assert line_alice.split()[-3:] == ["0", "1", "8"], line_alice


def test_an_account_detail_names_its_projects_and_keys(tmp_path):
    with _server(tmp_path) as base:
        session, _ = _register(base, "detail@exemple.test")
        key = session.post(f"{base}/api/keys", json={"name": "poste-fixe"}, timeout=30)
        identifier_key = key.json()["id"]
        spec = requests.get(f"{base}/api/examples/vitrine", timeout=30).json()["spec"]
        project = session.post(f"{base}/api/compile", json={"spec": spec}, timeout=180)
        assert project.status_code == 201, project.text

    rendered = admin(tmp_path, "compte", "detail@exemple.test")
    assert rendered.returncode == 0, rendered.stderr
    assert project.json()["id"] in rendered.stdout
    assert identifier_key in rendered.stdout
    assert "poste-fixe" in rendered.stdout
    assert "Recovery codes left: 8" in rendered.stdout


def test_the_address_is_normalized_as_at_registration(tmp_path):
    """Without it, the operator types the address as it was dictated to them and
    finds nothing, while the account exists."""
    with _server(tmp_path) as base:
        _register(base, "casse@exemple.test")
    rendered = admin(tmp_path, "compte", "  CASSE@Exemple.TEST  ")
    assert rendered.returncode == 0, rendered.stderr
    assert "casse@exemple.test" in rendered.stdout


def test_an_unknown_account_fails_outright(tmp_path):
    IdentityStore(tmp_path)
    rendered = admin(tmp_path, "compte", "personne@exemple.test")
    assert rendered.returncode == 1
    assert "No account for" in rendered.stderr


# ---------------------------------------------------------------------------
# Writes — the effect, not the display
# ---------------------------------------------------------------------------

def test_the_new_codes_really_open_the_account(tmp_path):
    """The whole help-desk gesture: someone lost their password AND their codes,
    the operator dictates new ones, and they take back control.

    Checking that the command prints eight codes would prove nothing: what counts
    is that one of these codes, presented on the wire, really resets the
    password.
    """
    with _server(tmp_path) as base:
        _, body = _register(base, "bloque@exemple.test")
        old = body["recovery_codes"]

        rendered = admin(tmp_path, "codes", "bloque@exemple.test")
        assert rendered.returncode == 0, rendered.stderr
        new = [line.strip() for line in rendered.stdout.splitlines()
                    if line.startswith("  ") and line.strip()]
        assert len(new) == 8
        assert not set(old) & set(new)

        # The old series is dead…
        assert requests.post(f"{base}/api/auth/recover", timeout=30, json={
            "email": "bloque@exemple.test", "code": old[0],
            "password": "Repris-Par-Ancien-2026"}).status_code == 401
        # …the new one opens.
        assert requests.post(f"{base}/api/auth/recover", timeout=30, json={
            "email": "bloque@exemple.test", "code": new[0],
            "password": "Repris-Par-Nouveau-2026"}).status_code == 204
        assert requests.post(f"{base}/api/auth/login", timeout=30, json={
            "email": "bloque@exemple.test",
            "password": "Repris-Par-Nouveau-2026"}).status_code == 200


def test_a_revoked_key_stops_working_on_the_wire(tmp_path):
    with _server(tmp_path) as base:
        session, _ = _register(base, "cle@exemple.test")
        key = session.post(f"{base}/api/keys", json={"name": "à révoquer"},
                           timeout=30).json()
        call = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
        header = {"Authorization": f"Bearer {key['key']}"}
        assert requests.post(f"{base}/mcp", json=call, headers=header,
                             timeout=30).status_code == 200

        rendered = admin(tmp_path, "revoquer-cle", key["id"])
        assert rendered.returncode == 0, rendered.stderr

        refusal = requests.post(f"{base}/mcp", json=call, headers=header, timeout=30)
        assert refusal.status_code in (401, 403), refusal.text

    # Twice: it is no longer active, the command says so without lying.
    encore = admin(tmp_path, "revoquer-cle", key["id"])
    assert encore.returncode == 1
    assert "No active key" in encore.stderr


def test_extend_pushes_deadline_from_now(tmp_path):
    """"Keep it thirty more days" is said afterwards, often on an ALREADY expired
    project: starting from the old date would extend nothing."""
    with _server(tmp_path) as base:
        session, _ = _register(base, "prolonge@exemple.test")
        spec = requests.get(f"{base}/api/examples/vitrine", timeout=30).json()["spec"]
        project = session.post(f"{base}/api/compile", json={"spec": spec},
                              timeout=180).json()["id"]

    site_store = IdentityStore(_space(tmp_path))
    with sqlite_db(site_store.path) as db:
        db.execute("UPDATE projects SET expires_at = ?", (int(time.time()) - 100_000,))

    assert admin(tmp_path, "prolonger", project, "--jours", "30").returncode == 0
    with sqlite_db(site_store.path) as db:
        deadline = db.execute("SELECT expires_at FROM projects").fetchone()[0]
    assert deadline > int(time.time()) + 29 * 24 * 3600


def test_extending_without_limit_removes_the_deadline(tmp_path):
    with _server(tmp_path) as base:
        session, _ = _register(base, "toujours@exemple.test")
        spec = requests.get(f"{base}/api/examples/vitrine", timeout=30).json()["spec"]
        project = session.post(f"{base}/api/compile", json={"spec": spec},
                              timeout=180).json()["id"]

    assert admin(tmp_path, "prolonger", project, "--jamais").returncode == 0
    site_store = IdentityStore(_space(tmp_path))
    with sqlite_db(site_store.path) as db:
        assert db.execute("SELECT expires_at FROM projects").fetchone()[0] is None


def test_expire_lets_the_purge_clean_up(tmp_path):
    """Deleting from the command would double the deletion path, and two paths
    end up diverging — the least used one being the one that breaks. The command
    marks expired, the purge cleans up."""
    with _server(tmp_path, MONL_PURGE_INTERVAL_SECONDS="1") as base:
        session, _ = _register(base, "expire@exemple.test")
        spec = requests.get(f"{base}/api/examples/vitrine", timeout=30).json()["spec"]
        project = session.post(f"{base}/api/compile", json={"spec": spec},
                              timeout=180).json()["id"]

        assert admin(tmp_path, "expirer", project).returncode == 0

        site_store = IdentityStore(_space(tmp_path))
        for _ in range(40):
            with sqlite_db(site_store.path) as db:
                if db.execute("SELECT COUNT(*) FROM projects").fetchone()[0] == 0:
                    break
            time.sleep(0.25)
        with sqlite_db(site_store.path) as db:
            assert db.execute("SELECT COUNT(*) FROM projects").fetchone()[0] == 0


def test_deleting_without_confirm_touches_nothing(tmp_path):
    """The witness. Without it, a command that ALWAYS deleted would pass the next
    test."""
    with _server(tmp_path) as base:
        _register(base, "prudent@exemple.test")

    rendered = admin(tmp_path, "supprimer-compte", "prudent@exemple.test")
    assert rendered.returncode == 1
    assert "Nothing was done" in rendered.stdout
    assert "prudent@exemple.test" in admin(tmp_path, "comptes").stdout


def test_deleting_with_confirm_erases_down_to_disk(tmp_path):
    with _server(tmp_path) as base:
        session, _ = _register(base, "partant@exemple.test")
        spec = requests.get(f"{base}/api/examples/vitrine", timeout=30).json()["spec"]
        project = session.post(f"{base}/api/compile", json={"spec": spec},
                              timeout=180).json()["id"]
        folder = next(path for path in tmp_path.rglob(project) if path.is_dir())
        assert folder.is_dir()

    rendered = admin(tmp_path, "supprimer-compte", "partant@exemple.test", "--confirmer")
    assert rendered.returncode == 0, rendered.stderr
    assert not folder.exists(), "the compiled folder survives the deletion"

    site_store = IdentityStore(_space(tmp_path))
    with sqlite_db(site_store.path) as db:
        for table in ("users", "projects", "api_keys", "recovery_codes"):
            assert db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0, table


# ---------------------------------------------------------------------------
# La trace
# ---------------------------------------------------------------------------

def test_every_writing_gesture_leaves_a_trace(tmp_path):
    """"Who deleted this account?" is the question asked the day things go
    wrong. Without a log, it has no answer."""
    with _server(tmp_path) as base:
        session, _ = _register(base, "trace@exemple.test")
        key = session.post(f"{base}/api/keys", json={"name": "tracee"},
                           timeout=30).json()["id"]

    gestures = {
        "cle_revoquee_par_exploitant": ("revoquer-cle", key),
        "codes_regeneres_par_exploitant": ("codes", "trace@exemple.test"),
        "compte_supprime_par_exploitant": ("supprimer-compte", "trace@exemple.test",
                                           "--confirmer"),
    }
    for event, arguments in gestures.items():
        rendered = admin(tmp_path, *arguments)
        assert rendered.returncode == 0, rendered.stderr
        assert event in rendered.stderr, f"{event} missing from the log"


def test_the_administration_log_gives_no_bare_identifier(tmp_path):
    """Same rule as for the server: identifiers are truncated to eight characters
    — enough to cross-check, too short to look like a secret."""
    with _server(tmp_path) as base:
        _, body = _register(base, "nu@exemple.test")

    site_store = IdentityStore(_space(tmp_path))
    with sqlite_db(site_store.path) as db:
        identifier = db.execute("SELECT id FROM users").fetchone()[0]

    rendered = admin(tmp_path, "codes", "nu@exemple.test")
    assert identifier not in rendered.stderr, "the full identifier is logged"
    assert identifier[:8] in rendered.stderr
    # And no recovery code must end up in the log.
    for code in body["recovery_codes"]:
        assert code not in rendered.stderr


def test_administration_opens_no_route(tmp_path):
    """The decision this module carries: the HTTP surface does NOT move.

    A web panel would have become the target whose single flaw gives all
    accounts. This test fails if someone one day adds an administration route
    meaning well.
    """
    with _server(tmp_path) as base:
        schema = requests.get(f"{base}/openapi.json", timeout=30).json()
        paths = list(schema["paths"])
    assert not [path for path in paths if "admin" in path.lower()], paths
    assert "administration" not in json.dumps(schema).lower()


def test_the_cli_actions_are_also_checked_in_process(tmp_path, capsys):
    """The subprocesses prove the complete gesture; this covers its decisions.

    A command printing the right text but wiring the wrong argument would
    otherwise stay invisible to coverage: here each action reads or modifies the
    same store, and the assertions are about the effect obtained.
    """
    from argparse import Namespace

    from monl_platform import administration
    from monl_platform.service import CompilationService

    site_store = IdentityStore(tmp_path)
    service = CompilationService(tmp_path)
    user = site_store.register("direct@exemple.test", PASSWORD)
    project_id = "projet-direct"
    site_store.add_project(user["id"], project_id, "Projet direct")
    key = site_store.create_api_key(user["id"], "poste")

    assert administration._date(None) == "—"
    assert administration._deadline(None) == "never"
    assert administration._accounts(site_store, service, Namespace()) == 0
    assert "direct@exemple.test" in capsys.readouterr().out

    administration._account(site_store, service, Namespace(email="direct@exemple.test"))
    detail = capsys.readouterr().out
    assert project_id in detail and key["id"] in detail
    administration._projects(site_store, service, Namespace(compte=None))
    assert project_id in capsys.readouterr().out

    administration._codes(site_store, service,
                          Namespace(email="direct@exemple.test"))
    codes = [line.strip() for line in capsys.readouterr().out.splitlines()
             if line.startswith("  ")]
    assert len(codes) == 8
    assert site_store.consume_recovery_code(
        user["email"], codes[0], "Nouveau-MotDePasse-2026")
    assert site_store.api_key_user(key["key"]) is None
    key = site_store.create_api_key(user["id"], "nouveau poste")

    assert administration._extend(
        site_store, service, Namespace(projet=project_id, jours=2, jamais=False)
    ) == 0
    assert administration._expire(
        site_store, service, Namespace(projet=project_id)
    ) == 0
    assert administration._revoke(
        site_store, service, Namespace(cle=key["id"])
    ) == 0
    assert administration._delete(
        site_store, service,
        Namespace(email="direct@exemple.test", confirmer=False)
    ) == 1
    capsys.readouterr()
    assert administration._delete(
        site_store, service,
        Namespace(email="direct@exemple.test", confirmer=True)
    ) == 0
    assert site_store.account_by_address("direct@exemple.test") is None


def test_the_cli_names_invalid_inputs_and_option_positions(tmp_path, capsys):
    from argparse import Namespace

    from monl_platform import administration

    site_store = IdentityStore(tmp_path)
    with pytest.raises(SystemExit) as error:
        administration._account_ou_exit(site_store, "absent@exemple.test")
    assert error.value.code == 1
    assert "No account for" in capsys.readouterr().err

    assert administration._extend(
        site_store, None, Namespace(projet="absent", jours=30, jamais=False)
    ) == 1
    assert administration._expire(
        site_store, None, Namespace(projet="absent")
    ) == 1
    assert administration._revoke(
        site_store, None, Namespace(cle="absent")
    ) == 1
    capsys.readouterr()

    # The parser accepts --workspace before AND after the sub-verb.
    assert administration.main(["--workspace", str(tmp_path), "comptes"]) == 0
    assert administration.main(["comptes", "--workspace", str(tmp_path)]) == 0
    assert "No accounts" in capsys.readouterr().out


def test_the_cli_reads_the_site_log_without_exposing_its_token(tmp_path):
    """A crash trace is readable from the shell, never served over HTTP."""
    identifier = "a" * 32
    secret = "monl_A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6"
    site_store = IdentityStore(tmp_path)
    store = PlatformStore(tmp_path)
    user = site_store.register("journal-site@exemple.test", PASSWORD)
    site_store.add_project(user["id"], identifier, "Journal site")
    store.create_project(user["id"], identifier, "journal-site")
    project = store.get_project(identifier)
    folder = project_directory(tmp_path, user["id"], identifier)
    (folder / "app.py").write_text("# backend présent\n", encoding="utf-8")
    (folder / "serve.py").write_text(
        f"""import sys
from fastapi import FastAPI

app = FastAPI()

@app.get('/crash')
def crash():
    print('SITE_ADMIN_CRASH https://client.example/reset?token={secret}',
          file=sys.stderr, flush=True)
    raise RuntimeError('crash relisible par exploitant')
""",
        encoding="utf-8",
    )
    sites = SiteManager(store, tmp_path, "localhost", startup_timeout=25)
    try:
        running = sites.start_project(project)
        assert requests.get(f"http://127.0.0.1:{running.port}/crash", timeout=10).status_code == 500
    finally:
        sites.stop_all()

    rendered = admin(tmp_path, "journal", identifier)
    assert rendered.returncode == 0, rendered.stderr
    assert "SITE_ADMIN_CRASH" in rendered.stdout
    assert "RuntimeError" in rendered.stdout
    assert "crash relisible par exploitant" in rendered.stdout
    assert secret not in rendered.stdout
    assert "token=[masked]" in rendered.stdout
    assert "journal_site_lu_par_exploitant" in rendered.stderr


def test_the_english_names_do_the_same_gestures(tmp_path):
    """The English verb and option names, measured by their EFFECT.

    The French names stay accepted as aliases (the tests above go through
    them); this one proves the new names are not mere help text: each verb
    changes the database exactly as its French twin does."""
    address = "anglais@exemple.test"
    with _server(tmp_path) as base:
        session, _ = _register(base, address)
        spec = requests.get(f"{base}/api/examples/vitrine", timeout=30).json()["spec"]
        project = session.post(f"{base}/api/compile", json={"spec": spec},
                              timeout=180).json()["id"]
    site_store = IdentityStore(_space(tmp_path))

    def deadline():
        with sqlite_db(site_store.path) as db:
            return db.execute("SELECT expires_at FROM projects").fetchone()[0]

    assert address in admin(tmp_path, "accounts").stdout
    assert project in admin(tmp_path, "account", address).stdout
    assert project in admin(tmp_path, "projects", "--account", address).stdout
    assert admin(tmp_path, "extend", project, "--never").returncode == 0
    assert deadline() is None
    assert admin(tmp_path, "extend", project, "--days", "30").returncode == 0
    assert deadline() > int(time.time()) + 29 * 24 * 3600
    assert admin(tmp_path, "expire", project).returncode == 0
    assert deadline() <= int(time.time())
    assert admin(tmp_path, "delete-account", address).returncode == 1
    assert address in admin(tmp_path, "accounts").stdout
    rendered = admin(tmp_path, "delete-account", address, "--confirm")
    assert rendered.returncode == 0, rendered.stderr
    assert address not in admin(tmp_path, "accounts").stdout


def test_backup_and_keep_like_backup_and_keep(tmp_path, capsys):
    """`backup --keep` rotates like `sauvegarde --garder`, which stays accepted."""
    from monl_platform.__main__ import main as platform

    space = tmp_path / "espace"
    IdentityStore(space)
    folder = tmp_path / "copies"
    for i, verb, option in ((1, "backup", "--keep"), (2, "sauvegarde", "--garder"),
                             (3, "backup", "--keep")):
        target = folder / f"base-{i}.sqlite3"
        assert platform([verb, str(target), "--workspace", str(space),
                           option, "2"]) == 0
        os.utime(target, (i, i))
    assert sorted(f.name for f in folder.iterdir()) == ["base-2.sqlite3", "base-3.sqlite3"]
    assert "Backup removed" in capsys.readouterr().out
