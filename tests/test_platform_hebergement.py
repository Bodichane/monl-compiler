"""Démarrer un projet, c'est démarrer son BACKEND COMPILÉ — pas un build IA.

POINT 161. Tant que la plateforme construisait le frontend, « héberger »
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
import uuid

import pytest

from monl.cli import compile_project
from monl_platform.hosting import SiteManager, SiteNotCompiledError
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
