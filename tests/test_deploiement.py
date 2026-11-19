"""Execution proofs of the generated backend's deployment bricks."""

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


def test_health_and_readiness_are_reachable_without_token(projet):
    with _serveur(projet) as (base, _processus):
        vivacite = requests.get(f"{base}/health", timeout=5)
        readiness = requests.get(f"{base}/health/ready", timeout=5)

    assert vivacite.status_code == 200
    assert vivacite.json() == {"status": "ok"}
    assert readiness.status_code == 200
    assert readiness.json() == {"status": "ready"}


def test_readiness_returns_503_if_the_database_becomes_unreachable(projet):
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


def test_cors_is_absent_without_variable(projet):
    with _serveur(projet) as (base, _processus):
        reponse = requests.get(f"{base}/health", headers={"Origin": "https://client.test"},
                               timeout=5)

    assert reponse.status_code == 200
    assert "access-control-allow-origin" not in reponse.headers


def test_cors_only_allows_the_declared_origin(projet):
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
    assert "origin '*'" in sortie


def test_json_logs_are_structured_and_do_not_contain_the_password(projet):
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


def test_production_without_secret_refuses_to_start(projet):
    processus = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app:app", "--host", "127.0.0.1",
         "--port", str(_port_libre()), "--no-access-log"],
        cwd=str(projet), env=_environnement(MONL_ENV="production"),
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    sortie, _ = processus.communicate(timeout=10)

    assert processus.returncode != 0
    assert "MONL_JWT_SECRET" in sortie


def test_a_project_delivered_without_secret_creates_it_at_first_start(projet):
    (projet / ".jwt_secret").unlink()

    with _serveur(projet) as (base, _processus):
        assert requests.get(f"{base}/health", timeout=5).status_code == 200

    secret = projet / ".jwt_secret"
    assert secret.is_file()
    assert len(secret.read_text(encoding="utf-8").strip()) == 64
    assert secret.stat().st_mode & 0o077 == 0


def test_dockerfile_and_dockerignore_are_created_and_preserved(projet):
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


def test_healthchecks_are_not_in_the_frontend_contract(projet):
    contract = json.loads((projet / "frontend_contract.json").read_text(encoding="utf-8"))
    chemins = {route["path"] for route in contract["routes"]}

    assert "/health" not in chemins
    assert "/health/ready" not in chemins


# --------------------------------------------------------------------------
# POINT 133: the container serves the SITE, not only the API
# --------------------------------------------------------------------------

def test_the_wrapper_is_written_at_compile_time(projet):
    """It was only written by 'monl run'. The Dockerfile, however, is produced by
    'monl compile': the image therefore could not start it."""
    wrapper = projet / "serve.py"
    assert wrapper.exists()
    etat = json.loads((projet / "monl.json").read_text(encoding="utf-8"))
    assert "serve.py" in etat["backend_sha256"], (
        "le wrapper décide quels dossiers sont servis : il doit être scellé "
        "comme le reste du backend généré")


def test_the_container_runs_the_wrapper_not_the_bare_api(projet):
    contenu = (projet / "Dockerfile").read_text(encoding="utf-8")
    assert '"serve:app"' in contenu
    assert '"app:app"' not in contenu


def test_an_inherited_dockerfile_is_refreshed(projet):
    """A never-touched template is refreshed; a customized file is not (the
    neighboring test guards that second side). Without this catch-up, every
    already compiled project would keep a container answering 404 on /site, and
    nothing would tell it."""
    from monl.cli import DOCKERFILES_HERITES
    dockerfile = projet / "Dockerfile"
    dockerfile.write_text(DOCKERFILES_HERITES[0], encoding="utf-8")
    compile_project(str(projet / "spec.ml"), str(projet))
    assert '"serve:app"' in dockerfile.read_text(encoding="utf-8")


def test_the_wrapper_is_protected_from_the_ai():
    """It is there when the interface agent passes, and IT decides which folders
    are served."""
    from monl.frontend_ai import PROTECTED_ARTEFACTS
    assert "serve.py" in PROTECTED_ARTEFACTS


def test_the_wrapper_starts_without_frontend(projet):
    """The interface is built AFTER compilation: the wrapper must start before it
    exists, otherwise the image would not start at all. And the absence is SAID —
    a silent 404 /site is the defect this wrapper exists to prevent."""
    assert not (projet / "frontend").exists()
    with _serveur(projet, module="serve:app") as (base, processus):
        assert requests.get(f"{base}/health", timeout=5).status_code == 200
        assert requests.get(f"{base}/site/", timeout=5).status_code == 404
    assert "frontend/ missing" in (processus._monl_sortie or "")


def test_the_wrapper_serves_the_site_when_the_frontend_exists(projet):
    frontend = projet / "frontend"
    frontend.mkdir()
    (frontend / "index.html").write_text(
        "<!doctype html><title>Vitrine</title><p>ok", encoding="utf-8")
    with _serveur(projet, module="serve:app") as (base, _processus):
        page = requests.get(f"{base}/site/", timeout=5)
        assert page.status_code == 200
        assert "Vitrine" in page.text


# --------------------------------------------------------------------------
# POINT 134: the wrapper's seal, all the way
# --------------------------------------------------------------------------

def test_a_sealed_but_missing_artifact_fails_consistency(projet):
    """The loop only compared an artifact if it EXISTED: a vanished file said
    nothing. Since point 133, 'monl run --check' could therefore certify
    "consistency checked" on a project whose Dockerfile runs `serve:app` while the
    module is gone. The hole also held for manage.py and sandbox_ai.py — it did
    not show because no artifact was yet designated by the container."""
    from monl.cli import check_coherence
    (projet / "serve.py").unlink()
    ok, erreurs, _ = check_coherence(str(projet))
    assert not ok
    assert any("serve.py" in e and "missing" in e for e in erreurs), erreurs


def test_monl_run_does_not_invalidate_the_state_it_just_checked(projet, monkeypatch):
    """'monl run' rewrote the wrapper at every start. Since it is sealed, that
    rewrite turned against the project: should a later monl version change the
    rendering, the NEXT start refused to run, wrongly blaming a "hand edit"."""
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
    """The counterpart of the previous test: no longer rewriting must not deprive
    of a wrapper a project compiled by an earlier monl, which has none and whose
    state seals none. It has nothing to contradict, so it is written."""
    import monl.cli as cli
    from monl.cli import cmd_run
    (projet / "serve.py").unlink()
    etat = json.loads((projet / "monl.json").read_text(encoding="utf-8"))
    etat["backend_sha256"].pop("serve.py")
    (projet / "monl.json").write_text(json.dumps(etat, indent=2), encoding="utf-8")
    monkeypatch.setattr(cli.subprocess, "run", lambda *a, **k: None)

    cmd_run(str(projet), skip_smoke=True)

    assert (projet / "serve.py").exists()


def test_the_inherited_upload_template_is_refreshed_too(projet):
    """Two templates were really emitted in the repository's history: the base
    form and the Upload variant. Catching up only the first would leave every
    upload project with a container answering 404."""
    from monl.cli import DOCKERFILES_HERITES
    dockerfile = projet / "Dockerfile"
    dockerfile.write_text(DOCKERFILES_HERITES[1], encoding="utf-8")
    compile_project(str(projet / "spec.ml"), str(projet))
    assert '"serve:app"' in dockerfile.read_text(encoding="utf-8")


def test_the_inherited_template_with_french_comments_is_refreshed(projet):
    """The requirements.txt form with French secret instructions was emitted
    until the generated comments moved to English. A project compiled with it
    and never edited must receive the current template — the inherited copy
    is written out in full, so a single wrong byte in it would freeze every
    such Dockerfile forever, silently (point 164)."""
    import hashlib

    from monl.cli import DOCKERFILES_HERITES
    from monl.cli.nomenclature import DEFAULT_DOCKERFILE
    ancien = DOCKERFILES_HERITES[-1]
    # The fingerprint of the bytes REALLY emitted, taken from the template as
    # it stood before the migration. Writing the inherited form into the
    # project and checking it gets refreshed proves nothing about those
    # bytes: a corrupted copy stays consistent with itself (measured).
    assert hashlib.sha256(ancien.encode("utf-8")).hexdigest() == (
        "8296f97a1cb627bc8420715306de7c69cb926153c06eba9809e532686ada93a7")
    dockerfile = projet / "Dockerfile"
    dockerfile.write_text(ancien, encoding="utf-8")
    compile_project(str(projet / "spec.ml"), str(projet))
    assert dockerfile.read_text(encoding="utf-8") == DEFAULT_DOCKERFILE
