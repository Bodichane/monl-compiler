"""Preuves du démarrage de la plateforme sans service IA réel."""

import pytest

from monl_platform import __main__ as platform_main


def test_les_reglages_sont_lus_dans_lenvironnement():
    settings = platform_main.load_settings(
        {
            "MONL_PLATFORM_DATABASE": "/tmp/monl-platform.db",
            "MONL_PLATFORM_WORKSPACE": "/tmp/monl-platform-workspaces",
            "MONL_PLATFORM_DOMAIN": "sites.example.test",
            "MONL_PLATFORM_JWT_SECRET": "secret-de-test-suffisamment-long",
            "MONL_PLATFORM_QUOTA": "4321",
            "MONL_PLATFORM_HOST": "0.0.0.0",
            "MONL_PLATFORM_PORT": "8765",
            "MONL_PLATFORM_WORKER_INTERVAL": "1.25",
            "MONL_PLATFORM_PRICES": "/tmp/prices.json",
            "MONL_PLATFORM_AI_PROVIDER": "yandex",
            "MONL_PLATFORM_AI_MODEL": "qwen3/latest",
        }
    )

    assert settings.database == "/tmp/monl-platform.db"
    assert settings.workspace_root == "/tmp/monl-platform-workspaces"
    assert settings.domain == "sites.example.test"
    assert settings.jwt_secret == "secret-de-test-suffisamment-long"
    assert settings.quota_limit == 4321
    assert settings.host == "0.0.0.0"
    assert settings.port == 8765
    assert settings.worker_interval == 1.25
    assert settings.prices_path == "/tmp/prices.json"
    assert settings.ai_provider == "yandex"
    assert settings.ai_model == "qwen3/latest"


def test_une_cle_absente_est_nommee_au_demarrage(monkeypatch, capsys):
    monkeypatch.setenv("MONL_PLATFORM_JWT_SECRET", "secret-de-test-suffisamment-long")
    monkeypatch.setenv("MONL_PLATFORM_AI_MODEL", "qwen3/latest")
    monkeypatch.setenv("YANDEX_FOLDER_ID", "folder-de-test")
    monkeypatch.delenv("YANDEX_API_KEY", raising=False)

    assert platform_main.main([]) == 2
    captured = capsys.readouterr()
    assert "YANDEX_API_KEY" in captured.err
    assert "Traceback" not in captured.err


def test_aucun_secret_nest_accepté_en_argument(capsys):
    with pytest.raises(SystemExit) as exit_info:
        platform_main.main(["--jwt-secret", "secret-de-test-suffisamment-long"])

    assert exit_info.value.code == 2
    assert "--jwt-secret" in capsys.readouterr().err


def test_le_demarrage_configure_uvicorn_depuis_lenvironnement(monkeypatch, tmp_path):
    monkeypatch.setenv("MONL_PLATFORM_DATABASE", str(tmp_path / "platform.db"))
    monkeypatch.setenv("MONL_PLATFORM_WORKSPACE", str(tmp_path / "workspaces"))
    monkeypatch.setenv("MONL_PLATFORM_DOMAIN", "sites.example.test")
    monkeypatch.setenv("MONL_PLATFORM_JWT_SECRET", "secret-de-test-suffisamment-long")
    monkeypatch.setenv("MONL_PLATFORM_QUOTA", "4321")
    monkeypatch.setenv("MONL_PLATFORM_HOST", "127.0.0.2")
    monkeypatch.setenv("MONL_PLATFORM_PORT", "8765")
    monkeypatch.setenv("MONL_PLATFORM_WORKER_INTERVAL", "1.25")
    monkeypatch.setenv("MONL_PLATFORM_PRICES", str(tmp_path / "prices.json"))
    monkeypatch.setenv("MONL_PLATFORM_AI_PROVIDER", "yandex")
    monkeypatch.setenv("MONL_PLATFORM_AI_MODEL", "qwen3/latest")
    monkeypatch.setenv("YANDEX_API_KEY", "cle-de-test")
    monkeypatch.setenv("YANDEX_FOLDER_ID", "folder-de-test")
    launched = {}

    import uvicorn

    def fake_run(application, host, port):
        launched.update(application=application, host=host, port=port)

    monkeypatch.setattr(uvicorn, "run", fake_run)

    assert platform_main.main([]) == 0
    application = launched["application"]
    assert launched["host"] == "127.0.0.2"
    assert launched["port"] == 8765
    assert application.state.quota.max_tokens == 4321
    assert application.state.sites.domain == "sites.example.test"
    assert application.state.worker.poll_interval == 1.25
    assert application.state.worker.prices_path == str(tmp_path / "prices.json")
    assert application.state.worker.provider_factory({}, {}).model == "qwen3/latest"
    application.state.store.close()
