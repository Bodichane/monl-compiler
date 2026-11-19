"""Starting a project means starting its COMPILED BACKEND — not an AI build.

POINT 162. As long as the platform built the frontend, "hosting" meant
serving the SNAPSHOT of a successful build: ``start_project`` queried the
build queue and refused any project that had none. With the builder removed,
this door never opened again — hosting would have become dead code while
seeing the API run is precisely the use we keep.

What these tests prove, against a real process and real requests: a COMPILED
project starts and answers, even WITHOUT a frontend (the serve.py wrapper says
it itself: "the API answers, /site will return 404"), and an uncompiled
project is refused by NAMING the missing file.
"""

import hashlib
import http.client
import io
import os
import tempfile
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

import pytest
import requests
import uvicorn

from monl.cli import compile_project
from monl_platform.app import create_app
from monl_platform.builder_host import SITE_MAX_BODY_BYTES
from monl_platform.hosting import (
    SITE_LOG_COMPACT_BYTES,
    SiteHostingError,
    SiteManager,
    SiteNotCompiledError,
)
from monl_platform.hosting_admission import (
    DEFAULT_MAX_RUNNING_SITES,
    DEFAULT_MAX_RUNNING_SITES_PER_ACCOUNT,
    hosting_limits,
)
from monl_platform.identity import IdentityStore
from monl_platform.paths import project_directory
from monl_platform.store import PlatformStore

SPEC = """app TestHebergement

entity Note
    titre: String
    contenu: Text

actor Membre selfRegister

rule Note.titre required
rule Note.Read public

workflow GererNotes for Membre
    Create Note
    Read Note
    Update Note
    Delete Note

landing
    brief: "Banc d'essai de l'hébergement : un carnet de notes minimal."
    link "Contact": "mailto:contact@monl.test"
"""


@pytest.fixture()
def plateforme(tmp_path):
    store = PlatformStore(tmp_path)
    identity = IdentityStore(store.workspace)
    user = identity.register("hote@monl.test", "MotDePasse-123")
    project_id = uuid.uuid4().hex
    identity.add_project(user["id"], project_id, "banc")
    store.create_project(user["id"], project_id, "banc")
    projet = store.get_project(project_id)
    sites = SiteManager(store, tmp_path / "projets", "localhost", startup_timeout=25)
    yield store, projet, sites, tmp_path
    sites.stop_all()


@pytest.fixture()
def application_hebergement(tmp_path, request):
    """Builds an app after setting the environment and cleans up in finally."""
    def construire():
        app = create_app(workspace=tmp_path / "projets", domain="localhost")

        def arreter():
            # Stops even if the test raises: the finalizer belongs to the
            # fixture.
            sites = app.state.sites
            pids = [site.process.pid for site in sites._running.values()]
            sites.stop_all()
            if request.node.name == "test_the_fixture_stops_a_site_that_answered":
                assert pids, "the cleanup witness saw no site start"
            for pid in pids:
                with pytest.raises(ProcessLookupError):
                    os.kill(pid, 0)

        request.addfinalizer(arreter)
        return app

    return construire


def test_the_fixture_stops_a_site_that_answered(tmp_path, application_hebergement):
    app = application_hebergement()
    projet = _compiled_project(
        app.state.store, app.state.identity_store, tmp_path / "projets",
        "temoin-nettoyage@monl.test", "temoin-nettoyage",
    )
    running = app.state.sites.start_project(projet)
    assert _get(running.port, "/openapi.json")[0] == 200


def _compiler(projet, racine, tmp_path):
    """Compiles the spec IN the project's private folder, as the console will."""
    dossier = project_directory(racine, projet["user_id"], projet["project_id"])
    (dossier / "spec.ml").write_text(SPEC, encoding="utf-8")
    compile_project(str(dossier / "spec.ml"), str(dossier))
    return dossier


def _get(port, chemin):
    connexion = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        connexion.request("GET", chemin)
        reponse = connexion.getresponse()
        return reponse.status, reponse.read()
    finally:
        connexion.close()


def _attendre_marqueur(chemin, marqueur):
    marqueurs = (marqueur,) if isinstance(marqueur, str) else tuple(marqueur)
    for _ in range(100):
        if chemin.is_file():
            contenu = chemin.read_text(encoding="utf-8", errors="replace")
            if all(attendu in contenu for attendu in marqueurs):
                return contenu
        time.sleep(0.02)
    return chemin.read_text(encoding="utf-8", errors="replace") if chemin.is_file() else ""


@pytest.mark.parametrize("valeur", ["invalide", "0", "-1"])
def test_invalid_caps_fall_back_to_defaults(monkeypatch, valeur):
    monkeypatch.setenv("MONL_MAX_RUNNING_SITES", valeur)
    monkeypatch.setenv("MONL_MAX_RUNNING_SITES_PER_ACCOUNT", valeur)

    assert hosting_limits() == (
        DEFAULT_MAX_RUNNING_SITES,
        DEFAULT_MAX_RUNNING_SITES_PER_ACCOUNT,
    )


@contextmanager
def _platform_server(application):
    config = uvicorn.Config(application, host="127.0.0.1", port=0, log_level="error")
    server = uvicorn.Server(config)
    with server.capture_signals():
        fil = threading.Thread(target=server.run, daemon=True)
        fil.start()
        while not server.started:
            assert fil.is_alive(), "uvicorn stopped before starting"
            time.sleep(0.01)
        port = server.servers[0].sockets[0].getsockname()[1]
        try:
            yield f"http://127.0.0.1:{port}"
        finally:
            server.should_exit = True
            fil.join(10)


def _compiled_project(store, identities, racine, email, slug):
    user = identities.register(email, "MotDePasse-123")
    project_id = uuid.uuid4().hex
    identities.add_project(user["id"], project_id, slug)
    store.create_project(user["id"], project_id, slug)
    projet = store.get_project(project_id)
    _compiler(projet, racine, racine.parent)
    return projet


def test_global_cap_refuses_without_creating_a_process_and_answers_503(
        tmp_path, monkeypatch, capsys, application_hebergement):
    monkeypatch.setenv("MONL_MAX_RUNNING_SITES", "2")
    monkeypatch.setenv("MONL_MAX_RUNNING_SITES_PER_ACCOUNT", "10")
    app = application_hebergement()
    projets = [
        _compiled_project(app.state.store, app.state.identity_store,
                        tmp_path / "projets", f"global-{i}@monl.test", f"global-{i}")
        for i in range(3)
    ]
    capsys.readouterr()
    sites = app.state.sites
    sites.start_project(projets[0])
    sites.start_project(projets[1])
    processus = {site.process.pid for site in sites._running.values()}

    with _platform_server(app) as base:
        refus = requests.get(
            base + "/openapi.json", headers={"Host": "global-2.localhost"}, timeout=10
        )
        assert refus.status_code == 503, refus.text
        assert refus.headers["Retry-After"] == "300"
        assert set(sites._running) == {p["project_id"] for p in projets[:2]}
        assert {site.process.pid for site in sites._running.values()} == processus


def test_evicting_the_oldest_idle_and_refusing_when_all_are_recent(
        tmp_path, monkeypatch, capsys, application_hebergement):
    monkeypatch.setenv("MONL_MAX_RUNNING_SITES", "2")
    monkeypatch.setenv("MONL_MAX_RUNNING_SITES_PER_ACCOUNT", "10")
    app = application_hebergement()
    projets = [
        _compiled_project(app.state.store, app.state.identity_store,
                        tmp_path / "projets", f"eviction-{i}@monl.test", f"eviction-{i}")
        for i in range(4)
    ]
    capsys.readouterr()
    instant = [0.0]
    sites = app.state.sites
    sites._clock = lambda: instant[0]
    ancien = sites.start_project(projets[0])
    instant[0] = 301.0
    recent = sites.start_project(projets[1])
    sites.forward(recent, "GET", "/openapi.json", {}, b"")
    nouveau = sites.start_project(projets[2])

    assert ancien.process.poll() is not None
    assert projets[0]["project_id"] not in sites._running
    assert sites.is_running(projets[1]["project_id"])
    assert sites.is_running(nouveau.project_id)
    with pytest.raises(SiteHostingError, match="active-site limit"):
        sites.start_project(projets[3])
    assert len(sites._running) == 2


def test_per_account_cap_does_not_block_another_account(
        tmp_path, monkeypatch, capsys, application_hebergement):
    monkeypatch.setenv("MONL_MAX_RUNNING_SITES", "10")
    monkeypatch.setenv("MONL_MAX_RUNNING_SITES_PER_ACCOUNT", "1")
    app = application_hebergement()
    identities, store = app.state.identity_store, app.state.store
    alice = identities.register("alice-plafond@monl.test", "MotDePasse-123")
    projets = []
    for i in range(2):
        project_id = uuid.uuid4().hex
        identities.add_project(alice["id"], project_id, f"alice-{i}")
        store.create_project(alice["id"], project_id, f"alice-{i}")
        projet = store.get_project(project_id)
        _compiler(projet, tmp_path / "projets", tmp_path)
        projets.append(projet)
    bob = _compiled_project(store, identities, tmp_path / "projets",
                          "bob-plafond@monl.test", "bob")
    capsys.readouterr()
    sites = app.state.sites
    sites.start_project(projets[0])

    with pytest.raises(SiteHostingError, match="active-site limit"):
        sites.start_project(projets[1])
    running_bob = sites.start_project(bob)

    assert sites.is_running(projets[0]["project_id"])
    assert _get(running_bob.port, "/openapi.json")[0] == 200


def _announce_without_sending(base, hote, taille):
    """Forges a lying `Content-Length`, and sends NO body byte.

    `requests` always recomputes the header from the body it is given: the
    forged announcement never reaches the server, which sees the real size and
    rightly answers 200. Measured — the first version of this witness missed what
    it thought it measured. So raw HTTP is needed.

    Sending no body is deliberate: it is what makes the witness UNAVOIDABLE. A
    server that did not read the announcement would wait for the promised 40 MiB
    and the test would fail on a timeout, never by accident on a 200.
    """
    connexion = http.client.HTTPConnection(base.removeprefix("http://"), timeout=10)
    try:
        connexion.putrequest("POST", "/echo", skip_host=True,
                             skip_accept_encoding=True)
        connexion.putheader("Host", hote)
        connexion.putheader("Content-Length", str(taille))
        connexion.endheaders()
        return connexion.getresponse().status
    finally:
        connexion.close()


def test_relay_bounds_the_body_and_forwards_a_legitimate_body_intact(
        tmp_path, monkeypatch, capsys, application_hebergement):
    monkeypatch.setenv("MONL_MAX_RUNNING_SITES", "2")
    app = application_hebergement()
    projet = _compiled_project(
        app.state.store, app.state.identity_store, tmp_path / "projets",
        "relais@monl.test", "relais",
    )
    dossier = project_directory(
        tmp_path / "projets", projet["user_id"], projet["project_id"]
    )
    (dossier / "serve.py").write_text(
        """import hashlib
from fastapi import FastAPI, Request

app = FastAPI()

@app.post('/echo')
async def echo(request: Request):
    corps = await request.body()
    return {'taille': len(corps), 'sha256': hashlib.sha256(corps).hexdigest()}
""",
        encoding="utf-8",
    )
    capsys.readouterr()
    corps = b"monl" * (1024 * 1024 // 4)
    with _platform_server(app) as base:
        accepte = requests.post(
            base + "/echo", data=corps, headers={"Host": "relais.localhost"}, timeout=20
        )
        refuse = requests.post(
            base + "/echo",
            data=(b"x" * (1024 * 1024) for _ in range(41)),
            headers={"Host": "relais.localhost"},
            timeout=30,
        )
        refuse_annonce = _announce_without_sending(
            base, "relais.localhost", SITE_MAX_BODY_BYTES + 1
        )

    assert accepte.status_code == 200, accepte.text
    assert accepte.json() == {
        "taille": len(corps),
        "sha256": hashlib.sha256(corps).hexdigest(),
    }
    assert refuse.status_code == 413, refuse.text
    assert refuse_annonce == 413, refuse_annonce


def test_a_compiled_project_starts_and_its_api_answers(plateforme, capsys):
    store, projet, sites, tmp_path = plateforme
    dossier = _compiler(projet, tmp_path / "projets", tmp_path)
    capsys.readouterr()
    # The frontend is NOT built by the platform: that is the whole heading.
    assert not (dossier / "frontend").exists()

    running = sites.start_project(projet)

    statut, corps = _get(running.port, "/openapi.json")
    assert statut == 200, corps[:200]
    assert b"/note" in corps.lower(), "the spec's routes must be served"
    assert sites.is_running(projet["project_id"])


def test_an_uncompiled_project_is_refused_naming_what_is_missing(plateforme):
    """The counter-proof: without a compiled backend, starting must FAIL.

    Without it, a ``_require_site`` requiring nothing any more would let
    ``uvicorn`` die on an empty folder and the error would talk about startup,
    never compilation — one would look for the failure on the wrong side.
    """
    store, projet, sites, tmp_path = plateforme
    project_directory(tmp_path / "projets", projet["user_id"], projet["project_id"])

    with pytest.raises(SiteNotCompiledError) as echec:
        sites.start_project(projet)

    assert "app.py" in str(echec.value)


def test_the_frontend_stays_optional_and_the_site_says_so(plateforme, capsys):
    """/site returns 404 without a frontend, but the API does answer."""
    store, projet, sites, tmp_path = plateforme
    _compiler(projet, tmp_path / "projets", tmp_path)
    capsys.readouterr()

    running = sites.start_project(projet)

    assert _get(running.port, "/site/")[0] == 404
    assert _get(running.port, "/openapi.json")[0] == 200


def test_a_crashing_site_leaves_the_trace_of_its_error(plateforme, capsys):
    """The file must explain a crash, not only prove its presence."""
    _store, projet, sites, tmp_path = plateforme
    dossier = _compiler(projet, tmp_path / "projets", tmp_path)
    capsys.readouterr()
    (dossier / "serve.py").write_text(
        """import sys
from fastapi import FastAPI

app = FastAPI()

@app.get('/crash')
def crash():
    print('SITE_CRASH_MARKER: panne volontaire', file=sys.stderr, flush=True)
    raise RuntimeError('erreur volontaire du site')
""",
        encoding="utf-8",
    )

    running = sites.start_project(projet)
    assert _get(running.port, "/crash")[0] == 500

    journal = sites.site_log_path(projet)
    contenu = _attendre_marqueur(
        journal, ("SITE_CRASH_MARKER", "RuntimeError", "erreur volontaire du site")
    )
    assert "SITE_CRASH_MARKER" in contenu
    assert "RuntimeError" in contenu
    assert "erreur volontaire du site" in contenu


def test_a_sites_output_stays_bounded(plateforme, capsys):
    """An output loop must not turn the log into a disk failure."""
    _store, projet, sites, tmp_path = plateforme
    dossier = _compiler(projet, tmp_path / "projets", tmp_path)
    capsys.readouterr()
    (dossier / "serve.py").write_text(
        f"""import sys
from fastapi import FastAPI

app = FastAPI()

@app.get('/bruit')
def bruit():
    print('SITE_OUTPUT ' + 'x' * ({SITE_LOG_COMPACT_BYTES} + 4096), file=sys.stderr, flush=True)
    return {{'ok': True}}
""",
        encoding="utf-8",
    )

    running = sites.start_project(projet)
    assert _get(running.port, "/bruit")[0] == 200
    journal = sites.site_log_path(projet)
    _attendre_marqueur(journal, "SITE_OUTPUT")
    # The DISK bound is the compaction threshold, not the kept size: the log
    # grows up to double before being brought back to its end, because
    # compacting at every block would reread the whole file every 8 KiB.
    assert journal.stat().st_size <= SITE_LOG_COMPACT_BYTES


def test_the_log_bound_holds_DURING_compaction(tmp_path, monkeypatch):
    """A disk bound holds at every moment, not only at the end.

    THE MEASURED DEFECT. Compaction happened AFTER writing the block: the file
    therefore exceeded the bound, then came back to it — and compaction rereads
    the whole log, truncates and rewrites, which takes time. CI photographed that
    moment: 2,101,261 bytes for an announced bound of 2,097,152. The size witness
    that already existed passed or failed depending on the amount of noise
    uvicorn wrote BEFORE, that is depending on nothing at all.

    This witness changes no size: it only lengthens the window that already
    exists, by making compaction wait when it starts, and it photographs the disk
    meanwhile.
    """
    journal = tmp_path / "site.log"
    journal.touch()

    entre = threading.Event()
    sortir = threading.Event()
    vrai_compactage = SiteManager._compacter_journal

    def waiting_compaction(fichier):
        entre.set()
        sortir.wait(10)
        return vrai_compactage(fichier)

    monkeypatch.setattr(
        SiteManager, "_compacter_journal", staticmethod(waiting_compaction)
    )

    ligne = b"SITE_OUTPUT " + b"x" * (SITE_LOG_COMPACT_BYTES + 4096) + b"\n"
    flux = io.BufferedReader(io.BytesIO(ligne))
    fil = threading.Thread(
        target=SiteManager._capture_output, args=(flux, journal), daemon=True
    )
    fil.start()
    try:
        assert entre.wait(10), "no compaction: the witness would measure nothing"
        pic = journal.stat().st_size
    finally:
        sortir.set()
        fil.join(10)

    assert pic <= SITE_LOG_COMPACT_BYTES, (
        f"the log occupies {pic} bytes during compaction, "
        f"for an announced bound of {SITE_LOG_COMPACT_BYTES}"
    )


def test_the_bounded_log_keeps_the_END_never_the_beginning():
    """A bound that holds does not say what is kept is useful.

    The first version stopped writing once the bound was reached: the file size
    was right, and the megabyte kept was the least useful. A site that chatters
    then crashes lost its crash trace ENTIRELY, because it comes last —
    measured, not assumed.

    The existing size witness passed in both cases. That is why this one
    measures what is KEPT: the last line the site wrote must be found in its log,
    and the first must be whole.
    """
    with tempfile.TemporaryDirectory() as base:
        journal = Path(base) / "site.log"
        bavardage = b"ligne de trafic ordinaire\n" * 400_000       # ~10 Mio
        plantage = b"TRACE-DU-PLANTAGE: RuntimeError: base absente\n"
        SiteManager._capture_output(io.BytesIO(bavardage + plantage), journal)

        contenu = journal.read_bytes()
        assert len(contenu) <= SITE_LOG_COMPACT_BYTES, len(contenu)
        assert len(contenu) < len(bavardage), "no compaction happened"
        assert b"TRACE-DU-PLANTAGE" in contenu, "the crash trace is lost"
        assert contenu.rstrip(b"\n").split(b"\n")[-1].startswith(b"TRACE-DU-PLANTAGE")
        # No fragment at the head: it would be taken for a message truncated by
        # the site itself rather than by the bound.
        assert contenu.split(b"\n")[0] == b"ligne de trafic ordinaire"


@pytest.mark.parametrize("canal", ["api", "mcp"])
def test_creation_compilee_demarre_directement(application_hebergement, canal):
    """Issue #115: no intermediate /compiler, on a real server."""
    app = application_hebergement()
    spec = (Path(__file__).parents[1] / "exemples/02_boutique.ml").read_text()
    try:
        with _platform_server(app) as base, requests.Session() as session:
            inscription = session.post(base + "/api/auth/register", json={
                "email": "direct@monl.test", "password": "MotDePasse-123"}, timeout=10)
            assert inscription.status_code == 201, inscription.text
            if canal == "api":
                compilation = session.post(base + "/api/compile", json={"spec": spec}, timeout=120)
                assert compilation.status_code == 201, compilation.text
                project_id = compilation.json()["id"]
            else:
                from test_platform_mcp_boucle import _appel

                cle = session.post(base + "/api/keys", json={"name": "direct"},
                                   timeout=10).json()["key"]
                project_id = _appel(base, cle, "monl_compile_backend", {"spec": spec})["project_id"]
            demarrage = session.post(base + f"/api/projects/{project_id}/start", timeout=30)
            assert demarrage.status_code == 200, demarrage.text
            site = requests.get(base + "/openapi.json",
                                headers={"Host": demarrage.json()["host"]}, timeout=10)
            assert site.status_code == 200, site.text
            compte = inscription.json()["user"]["id"]
            dossier = project_directory(app.state.builder_runtime.workspace_root, compte, project_id)
            assert (dossier / "app.py").is_file()
            assert not (app.state.compilation_service.workspace / project_id).exists()
    finally:
        app.state.sites.stop_all()
