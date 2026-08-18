"""Preuves de la forme de modèle Yandex sans appel réseau."""

import json

import pytest

from monl import frontend_ai


class _Response:
    status_code = 200
    text = ""

    def json(self):
        return {
            "choices": [{"message": {"content": '{"files": {}}'}}],
            "usage": {"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 5},
        }


def _configure_yandex(monkeypatch):
    monkeypatch.setenv("YANDEX_API_KEY", "cle-de-test")
    monkeypatch.setenv("YANDEX_FOLDER_ID", "folder-de-test")


def test_un_nom_nu_devient_uri_sur_le_fil_et_reste_lisible(monkeypatch):
    _configure_yandex(monkeypatch)
    sent = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        sent.update(url=url, headers=headers, body=json)
        return _Response()

    import requests

    monkeypatch.setattr(requests, "post", fake_post)
    model = "qwen3-235b-a22b-fp8/latest"
    provider = frontend_ai.PROVIDERS["yandex"](model=model)

    provider("brief")

    assert sent["body"]["model"] == "gpt://folder-de-test/qwen3-235b-a22b-fp8/latest"
    assert provider.model == model


@pytest.mark.parametrize("model", [
    "gpt://autre-folder/qwen3/latest",
    "art://folder/yandex-art/latest",
    "custom+scheme://modele",
])
def test_une_uri_existante_passe_inchangee(monkeypatch, model):
    _configure_yandex(monkeypatch)
    sent = {}

    def fake_post(_url, headers=None, json=None, timeout=None):
        sent.update(headers=headers, body=json)
        return _Response()

    import requests

    monkeypatch.setattr(requests, "post", fake_post)
    provider = frontend_ai.PROVIDERS["yandex"](model=model)

    provider("brief")

    assert sent["body"]["model"] == model
    assert provider.model == model


def test_la_telemetrie_regroupe_sur_le_nom_lisible(monkeypatch, tmp_path):
    _configure_yandex(monkeypatch)
    import requests

    monkeypatch.setattr(requests, "post", lambda *args, **kwargs: _Response())
    model = "qwen3-235b-a22b-fp8/latest"
    provider = frontend_ai.PROVIDERS["yandex"](model=model)
    provider("brief")

    frontend_ai._record_provider_usage(
        str(tmp_path), provider, "construction", 1, run_id="run-test"
    )
    event = json.loads((tmp_path / frontend_ai.USAGE_FILENAME).read_text())

    assert event["model"] == model
    assert "gpt://folder-de-test/" not in (tmp_path / frontend_ai.USAGE_FILENAME).read_text()


def test_model_absent_reste_refuse(monkeypatch):
    _configure_yandex(monkeypatch)

    with pytest.raises(frontend_ai.FrontendAIError, match="modèle manquant"):
        frontend_ai.PROVIDERS["yandex"](model=None)


def test_dossier_yandex_absent_est_nomme(monkeypatch):
    monkeypatch.setenv("YANDEX_API_KEY", "cle-de-test")
    monkeypatch.delenv("YANDEX_FOLDER_ID", raising=False)

    with pytest.raises(frontend_ai.FrontendAIError, match="YANDEX_FOLDER_ID"):
        frontend_ai.PROVIDERS["yandex"](model="qwen3/latest")


def test_leffort_de_raisonnement_est_absent_par_defaut(monkeypatch):
    _configure_yandex(monkeypatch)
    sent = {}

    def fake_post(_url, headers=None, json=None, timeout=None):
        sent.update(headers=headers, body=json)
        return _Response()

    import requests

    monkeypatch.delenv("MONL_YANDEX_REASONING_EFFORT", raising=False)
    monkeypatch.setattr(requests, "post", fake_post)
    provider = frontend_ai.PROVIDERS["yandex"](model="qwen3/latest")

    provider("brief")

    assert "reasoning_effort" not in sent["body"]


@pytest.mark.parametrize("effort", ["low", "medium", "high"])
def test_un_effort_permis_est_transmis_tel_quel(monkeypatch, effort):
    _configure_yandex(monkeypatch)
    sent = {}

    def fake_post(_url, headers=None, json=None, timeout=None):
        sent.update(headers=headers, body=json)
        return _Response()

    import requests

    monkeypatch.setenv("MONL_YANDEX_REASONING_EFFORT", effort)
    monkeypatch.setattr(requests, "post", fake_post)
    provider = frontend_ai.PROVIDERS["yandex"](model="qwen3/latest")

    provider("brief")

    assert sent["body"]["reasoning_effort"] == effort


def test_none_reste_un_alias_pour_omettre_leffort(monkeypatch):
    _configure_yandex(monkeypatch)
    sent = {}

    def fake_post(_url, headers=None, json=None, timeout=None):
        sent.update(headers=headers, body=json)
        return _Response()

    import requests

    monkeypatch.setenv("MONL_YANDEX_REASONING_EFFORT", "none")
    monkeypatch.setattr(requests, "post", fake_post)
    provider = frontend_ai.PROVIDERS["yandex"](model="qwen3/latest")

    provider("brief")

    assert "reasoning_effort" not in sent["body"]


def test_un_effort_interdit_est_refuse_avant_tout_appel_http(monkeypatch):
    _configure_yandex(monkeypatch)
    monkeypatch.setenv("MONL_YANDEX_REASONING_EFFORT", "none-ish")

    import requests

    def fail_post(*args, **kwargs):
        pytest.fail("aucun appel HTTP ne doit partir pour une valeur interdite")

    monkeypatch.setattr(requests, "post", fail_post)
    with pytest.raises(frontend_ai.FrontendAIError) as erreur:
        frontend_ai.PROVIDERS["yandex"](model="qwen3/latest")

    message = str(erreur.value)
    assert "MONL_YANDEX_REASONING_EFFORT" in message
    assert "low, medium, high" in message
