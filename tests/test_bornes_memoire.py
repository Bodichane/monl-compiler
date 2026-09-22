"""Une borne de corps se mesure en MÉMOIRE, jamais en code de retour.

Les deux témoins qui gardent déjà ces bornes — `test_limite_corps_http.py`
(point 186) et `test_platform_hebergement.py` — vérifient qu'un corps trop gros
reçoit un 413. **Ils seraient verts sur un serveur qui avale tout avant de
refuser** : le code HTTP est ce que la borne CONTRAINT, la mémoire est ce
qu'elle SERT. C'est le reproche du point 172, transposé.

Mesuré en écrivant ce fichier, sur `/api/auth/register` (route ANONYME) avec
400 Mio poussés en chunked :

===================  ==============  ================
                     RSS au pic      réponse
===================  ==============  ================
avec la borne        +1,6 Mio        413
borne désarmée       +397,6 Mio      400
===================  ==============  ================

L'ancien code avalait 400 Mio pour finalement répondre « corps JSON
invalide ». Un seul appel non authentifié, et la plateforme tourne sur un vieux
PC.

**Pas d'étalonnage de bruit ici**, contrairement aux oracles temporels des
points 160 et 168 : l'écart mesuré est d'un facteur 250, et la mémoire d'un
processus au repos ne varie pas de dizaines de mégaoctets. Un seuil fixe,
largement au-dessus de ce que le serveur alloue légitimement, suffit — et
c'est ce qui rend ces témoins stables en CI.
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

#: Ce qu'on pousse. Très au-dessus des deux bornes (300 Kio et 40 Mio), et
#: assez pour que l'absence de borne se voie sans ambiguïté.
POUSSE_MIO = 200

#: Ce qu'un serveur qui BORNE a le droit d'allouer en plus. Le lecteur JSON de
#: la plateforme ne garde rien au-delà de 300 Kio ; le relais, lui, accumule
#: jusqu'à sa propre borne parce qu'il doit retransmettre le corps — d'où deux
#: seuils, chacun dérivé de ce que la borne AUTORISE.
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
    """La mémoire RÉSIDENTE du processus, en mégaoctets.

    `VmRSS` et pas `VmSize` : la mémoire virtuelle d'un processus Python ne dit
    rien de ce qu'il occupe vraiment, et elle bouge pour des raisons qui n'ont
    aucun rapport avec le corps qu'on lui envoie.
    """
    contenu = pathlib.Path(f"/proc/{pid}/status").read_text(encoding="utf-8")
    for ligne in contenu.splitlines():
        if ligne.startswith("VmRSS:"):
            return int(ligne.split()[1]) / 1024
    pytest.fail("VmRSS absent de /proc/<pid>/status : la mesure serait muette")


@contextlib.contextmanager
def _plateforme_mesurable(workspace, **environnement):
    """La plateforme dans son PROPRE processus, dont on peut lire la mémoire.

    Un serveur monté dans un fil du processus pytest mélangerait sa mémoire à
    celle de la suite. La socket est liée ici et passée à l'enfant, discipline
    du point 140 : le port ne redevient jamais libre entre le choix et
    l'écoute.
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


def _pousser_et_mesurer(base, chemin, pid, *, hote=None, mio=POUSSE_MIO):
    """Pousse `mio` mégaoctets en chunked, en relevant la RSS pendant l'envoi.

    En chunked, le serveur n'a AUCUN moyen de connaître la taille à l'avance :
    c'est le seul envoi qui éprouve vraiment la lecture cumulative. Relever la
    mémoire APRÈS coup ne prouverait rien — Python ne rend pas forcément au
    système ce qu'il a libéré, mais il ne rend pas non plus visible ce qu'il a
    tenu un instant.
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


def test_la_plateforme_refuse_un_corps_enorme_sans_le_garder(tmp_path):
    """Le cas le plus grave : une route ANONYME, ouverte à quiconque.

    `/api/auth/register` n'exige aucun jeton. Sans borne de flux, un seul appel
    faisait allouer au serveur la taille du corps envoyé — mesuré à +397,6 Mio
    pour 400 Mio poussés, avec un 400 « corps JSON invalide » en guise de
    réponse.
    """
    with _plateforme_mesurable(tmp_path / "projets") as (base, processus):
        repos = _rss_mio(processus.pid)
        statut, pic, _ = _pousser_et_mesurer(base, "/api/auth/register",
                                             processus.pid)
        croissance = pic - repos

    # La MÉMOIRE d'abord : c'est la garantie que ce fichier porte, et le
    # statut est déjà gardé par `test_limite_corps_http.py`. Assertée en
    # second, elle ne serait jamais atteinte — la contre-épreuve rougirait sur
    # le code HTTP, donc pour la même raison que le témoin existant, et ce
    # fichier ne garderait rien de plus (point 170).
    assert croissance < MARGE_MIO, (
        f"le serveur a grossi de {croissance:.1f} Mio en recevant "
        f"{POUSSE_MIO} Mio : le corps est matérialisé avant d'être refusé"
    )
    assert statut == 413, f"réponse {statut} au lieu d'un refus de taille"


def test_le_relais_refuse_un_corps_enorme_sans_le_garder(tmp_path):
    """Le relais accumule par NÉCESSITÉ — il doit retransmettre le corps.

    Sa borne ne promet donc pas « rien en mémoire » mais « au plus
    SITE_MAX_BODY_BYTES par requête en vol », et le seuil de ce témoin est
    DÉRIVÉ de la constante plutôt qu'écrit à la main : relever la borne sans
    toucher au témoin ferait mentir le témoin.

    **La limite qui reste, et qui est énoncée** : plusieurs requêtes
    simultanées multiplient cette empreinte. La fermer demanderait de relayer
    en flux plutôt que d'accumuler — un autre chantier, qui se traite aussi en
    amont chez le serveur frontal (`client_max_body_size`).
    """
    # TOUT sous le même dossier : la plateforme du sous-processus lit sa base
    # dans `MONL_PLATFORM_WORKSPACE/platform.sqlite3`. Un store créé ailleurs
    # donnerait deux bases, le projet resterait introuvable, et le relais ne
    # serait jamais atteint — mesuré en écrivant ce test.
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
        # Le site doit tourner : la borne vit APRÈS la résolution de l'hôte.
        # L'amorce vise `/note`, qui n'existe QUE sur le site — `/openapi.json`
        # aurait répondu 200 depuis la PLATEFORME sans que le relais soit même
        # sollicité, et l'amorce aurait certifié le contraire de ce qu'elle
        # mesure.
        amorce = requests.get(base + "/note",
                              headers={"Host": "memoire.localhost"}, timeout=60)
        assert amorce.status_code == 200, (
            f"le relais n'a pas atteint le site ({amorce.status_code}) : "
            f"{amorce.text[:200]}")
        repos = _rss_mio(processus.pid)
        statut, pic, _ = _pousser_et_mesurer(base, "/note", processus.pid,
                                             hote="memoire.localhost")
        croissance = pic - repos

    assert croissance < SEUIL_RELAIS_MIO, (
        f"le relais a grossi de {croissance:.1f} Mio en recevant "
        f"{POUSSE_MIO} Mio : il accumule au-delà de sa propre borne"
    )
    assert statut == 413, f"réponse {statut} au lieu d'un refus de taille"
