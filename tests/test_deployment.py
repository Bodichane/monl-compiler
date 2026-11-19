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


def _port_free():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _environment(**values):
    env = os.environ.copy()
    for name in ("MONL_CORS_ORIGINS", "MONL_LOG_FORMAT", "MONL_ENV",
                "MONL_JWT_SECRET"):
        env.pop(name, None)
    env.update({name: valeur for name, valeur in values.items() if valeur is not None})
    return env


@contextlib.contextmanager
def _server(project, module="app:app", **variables):
    port = _port_free()
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", module, "--host", "127.0.0.1",
         "--port", str(port), "--no-access-log"],
        cwd=str(project), env=_environment(**variables),
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(100):
            if process.poll() is not None:
                output = process.stdout.read() if process.stdout else ""
                pytest.fail(f"server stopped at startup:\n{output}")
            try:
                response = requests.get(f"{base}/health", timeout=1)
                if response.status_code == 200:
                    break
            except requests.RequestException:
                time.sleep(0.05)
        else:
            pytest.fail("server not started")
        yield base, process
    finally:
        if process.poll() is None:
            process.terminate()
        try:
            output, _ = process.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            output, _ = process.communicate(timeout=5)
        process._monl_output = output


@pytest.fixture
def project(tmp_path):
    spec = tmp_path / "spec.ml"
    spec.write_text(SPEC, encoding="utf-8")
    compile_project(str(spec), str(tmp_path))
    return tmp_path


def test_health_and_readiness_are_reachable_without_token(project):
    with _server(project) as (base, _process):
        liveness = requests.get(f"{base}/health", timeout=5)
        readiness = requests.get(f"{base}/health/ready", timeout=5)

    assert liveness.status_code == 200
    assert liveness.json() == {"status": "ok"}
    assert readiness.status_code == 200
    assert readiness.json() == {"status": "ready"}


def test_readiness_returns_503_if_the_database_becomes_unreachable(project):
    with _server(project) as (base, _process):
        base_of_donnees = project / "app.db"
        backup = project / "app.db.sauvegarde-a3"
        base_of_donnees.rename(backup)
        base_of_donnees.mkdir()
        try:
            response = requests.get(f"{base}/health/ready", timeout=5)
        finally:
            base_of_donnees.rmdir()
            backup.rename(base_of_donnees)

    assert response.status_code == 503
    assert response.json() == {"detail": "Service indisponible"}


def test_cors_is_missing_without_variable(project):
    with _server(project) as (base, _process):
        response = requests.get(f"{base}/health", headers={"Origin": "https://client.test"},
                               timeout=5)

    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers


def test_cors_only_allows_the_declared_origin(project):
    with _server(project, MONL_CORS_ORIGINS="https://client.test, https://admin.test") as (
        base, _process
    ):
        response = requests.get(f"{base}/health", headers={"Origin": "https://client.test"},
                               timeout=5)

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://client.test"
    assert response.headers["access-control-allow-credentials"] == "true"


def test_cors_refuses_star_at_startup(project):
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app:app", "--host", "127.0.0.1",
         "--port", str(_port_free()), "--no-access-log"],
        cwd=str(project), env=_environment(MONL_CORS_ORIGINS="*"),
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    output, _ = process.communicate(timeout=10)

    assert process.returncode != 0
    assert "MONL_CORS_ORIGINS" in output
    assert "origin '*'" in output


def test_json_logs_are_structured_and_do_not_contain_the_password(project):
    password = "MotDePasse-A3-NE-JAMAIS-JOURNALISER"
    with _server(project, MONL_LOG_FORMAT="json") as (base, process):
        inscription = requests.post(
            f"{base}/register", timeout=5,
            json={"username": "log@exemple.test", "password": password,
                  "actor": "Membre"},
        )
        assert inscription.status_code == 200
        response = requests.get(
            f"{base}/health", headers={"X-Request-ID": "demande-A3"}, timeout=5)
        assert response.status_code == 200
        assert response.headers["X-Request-ID"] == "demande-A3"
    output = getattr(process, "_monl_output", "")

    assert password not in output
    lines_json = []
    for line in output.splitlines():
        try:
            object_ = json.loads(line)
        except json.JSONDecodeError:
            continue
        if "request_id" in object_:
            lines_json.append(object_)
    assert lines_json
    assert all({"timestamp", "method", "path", "status_code", "duration_ms",
                "request_id"} <= set(object_) for object_ in lines_json)
    assert any(object_["request_id"] == "demande-A3" for object_ in lines_json)


def test_production_without_secret_refuses_to_start(project):
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app:app", "--host", "127.0.0.1",
         "--port", str(_port_free()), "--no-access-log"],
        cwd=str(project), env=_environment(MONL_ENV="production"),
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    output, _ = process.communicate(timeout=10)

    assert process.returncode != 0
    assert "MONL_JWT_SECRET" in output


def test_a_project_delivered_without_secret_creates_it_at_first_start(project):
    (project / ".jwt_secret").unlink()

    with _server(project) as (base, _process):
        assert requests.get(f"{base}/health", timeout=5).status_code == 200

    secret = project / ".jwt_secret"
    assert secret.is_file()
    assert len(secret.read_text(encoding="utf-8").strip()) == 64
    assert secret.stat().st_mode & 0o077 == 0


def test_dockerfile_and_dockerignore_are_created_and_preserved(project):
    dockerfile = project / "Dockerfile"
    dockerignore = project / ".dockerignore"
    assert dockerfile.exists()
    assert dockerignore.exists()
    content_dockerignore = dockerignore.read_text(encoding="utf-8")
    for motif in (".jwt_secret", "*.db", "__pycache__", "frontend.precedent/"):
        assert motif in content_dockerignore

    dockerfile.write_text("FROM image-adaptee\n", encoding="utf-8")
    dockerignore.write_text(".jwt_secret\n# adaptation locale\n", encoding="utf-8")
    compile_project(str(project / "spec.ml"), str(project))

    assert dockerfile.read_text(encoding="utf-8") == "FROM image-adaptee\n"
    assert dockerignore.read_text(encoding="utf-8") == ".jwt_secret\n# adaptation locale\n"


def test_healthchecks_are_not_in_the_frontend_contract(project):
    contract = json.loads((project / "frontend_contract.json").read_text(encoding="utf-8"))
    paths = {route["path"] for route in contract["routes"]}

    assert "/health" not in paths
    assert "/health/ready" not in paths


# --------------------------------------------------------------------------
# POINT 133: the container serves the SITE, not only the API
# --------------------------------------------------------------------------

def test_the_wrapper_is_written_at_compile_time(project):
    """It was only written by 'monl run'. The Dockerfile, however, is produced by
    'monl compile': the image therefore could not start it."""
    wrapper = project / "serve.py"
    assert wrapper.exists()
    state = json.loads((project / "monl.json").read_text(encoding="utf-8"))
    assert "serve.py" in state["backend_sha256"], (
        "the wrapper decides which folders are served: it must be sealed "
        "like the rest of the generated backend")


def test_the_container_runs_the_wrapper_not_the_bare_api(project):
    content = (project / "Dockerfile").read_text(encoding="utf-8")
    assert '"serve:app"' in content
    assert '"app:app"' not in content


def test_an_inherited_dockerfile_is_refreshed(project):
    """A never-touched template is refreshed; a customized file is not (the
    neighboring test guards that second side). Without this catch-up, every
    already compiled project would keep a container answering 404 on /site, and
    nothing would tell it."""
    from monl.cli import DOCKERFILES_INHERITED
    dockerfile = project / "Dockerfile"
    dockerfile.write_text(DOCKERFILES_INHERITED[0], encoding="utf-8")
    compile_project(str(project / "spec.ml"), str(project))
    assert '"serve:app"' in dockerfile.read_text(encoding="utf-8")


def test_the_wrapper_is_protected_from_the_ai():
    """It is there when the interface agent passes, and IT decides which folders
    are served."""
    from monl.frontend_ai import PROTECTED_ARTIFACTS
    assert "serve.py" in PROTECTED_ARTIFACTS


def test_the_wrapper_starts_without_frontend(project):
    """The interface is built AFTER compilation: the wrapper must start before it
    exists, otherwise the image would not start at all. And the absence is SAID —
    a silent 404 /site is the defect this wrapper exists to prevent."""
    assert not (project / "frontend").exists()
    with _server(project, module="serve:app") as (base, process):
        assert requests.get(f"{base}/health", timeout=5).status_code == 200
        assert requests.get(f"{base}/site/", timeout=5).status_code == 404
    assert "frontend/ missing" in (process._monl_output or "")


def test_the_wrapper_serves_the_site_when_the_frontend_exists(project):
    frontend = project / "frontend"
    frontend.mkdir()
    (frontend / "index.html").write_text(
        "<!doctype html><title>Vitrine</title><p>ok", encoding="utf-8")
    with _server(project, module="serve:app") as (base, _process):
        page = requests.get(f"{base}/site/", timeout=5)
        assert page.status_code == 200
        assert "Vitrine" in page.text


# --------------------------------------------------------------------------
# POINT 134: the wrapper's seal, all the way
# --------------------------------------------------------------------------

def test_a_sealed_but_missing_artifact_fails_consistency(project):
    """The loop only compared an artifact if it EXISTED: a vanished file said
    nothing. Since point 133, 'monl run --check' could therefore certify
    "consistency checked" on a project whose Dockerfile runs `serve:app` while the
    module is gone. The hole also held for manage.py and sandbox_ai.py — it did
    not show because no artifact was yet designated by the container."""
    from monl.cli import check_coherence
    (project / "serve.py").unlink()
    ok, errors, _ = check_coherence(str(project))
    assert not ok
    assert any("serve.py" in e and "missing" in e for e in errors), errors


def test_monl_run_does_not_invalidate_the_state_it_just_checked(project, monkeypatch):
    """'monl run' rewrote the wrapper at every start. Since it is sealed, that
    rewrite turned against the project: should a later monl version change the
    rendering, the NEXT start refused to run, wrongly blaming a "hand edit"."""
    import monl.cli as cli
    from monl.cli import check_coherence, cmd_run
    rendered = cli.render_wrapper
    monkeypatch.setattr(cli, "render_wrapper",
                        lambda a=None: rendered(a) + "\n# version ultérieure\n")
    monkeypatch.setattr(cli.subprocess, "run", lambda *a, **k: None)

    cmd_run(str(project), skip_smoke=True)

    ok, errors, _ = check_coherence(str(project))
    assert ok, errors


def test_an_old_project_gets_its_wrapper_at_launch(project, monkeypatch):
    """The counterpart of the previous test: no longer rewriting must not deprive
    of a wrapper a project compiled by an earlier monl, which has none and whose
    state seals none. It has nothing to contradict, so it is written."""
    import monl.cli as cli
    from monl.cli import cmd_run
    (project / "serve.py").unlink()
    state = json.loads((project / "monl.json").read_text(encoding="utf-8"))
    state["backend_sha256"].pop("serve.py")
    (project / "monl.json").write_text(json.dumps(state, indent=2), encoding="utf-8")
    monkeypatch.setattr(cli.subprocess, "run", lambda *a, **k: None)

    cmd_run(str(project), skip_smoke=True)

    assert (project / "serve.py").exists()


def test_the_inherited_upload_template_is_refreshed_too(project):
    """Two templates were really emitted in the repository's history: the base
    form and the Upload variant. Catching up only the first would leave every
    upload project with a container answering 404."""
    from monl.cli import DOCKERFILES_INHERITED
    dockerfile = project / "Dockerfile"
    dockerfile.write_text(DOCKERFILES_INHERITED[1], encoding="utf-8")
    compile_project(str(project / "spec.ml"), str(project))
    assert '"serve:app"' in dockerfile.read_text(encoding="utf-8")


def test_the_inherited_template_with_french_comments_is_refreshed(project):
    """The requirements.txt form with French secret instructions was emitted
    until the generated comments moved to English. A project compiled with it
    and never edited must receive the current template — the inherited copy
    is written out in full, so a single wrong byte in it would freeze every
    such Dockerfile forever, silently (point 164)."""
    import hashlib

    from monl.cli import DOCKERFILES_INHERITED
    from monl.cli.nomenclature import DEFAULT_DOCKERFILE
    old = DOCKERFILES_INHERITED[-1]
    # The fingerprint of the bytes REALLY emitted, taken from the template as
    # it stood before the migration. Writing the inherited form into the
    # project and checking it gets refreshed proves nothing about those
    # bytes: a corrupted copy stays consistent with itself (measured).
    assert hashlib.sha256(old.encode("utf-8")).hexdigest() == (
        "8296f97a1cb627bc8420715306de7c69cb926153c06eba9809e532686ada93a7")
    dockerfile = project / "Dockerfile"
    dockerfile.write_text(old, encoding="utf-8")
    compile_project(str(project / "spec.ml"), str(project))
    assert dockerfile.read_text(encoding="utf-8") == DEFAULT_DOCKERFILE
