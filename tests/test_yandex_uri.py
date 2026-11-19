"""Proofs of the Yandex model form without a network call."""

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


def test_a_bare_name_becomes_a_uri_on_the_wire_and_stays_readable(monkeypatch):
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
def test_an_existing_uri_passes_unchanged(monkeypatch, model):
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


def test_telemetry_groups_on_the_readable_name(monkeypatch, tmp_path):
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


def test_missing_model_stays_refused(monkeypatch):
    _configure_yandex(monkeypatch)

    with pytest.raises(frontend_ai.FrontendAIError, match="model missing"):
        frontend_ai.PROVIDERS["yandex"](model=None)


def test_missing_yandex_folder_is_named(monkeypatch):
    monkeypatch.setenv("YANDEX_API_KEY", "cle-de-test")
    monkeypatch.delenv("YANDEX_FOLDER_ID", raising=False)

    with pytest.raises(frontend_ai.FrontendAIError, match="YANDEX_FOLDER_ID"):
        frontend_ai.PROVIDERS["yandex"](model="qwen3/latest")


def test_reasoning_effort_is_absent_by_default(monkeypatch):
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
def test_an_allowed_effort_is_passed_as_is(monkeypatch, effort):
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


def test_none_stays_an_alias_to_omit_the_effort(monkeypatch):
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


def test_a_forbidden_effort_is_refused_before_any_http_call(monkeypatch):
    _configure_yandex(monkeypatch)
    monkeypatch.setenv("MONL_YANDEX_REASONING_EFFORT", "none-ish")

    import requests

    def fail_post(*args, **kwargs):
        pytest.fail("no HTTP call must go out for a forbidden value")

    monkeypatch.setattr(requests, "post", fail_post)
    with pytest.raises(frontend_ai.FrontendAIError) as erreur:
        frontend_ai.PROVIDERS["yandex"](model="qwen3/latest")

    message = str(erreur.value)
    assert "MONL_YANDEX_REASONING_EFFORT" in message
    assert "low, medium, high" in message
