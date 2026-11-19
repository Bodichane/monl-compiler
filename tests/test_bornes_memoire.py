"""A body bound is measured in MEMORY, never by status code.

The two witnesses already guarding these bounds — `test_limite_corps_http.py`
(point 186) and `test_platform_hebergement.py` — check that a too-large body
gets a 413. **They would be green on a server that swallows everything before
refusing**: the HTTP code is what the bound CONSTRAINS, memory is what it
SERVES. It is point 172's complaint, transposed.

Measured while writing this file, on `/api/auth/register` (ANONYMOUS route)
with 400 MiB pushed chunked:

===================  ==============  ================
                     peak RSS        response
===================  ==============  ================
with the bound       +1.6 MiB        413
bound disarmed       +397.6 MiB      400
===================  ==============  ================

The old code swallowed 400 MiB to finally answer "invalid JSON body". A
single unauthenticated call, and the platform runs on an old PC.

**No noise calibration here**, unlike the time oracles of points 160 and 168:
the measured gap is a factor of 250, and an idle process's memory does not
vary by tens of megabytes. A fixed threshold, well above what the server
legitimately allocates, is enough — and that is what makes these witnesses
stable in CI.
"""

import contextlib
import http.client
import os
import pathlib
import socket
import subprocess
import sys
import tempfile
import time
import uuid

import pytest
import requests

from monl.cli import compile_project
from monl_platform.builder_host import SITE_MAX_BODY_BYTES
from monl_platform.identity import IdentityStore
from monl_platform.paths import project_directory
from monl_platform.store import PlatformStore

RACINE = pathlib.Path(__file__).resolve().parent.parent

pytestmark = pytest.mark.skipif(
    not pathlib.Path("/proc/self/status").is_file(),
    reason="/proc absent : la mémoire d'un processus ne se mesure pas hors Linux",
)

#: What we push. Far above both bounds (300 KiB and 40 MiB), and enough for the
#: absence of a bound to show unambiguously.
POUSSE_MIO = 200

#: What a server that BOUNDS is allowed to allocate on top. The platform's JSON
#: reader keeps nothing beyond 300 KiB; the relay, however, accumulates up to
#: its own bound because it must forward the body — hence two thresholds, each
#: derived from what the bound ALLOWS.
MARGE_MIO = 60
SEUIL_RELAIS_MIO = SITE_MAX_BODY_BYTES / (1024 * 1024) + MARGE_MIO

SPEC = """app BancMemoire

entity Note
    titre: String

actor Membre selfRegister

rule Note.titre required
rule Note.Read public

workflow GererNotes for Membre
    Create Note
    Read Note

landing
    brief: "Banc d'essai des bornes de corps."
    link "Contact": "mailto:contact@monl.test"
"""


def _rss_mio(pid):
    """The process's RESIDENT memory, in megabytes.

    `VmRSS` and not `VmSize`: a Python process's virtual memory says nothing of
    what it really occupies, and it moves for reasons unrelated to the body sent
    to it.
    """
    contenu = pathlib.Path(f"/proc/{pid}/status").read_text(encoding="utf-8")
    for ligne in contenu.splitlines():
        if ligne.startswith("VmRSS:"):
            return int(ligne.split()[1]) / 1024
    pytest.fail("VmRSS absent de /proc/<pid>/status : la mesure serait muette")


@contextlib.contextmanager
def _plateforme_mesurable(workspace, **environnement):
    """The platform in its OWN process, whose memory can be read.

    A server mounted in a thread of the pytest process would mix its memory with
    the suite's. The socket is bound here and passed to the child, point 140's
    discipline: the port never becomes free between choosing and listening.
    """
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    sock.listen(128)
    port = sock.getsockname()[1]
    descripteur = sock.fileno()
    os.set_inheritable(descripteur, True)

    env = os.environ.copy()
    env["PYTHONPATH"] = str(RACINE / "src")
    env["MONL_PLATFORM_WORKSPACE"] = str(workspace)
    env.update(environnement)

    journal = tempfile.TemporaryFile(mode="w+", encoding="utf-8", errors="replace")
    try:
        try:
            processus = subprocess.Popen(
                [sys.executable, "-m", "uvicorn", "monl_platform.app:app",
                 "--fd", str(descripteur)],
                cwd=str(RACINE), env=env, pass_fds=(descripteur,),
                stdout=journal, stderr=subprocess.STDOUT,
            )
        finally:
            sock.close()
        base = f"http://127.0.0.1:{port}"
        try:
            for _ in range(160):
                if processus.poll() is not None:
                    pytest.fail(_diagnostic("la plateforme s'est arrêtée", journal))
                try:
                    if requests.get(base + "/health", timeout=1).status_code == 200:
                        break
                except requests.RequestException:
                    pass
                time.sleep(0.25)
            else:
                pytest.fail(_diagnostic("la plateforme n'a jamais répondu", journal))
            yield base, processus
        finally:
            if processus.poll() is None:
                processus.terminate()
                try:
                    processus.wait(timeout=10)
                except subprocess.TimeoutExpired:  # pragma: no cover - filet
                    processus.kill()
                    processus.wait(timeout=5)
    finally:
        journal.close()


def _diagnostic(entete, journal):
    journal.seek(0)
    sortie = journal.read().strip()
    return f"{entete}\n--- sortie d'uvicorn ---\n{sortie or '(rien écrit)'}"


def _push_and_measure(base, chemin, pid, *, hote=None, mio=POUSSE_MIO):
    """Pushes `mio` megabytes chunked, sampling RSS during the send.

    In chunked mode, the server has NO way to know the size in advance: it is
    the only send that really tests cumulative reading. Sampling memory
    AFTERWARDS would prove nothing — Python does not necessarily return to the
    system what it freed, but it does not make visible either what it held for
    an instant.
    """
    bloc = b"x" * (1024 * 1024)
    connexion = http.client.HTTPConnection(base.removeprefix("http://"), timeout=180)
    pic = _rss_mio(pid)
    coupe_a = None
    try:
        connexion.putrequest("POST", chemin, skip_host=hote is not None,
                             skip_accept_encoding=True)
        if hote is not None:
            connexion.putheader("Host", hote)
        connexion.putheader("Content-Type", "application/json")
        connexion.putheader("Transfer-Encoding", "chunked")
        connexion.endheaders()
        for tour in range(mio):
            try:
                connexion.send(b"%x\r\n" % len(bloc) + bloc + b"\r\n")
            except OSError:
                coupe_a = tour
                break
            if tour % 10 == 0:
                pic = max(pic, _rss_mio(pid))
        pic = max(pic, _rss_mio(pid))
        if coupe_a is None:
            with contextlib.suppress(OSError):
                connexion.send(b"0\r\n\r\n")
        try:
            statut = connexion.getresponse().status
        except Exception:
            statut = None
    finally:
        connexion.close()
    return statut, pic, coupe_a


def test_the_platform_refuses_a_huge_body_without_keeping_it(tmp_path):
    """The most serious case: an ANONYMOUS route, open to anyone.

    `/api/auth/register` requires no token. Without a stream bound, a single
    call made the server allocate the size of the sent body — measured at
    +397.6 MiB for 400 MiB pushed, with a 400 "invalid JSON body" as the answer.
    """
    with _plateforme_mesurable(tmp_path / "projets") as (base, processus):
        repos = _rss_mio(processus.pid)
        statut, pic, _ = _push_and_measure(base, "/api/auth/register",
                                             processus.pid)
        croissance = pic - repos

    # MEMORY first: that is the guarantee this file carries, and the status is
    # already guarded by `test_limite_corps_http.py`. Asserted second, it would
    # never be reached — the counter-proof would go red on the HTTP code, hence
    # for the same reason as the existing witness, and this file would guard
    # nothing more (point 170).
    assert croissance < MARGE_MIO, (
        f"le serveur a grossi de {croissance:.1f} Mio en recevant "
        f"{POUSSE_MIO} Mio : le corps est matérialisé avant d'être refusé"
    )
    assert statut == 413, f"réponse {statut} au lieu d'un refus de taille"


def test_the_relay_refuses_a_huge_body_without_keeping_it(tmp_path):
    """The relay accumulates by NECESSITY — it must forward the body.

    Its bound therefore promises not "nothing in memory" but "at most
    SITE_MAX_BODY_BYTES per in-flight request", and this witness's threshold is
    DERIVED from the constant rather than hand-written: raising the bound without
    touching the witness would make the witness lie.

    **The limit that remains, and is stated**: several simultaneous requests
    multiply this footprint. Closing it would require relaying as a stream
    rather than accumulating — another project, also handled upstream at the
    front server (`client_max_body_size`).
    """
    # EVERYTHING under the same folder: the subprocess platform reads its
    # database in `MONL_PLATFORM_WORKSPACE/platform.sqlite3`. A store created
    # elsewhere would give two databases, the project would stay unfindable,
    # and the relay would never be reached — measured while writing this test.
    workspace = tmp_path / "projets"
    store = PlatformStore(workspace)
    identites = IdentityStore(store.workspace)
    compte = identites.register("memoire@monl.test", "MotDePasse-123")
    project_id = uuid.uuid4().hex
    identites.add_project(compte["id"], project_id, "memoire")
    store.create_project(compte["id"], project_id, "memoire")
    projet = store.get_project(project_id)
    dossier = project_directory(workspace, projet["user_id"], projet["project_id"])
    (dossier / "spec.ml").write_text(SPEC, encoding="utf-8")
    compile_project(str(dossier / "spec.ml"), str(dossier))

    with _plateforme_mesurable(workspace, MONL_PLATFORM_DOMAIN="localhost") as (
            base, processus):
        # The site must be running: the bound lives AFTER host resolution. The
        # warm-up targets `/note`, which exists ONLY on the site —
        # `/openapi.json` would have answered 200 from the PLATFORM without the
        # relay even being called, and the warm-up would have certified the
        # opposite of what it measures.
        amorce = requests.get(base + "/note",
                              headers={"Host": "memoire.localhost"}, timeout=60)
        assert amorce.status_code == 200, (
            f"le relais n'a pas atteint le site ({amorce.status_code}) : "
            f"{amorce.text[:200]}")
        repos = _rss_mio(processus.pid)
        statut, pic, _ = _push_and_measure(base, "/note", processus.pid,
                                             hote="memoire.localhost")
        croissance = pic - repos

    assert croissance < SEUIL_RELAIS_MIO, (
        f"le relais a grossi de {croissance:.1f} Mio en recevant "
        f"{POUSSE_MIO} Mio : il accumule au-delà de sa propre borne"
    )
    assert statut == 413, f"réponse {statut} au lieu d'un refus de taille"
