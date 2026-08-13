"""Preuves d'exécution des briques de déploiement du backend généré."""

import contextlib
import json
import os
import socket
import subprocess
import sys
import time

import pytest
import requests

from monl.cli import compile_project

SPEC = """app Deploiement

entity Note
    titre: String

actor Membre selfRegister

workflow Ecrire for Membre
    Create Note
"""


def _port_libre():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _environnement(**valeurs):
    env = os.environ.copy()
    for nom in ("MONL_CORS_ORIGINS", "MONL_LOG_FORMAT", "MONL_ENV",
                "MONL_JWT_SECRET"):
        env.pop(nom, None)
    env.update({nom: valeur for nom, valeur in valeurs.items() if valeur is not None})
    return env


@contextlib.contextmanager
def _serveur(projet, module="app:app", **variables):
    port = _port_libre()
    processus = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", module, "--host", "127.0.0.1",
         "--port", str(port), "--no-access-log"],
        cwd=str(projet), env=_environnement(**variables),
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(100):
            if processus.poll() is not None:
                sortie = processus.stdout.read() if processus.stdout else ""
                pytest.fail(f"serveur arrêté au démarrage :\n{sortie}")
            try:
                reponse = requests.get(f"{base}/health", timeout=1)
                if reponse.status_code == 200:
                    break
            except requests.RequestException:
                time.sleep(0.05)
        else:
            pytest.fail("serveur non démarré")
        yield base, processus
    finally:
        if processus.poll() is None:
            processus.terminate()
        try:
            sortie, _ = processus.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            processus.kill()
            sortie, _ = processus.communicate(timeout=5)
        processus._monl_sortie = sortie


@pytest.fixture
def projet(tmp_path):
    spec = tmp_path / "spec.ml"
    spec.write_text(SPEC, encoding="utf-8")
    compile_project(str(spec), str(tmp_path))
    return tmp_path


def test_sante_et_readiness_sont_accessibles_sans_jeton(projet):
    with _serveur(projet) as (base, _processus):
        vivacite = requests.get(f"{base}/health", timeout=5)
        readiness = requests.get(f"{base}/health/ready", timeout=5)

    assert vivacite.status_code == 200
    assert vivacite.json() == {"status": "ok"}
    assert readiness.status_code == 200
    assert readiness.json() == {"status": "ready"}


def test_readiness_renvoie_503_si_la_base_devient_inaccessible(projet):
    with _serveur(projet) as (base, _processus):
        base_de_donnees = projet / "app.db"
        sauvegarde = projet / "app.db.sauvegarde-a3"
        base_de_donnees.rename(sauvegarde)
        base_de_donnees.mkdir()
        try:
            reponse = requests.get(f"{base}/health/ready", timeout=5)
        finally:
            base_de_donnees.rmdir()
            sauvegarde.rename(base_de_donnees)

    assert reponse.status_code == 503
    assert reponse.json() == {"detail": "Service indisponible"}


def test_cors_est_absent_sans_variable(projet):
    with _serveur(projet) as (base, _processus):
        reponse = requests.get(f"{base}/health", headers={"Origin": "https://client.test"},
                               timeout=5)

    assert reponse.status_code == 200
    assert "access-control-allow-origin" not in reponse.headers


def test_cors_nautorise_que_lorigine_declaree(projet):
    with _serveur(projet, MONL_CORS_ORIGINS="https://client.test, https://admin.test") as (
        base, _processus
    ):
        reponse = requests.get(f"{base}/health", headers={"Origin": "https://client.test"},
                               timeout=5)

    assert reponse.status_code == 200
    assert reponse.headers["access-control-allow-origin"] == "https://client.test"
    assert reponse.headers["access-control-allow-credentials"] == "true"


def test_cors_refuse_etoile_au_demarrage(projet):
    processus = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app:app", "--host", "127.0.0.1",
         "--port", str(_port_libre()), "--no-access-log"],
        cwd=str(projet), env=_environnement(MONL_CORS_ORIGINS="*"),
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    sortie, _ = processus.communicate(timeout=10)

    assert processus.returncode != 0
    assert "MONL_CORS_ORIGINS" in sortie
    assert "origine '*'" in sortie


def test_logs_json_sont_structures_et_ne_contiennent_pas_le_mot_de_passe(projet):
    mot_de_passe = "MotDePasse-A3-NE-JAMAIS-JOURNALISER"
    with _serveur(projet, MONL_LOG_FORMAT="json") as (base, processus):
        inscription = requests.post(
            f"{base}/register", timeout=5,
            json={"username": "log@exemple.test", "password": mot_de_passe,
                  "actor": "Membre"},
        )
        assert inscription.status_code == 200
        reponse = requests.get(
            f"{base}/health", headers={"X-Request-ID": "demande-A3"}, timeout=5)
        assert reponse.status_code == 200
        assert reponse.headers["X-Request-ID"] == "demande-A3"
    sortie = getattr(processus, "_monl_sortie", "")

    assert mot_de_passe not in sortie
    lignes_json = []
    for ligne in sortie.splitlines():
        try:
            objet = json.loads(ligne)
        except json.JSONDecodeError:
            continue
        if "request_id" in objet:
            lignes_json.append(objet)
    assert lignes_json
    assert all({"timestamp", "method", "path", "status_code", "duration_ms",
                "request_id"} <= set(objet) for objet in lignes_json)
    assert any(objet["request_id"] == "demande-A3" for objet in lignes_json)


def test_production_sans_secret_refuse_le_demarrage(projet):
    processus = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app:app", "--host", "127.0.0.1",
         "--port", str(_port_libre()), "--no-access-log"],
        cwd=str(projet), env=_environnement(MONL_ENV="production"),
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    sortie, _ = processus.communicate(timeout=10)

    assert processus.returncode != 0
    assert "MONL_JWT_SECRET" in sortie


def test_dockerfile_et_dockerignore_sont_crees_et_preserves(projet):
    dockerfile = projet / "Dockerfile"
    dockerignore = projet / ".dockerignore"
    assert dockerfile.exists()
    assert dockerignore.exists()
    contenu_dockerignore = dockerignore.read_text(encoding="utf-8")
    for motif in (".jwt_secret", "*.db", "__pycache__", "frontend.precedent/"):
        assert motif in contenu_dockerignore

    dockerfile.write_text("FROM image-adaptee\n", encoding="utf-8")
    dockerignore.write_text(".jwt_secret\n# adaptation locale\n", encoding="utf-8")
    compile_project(str(projet / "spec.ml"), str(projet))

    assert dockerfile.read_text(encoding="utf-8") == "FROM image-adaptee\n"
    assert dockerignore.read_text(encoding="utf-8") == ".jwt_secret\n# adaptation locale\n"


def test_les_healthchecks_ne_sont_pas_dans_le_contrat_frontend(projet):
    contract = json.loads((projet / "frontend_contract.json").read_text(encoding="utf-8"))
    chemins = {route["path"] for route in contract["routes"]}

    assert "/health" not in chemins
    assert "/health/ready" not in chemins


# --------------------------------------------------------------------------
# POINT 133 : le conteneur sert le SITE, pas seulement l'API
# --------------------------------------------------------------------------

def test_le_wrapper_est_ecrit_des_la_compilation(projet):
    """Il n'était écrit que par 'monl run'. Le Dockerfile, lui, est produit par
    'monl compile' : l'image ne pouvait donc pas le lancer."""
    wrapper = projet / "serve.py"
    assert wrapper.exists()
    etat = json.loads((projet / "monl.json").read_text(encoding="utf-8"))
    assert "serve.py" in etat["backend_sha256"], (
        "le wrapper décide quels dossiers sont servis : il doit être scellé "
        "comme le reste du backend généré")


def test_le_conteneur_lance_le_wrapper_et_non_lapi_nue(projet):
    contenu = (projet / "Dockerfile").read_text(encoding="utf-8")
    assert '"serve:app"' in contenu
    assert '"app:app"' not in contenu


def test_un_dockerfile_herite_est_rafraichi(projet):
    """Un gabarit jamais touché se rafraîchit ; un fichier personnalisé non
    (c'est le test voisin qui garde ce second versant). Sans ce rattrapage,
    tout projet déjà compilé garderait un conteneur qui répond 404 sur /site,
    et rien ne le lui dirait."""
    from monl.cli import DOCKERFILES_HERITES
    dockerfile = projet / "Dockerfile"
    dockerfile.write_text(DOCKERFILES_HERITES[0], encoding="utf-8")
    compile_project(str(projet / "spec.ml"), str(projet))
    assert '"serve:app"' in dockerfile.read_text(encoding="utf-8")


def test_le_wrapper_est_protege_de_lia():
    """Il est là quand l'agent d'interface passe, et c'est LUI qui décide
    quels dossiers sont servis."""
    from monl.frontend_ai import PROTECTED_ARTEFACTS
    assert "serve.py" in PROTECTED_ARTEFACTS


def test_le_wrapper_demarre_sans_frontend(projet):
    """L'interface est construite APRÈS la compilation : le wrapper doit
    démarrer avant qu'elle n'existe, sinon l'image ne démarrerait pas du tout.
    Et l'absence est DITE — un /site en 404 muet est le défaut que ce wrapper
    existe pour empêcher."""
    assert not (projet / "frontend").exists()
    with _serveur(projet, module="serve:app") as (base, processus):
        assert requests.get(f"{base}/health", timeout=5).status_code == 200
        assert requests.get(f"{base}/site/", timeout=5).status_code == 404
    assert "frontend/ absent" in (processus._monl_sortie or "")


def test_le_wrapper_sert_le_site_quand_le_frontend_existe(projet):
    frontend = projet / "frontend"
    frontend.mkdir()
    (frontend / "index.html").write_text(
        "<!doctype html><title>Vitrine</title><p>ok", encoding="utf-8")
    with _serveur(projet, module="serve:app") as (base, _processus):
        page = requests.get(f"{base}/site/", timeout=5)
        assert page.status_code == 200
        assert "Vitrine" in page.text


# --------------------------------------------------------------------------
# POINT 134 : le scellé du wrapper, jusqu'au bout
# --------------------------------------------------------------------------

def test_un_artefact_scelle_mais_absent_fait_echouer_la_coherence(projet):
    """La boucle ne comparait un artefact que s'il EXISTAIT : un fichier
    disparu ne disait rien. Depuis le point 133, 'monl run --check' pouvait
    donc certifier « cohérence vérifiée » sur un projet dont le Dockerfile
    lance `serve:app` alors que le module n'est plus là. Le trou valait aussi
    pour manage.py et sandbox_ai.py — il ne se voyait pas parce qu'aucun
    artefact n'était encore désigné par le conteneur."""
    from monl.cli import check_coherence
    (projet / "serve.py").unlink()
    ok, erreurs, _ = check_coherence(str(projet))
    assert not ok
    assert any("serve.py" in e and "absent" in e for e in erreurs), erreurs


def test_monl_run_ninvalide_pas_letat_quil_vient_de_verifier(projet, monkeypatch):
    """'monl run' réécrivait le wrapper à chaque lancement. Depuis qu'il est
    scellé, cette réécriture se retournait contre le projet : qu'une version
    ultérieure de monl change le rendu, et le lancement SUIVANT refusait de
    démarrer en accusant à tort une « modification à la main »."""
    import monl.cli as cli
    from monl.cli import check_coherence, cmd_run
    rendu = cli.rendre_wrapper
    monkeypatch.setattr(cli, "rendre_wrapper",
                        lambda a=None: rendu(a) + "\n# version ultérieure\n")
    monkeypatch.setattr(cli.subprocess, "run", lambda *a, **k: None)

    cmd_run(str(projet), skip_smoke=True)

    ok, erreurs, _ = check_coherence(str(projet))
    assert ok, erreurs


def test_un_projet_ancien_recoit_son_wrapper_au_lancement(projet, monkeypatch):
    """Le pendant du test précédent : ne plus réécrire ne doit pas priver de
    wrapper un projet compilé par un monl antérieur, qui n'en a pas et dont
    l'état n'en scelle aucun. Il n'a rien à contredire, donc on l'écrit."""
    import monl.cli as cli
    from monl.cli import cmd_run
    (projet / "serve.py").unlink()
    etat = json.loads((projet / "monl.json").read_text(encoding="utf-8"))
    etat["backend_sha256"].pop("serve.py")
    (projet / "monl.json").write_text(json.dumps(etat, indent=2), encoding="utf-8")
    monkeypatch.setattr(cli.subprocess, "run", lambda *a, **k: None)

    cmd_run(str(projet), skip_smoke=True)

    assert (projet / "serve.py").exists()


def test_le_gabarit_herite_upload_est_rafraichi_aussi(projet):
    """Deux gabarits ont réellement été émis dans l'histoire du dépôt : la
    forme de base et la variante Upload. Ne rattraper que la première
    laisserait tout projet à téléversement avec un conteneur en 404."""
    from monl.cli import DOCKERFILES_HERITES
    dockerfile = projet / "Dockerfile"
    dockerfile.write_text(DOCKERFILES_HERITES[1], encoding="utf-8")
    compile_project(str(projet / "spec.ml"), str(projet))
    assert '"serve:app"' in dockerfile.read_text(encoding="utf-8")
