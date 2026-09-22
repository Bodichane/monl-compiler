"""Démarrer un projet, c'est démarrer son BACKEND COMPILÉ — pas un build IA.

POINT 162. Tant que la plateforme construisait le frontend, « héberger »
voulait dire servir le SNAPSHOT d'une construction réussie : ``start_project``
interrogeait la file de builds et refusait tout projet qui n'en avait aucun.
Le constructeur retiré, cette porte ne s'ouvrait plus jamais — l'hébergement
serait devenu du code mort alors que voir l'API tourner est justement l'usage
qu'on garde.

Ce que ces tests prouvent, contre un vrai processus et de vraies requêtes :
un projet COMPILÉ démarre et répond, même SANS frontend (le wrapper serve.py
le dit lui-même : « l'API répond, /site renverra 404 »), et un projet non
compilé est refusé en NOMMANT le fichier absent.
"""

import hashlib
import http.client
import io
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


def _compiler(projet, racine, tmp_path):
    """Compile la spec DANS le dossier privé du projet, comme le fera la console."""
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
def test_les_plafonds_invalides_replient_sur_les_defauts(monkeypatch, valeur):
    monkeypatch.setenv("MONL_MAX_RUNNING_SITES", valeur)
    monkeypatch.setenv("MONL_MAX_RUNNING_SITES_PER_ACCOUNT", valeur)

    assert hosting_limits() == (
        DEFAULT_MAX_RUNNING_SITES,
        DEFAULT_MAX_RUNNING_SITES_PER_ACCOUNT,
    )


@contextmanager
def _serveur_plateforme(application):
    config = uvicorn.Config(application, host="127.0.0.1", port=0, log_level="error")
    server = uvicorn.Server(config)
    with server.capture_signals():
        fil = threading.Thread(target=server.run, daemon=True)
        fil.start()
        while not server.started:
            assert fil.is_alive(), "uvicorn s'est arrêté avant de démarrer"
            time.sleep(0.01)
        port = server.servers[0].sockets[0].getsockname()[1]
        try:
            yield f"http://127.0.0.1:{port}"
        finally:
            server.should_exit = True
            fil.join(10)


def _projet_compile(store, identities, racine, email, slug):
    user = identities.register(email, "MotDePasse-123")
    project_id = uuid.uuid4().hex
    identities.add_project(user["id"], project_id, slug)
    store.create_project(user["id"], project_id, slug)
    projet = store.get_project(project_id)
    _compiler(projet, racine, racine.parent)
    return projet


def test_plafond_global_refuse_sans_creer_de_processus_et_repond_503(
        tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("MONL_MAX_RUNNING_SITES", "2")
    monkeypatch.setenv("MONL_MAX_RUNNING_SITES_PER_ACCOUNT", "10")
    app = create_app(workspace=tmp_path / "projets", domain="localhost")
    projets = [
        _projet_compile(app.state.store, app.state.identity_store,
                        tmp_path / "projets", f"global-{i}@monl.test", f"global-{i}")
        for i in range(3)
    ]
    capsys.readouterr()
    sites = app.state.sites
    sites.start_project(projets[0])
    sites.start_project(projets[1])
    processus = {site.process.pid for site in sites._running.values()}

    with _serveur_plateforme(app) as base:
        refus = requests.get(
            base + "/openapi.json", headers={"Host": "global-2.localhost"}, timeout=10
        )
        assert refus.status_code == 503, refus.text
        assert refus.headers["Retry-After"] == "300"
        assert set(sites._running) == {p["project_id"] for p in projets[:2]}
        assert {site.process.pid for site in sites._running.values()} == processus


def test_eviction_du_plus_ancien_inactif_et_refus_quand_tous_sont_recents(
        tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("MONL_MAX_RUNNING_SITES", "2")
    monkeypatch.setenv("MONL_MAX_RUNNING_SITES_PER_ACCOUNT", "10")
    app = create_app(workspace=tmp_path / "projets", domain="localhost")
    projets = [
        _projet_compile(app.state.store, app.state.identity_store,
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
    with pytest.raises(SiteHostingError, match="plafond de sites actifs"):
        sites.start_project(projets[3])
    assert len(sites._running) == 2


def test_plafond_par_compte_nempeche_pas_un_autre_compte(
        tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("MONL_MAX_RUNNING_SITES", "10")
    monkeypatch.setenv("MONL_MAX_RUNNING_SITES_PER_ACCOUNT", "1")
    app = create_app(workspace=tmp_path / "projets", domain="localhost")
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
    bob = _projet_compile(store, identities, tmp_path / "projets",
                          "bob-plafond@monl.test", "bob")
    capsys.readouterr()
    sites = app.state.sites
    sites.start_project(projets[0])

    with pytest.raises(SiteHostingError, match="plafond de sites actifs"):
        sites.start_project(projets[1])
    running_bob = sites.start_project(bob)

    assert sites.is_running(projets[0]["project_id"])
    assert _get(running_bob.port, "/openapi.json")[0] == 200


def _annoncer_sans_envoyer(base, hote, taille):
    """Forge un `Content-Length` mensonger, et n'envoie AUCUN octet de corps.

    `requests` recalcule toujours l'en-tête depuis le corps qu'on lui donne :
    l'annonce forgée n'atteint jamais le serveur, qui voit la taille réelle et
    répond 200 à juste titre. Mesuré — la première version de ce témoin passait
    à côté de ce qu'elle croyait mesurer. Il faut donc parler HTTP en brut.

    N'envoyer aucun corps est délibéré : c'est ce qui rend le témoin
    INCONTOURNABLE. Un serveur qui ne lirait pas l'annonce attendrait les
    40 Mio promis et le test échouerait sur un dépassement de délai, jamais par
    accident sur un 200.
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


def test_relais_borne_le_corps_et_transmet_un_corps_legitime_intact(
        tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("MONL_MAX_RUNNING_SITES", "2")
    app = create_app(workspace=tmp_path / "projets", domain="localhost")
    projet = _projet_compile(
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
    with _serveur_plateforme(app) as base:
        accepte = requests.post(
            base + "/echo", data=corps, headers={"Host": "relais.localhost"}, timeout=20
        )
        refuse = requests.post(
            base + "/echo",
            data=(b"x" * (1024 * 1024) for _ in range(41)),
            headers={"Host": "relais.localhost"},
            timeout=30,
        )
        refuse_annonce = _annoncer_sans_envoyer(
            base, "relais.localhost", SITE_MAX_BODY_BYTES + 1
        )

    assert accepte.status_code == 200, accepte.text
    assert accepte.json() == {
        "taille": len(corps),
        "sha256": hashlib.sha256(corps).hexdigest(),
    }
    assert refuse.status_code == 413, refuse.text
    assert refuse_annonce == 413, refuse_annonce


def test_un_projet_compile_demarre_et_son_api_repond(plateforme, capsys):
    store, projet, sites, tmp_path = plateforme
    dossier = _compiler(projet, tmp_path / "projets", tmp_path)
    capsys.readouterr()
    # Le frontend n'est PAS construit par la plateforme : c'est tout le cap.
    assert not (dossier / "frontend").exists()

    running = sites.start_project(projet)

    statut, corps = _get(running.port, "/openapi.json")
    assert statut == 200, corps[:200]
    assert b"/note" in corps.lower(), "les routes de la spec doivent être servies"
    assert sites.is_running(projet["project_id"])


def test_un_projet_non_compile_est_refuse_en_nommant_ce_qui_manque(plateforme):
    """La contre-épreuve : sans backend compilé, le démarrage doit ÉCHOUER.

    Sans elle, un ``_require_site`` qui n'exigerait plus rien laisserait
    ``uvicorn`` mourir sur un dossier vide et l'erreur parlerait de démarrage,
    jamais de compilation — on chercherait la panne du mauvais côté.
    """
    store, projet, sites, tmp_path = plateforme
    project_directory(tmp_path / "projets", projet["user_id"], projet["project_id"])

    with pytest.raises(SiteNotCompiledError) as echec:
        sites.start_project(projet)

    assert "app.py" in str(echec.value)


def test_le_frontend_reste_facultatif_et_le_site_le_dit(plateforme, capsys):
    """/site renvoie 404 sans frontend, mais l'API, elle, répond."""
    store, projet, sites, tmp_path = plateforme
    _compiler(projet, tmp_path / "projets", tmp_path)
    capsys.readouterr()

    running = sites.start_project(projet)

    assert _get(running.port, "/site/")[0] == 404
    assert _get(running.port, "/openapi.json")[0] == 200


def test_un_site_qui_plante_laisse_la_trace_de_son_erreur(plateforme, capsys):
    """Le fichier doit expliquer un crash, pas seulement prouver sa présence."""
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


def test_la_sortie_dun_site_reste_bornee(plateforme, capsys):
    """Une boucle de sortie ne doit pas transformer le journal en panne disque."""
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
    # La borne DISQUE est le seuil de compactage, pas la taille conservée : le
    # journal grossit jusqu'au double avant d'être ramené à sa fin, parce que
    # compacter à chaque bloc relirait tout le fichier à chaque 8 Kio.
    assert journal.stat().st_size <= SITE_LOG_COMPACT_BYTES


def test_la_borne_du_journal_tient_PENDANT_le_compactage(tmp_path, monkeypatch):
    """Une borne de disque se tient à chaque instant, pas seulement à la fin.

    LE DÉFAUT MESURÉ. Le compactage avait lieu APRÈS l'écriture du bloc : le
    fichier dépassait donc la borne, puis y revenait — et le compactage relit
    tout le journal, tronque et réécrit, ce qui dure. La CI a photographié cet
    instant : 2 101 261 octets pour une borne annoncée à 2 097 152. Le témoin
    de taille qui existait déjà passait ou tombait selon la quantité de bruit
    écrite AVANT par uvicorn, c'est-à-dire selon rien du tout.

    Ce témoin-ci ne change aucune taille : il allonge seulement la fenêtre qui
    existe déjà, en faisant patienter le compactage au moment où il commence,
    et il photographie le disque pendant ce temps.
    """
    journal = tmp_path / "site.log"
    journal.touch()

    entre = threading.Event()
    sortir = threading.Event()
    vrai_compactage = SiteManager._compacter_journal

    def compactage_qui_patiente(fichier):
        entre.set()
        sortir.wait(10)
        return vrai_compactage(fichier)

    monkeypatch.setattr(
        SiteManager, "_compacter_journal", staticmethod(compactage_qui_patiente)
    )

    ligne = b"SITE_OUTPUT " + b"x" * (SITE_LOG_COMPACT_BYTES + 4096) + b"\n"
    flux = io.BufferedReader(io.BytesIO(ligne))
    fil = threading.Thread(
        target=SiteManager._capture_output, args=(flux, journal), daemon=True
    )
    fil.start()
    try:
        assert entre.wait(10), "aucun compactage : le témoin ne mesurerait rien"
        pic = journal.stat().st_size
    finally:
        sortir.set()
        fil.join(10)

    assert pic <= SITE_LOG_COMPACT_BYTES, (
        f"le journal occupe {pic} octets pendant le compactage, "
        f"pour une borne annoncée à {SITE_LOG_COMPACT_BYTES}"
    )


def test_le_journal_borne_garde_la_FIN_et_jamais_le_debut():
    """Une borne tenue ne dit pas que ce qu'on garde sert à quelque chose.

    La première version cessait d'écrire une fois la borne atteinte : la taille
    du fichier était juste, et le mégaoctet conservé était le moins utile. Un
    site qui bavarde puis plante perdait ENTIÈREMENT la trace de son plantage,
    parce qu'elle arrive en dernier — mesuré, pas supposé.

    Le témoin de taille qui existait passait dans les deux cas. C'est pourquoi
    celui-ci mesure ce qu'on GARDE : la dernière ligne écrite par le site doit
    se retrouver dans son journal, et la première doit être entière.
    """
    with tempfile.TemporaryDirectory() as base:
        journal = Path(base) / "site.log"
        bavardage = b"ligne de trafic ordinaire\n" * 400_000       # ~10 Mio
        plantage = b"TRACE-DU-PLANTAGE: RuntimeError: base absente\n"
        SiteManager._capture_output(io.BytesIO(bavardage + plantage), journal)

        contenu = journal.read_bytes()
        assert len(contenu) <= SITE_LOG_COMPACT_BYTES, len(contenu)
        assert len(contenu) < len(bavardage), "aucun compactage n'a eu lieu"
        assert b"TRACE-DU-PLANTAGE" in contenu, "la trace du plantage est perdue"
        assert contenu.rstrip(b"\n").split(b"\n")[-1].startswith(b"TRACE-DU-PLANTAGE")
        # Pas de fragment en tête : on le prendrait pour un message tronqué par
        # le site lui-même plutôt que par la borne.
        assert contenu.split(b"\n")[0] == b"ligne de trafic ordinaire"
