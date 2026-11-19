"""Proofs of model routing per frontend generation stage."""

import json

import pytest

from monl import cli, frontend_ai
from monl.usage import build_usage_report


def _target(prompt):
    line = next(line for line in prompt.splitlines()
                 if line.startswith("The target file is exactly: "))
    return line.rsplit(": ", 1)[1]


class FakeChunkProvider:
    chunked_generation = True
    provider_name = "yandex"
    max_output_tokens = 8_000

    def __init__(self, model):
        self.model = model
        self.last_usage = None
        self.calls = []

    def __call__(self, prompt):
        target = _target(prompt)
        self.calls.append(target)
        self.last_usage = {
            "duration_seconds": 0.1,
            "input_tokens": 10,
            "output_tokens": 5,
            "total_tokens": 15,
        }
        return json.dumps({"files": {target: f"/* {self.model} */"}})


def test_without_match_the_global_provider_stays_alone(tmp_path):
    project = tmp_path / "projet"
    project.mkdir()
    provider = FakeChunkProvider("modele-global")

    def unexpected_factory(_model):
        raise AssertionError("la fabrique ne doit pas être appelée sans routage")

    frontend_ai._generate_chunked_files(
        str(project), provider, "brief", "construction", 1, lambda _msg: None,
        run_id="run-default", provider_factory=unexpected_factory,
    )

    events = [json.loads(line) for line in
              (project / frontend_ai.USAGE_FILENAME).read_text().splitlines()]
    assert [event["stage"] for event in events] == ["index.html", "styles.css", "app.js"]
    assert {event["model"] for event in events} == {"modele-global"}
    assert provider.calls == ["index.html", "styles.css", "app.js"]


def test_styles_css_can_be_routed_and_usage_groups_two_models(
        monkeypatch, tmp_path, capsys):
    project = tmp_path / "projet"
    project.mkdir()
    (project / "monl.json").write_text("{}", encoding="utf-8")
    brief = project / "docs/FRONTEND_PROMPT.md"
    brief.parent.mkdir(parents=True, exist_ok=True)
    brief.write_text("brief", encoding="utf-8")
    providers = {}

    def provider_factory(model):
        providers.setdefault(model, FakeChunkProvider(model))
        return providers[model]

    global_provider = provider_factory("modele-global")
    monkeypatch.setattr(frontend_ai, "_design_completeness_errors", lambda *_args: [])
    monkeypatch.setattr(cli, "check_coherence", lambda _project: (True, [], []))
    monkeypatch.setattr("monl.smoke_test.run_smoke_test",
                        lambda _project, say=None: (True, [], []))

    ok, errors = frontend_ai.generate_and_verify(
        str(project), global_provider, say=lambda _msg: None,
        model_routes={"styles.css": "modele-css"}, provider_factory=provider_factory,
    )
    assert ok, errors
    assert sorted(path.name for path in (project / "frontend").iterdir()) == [
        "app.js", "index.html", "styles.css",
    ]

    report = build_usage_report(str(project))
    assert {(item["provider"], item["model"]) for item in report["totals"]} == {
        ("yandex", "modele-global"),
        ("yandex", "modele-css"),
    }
    assert {event["model"] for event in
            (json.loads(line) for line in
             (project / frontend_ai.USAGE_FILENAME).read_text().splitlines())} == {
        "modele-global", "modele-css",
    }

    cli.main(["usage", str(project)])
    output = capsys.readouterr().out
    assert "yandex / modele-global" in output
    assert "yandex / modele-css" in output


def test_unknown_target_refused_by_name(tmp_path):
    project = tmp_path / "projet"
    project.mkdir()
    provider = FakeChunkProvider("modele-global")

    with pytest.raises(frontend_ai.FrontendAIError, match="cible-inexistante"):
        frontend_ai._generate_chunked_files(
            str(project), provider, "brief", "construction", 1, lambda _msg: None,
            run_id="run-unknown", model_routes={"cible-inexistante": "modele-css"},
            provider_factory=lambda model: FakeChunkProvider(model),
        )


def test_cli_option_passes_routing_to_generation(monkeypatch, tmp_path):
    project = tmp_path / "projet"
    project.mkdir()
    captured = {}

    class Provider:
        model = "modele-global"

    def provider_factory(model):
        captured.setdefault("providers", []).append(model)
        return Provider()

    def fake_generate(_project, provider, **kwargs):
        captured["provider"] = provider
        captured.update(kwargs)
        return True, []

    monkeypatch.setitem(frontend_ai.PROVIDERS, "claude", provider_factory)
    monkeypatch.setattr(frontend_ai, "generate_and_verify", fake_generate)

    cli.main([
        "frontend", str(project), "--model-for", "styles.css=modele-css",
    ])

    assert captured["providers"] == ["claude-sonnet-4-6"]
    assert captured["model_routes"] == {"styles.css": "modele-css"}
    assert captured["provider_factory"]("modele-css").model == "modele-global"
    assert captured["providers"][-1] == "modele-css"


def test_help_documente_l_option_repetable():
    with pytest.raises(SystemExit) as exit_info:
        cli.main(["frontend", "--help"])
    assert exit_info.value.code == 0
