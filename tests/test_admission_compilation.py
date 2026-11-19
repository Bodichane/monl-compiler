"""HTTP witnesses of the admission shared by both compilation routes."""

import socket
import threading
import time

import pytest
import requests
import uvicorn

from monl_platform import builder_build_routes
from monl_platform.app import create_app
from monl_platform.service import CompilationService

SPEC = """app Admission

entity Item
    label: String

actor Admin
rule Item.Read public
workflow Manage for Admin
    Create Item
    Read Item
"""


def _port_free():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture()
def platform(tmp_path, monkeypatch):
    monkeypatch.setenv("MONL_MAX_CONCURRENT_COMPILES", "1")
    port = _port_free()
    server = uvicorn.Server(uvicorn.Config(
        create_app(workspace=tmp_path / "projects"),
        host="127.0.0.1",
        port=port,
        log_level="error",
    ))
    fil = threading.Thread(target=server.run, daemon=True)
    fil.start()
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(100):
            try:
                if requests.get(f"{base}/health", timeout=0.2).status_code == 200:
                    break
            except requests.RequestException:
                time.sleep(0.02)
        else:
            pytest.fail("the platform did not start")
        yield base
    finally:
        server.should_exit = True
        fil.join(timeout=10)
        assert not fil.is_alive()


def _register(base, email):
    session = requests.Session()
    response = session.post(
        f"{base}/api/auth/register",
        json={"email": email, "password": "MotDePasse-123"},
        timeout=10,
    )
    assert response.status_code == 201, response.text
    return session


def _create_project(base, session):
    response = session.post(f"{base}/api/compile", json={"spec": SPEC}, timeout=60)
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_compilation_and_recompilation_share_the_quota(platform):
    session = _register(platform, "quota@exemple.test")
    project = _create_project(platform, session)

    for _ in range(9):
        response = session.post(
            f"{platform}/api/projects/{project}/compiler", timeout=60
        )
        assert response.status_code == 201, response.text

    refused = session.post(f"{platform}/api/compile", json={"spec": SPEC}, timeout=10)
    assert refused.status_code == 429
    assert "Retry-After" in refused.headers


def test_a_recompilation_holds_the_semaphore_then_frees_it(
    platform, monkeypatch
):
    session = _register(platform, "semaphore@exemple.test")
    project = _create_project(platform, session)
    entre = threading.Event()
    exit_ = threading.Event()
    true_compiler = builder_build_routes.compiler_the_project

    def compilation_kept(*args, **kwargs):
        entre.set()
        assert exit_.wait(timeout=10)
        return true_compiler(*args, **kwargs)

    monkeypatch.setattr(builder_build_routes, "compiler_the_project", compilation_kept)
    result = {}

    def launch():
        result["reponse"] = session.post(
            f"{platform}/api/projects/{project}/compiler", timeout=60
        )

    fil = threading.Thread(target=launch)
    fil.start()
    assert entre.wait(timeout=10)
    occupied = session.post(f"{platform}/api/projects/{project}/compiler", timeout=10)
    assert occupied.status_code == 503
    assert occupied.headers["Retry-After"] == "5"
    exit_.set()
    fil.join(timeout=60)
    assert result["reponse"].status_code == 201, result["reponse"].text

    next_ = session.post(f"{platform}/api/projects/{project}/compiler", timeout=60)
    assert next_.status_code == 201, next_.text


def test_compilation_and_recompilation_share_the_semaphore(
    platform, monkeypatch
):
    session = _register(platform, "semaphore-partage@exemple.test")
    project = _create_project(platform, session)
    entre = threading.Event()
    exit_ = threading.Event()
    true_compilation = CompilationService.compile

    def compilation_kept(service, spec, **kwargs):
        entre.set()
        assert exit_.wait(timeout=10)
        return true_compilation(service, spec, **kwargs)

    monkeypatch.setattr(CompilationService, "compile", compilation_kept)
    result = {}

    def launch():
        result["reponse"] = session.post(
            f"{platform}/api/compile", json={"spec": SPEC}, timeout=60
        )

    fil = threading.Thread(target=launch)
    fil.start()
    assert entre.wait(timeout=10)
    occupied = session.post(f"{platform}/api/projects/{project}/compiler", timeout=10)
    assert occupied.status_code == 503
    assert occupied.headers["Retry-After"] == "5"
    exit_.set()
    fil.join(timeout=60)
    assert result["reponse"].status_code == 201, result["reponse"].text

    next_ = session.post(f"{platform}/api/projects/{project}/compiler", timeout=60)
    assert next_.status_code == 201, next_.text


def test_a_legitimate_call_passes_and_errors_free_the_slot(platform):
    session = _register(platform, "erreurs@exemple.test")

    invalid = session.post(f"{platform}/api/compile", json={"spec": ""}, timeout=10)
    assert invalid.status_code == 422
    project = _create_project(platform, session)

    missing = session.post(
        f"{platform}/api/projects/projet-absent/compiler", timeout=10
    )
    assert missing.status_code == 404
    legitimate = session.post(
        f"{platform}/api/projects/{project}/compiler", timeout=60
    )
    assert legitimate.status_code == 201, legitimate.text
