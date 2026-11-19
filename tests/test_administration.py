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
MOT_DE_PASSE = "MotDePasse-Administration-2026"


def _environnement(**extra):
    env = os.environ.copy()
    env["PYTHONPATH"] = os.path.join(RACINE, "src")
    env.update(extra)
    return env


def _server(dossier, **extra):
    return uvicorn_server(str(dossier), env=_environnement(**extra),
                          module="monl_platform.app:app", ready_path="/health")


def _espace(tmp_path):
    candidat = tmp_path / "platform-projects"
    return candidat if candidat.exists() else tmp_path


def admin(tmp_path, *arguments):
    """Runs the command the way the operator runs it, and returns the process."""
    return subprocess.run(
        [sys.executable, "-m", "monl_platform", "admin", *arguments,
         "--workspace", str(_espace(tmp_path))],
        capture_output=True, text=True, env=_environnement(), cwd=RACINE, timeout=120)


def _inscrire(base, adresse):
    session = requests.Session()
    reponse = session.post(f"{base}/api/auth/register", timeout=30,
                           json={"email": adresse, "password": MOT_DE_PASSE})
    assert reponse.status_code == 201, reponse.text
    return session, reponse.json()


# ---------------------------------------------------------------------------
# Lectures
# ---------------------------------------------------------------------------

def test_the_list_shows_accounts_and_what_they_carry(tmp_path):
    with _server(tmp_path) as base:
        session, _ = _inscrire(base, "alice@exemple.test")
        _inscrire(base, "bob@exemple.test")
        assert session.post(f"{base}/api/keys", json={"name": "portable"},
                            timeout=30).status_code == 201

    rendu = admin(tmp_path, "comptes")
    assert rendu.returncode == 0, rendu.stderr
    assert "alice@exemple.test" in rendu.stdout
    assert "bob@exemple.test" in rendu.stdout
    ligne_alice = next(ligne for ligne in rendu.stdout.splitlines()
                       if ligne.startswith("alice@"))
    assert ligne_alice.split()[-3:] == ["0", "1", "8"], ligne_alice


def test_an_account_detail_names_its_projects_and_keys(tmp_path):
    with _server(tmp_path) as base:
        session, _ = _inscrire(base, "detail@exemple.test")
        cle = session.post(f"{base}/api/keys", json={"name": "poste-fixe"}, timeout=30)
        identifiant_cle = cle.json()["id"]
        spec = requests.get(f"{base}/api/examples/vitrine", timeout=30).json()["spec"]
        projet = session.post(f"{base}/api/compile", json={"spec": spec}, timeout=180)
        assert projet.status_code == 201, projet.text

    rendu = admin(tmp_path, "compte", "detail@exemple.test")
    assert rendu.returncode == 0, rendu.stderr
    assert projet.json()["id"] in rendu.stdout
    assert identifiant_cle in rendu.stdout
    assert "poste-fixe" in rendu.stdout
    assert "Recovery codes left: 8" in rendu.stdout


def test_the_address_is_normalized_as_at_registration(tmp_path):
    """Without it, the operator types the address as it was dictated to them and
    finds nothing, while the account exists."""
    with _server(tmp_path) as base:
        _inscrire(base, "casse@exemple.test")
    rendu = admin(tmp_path, "compte", "  CASSE@Exemple.TEST  ")
    assert rendu.returncode == 0, rendu.stderr
    assert "casse@exemple.test" in rendu.stdout


def test_an_unknown_account_fails_outright(tmp_path):
    IdentityStore(tmp_path)
    rendu = admin(tmp_path, "compte", "personne@exemple.test")
    assert rendu.returncode == 1
    assert "No account for" in rendu.stderr


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
        _, corps = _inscrire(base, "bloque@exemple.test")
        anciens = corps["recovery_codes"]

        rendu = admin(tmp_path, "codes", "bloque@exemple.test")
        assert rendu.returncode == 0, rendu.stderr
        nouveaux = [ligne.strip() for ligne in rendu.stdout.splitlines()
                    if ligne.startswith("  ") and ligne.strip()]
        assert len(nouveaux) == 8
        assert not set(anciens) & set(nouveaux)

        # The old series is dead…
        assert requests.post(f"{base}/api/auth/recover", timeout=30, json={
            "email": "bloque@exemple.test", "code": anciens[0],
            "password": "Repris-Par-Ancien-2026"}).status_code == 401
        # …the new one opens.
        assert requests.post(f"{base}/api/auth/recover", timeout=30, json={
            "email": "bloque@exemple.test", "code": nouveaux[0],
            "password": "Repris-Par-Nouveau-2026"}).status_code == 204
        assert requests.post(f"{base}/api/auth/login", timeout=30, json={
            "email": "bloque@exemple.test",
            "password": "Repris-Par-Nouveau-2026"}).status_code == 200


def test_a_revoked_key_stops_working_on_the_wire(tmp_path):
    with _server(tmp_path) as base:
        session, _ = _inscrire(base, "cle@exemple.test")
        cle = session.post(f"{base}/api/keys", json={"name": "à révoquer"},
                           timeout=30).json()
        appel = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
        entete = {"Authorization": f"Bearer {cle['key']}"}
        assert requests.post(f"{base}/mcp", json=appel, headers=entete,
                             timeout=30).status_code == 200

        rendu = admin(tmp_path, "revoquer-cle", cle["id"])
        assert rendu.returncode == 0, rendu.stderr

        refus = requests.post(f"{base}/mcp", json=appel, headers=entete, timeout=30)
        assert refus.status_code in (401, 403), refus.text

    # Twice: it is no longer active, the command says so without lying.
    encore = admin(tmp_path, "revoquer-cle", cle["id"])
    assert encore.returncode == 1
    assert "No active key" in encore.stderr


def test_prolonger_repousse_lecheance_depuis_maintenant(tmp_path):
    """"Keep it thirty more days" is said afterwards, often on an ALREADY expired
    project: starting from the old date would extend nothing."""
    with _server(tmp_path) as base:
        session, _ = _inscrire(base, "prolonge@exemple.test")
        spec = requests.get(f"{base}/api/examples/vitrine", timeout=30).json()["spec"]
        projet = session.post(f"{base}/api/compile", json={"spec": spec},
                              timeout=180).json()["id"]

    magasin = IdentityStore(_espace(tmp_path))
    with sqlite_db(magasin.path) as db:
        db.execute("UPDATE projects SET expires_at = ?", (int(time.time()) - 100_000,))

    assert admin(tmp_path, "prolonger", projet, "--jours", "30").returncode == 0
    with sqlite_db(magasin.path) as db:
        echeance = db.execute("SELECT expires_at FROM projects").fetchone()[0]
    assert echeance > int(time.time()) + 29 * 24 * 3600


def test_extending_without_limit_removes_the_deadline(tmp_path):
    with _server(tmp_path) as base:
        session, _ = _inscrire(base, "toujours@exemple.test")
        spec = requests.get(f"{base}/api/examples/vitrine", timeout=30).json()["spec"]
        projet = session.post(f"{base}/api/compile", json={"spec": spec},
                              timeout=180).json()["id"]

    assert admin(tmp_path, "prolonger", projet, "--jamais").returncode == 0
    magasin = IdentityStore(_espace(tmp_path))
    with sqlite_db(magasin.path) as db:
        assert db.execute("SELECT expires_at FROM projects").fetchone()[0] is None


def test_expire_lets_the_purge_clean_up(tmp_path):
    """Deleting from the command would double the deletion path, and two paths
    end up diverging — the least used one being the one that breaks. The command
    marks expired, the purge cleans up."""
    with _server(tmp_path, MONL_PURGE_INTERVAL_SECONDS="1") as base:
        session, _ = _inscrire(base, "expire@exemple.test")
        spec = requests.get(f"{base}/api/examples/vitrine", timeout=30).json()["spec"]
        projet = session.post(f"{base}/api/compile", json={"spec": spec},
                              timeout=180).json()["id"]

        assert admin(tmp_path, "expirer", projet).returncode == 0

        magasin = IdentityStore(_espace(tmp_path))
        for _ in range(40):
            with sqlite_db(magasin.path) as db:
                if db.execute("SELECT COUNT(*) FROM projects").fetchone()[0] == 0:
                    break
            time.sleep(0.25)
        with sqlite_db(magasin.path) as db:
            assert db.execute("SELECT COUNT(*) FROM projects").fetchone()[0] == 0


def test_deleting_without_confirm_touches_nothing(tmp_path):
    """The witness. Without it, a command that ALWAYS deleted would pass the next
    test."""
    with _server(tmp_path) as base:
        _inscrire(base, "prudent@exemple.test")

    rendu = admin(tmp_path, "supprimer-compte", "prudent@exemple.test")
    assert rendu.returncode == 1
    assert "Nothing was done" in rendu.stdout
    assert "prudent@exemple.test" in admin(tmp_path, "comptes").stdout


def test_deleting_with_confirm_erases_down_to_disk(tmp_path):
    with _server(tmp_path) as base:
        session, _ = _inscrire(base, "partant@exemple.test")
        spec = requests.get(f"{base}/api/examples/vitrine", timeout=30).json()["spec"]
        projet = session.post(f"{base}/api/compile", json={"spec": spec},
                              timeout=180).json()["id"]
        dossier = next(chemin for chemin in tmp_path.rglob(projet) if chemin.is_dir())
        assert dossier.is_dir()

    rendu = admin(tmp_path, "supprimer-compte", "partant@exemple.test", "--confirmer")
    assert rendu.returncode == 0, rendu.stderr
    assert not dossier.exists(), "the compiled folder survives the deletion"

    magasin = IdentityStore(_espace(tmp_path))
    with sqlite_db(magasin.path) as db:
        for table in ("users", "projects", "api_keys", "recovery_codes"):
            assert db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0, table


# ---------------------------------------------------------------------------
# La trace
# ---------------------------------------------------------------------------

def test_every_writing_gesture_leaves_a_trace(tmp_path):
    """"Who deleted this account?" is the question asked the day things go
    wrong. Without a log, it has no answer."""
    with _server(tmp_path) as base:
        session, _ = _inscrire(base, "trace@exemple.test")
        cle = session.post(f"{base}/api/keys", json={"name": "tracee"},
                           timeout=30).json()["id"]

    gestes = {
        "cle_revoquee_par_exploitant": ("revoquer-cle", cle),
        "codes_regeneres_par_exploitant": ("codes", "trace@exemple.test"),
        "compte_supprime_par_exploitant": ("supprimer-compte", "trace@exemple.test",
                                           "--confirmer"),
    }
    for evenement, arguments in gestes.items():
        rendu = admin(tmp_path, *arguments)
        assert rendu.returncode == 0, rendu.stderr
        assert evenement in rendu.stderr, f"{evenement} missing from the log"


def test_the_administration_log_gives_no_bare_identifier(tmp_path):
    """Same rule as for the server: identifiers are truncated to eight characters
    — enough to cross-check, too short to look like a secret."""
    with _server(tmp_path) as base:
        _, corps = _inscrire(base, "nu@exemple.test")

    magasin = IdentityStore(_espace(tmp_path))
    with sqlite_db(magasin.path) as db:
        identifiant = db.execute("SELECT id FROM users").fetchone()[0]

    rendu = admin(tmp_path, "codes", "nu@exemple.test")
    assert identifiant not in rendu.stderr, "the full identifier is logged"
    assert identifiant[:8] in rendu.stderr
    # And no recovery code must end up in the log.
    for code in corps["recovery_codes"]:
        assert code not in rendu.stderr


def test_administration_opens_no_route(tmp_path):
    """The decision this module carries: the HTTP surface does NOT move.

    A web panel would have become the target whose single flaw gives all
    accounts. This test fails if someone one day adds an administration route
    meaning well.
    """
    with _server(tmp_path) as base:
        schema = requests.get(f"{base}/openapi.json", timeout=30).json()
        chemins = list(schema["paths"])
    assert not [chemin for chemin in chemins if "admin" in chemin.lower()], chemins
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

    magasin = IdentityStore(tmp_path)
    service = CompilationService(tmp_path)
    user = magasin.register("direct@exemple.test", MOT_DE_PASSE)
    project_id = "projet-direct"
    magasin.add_project(user["id"], project_id, "Projet direct")
    key = magasin.create_api_key(user["id"], "poste")

    assert administration._date(None) == "—"
    assert administration._echeance(None) == "never"
    assert administration._comptes(magasin, service, Namespace()) == 0
    assert "direct@exemple.test" in capsys.readouterr().out

    administration._compte(magasin, service, Namespace(email="direct@exemple.test"))
    detail = capsys.readouterr().out
    assert project_id in detail and key["id"] in detail
    administration._projets(magasin, service, Namespace(compte=None))
    assert project_id in capsys.readouterr().out

    administration._codes(magasin, service,
                          Namespace(email="direct@exemple.test"))
    codes = [line.strip() for line in capsys.readouterr().out.splitlines()
             if line.startswith("  ")]
    assert len(codes) == 8
    assert magasin.consume_recovery_code(
        user["email"], codes[0], "Nouveau-MotDePasse-2026")
    assert magasin.api_key_user(key["key"]) is None
    key = magasin.create_api_key(user["id"], "nouveau poste")

    assert administration._prolonger(
        magasin, service, Namespace(projet=project_id, jours=2, jamais=False)
    ) == 0
    assert administration._expirer(
        magasin, service, Namespace(projet=project_id)
    ) == 0
    assert administration._revoquer(
        magasin, service, Namespace(cle=key["id"])
    ) == 0
    assert administration._supprimer(
        magasin, service,
        Namespace(email="direct@exemple.test", confirmer=False)
    ) == 1
    capsys.readouterr()
    assert administration._supprimer(
        magasin, service,
        Namespace(email="direct@exemple.test", confirmer=True)
    ) == 0
    assert magasin.compte_par_adresse("direct@exemple.test") is None


def test_the_cli_names_invalid_inputs_and_option_positions(tmp_path, capsys):
    from argparse import Namespace

    from monl_platform import administration

    magasin = IdentityStore(tmp_path)
    with pytest.raises(SystemExit) as erreur:
        administration._compte_ou_sortir(magasin, "absent@exemple.test")
    assert erreur.value.code == 1
    assert "No account for" in capsys.readouterr().err

    assert administration._prolonger(
        magasin, None, Namespace(projet="absent", jours=30, jamais=False)
    ) == 1
    assert administration._expirer(
        magasin, None, Namespace(projet="absent")
    ) == 1
    assert administration._revoquer(
        magasin, None, Namespace(cle="absent")
    ) == 1
    capsys.readouterr()

    # The parser accepts --workspace before AND after the sub-verb.
    assert administration.main(["--workspace", str(tmp_path), "comptes"]) == 0
    assert administration.main(["comptes", "--workspace", str(tmp_path)]) == 0
    assert "No accounts" in capsys.readouterr().out


def test_the_cli_reads_the_site_log_without_exposing_its_token(tmp_path):
    """A crash trace is readable from the shell, never served over HTTP."""
    identifiant = "a" * 32
    secret = "monl_A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6"
    magasin = IdentityStore(tmp_path)
    store = PlatformStore(tmp_path)
    user = magasin.register("journal-site@exemple.test", MOT_DE_PASSE)
    magasin.add_project(user["id"], identifiant, "Journal site")
    store.create_project(user["id"], identifiant, "journal-site")
    projet = store.get_project(identifiant)
    dossier = project_directory(tmp_path, user["id"], identifiant)
    (dossier / "app.py").write_text("# backend présent\n", encoding="utf-8")
    (dossier / "serve.py").write_text(
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
        running = sites.start_project(projet)
        assert requests.get(f"http://127.0.0.1:{running.port}/crash", timeout=10).status_code == 500
    finally:
        sites.stop_all()

    rendu = admin(tmp_path, "journal", identifiant)
    assert rendu.returncode == 0, rendu.stderr
    assert "SITE_ADMIN_CRASH" in rendu.stdout
    assert "RuntimeError" in rendu.stdout
    assert "crash relisible par exploitant" in rendu.stdout
    assert secret not in rendu.stdout
    assert "token=[masked]" in rendu.stdout
    assert "journal_site_lu_par_exploitant" in rendu.stderr


def test_the_english_names_do_the_same_gestures(tmp_path):
    """The English verb and option names, measured by their EFFECT.

    The French names stay accepted as aliases (the tests above go through
    them); this one proves the new names are not mere help text: each verb
    changes the database exactly as its French twin does."""
    adresse = "anglais@exemple.test"
    with _server(tmp_path) as base:
        session, _ = _inscrire(base, adresse)
        spec = requests.get(f"{base}/api/examples/vitrine", timeout=30).json()["spec"]
        projet = session.post(f"{base}/api/compile", json={"spec": spec},
                              timeout=180).json()["id"]
    magasin = IdentityStore(_espace(tmp_path))

    def echeance():
        with sqlite_db(magasin.path) as db:
            return db.execute("SELECT expires_at FROM projects").fetchone()[0]

    assert adresse in admin(tmp_path, "accounts").stdout
    assert projet in admin(tmp_path, "account", adresse).stdout
    assert projet in admin(tmp_path, "projects", "--account", adresse).stdout
    assert admin(tmp_path, "extend", projet, "--never").returncode == 0
    assert echeance() is None
    assert admin(tmp_path, "extend", projet, "--days", "30").returncode == 0
    assert echeance() > int(time.time()) + 29 * 24 * 3600
    assert admin(tmp_path, "expire", projet).returncode == 0
    assert echeance() <= int(time.time())
    assert admin(tmp_path, "delete-account", adresse).returncode == 1
    assert adresse in admin(tmp_path, "accounts").stdout
    rendu = admin(tmp_path, "delete-account", adresse, "--confirm")
    assert rendu.returncode == 0, rendu.stderr
    assert adresse not in admin(tmp_path, "accounts").stdout


def test_backup_and_keep_like_sauvegarde_and_garder(tmp_path, capsys):
    """`backup --keep` rotates like `sauvegarde --garder`, which stays accepted."""
    from monl_platform.__main__ import main as plateforme

    espace = tmp_path / "espace"
    IdentityStore(espace)
    dossier = tmp_path / "copies"
    for i, verbe, option in ((1, "backup", "--keep"), (2, "sauvegarde", "--garder"),
                             (3, "backup", "--keep")):
        cible = dossier / f"base-{i}.sqlite3"
        assert plateforme([verbe, str(cible), "--workspace", str(espace),
                           option, "2"]) == 0
        os.utime(cible, (i, i))
    assert sorted(f.name for f in dossier.iterdir()) == ["base-2.sqlite3", "base-3.sqlite3"]
    assert "Backup removed" in capsys.readouterr().out
