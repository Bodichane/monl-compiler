"""Proofs of the current entry point, without a parallel JWT configuration."""

import pathlib

import pytest

from monl_platform import __main__ as platform_main


def test_startup_configures_uvicorn_from_the_arguments(monkeypatch):
    lance = {}

    def fake_run(application, host, port):
        lance.update(application=application, host=host, port=port)

    import uvicorn

    monkeypatch.setattr(uvicorn, "run", fake_run)

    assert platform_main.main(["--host", "127.0.0.2", "--port", "8765"]) == 0
    assert lance == {
        "application": "monl_platform.app:app",
        "host": "127.0.0.2",
        "port": 8765,
    }


def test_no_jwt_secret_is_accepted_as_an_argument(capsys):
    with pytest.raises(SystemExit) as exit_info:
        platform_main.main(["--jwt-secret", "secret-de-test-suffisamment-long"])

    assert exit_info.value.code == 2
    assert "--jwt-secret" in capsys.readouterr().err


def test_the_module_no_longer_knows_the_jwt_variable():
    source = pathlib.Path(platform_main.__file__).read_text(encoding="utf-8")
    assert "PLATFORM_" + "JWT_SECRET" not in source
