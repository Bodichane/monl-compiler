"""A page offering a download must deliver a file that exists.

The requested name is compared with what is REALLY on disk, never
concatenated to a path: directory traversal is impossible, not merely
unlikely.
"""

import hashlib
import socket
import threading
import time

import pytest
import requests
import uvicorn

from monl_platform.app import create_app
from monl_platform.downloads import (
    default_directory,
    list_artifacts,
    resolve_artifact,
)


class FakeProvider:
    provider_name = "test"
    model = "test-model"

    def __call__(self, _prompt):  # pragma: no cover - never called here
        raise AssertionError("download calls no AI")


@pytest.fixture()
def dist(tmp_path):
    folder = tmp_path / "dist"
    folder.mkdir()
    (folder / "monl_compiler-1.0.0-py3-none-any.whl").write_bytes(b"roue" * 64)
    (folder / "monl_compiler-1.0.0.tar.gz").write_bytes(b"sources" * 32)
    # What is not a distribution must not be published.
    (folder / "journal.txt").write_text("bruit", encoding="utf-8")
    (folder / "anciens").mkdir()
    (folder / "anciens" / "vieux-0.1.0.whl").write_bytes(b"vieux")
    return folder


def _free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture()
def platform(tmp_path, dist):
    app = create_app(
        workspace=tmp_path / "projects",
        domain="localhost",
        downloads_dir=str(dist),
    )
    port = _free_port()
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(100):
            try:
                if requests.get(f"{base}/health", timeout=0.2).status_code == 200:
                    break
            except requests.RequestException:
                time.sleep(0.02)
        else:
            pytest.fail("the server did not start")
        yield base
    finally:
        server.should_exit = True
        thread.join(timeout=10)


def test_only_distributions_are_published(dist):
    names = [a["name"] for a in list_artifacts(dist)]

    assert names == [
        "monl_compiler-1.0.0-py3-none-any.whl",
        "monl_compiler-1.0.0.tar.gz",
    ]


def test_the_wheel_comes_before_the_sources(dist):
    """The wheel is what installs: offering it second lengthens the path."""
    assert list_artifacts(dist)[0]["kind"] == "wheel"


def test_the_published_fingerprint_is_the_files(dist):
    artifact = list_artifacts(dist)[0]
    expected = hashlib.sha256(
        (dist / artifact["name"]).read_bytes()
    ).hexdigest()

    assert artifact["sha256"] == expected
    assert artifact["bytes"] == (dist / artifact["name"]).stat().st_size


def test_a_missing_folder_does_not_fail(tmp_path):
    """The platform can run without a built distribution."""
    assert list_artifacts(tmp_path / "nulle-part") == []
    assert list_artifacts(None) == []


def test_the_download_returns_the_file_bytes(platform, dist):
    listing = requests.get(f"{platform}/api/telechargements", timeout=10).json()
    name = listing["artifacts"][0]["name"]

    response = requests.get(f"{platform}/api/telechargements/{name}", timeout=10)

    assert response.status_code == 200
    assert response.content == (dist / name).read_bytes()


@pytest.mark.parametrize("name", [
    "../../etc/passwd",
    "..%2f..%2fetc%2fpasswd",
    "/etc/passwd",
    "journal.txt",
    "anciens/vieux-0.1.0.whl",
    "inconnu-9.9.9.whl",
])
def test_a_hostile_or_unknown_name_is_refused(platform, name):
    response = requests.get(f"{platform}/api/telechargements/{name}", timeout=10)

    assert response.status_code == 404, response.text


def test_resolution_never_concatenates_the_received_name(dist):
    assert resolve_artifact(dist, "../dist/journal.txt") is None
    assert resolve_artifact(dist, "journal.txt") is None
    assert resolve_artifact(dist, "monl_compiler-1.0.0.tar.gz") is not None
    assert resolve_artifact(None, "monl_compiler-1.0.0.tar.gz") is None


def test_the_folder_comes_from_the_environment_only():
    assert default_directory({}) is None
    assert default_directory({"MONL_PLATFORM_DOWNLOADS": "  "}) is None
    assert default_directory({"MONL_PLATFORM_DOWNLOADS": " dist "}) == "dist"
