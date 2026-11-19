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
PUSHED_MIB = 200

#: What a server that BOUNDS is allowed to allocate on top. The platform's JSON
#: reader keeps nothing beyond 300 KiB; the relay, however, accumulates up to
#: its own bound because it must forward the body — hence two thresholds, each
#: derived from what the bound ALLOWS.
MARGE_MIB = 60
THRESHOLD_RELAY_MIB = SITE_MAX_BODY_BYTES / (1024 * 1024) + MARGE_MIB

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


def _rss_mib(pid):
    """The process's RESIDENT memory, in megabytes.

    `VmRSS` and not `VmSize`: a Python process's virtual memory says nothing of
    what it really occupies, and it moves for reasons unrelated to the body sent
    to it.
    """
    content = pathlib.Path(f"/proc/{pid}/status").read_text(encoding="utf-8")
    for line in content.splitlines():
        if line.startswith("VmRSS:"):
            return int(line.split()[1]) / 1024
    pytest.fail("VmRSS missing from /proc/<pid>/status: the measurement would be mute")


@contextlib.contextmanager
def _platform_measurable(workspace, **environment):
    """The platform in its OWN process, whose memory can be read.

    A server mounted in a thread of the pytest process would mix its memory with
    the suite's. The socket is bound here and passed to the child, point 140's
    discipline: the port never becomes free between choosing and listening.
    """
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    sock.listen(128)
    port = sock.getsockname()[1]
    descriptor = sock.fileno()
    os.set_inheritable(descriptor, True)

    env = os.environ.copy()
    env["PYTHONPATH"] = str(RACINE / "src")
    env["MONL_PLATFORM_WORKSPACE"] = str(workspace)
    env.update(environment)

    log = tempfile.TemporaryFile(mode="w+", encoding="utf-8", errors="replace")
    try:
        try:
            process = subprocess.Popen(
                [sys.executable, "-m", "uvicorn", "monl_platform.app:app",
                 "--fd", str(descriptor)],
                cwd=str(RACINE), env=env, pass_fds=(descriptor,),
                stdout=log, stderr=subprocess.STDOUT,
            )
        finally:
            sock.close()
        base = f"http://127.0.0.1:{port}"
        try:
            for _ in range(160):
                if process.poll() is not None:
                    pytest.fail(_diagnostic("the platform stopped", log))
                try:
                    if requests.get(base + "/health", timeout=1).status_code == 200:
                        break
                except requests.RequestException:
                    pass
                time.sleep(0.25)
            else:
                pytest.fail(_diagnostic("the platform never answered", log))
            yield base, process
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:  # pragma: no cover - filet
                    process.kill()
                    process.wait(timeout=5)
    finally:
        log.close()


def _diagnostic(header, log):
    log.seek(0)
    output = log.read().strip()
    return f"{header}\n--- sortie d'uvicorn ---\n{output or '(rien écrit)'}"


def _push_and_measure(base, path, pid, *, hote=None, mib=PUSHED_MIB):
    """Pushes `mio` megabytes chunked, sampling RSS during the send.

    In chunked mode, the server has NO way to know the size in advance: it is
    the only send that really tests cumulative reading. Sampling memory
    AFTERWARDS would prove nothing — Python does not necessarily return to the
    system what it freed, but it does not make visible either what it held for
    an instant.
    """
    block = b"x" * (1024 * 1024)
    login = http.client.HTTPConnection(base.removeprefix("http://"), timeout=180)
    pic = _rss_mib(pid)
    coupe_a = None
    try:
        login.putrequest("POST", path, skip_host=hote is not None,
                             skip_accept_encoding=True)
        if hote is not None:
            login.putheader("Host", hote)
        login.putheader("Content-Type", "application/json")
        login.putheader("Transfer-Encoding", "chunked")
        login.endheaders()
        for tour in range(mib):
            try:
                login.send(b"%x\r\n" % len(block) + block + b"\r\n")
            except OSError:
                coupe_a = tour
                break
            if tour % 10 == 0:
                pic = max(pic, _rss_mib(pid))
        pic = max(pic, _rss_mib(pid))
        if coupe_a is None:
            with contextlib.suppress(OSError):
                login.send(b"0\r\n\r\n")
        try:
            status = login.getresponse().status
        except Exception:
            status = None
    finally:
        login.close()
    return status, pic, coupe_a


def test_the_platform_refuses_a_huge_body_without_keeping_it(tmp_path):
    """The most serious case: an ANONYMOUS route, open to anyone.

    `/api/auth/register` requires no token. Without a stream bound, a single
    call made the server allocate the size of the sent body — measured at
    +397.6 MiB for 400 MiB pushed, with a 400 "invalid JSON body" as the answer.
    """
    with _platform_measurable(tmp_path / "projets") as (base, process):
        repos = _rss_mib(process.pid)
        status, pic, _ = _push_and_measure(base, "/api/auth/register",
                                             process.pid)
        growth = pic - repos

    # MEMORY first: that is the guarantee this file carries, and the status is
    # already guarded by `test_limite_corps_http.py`. Asserted second, it would
    # never be reached — the counter-proof would go red on the HTTP code, hence
    # for the same reason as the existing witness, and this file would guard
    # nothing more (point 170).
    assert growth < MARGE_MIB, (
        f"the server grew by {growth:.1f} MiB while receiving "
        f"{PUSHED_MIB} MiB: the body is materialized before being refused"
    )
    assert status == 413, f"response {status} instead of a size refusal"


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
    identities = IdentityStore(store.workspace)
    account = identities.register("memoire@monl.test", "MotDePasse-123")
    project_id = uuid.uuid4().hex
    identities.add_project(account["id"], project_id, "memoire")
    store.create_project(account["id"], project_id, "memoire")
    project = store.get_project(project_id)
    folder = project_directory(workspace, project["user_id"], project["project_id"])
    (folder / "spec.ml").write_text(SPEC, encoding="utf-8")
    compile_project(str(folder / "spec.ml"), str(folder))

    with _platform_measurable(workspace, MONL_PLATFORM_DOMAIN="localhost") as (
            base, process):
        # The site must be running: the bound lives AFTER host resolution. The
        # warm-up targets `/note`, which exists ONLY on the site —
        # `/openapi.json` would have answered 200 from the PLATFORM without the
        # relay even being called, and the warm-up would have certified the
        # opposite of what it measures.
        warmup = requests.get(base + "/note",
                              headers={"Host": "memoire.localhost"}, timeout=60)
        assert warmup.status_code == 200, (
            f"the relay did not reach the site ({warmup.status_code}): "
            f"{warmup.text[:200]}")
        repos = _rss_mib(process.pid)
        status, pic, _ = _push_and_measure(base, "/note", process.pid,
                                             hote="memoire.localhost")
        growth = pic - repos

    assert growth < THRESHOLD_RELAY_MIB, (
        f"the relay grew by {growth:.1f} MiB while receiving "
        f"{PUSHED_MIB} MiB: it accumulates beyond its own bound"
    )
    assert status == 413, f"response {status} instead of a size refusal"
