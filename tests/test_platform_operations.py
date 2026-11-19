"""What it takes to open the platform to the public, tested while running.

Four operating guarantees, each against a real server or a real database: the
legal pages describe what the code really keeps, an account can be erased
entirely, the database backs up while live, and expired projects disappear
WITHOUT a restart.

Each carries its counter-proof: a guarantee one cannot make fail guarantees
nothing.
"""

import ast
import importlib
import os
import pathlib
import re
import shutil
import sqlite3
import subprocess
import sys
import time

import pytest
import requests

from monl.generator.runtime_base import DB_POOL_MAX_ENV, DB_POOL_MIN_ENV
from monl_platform import legal
from monl_platform.app import create_app
from monl_platform.backup_healthcheck import _sqlite_valid
from monl_platform.identity import IdentityStore
from tests.support.server import uvicorn_server
from tests.support.sqlite import sqlite_db

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PASSWORD = "MotDePasse-Exploitation-2026"


def _environment(**extra):
    env = os.environ.copy()
    env["PYTHONPATH"] = os.path.join(RACINE, "src")
    env.update(extra)
    return env


def _server(folder, **extra):
    return uvicorn_server(str(folder), env=_environment(**extra),
                          module="monl_platform.app:app", ready_path="/health")


def _account(base, address):
    session = requests.Session()
    response = session.post(f"{base}/api/auth/register", timeout=30,
                           json={"email": address, "password": PASSWORD})
    assert response.status_code == 201, response.text
    return session


@pytest.mark.parametrize(
    ("public_url", "cookie_secure", "started"),
    (
        ("https://monl.exemple.test", "1", True),
        ("https://monl.exemple.test", "0", False),
        ("http://monl.exemple.test", "0", True),
        ("", "0", True),
    ),
)
def test_startup_only_accepts_a_consistent_cookie_configuration(
    tmp_path, public_url, cookie_secure, started
):
    """The three requested schemes, plus the absence of URL, go through a real server import."""
    environment = _environment(
        MONL_PLATFORM_PUBLIC_URL=public_url,
        MONL_COOKIE_SECURE=cookie_secure,
        MONL_PLATFORM_WORKSPACE=str(tmp_path / "workspace"),
    )
    process = subprocess.run(
        [sys.executable, "-c", "from monl_platform.app import app"],
        cwd=RACINE,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if started:
        assert process.returncode == 0, process.stderr
    else:
        assert process.returncode != 0
        message = process.stdout + process.stderr
        assert "MONL_PLATFORM_PUBLIC_URL" in message
        assert "MONL_COOKIE_SECURE" in message
        assert "MONL_COOKIE_SECURE=1" in message


# ---------------------------------------------------------------------------
# 1. The legal pages
# ---------------------------------------------------------------------------

PAGES_LEGAL = ("/mentions-legales", "/conditions", "/confidentialite")


def test_the_legal_pages_are_served_and_linked(tmp_path):
    with _server(tmp_path) as base:
        for path in PAGES_LEGAL:
            response = requests.get(base + path, timeout=30)
            assert response.status_code == 200, path
            assert "text/html" in response.headers["content-type"]
        # A legal page nothing links to does not exist for the user.
        home = requests.get(base + "/", timeout=30).text
        for path in PAGES_LEGAL:
            assert f'href="{path}"' in home, path


def test_the_privacy_page_names_every_table_keeping_data(tmp_path):
    """The guarantee that keeps the page from lying as it ages.

    A privacy policy drifts away from the code without anything signaling it —
    and a false policy is worse than none, because it CLAIMS. This test reads the
    real schema and requires every table to appear.
    """
    store = IdentityStore(tmp_path)
    with sqlite_db(store.path) as db:
        tables = {row[0] for row in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%'")}
    described = {table for table, _, _ in legal.DONNEES}
    assert tables == described, (
        f"the schema and the page diverge — in the database only: {tables - described}; "
        f"described without existing: {described - tables}")
    for table in tables:
        assert table in legal.PRIVACY, f"{table} missing from the published text"


def test_the_privacy_page_names_every_cookie_really_set():
    """The previous test's counterpart, for what is set in the BROWSER.

    The page claimed "the only cookie set is `monl_session`", and it stayed true
    until the day the OAuth start gained its transient cookie (point 187): the
    sentence then became false without a line turning red. A forgotten table was
    already guarded; a forgotten cookie was not, although it is the only data the
    visitor takes home.

    The comparison goes BOTH ways — a cookie removed from the code but still on
    the page makes the page lie just as much.
    """
    racine = pathlib.Path(RACINE) / "src" / "monl_platform"
    poses = set()
    for path in racine.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for call in (n for n in ast.walk(tree) if isinstance(n, ast.Call)):
            target = call.func
            if not isinstance(target, ast.Attribute) or target.attr != "set_cookie":
                continue
            name = call.args[0] if call.args else None
            if isinstance(name, ast.Constant) and isinstance(name.value, str):
                poses.add(name.value)
                continue
            # A NAMED constant is resolved on the module, never by a regex on
            # the text: point 172 showed that an extractor seeing only literals
            # turns the guard green while looking at nothing. What cannot be
            # read makes the test FAIL.
            assert isinstance(name, ast.Name), (
                f"{path.name}: set_cookie called with an unreadable name")
            module = importlib.import_module(f"monl_platform.{path.stem}")
            poses.add(getattr(module, name.id))

    announced = set(re.findall(r"<code>(monl_[a-z_]+)</code>", legal.PRIVACY))
    assert poses == announced, (
        f"the page and the code diverge — set without being announced: "
        f"{poses - announced}; announced without being set: {announced - poses}")


def test_the_three_identities_live_on_the_legal_notice_page_only(tmp_path):
    """The pattern followed by Scaleway, Clever Cloud and OVH — checked on their
    sites.

    All three have a distinct "Legal notice" page, and that is where, and ONLY
    where, the publisher and the host live. monl repeated them at the top of the
    two other pages, without a title, with a line labeled "contact": the whole
    read like a contact details block, so the publisher and the host looked like
    ways of reaching us.

    The test guards both halves: they are ON the legal notice page, and no longer
    anywhere else. Without the second, going back would make nothing fail.
    """
    with _server(tmp_path) as base:
        mentions = requests.get(base + "/mentions-legales", timeout=30).text
        for emplacement in (legal.PUBLISHER, legal.CONTACT, legal.HOST):
            assert emplacement in mentions, f"{emplacement} missing from the legal notice"

        for path in ("/conditions", "/confidentialite"):
            page = requests.get(base + path, timeout=30).text
            assert legal.PUBLISHER not in page, f"the publisher came back on {path}"
            assert legal.HOST not in page, f"the host came back on {path}"
            # …but each must LEAD to the legal notice, otherwise the identity
            # becomes impossible to find from the document that commits it.
            assert 'href="/mentions-legales"' in page, path


def test_the_privacy_page_keeps_the_address_for_exercising_rights(tmp_path):
    """The contact address stays in the flow of the text, where the page talks
    about exercising one's rights. Sending it entirely to the legal notice would
    force changing pages at the very moment one wants to act."""
    with _server(tmp_path) as base:
        page = requests.get(base + "/confidentialite", timeout=30).text
        assert legal.CONTACT in page
        assert "ci-dessus" not in page, (
            "dangling reference: the identity box is no longer above")


def test_no_page_declares_itself_incomplete(tmp_path):
    """The service is open: no page must carry a placeholder to fill nor a
    warning box any more.

    Without this test, reintroducing a marker — by duplicating a constant, by
    emptying it during a rename — would put the pages back in "under
    construction" state without anything saying so. A warning wrongly shown on a
    legal document discredits what it otherwise states.
    """
    assert legal.est_complete()
    with _server(tmp_path) as base:
        for path in PAGES_LEGAL:
            page = requests.get(base + path, timeout=30).text
            assert legal.MARKER not in page, path
            assert 'class="trou"' not in page, path
            assert "Still to be filled in" not in page, path


def test_the_warning_names_what_is_really_missing(monkeypatch):
    """The warning's three states, including the PARTIAL one.

    The partial state is only crossed on the way, and so never looked at: that is
    where a frozen count ("these three placeholders") would send people to fix
    what is already right — same reproach as the compiler's point 97, an
    assumption shown as a diagnosis.
    """
    assert legal._lines_missing() == ""

    monkeypatch.setattr(legal, "CONTACT", "[CONTACT ADDRESS TO BE COMPLETED]")
    partial = legal._lines_missing()
    assert not legal.est_complete()
    assert "the contact address" in partial
    assert "the publisher" not in partial and "the host" not in partial

    monkeypatch.setattr(legal, "PUBLISHER", "[PUBLISHER TO BE COMPLETED]")
    monkeypatch.setattr(legal, "HOST", "[HOST TO BE COMPLETED]")
    empty = legal._lines_missing()
    for expected in ("the publisher", "the contact address", "the host"):
        assert expected in empty


# ---------------------------------------------------------------------------
# 2. La suppression de compte
# ---------------------------------------------------------------------------

def test_deleting_ones_account_erases_everything_including_disk(tmp_path):
    with _server(tmp_path) as base:
        session = _account(base, "partant@exemple.test")
        identifier = session.get(f"{base}/api/auth/me", timeout=30).json()["id"]

        key = session.post(f"{base}/api/keys", json={"name": "portable"}, timeout=30)
        assert key.status_code == 201
        brute = key.json()["key"]

        spec = requests.get(f"{base}/api/examples/vitrine", timeout=30).json()["spec"]
        compile = session.post(f"{base}/api/compile", json={"spec": spec}, timeout=180)
        assert compile.status_code == 201, compile.text
        project = compile.json()["id"]
        folder = tmp_path / "platform-projects" / project
        if not folder.exists():                       # default workspace
            folder = next(p for p in tmp_path.rglob(project) if p.is_dir())
        assert folder.is_dir()

        efface = session.request("DELETE", f"{base}/api/auth/account", timeout=60,
                                 json={"password": PASSWORD})
        assert efface.status_code == 204, efface.text

        # The account no longer exists…
        reopen = requests.post(f"{base}/api/auth/login", timeout=30,
                                json={"email": "partant@exemple.test",
                                      "password": PASSWORD})
        assert reopen.status_code == 401
        # …nor does its API key…
        mcp = requests.post(f"{base}/mcp", timeout=30,
                            headers={"Authorization": f"Bearer {brute}"},
                            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        assert mcp.status_code in (401, 403), mcp.text
        # …and its files have left the disk.
        assert not folder.exists(), "the compiled folder survives the deletion"

        store = IdentityStore(_space(tmp_path))
        with sqlite_db(store.path) as db:
            for table in ("users", "sessions", "projects", "api_keys"):
                reste = db.execute(
                    f"SELECT COUNT(*) FROM {table} WHERE "
                    f"{'id' if table == 'users' else 'user_id'} = ?",
                    (identifier,)).fetchone()[0]
                assert reste == 0, f"{table} keeps rows of the deleted account"


def test_a_wrong_password_deletes_nothing(tmp_path):
    """The counter-proof. Without it, a route that ALWAYS deleted would pass the
    previous test."""
    with _server(tmp_path) as base:
        session = _account(base, "prudent@exemple.test")
        refusal = session.request("DELETE", f"{base}/api/auth/account", timeout=30,
                                json={"password": "ce-n-est-pas-le-bon"})
        assert refusal.status_code == 403, refusal.text
        # The account still answers, and the session holds.
        assert session.get(f"{base}/api/auth/me", timeout=30).status_code == 200


def test_deletion_requires_a_session(tmp_path):
    with _server(tmp_path) as base:
        anonymous = requests.request("DELETE", f"{base}/api/auth/account", timeout=30,
                                   json={"password": PASSWORD})
        assert anonymous.status_code == 401


# ---------------------------------------------------------------------------
# 3. La sauvegarde
# ---------------------------------------------------------------------------

def _space(tmp_path):
    """The workspace really used by the test server."""
    candidate = tmp_path / "platform-projects"
    return candidate if candidate.exists() else tmp_path


def test_the_database_backs_up_while_being_written(tmp_path):
    """The point justifying the backup API rather than a `cp`.

    The platform writes in WAL: a file copy taken during a transaction can yield
    a truncated database. We therefore keep a connection open WITH an uncommitted
    write during the backup.
    """
    store = IdentityStore(tmp_path)
    store.register("garde@exemple.test", PASSWORD)

    bulky = sqlite3.connect(store.path, timeout=10)
    bulky.execute("PRAGMA journal_mode = WAL")
    bulky.execute("BEGIN")
    bulky.execute(
        "INSERT INTO rate_limits VALUES ('essai', 'sujet', 0, 1)")
    try:
        copy = store.back_up(tmp_path / "sauvegardes" / "base.sqlite3")
    finally:
        bulky.rollback()
        bulky.close()

    assert copy.exists() and copy.stat().st_size > 0
    with sqlite_db(copy) as reread:
        assert reread.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert reread.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 1
        assert reread.execute(
            "SELECT email FROM users").fetchone()[0] == "garde@exemple.test"


def test_the_backup_copy_leaves_no_wal_sidecars(tmp_path):
    """`Connection.backup()` also copies the source's page 1 header, which carries
    the journal mode: the copy silently inherits WAL, without any `-wal`/`-shm`
    appearing as long as nobody reads it — the backup produced by `sauvegarder()`
    therefore comes out clean.

    The NEXT READ triggers the leak: the container healthcheck
    (`backup_healthcheck._sqlite_valide`) opens the copy in `mode=ro` every 30 s
    to check its integrity — and a reader ALONE IS ENOUGH to create `-shm` on a
    WAL file, a lone reader CANNOT checkpoint it on close (the tidying checkpoint
    requires writing). Measured in real conditions (podman compose, backups every
    20 s for 18 h): **719 orphan `-wal`/`-shm` pairs** for 14 `.sqlite3` files —
    `_rotation` filters ONLY on `cible.suffix` (`.sqlite3`), which matches
    neither `.sqlite3-wal` nor `.sqlite3-shm`, so these sidecars are NEVER
    purged, whatever `--garder` is. A backup service without effective rotation
    fills the disk — the backup becomes the outage it was meant to prevent.
    """
    store = IdentityStore(tmp_path)
    store.register("annexe@exemple.test", PASSWORD)

    copy = store.back_up(tmp_path / "sauvegardes" / "base.sqlite3")
    assert _sqlite_valid(copy), "the probe must accept a healthy backup"

    for suffix in ("-wal", "-shm"):
        annexe = copy.with_name(copy.name + suffix)
        assert not annexe.exists(), (
            f"{annexe.name} survives after the healthcheck pass: never "
            "rotated by --garder, it accumulates forever on a "
            "continuously running service.")
    with sqlite_db(copy) as reread:
        assert reread.execute("PRAGMA journal_mode").fetchone()[0] == "delete"
        assert reread.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_rotation_lets_no_sidecar_accumulate(tmp_path):
    """The counter-proof at service scale: several cycles of backup + healthcheck
    probe + rotation, as the `compose.platform.yaml` loop runs two in parallel
    (the backup every `MONL_BACKUP_INTERVAL_SECONDS`, the probe every 30 s), must
    leave in the folder ONLY the `.sqlite3` files `--garder` chose to keep —
    nothing else."""
    from monl_platform.__main__ import _rotation

    store = IdentityStore(tmp_path)
    store.register("boucle@exemple.test", PASSWORD)
    folder = tmp_path / "sauvegardes"

    for i in range(5):
        target = store.back_up(folder / f"base-{i}.sqlite3")
        assert _sqlite_valid(target)          # the probe reads EACH backup
        _rotation(target, keep=2)

    remaining = sorted(f.name for f in folder.iterdir())
    assert remaining == ["base-3.sqlite3", "base-4.sqlite3"], remaining


def test_the_backup_command_works_from_the_command_line(tmp_path):
    store = IdentityStore(tmp_path)
    store.register("cli@exemple.test", PASSWORD)
    target = tmp_path / "copie.sqlite3"
    rendered = subprocess.run(
        [sys.executable, "-m", "monl_platform", "sauvegarde", str(target),
         "--workspace", str(tmp_path)],
        capture_output=True, text=True, env=_environment(), cwd=RACINE, timeout=120)
    assert rendered.returncode == 0, rendered.stderr
    assert str(target) in rendered.stdout
    with sqlite_db(target) as reread:
        assert reread.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 1


def _descriptors(path):
    """How many descriptors this process holds open on this database."""
    folder = pathlib.Path("/proc") / str(os.getpid()) / "fd"
    total = 0
    for entry in folder.iterdir():
        try:
            if str(path) in os.readlink(entry):
                total += 1
        except OSError:                       # descriptor closed in between
            continue
    return total


@pytest.mark.skipif(not os.path.isdir("/proc/self/fd"),
                    reason="descriptor counting requires /proc")
def test_the_database_leaves_no_connection_open_behind(tmp_path):
    """`with sqlite3.connect(...)` commits the transaction, but does not CLOSE.

    A CPython `Connection` object takes part in reference cycles: it is therefore
    only released by the cyclic garbage collector, not when the method returns.
    Measured before the fix: 500 reads left 197 descriptors open on the database,
    all released at once by a manual `gc.collect()`. It is not an eternal leak, it
    is worse to operate — a server under load can exhaust its descriptor limit
    before a generation-2 collection happens.

    The WAL is the witness: as long as a connection lives, SQLite does not fold it
    back into the main file. The database stayed at 4,096 bytes with 111 KB of
    journal beside it — and that is what made the documented restore fail, with a
    "disk I/O error" nothing explained.
    """
    store = IdentityStore(tmp_path)
    store.register("charge@exemple.test", PASSWORD)
    for _ in range(200):
        store.authenticate("charge@exemple.test", PASSWORD)

    open_ = _descriptors(store.path)
    assert open_ == 0, f"{open_} descriptors stay open on the database"
    assert not store.path.with_name(store.path.name + "-wal").exists(), (
        "the WAL survives: a connection stayed open")


# What a server killed mid-write leaves behind: the main database, plus a WAL
# journal nobody checkpointed. `os._exit` bypasses all cleanup — it is a kill
# -9, not a clean stop.
CRASH = """
import os, sys
sys.path.insert(0, {racine!r})
from monl_platform.identity import IdentityStore
magasin = IdentityStore({espace!r})
magasin.register({adresse!r}, {secret!r})
brute = __import__("sqlite3").connect(magasin.path)
brute.execute("PRAGMA journal_mode = WAL")
brute.execute("INSERT INTO rate_limits VALUES ('crash', 'sujet', 0, 1)")
brute.commit()
os._exit(0)
"""


def test_the_documented_restore_procedure_works(tmp_path):
    """`docs/EXPLOITATION.md` describes a restore in three steps. A procedure
    written and never played is a false procedure: it is only run on an outage
    day, when being wrong costs the most.

    The step people forget is the SECOND — removing `-wal` and `-shm`. The
    database runs in WAL: putting back the main file while leaving the PREVIOUS
    database's journal beside it restores two states at once. The case is not
    theoretical, but it only happens after a BRUTAL stop: this test therefore
    kills a real process mid-write, rather than assuming a WAL.
    """
    store = IdentityStore(tmp_path)
    store.register("avant@exemple.test", PASSWORD)
    copy = store.back_up(tmp_path / "sauvegardes" / "base.sqlite3")

    mort = subprocess.run(
        [sys.executable, "-c", CRASH.format(
            racine=os.path.join(RACINE, "src"), espace=str(tmp_path),
            adresse="apres@exemple.test", secret=PASSWORD)],
        capture_output=True, text=True, timeout=60)
    assert mort.returncode == 0, mort.stderr
    log = store.path.with_name(store.path.name + "-wal")
    assert log.exists(), "the killed process was supposed to leave a WAL behind"

    # --- the documented procedure, step by step ---
    # 1. the server is stopped — here, it is dead
    # 2. remove the journal of the database being replaced
    for suffix in ("-wal", "-shm"):
        store.path.with_name(store.path.name + suffix).unlink(missing_ok=True)
    # 3. put the backup back in place
    shutil.copy2(copy, store.path)

    reopened = IdentityStore(tmp_path)
    with sqlite_db(reopened.path) as db:
        addresses = {row[0] for row in db.execute("SELECT email FROM users")}
    assert addresses == {"avant@exemple.test"}, (
        "the restore must return the backed-up state, no more no less")
    assert reopened.authenticate("avant@exemple.test", PASSWORD) is not None


def test_rotation_keeps_only_the_most_recent(tmp_path):
    """A periodic backup without rotation fills the disk, and a full disk stops
    the service it protected: the backup becomes the outage. Rotation lives in the
    command that writes, so the two cannot diverge.
    """
    store = IdentityStore(tmp_path)
    store.register("rotation@exemple.test", PASSWORD)
    folder = tmp_path / "sauvegardes"

    for number in range(5):
        rendered = subprocess.run(
            [sys.executable, "-m", "monl_platform", "sauvegarde",
             str(folder / f"base-{number}.sqlite3"),
             "--workspace", str(tmp_path), "--garder", "3"],
            capture_output=True, text=True, env=_environment(),
            cwd=RACINE, timeout=120)
        assert rendered.returncode == 0, rendered.stderr
        # Each copy must carry a distinct modification date, otherwise the sort
        # has nothing to decide and the test proves nothing.
        os.utime(folder / f"base-{number}.sqlite3", (1_700_000 + number * 60,) * 2)

    remaining = sorted(f.name for f in folder.iterdir())
    assert remaining == ["base-2.sqlite3", "base-3.sqlite3", "base-4.sqlite3"], remaining


def test_rotation_sorts_on_date_never_on_name(tmp_path):
    """The trap: a name template is the operator's choice, and a month or day
    written without a leading zero puts alphabetical order at odds with time
    order.

    The first version of this test proved NOTHING — measured by tampering with
    the sort: the chosen names gave the same verdict in both orders. These make
    them diverge for real.

    `base-2026-8-9`  is the OLDEST, and alphabetically the larger of the two
                     ("8" > "1").
    `base-2026-12-01` is more RECENT, and alphabetically the smaller.

    Sorting on the name would therefore keep the oldest and erase the most
    recent: exactly the opposite of what a rotation is asked to do.
    """
    store = IdentityStore(tmp_path)
    store.register("tri@exemple.test", PASSWORD)
    folder = tmp_path / "sauvegardes"
    folder.mkdir(parents=True)

    for name, instant in (("base-2026-8-9.sqlite3", 1_000_000),      # the oldest
                         ("base-2026-12-01.sqlite3", 2_000_000)):   # more recent
        (folder / name).write_bytes(b"copie")
        os.utime(folder / name, (instant, instant))

    rendered = subprocess.run(
        [sys.executable, "-m", "monl_platform", "sauvegarde",
         str(folder / "base-2027-01-01.sqlite3"), "--workspace", str(tmp_path),
         "--garder", "2"],
        capture_output=True, text=True, env=_environment(), cwd=RACINE, timeout=120)
    assert rendered.returncode == 0, rendered.stderr

    remaining = {f.name for f in folder.iterdir()}
    assert remaining == {"base-2027-01-01.sqlite3", "base-2026-12-01.sqlite3"}, (
        f"rotation kept {sorted(remaining)} — sorting on the NAME would have "
        "kept base-2026-8-9, which is the oldest")


def test_without_keep_rotation_erases_nothing(tmp_path):
    """The witness. A rotation that always applied would erase the backups of
    whoever asked for nothing."""
    store = IdentityStore(tmp_path)
    store.register("temoin@exemple.test", PASSWORD)
    folder = tmp_path / "sauvegardes"
    for number in range(4):
        subprocess.run(
            [sys.executable, "-m", "monl_platform", "sauvegarde",
             str(folder / f"base-{number}.sqlite3"), "--workspace", str(tmp_path)],
            capture_output=True, text=True, env=_environment(),
            cwd=RACINE, timeout=120, check=True)
    assert len(list(folder.iterdir())) == 4


# ---------------------------------------------------------------------------
# 4. The periodic purge
# ---------------------------------------------------------------------------

def _expire(space, offset=-10):
    """Makes every project expire, as time would."""
    store = IdentityStore(space)
    with sqlite_db(store.path) as db:
        db.execute("UPDATE projects SET expires_at = ?", (int(time.time()) + offset,))
        return db.execute("SELECT COUNT(*) FROM projects").fetchone()[0]


def _remaining_projects(space):
    store = IdentityStore(space)
    with sqlite_db(store.path) as db:
        return db.execute("SELECT COUNT(*) FROM projects").fetchone()[0]


@pytest.mark.parametrize("interval,expected", [("1", 0), ("3600", 1)])
def test_expired_projects_go_without_restart(tmp_path, interval, expected):
    """The guarantee AND its counter-proof, in the same test.

    With a one-second interval, the expired project must disappear while the
    server runs. With the default interval, it must STAY — otherwise we would not
    know whether the loop erased it or merely mounting the application did.
    """
    with _server(tmp_path, MONL_PURGE_INTERVAL_SECONDS=interval) as base:
        session = _account(base, f"purge{interval}@exemple.test")
        spec = requests.get(f"{base}/api/examples/vitrine", timeout=30).json()["spec"]
        compile = session.post(f"{base}/api/compile", json={"spec": spec}, timeout=180)
        assert compile.status_code == 201, compile.text

        space = _space(tmp_path)
        assert _expire(space) == 1

        for _ in range(40):                     # at most ten seconds
            if _remaining_projects(space) == expected:
                break
            time.sleep(0.25)
        assert _remaining_projects(space) == expected


def test_the_purge_is_the_same_function_at_startup_and_in_the_loop():
    """Two copies of the cleanup would have ended up diverging, and cleaning
    would have lost."""
    from monl_platform import app as module
    assert callable(module._purge)
    sources = (pathlib.Path(module.__file__),
               pathlib.Path(module.__file__).with_name("app_lifecycle.py"))
    calls = [node for source in sources
              for node in ast.walk(ast.parse(source.read_text(encoding="utf-8")))
              if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
              and node.func.id == "_purge"]
    assert len(calls) == 2, (
        "the purge must be called exactly twice — at startup and "
        "in the loop — by the SAME function")
    assert all(len(call.args) == 3 and isinstance(call.args[2], ast.Name)
               and call.args[2].id == "builder_runtime" for call in calls), (
        "both purges must use the live sites manager")


def test_building_the_application_starts_no_thread(tmp_path):
    """The thread lives in the lifespan, not in `create_app`: otherwise every test
    building an application would leave a thread behind."""
    import threading
    before = {fil.name for fil in threading.enumerate()}
    create_app(workspace=tmp_path)
    apres = {fil.name for fil in threading.enumerate()}
    assert not {name for name in apres - before if "purge" in name}


# ---------------------------------------------------------------------------
# 5. Le document d'exploitation
# ---------------------------------------------------------------------------

DOCUMENT = pathlib.Path(RACINE) / "docs" / "EXPLOITATION.md"
SOURCES = pathlib.Path(RACINE) / "src" / "monl_platform"


def _variables_lues_par(source, name_file):
    """The environment variables read by a module, resolved by AST.

    The previous version looked for `os.environ.get("MONL_…")` with a regular
    expression: it therefore saw ONLY names hard-coded at the point of reading.
    Storing a name in a constant — which is good practice, and what was done for
    `MONL_COOKIE_SECURE` so that a rename does not leave two truths — made the
    variable invisible and led to concluding "documented but not read". The remedy
    would then have been to REMOVE it from the document, that is, to delete the
    documentation of an active security setting.

    A surface is measured by AST, never by grep (point 153): imports and
    indirections escape text.
    """
    tree = ast.parse(source, filename=name_file)
    constants = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant) \
                and isinstance(node.value.value, str):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    constants[target.id] = node.value.value

    def _name(argument):
        if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
            return argument.value
        if isinstance(argument, ast.Name):
            return constants.get(argument.id)
        return None

    found = set()
    for node in ast.walk(tree):
        argument = None
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                and node.func.attr in {"get", "pop"} and node.args:
            target = node.func.value
            if (isinstance(target, ast.Attribute) and target.attr == "environ") or \
                    (isinstance(target, ast.Name) and target.id in {"environ", "source"}):
                argument = node.args[0]
        elif isinstance(node, ast.Subscript):
            target = node.value
            if isinstance(target, ast.Attribute) and target.attr == "environ":
                argument = node.slice
        name = _name(argument) if argument is not None else None
        if name and name.startswith("MONL_"):
            found.add(name)
    return found


def test_the_variable_extractor_sees_the_literal_AND_the_constant():
    """Without this witness, a mute extractor would turn the rule above green.

    A guarantee that stops applying to anything makes no noise (point 154): the
    EXTRACTOR's witness prevents it.
    """
    source = (
        'CLE = "MONL_PAR_CONSTANTE"\n'
        'def lire(environ=None):\n'
        '    source = os.environ if environ is None else environ\n'
        '    a = os.environ.get("MONL_EN_DUR")\n'
        '    b = source.get(CLE)\n'
        '    c = os.environ["MONL_PAR_INDICE"]\n'
        '    return a, b, c\n'
    )
    assert _variables_lues_par(source, "sonde.py") == {
        "MONL_EN_DUR", "MONL_PAR_CONSTANTE", "MONL_PAR_INDICE"}
    # Counter-proof: the old regular-expression read saw only one of the three.
    assert set(re.findall(r'os\.environ\.get\(\s*"([A-Z_]+)"', source)) == {
        "MONL_EN_DUR"}


def test_the_operations_document_names_every_variable_and_nothing_else():
    """Same guarantee as for the privacy page, on the other document.

    An operations doc drifts without anything signaling it, and it is only reread
    during an incident. Two symmetrical faults are forbidden: a variable the code
    reads and the document keeps quiet about (nobody will know how to set it), a
    documented variable the code ignores (it will be set for nothing, believing
    one has acted).
    """
    lues = set()
    for file in SOURCES.glob("*.py"):
        lues |= _variables_lues_par(file.read_text(encoding="utf-8"),
                                    file.name)
    # Deployment reads variables too, and the compose shell is a reader just
    # like Python: `MONL_BACKUP_INTERVAL_SECONDS` sets the backup service's
    # period without ever going through `os.environ`. Looking only at Python
    # sources would make this variable a ghost while it acts — and push people
    # to remove it from the document.
    compose = (pathlib.Path(RACINE) / "compose.platform.yaml").read_text(encoding="utf-8")
    lues |= set(re.findall(r"\$\{?(MONL_[A-Z_]+)", compose))
    text = DOCUMENT.read_text(encoding="utf-8")
    cited = set(re.findall(r"`(MONL_[A-Z_]+)`", text))
    # EXPLOITATION.md also covers generated backends' settings. These are not
    # read by the platform itself: the dedicated witness below checks them in
    # the produced app.py, while this witness keeps the exact bijection of the
    # platform's surface.
    backend_generated = {DB_POOL_MIN_ENV, DB_POOL_MAX_ENV}
    assert lues == cited - backend_generated, (
        f"read without being documented: {sorted(lues - cited)}; "
        f"documented without being read: {sorted((cited - backend_generated) - lues)}")
    assert backend_generated <= cited


def test_pool_settings_are_read_in_the_generated_app(tmp_path):
    """The same AST extractor checks the code really produced."""
    from monl.cli import compile_project

    spec = tmp_path / "spec.ml"
    spec.write_text(
        """app PoolDocs

entity User
    name: String

actor User selfRegister
workflow W for User
    Create User
    Read User
""",
        encoding="utf-8",
    )
    compile_project(str(spec), str(tmp_path))
    lues = _variables_lues_par((tmp_path / "app.py").read_text(encoding="utf-8"), "app.py")
    assert {DB_POOL_MIN_ENV, DB_POOL_MAX_ENV} <= lues


def test_the_operations_document_names_every_logged_event():
    """The event list serves to write alerts. Incomplete, it makes people monitor
    a service believing they see everything."""
    emitted = set()
    for file in SOURCES.glob("*.py"):
        if file.name == "journal.py":
            continue
        emitted |= set(re.findall(r'\b(?:evenement|anomalie|panne)\(\s*"([a-z_]+)"',
                               file.read_text(encoding="utf-8")))
    text = DOCUMENT.read_text(encoding="utf-8")
    missing = sorted(name for name in emitted if f"`{name}`" not in text)
    assert not missing, f"events emitted but missing from the document: {missing}"


def test_the_document_exaggerates_neither_blockers_nor_backup():
    text = DOCUMENT.read_text(encoding="utf-8")

    assert "Five blocking points, two of which are done." in text
    assert "Five blocking points, the first of which is done." not in text
    assert "SEPARATE from the database, but on the SAME machine" in text
    assert "corrupted database" in text
    assert "loss of the disk or machine" in text


def test_the_document_recalls_the_two_settings_forgotten_in_production():
    """The witness of the two settings whose absence does not show: a session
    cookie in the clear, and rate limiting that counts the whole planet on the
    proxy's address."""
    text = DOCUMENT.read_text(encoding="utf-8")
    assert "MONL_COOKIE_SECURE=1" in text
    assert "MONL_TRUST_PROXY=1" in text
    # And the blocking points that no variable settles: a published contact
    # address must RECEIVE, otherwise the rights the privacy policy announces
    # cannot be exercised.
    assert "src/monl_platform/legal.py" in text
    assert legal.CONTACT in text


def test_the_document_gives_the_flag_that_keeps_the_healthcheck():
    """The OCI format does not carry `HEALTHCHECK`, and podman builds in OCI.

    Measured: `podman inspect --format '{{.HealthCheck}}'` returns `<nil>` on the
    image built by default, and the full check with `--format docker` — after
    which the container really becomes `healthy`.

    The witness requires the FLAG and not only the mention of the problem: the
    first draft advised wiring a probe elsewhere, while an option is enough. A
    document describing a limitation without giving the remedy it knows sends
    people to work for nothing.

    It also requires the CONSEQUENCE to be written: building without the flag
    breaks nothing visible — the route answers, the application runs — and
    supervision goes silent. Without this sentence, the operator reads a format
    subtlety and moves on.
    """
    text = DOCUMENT.read_text(encoding="utf-8")
    assert "`HEALTHCHECK`" in text
    assert "--format docker" in text, (
        "the document names the problem without giving the flag that fixes it")
    assert "--podman-build-args" in text, (
        "the flag is given for `podman build` but not for the "
        "COMPOSE path, which is the one this document recommends")
    assert "`/ready`" in text
    assert "`healthy`" in text
    # Case-insensitive: the document writes "SUPERVISION" in capitals for
    # emphasis, and a witness requiring the lower-case form would get the
    # document corrected instead of the defect.
    assert "supervision" in text.lower(), (
        "the consequence is not written: without it, the limitation passes for "
        "a format detail")
