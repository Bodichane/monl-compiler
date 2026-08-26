"""Preuves du point d'entrée actuel, sans configuration JWT parallèle."""

import pytest

from monl_platform import __main__ as platform_main


def test_le_demarrage_configure_uvicorn_depuis_les_arguments(monkeypatch):
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


def test_aucun_secret_jwt_n_est_accepte_en_argument(capsys):
    with pytest.raises(SystemExit) as exit_info:
        platform_main.main(["--jwt-secret", "secret-de-test-suffisamment-long"])

    assert exit_info.value.code == 2
    assert "--jwt-secret" in capsys.readouterr().err


def test_le_module_ne_connait_plus_la_variable_jwt():
    source = open(platform_main.__file__, encoding="utf-8").read()
    assert "PLATFORM_" + "JWT_SECRET" not in source
