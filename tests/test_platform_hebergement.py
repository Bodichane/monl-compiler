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

import http.client
import io
import tempfile
import time
import uuid
from pathlib import Path

import pytest

from monl.cli import compile_project
from monl_platform.hosting import (
    SITE_LOG_COMPACT_BYTES,
    SiteManager,
    SiteNotCompiledError,
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
