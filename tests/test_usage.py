"""Preuves du journal de coût et de la commande ``monl usage``."""

import json

import pytest

from monl import cli, frontend_ai
from monl.usage import build_usage_report


def _event(run_id="run-opaque", model="modele-test", **extra):
    event = {
        "timestamp": "2026-08-17T00:00:00+00:00",
        "provider": "yandex",
        "model": model,
        "operation": "construction",
        "attempt": 1,
        "duration_seconds": 1.5,
        "input_tokens": 100,
        "output_tokens": 50,
        "total_tokens": 150,
    }
    if run_id is not None:
        event["run_id"] = run_id
    event.update(extra)
    return event


def _write_journal(project, events):
    path = project / frontend_ai.USAGE_FILENAME
    path.write_text("".join(json.dumps(event) + "\n" for event in events), encoding="utf-8")
    return path


def _write_prices(path, model="modele-test"):
    path.write_text(json.dumps({
        "currency": "RUB",
        "prices": {
            "yandex": {
                model: {
                    "input_per_million_tokens": 100,
                    "output_per_million_tokens": 200,
                },
            },
        },
    }), encoding="utf-8")


def test_deux_executions_successives_restent_separees(monkeypatch, tmp_path):
    project = tmp_path / "projet"
    project.mkdir()

    class Provider:
        provider_name = "yandex"
        model = "modele-test"
        last_usage = None

        def __call__(self, _prompt):
            self.last_usage = {
                "duration_seconds": 1.0,
                "input_tokens": 10,
                "output_tokens": 5,
                "total_tokens": 15,
            }
            return '{"files": {"index.html": "<html></html>"}}'

    monkeypatch.setattr(frontend_ai, "build_generation_prompt", lambda *args: "brief")
    monkeypatch.setattr(frontend_ai, "parse_files_payload",
                        lambda _raw: {"index.html": "<html></html>"})
    monkeypatch.setattr(frontend_ai, "_write_files", lambda *_args: None)
    monkeypatch.setattr(frontend_ai, "activate_asset_manifest", lambda *_args: None)
    monkeypatch.setattr(frontend_ai, "_design_completeness_errors", lambda *_args: [])
    monkeypatch.setattr(cli, "check_coherence", lambda _project: (True, [], []))
    monkeypatch.setattr("monl.smoke_test.run_smoke_test",
                        lambda _project, say=None: (True, [], []))

    assert frontend_ai.generate_and_verify(str(project), Provider(), say=lambda _msg: None)[0]
    assert frontend_ai.generate_and_verify(str(project), Provider(), say=lambda _msg: None)[0]

    events = [json.loads(line) for line in
              (project / frontend_ai.USAGE_FILENAME).read_text().splitlines()]
    assert len(events) == 2
    assert len({event["run_id"] for event in events}) == 2

    report = build_usage_report(str(project))
    assert len(report["executions"]) == 2
    assert all(execution["known"] for execution in report["executions"])


def test_modele_sans_prix_rapporte_les_jetons_sans_inventer_un_chiffre(tmp_path):
    project = tmp_path / "projet"
    project.mkdir()
    _write_journal(project, [_event()])
    prices = tmp_path / "prices.json"
    _write_prices(prices, model="autre-modele")

    report = build_usage_report(str(project), str(prices))
    execution = report["executions"][0]
    assert execution["input_tokens"] == 100
    assert execution["output_tokens"] == 50
    assert execution["cost"] is None
    assert execution["price_status"] == "not_declared"
    assert report["project_total"]["cost"] is None


def test_evenements_sans_run_id_forment_un_lot_inconnu(tmp_path):
    project = tmp_path / "projet"
    project.mkdir()
    _write_journal(project, [_event(None, stage="index.html"),
                             _event(None, stage="styles.css")])

    report = build_usage_report(str(project))
    assert len(report["executions"]) == 1
    execution = report["executions"][0]
    assert execution["known"] is False
    assert execution["run_id"] is None
    assert execution["input_tokens"] == 200
    assert execution["stages"] == ["index.html", "styles.css"]


def test_json_est_exploitable_et_signale_les_lignes_illisibles(tmp_path, capsys):
    project = tmp_path / "projet"
    project.mkdir()
    (project / "monl.json").write_text("{}", encoding="utf-8")
    journal = _write_journal(project, [_event()])
    with journal.open("a", encoding="utf-8") as fh:
        fh.write("pas du json\n")
    prices = tmp_path / "prices.json"
    _write_prices(prices)

    cli.main(["usage", str(project), "--prices", str(prices), "--json"])
    report = json.loads(capsys.readouterr().out)
    assert report["executions"][0]["cost"] == pytest.approx(0.02)
    assert report["project_total"]["cost"] == pytest.approx(0.02)
    assert report["malformed_lines"] == [{"line": 2, "error": "JSON invalide"}]


def test_journal_n_ajoute_ni_prompt_ni_cle(tmp_path):
    project = tmp_path / "projet"
    project.mkdir()
    provider = type("Provider", (), {
        "provider_name": "yandex",
        "model": "modele-test",
        "last_usage": {
            "duration_seconds": 1,
            "input_tokens": 1,
            "output_tokens": 1,
            "total_tokens": 2,
            "prompt": "prompt-client",
            "response": "reponse-client",
            "api_key": "cle-secrete",
        },
    })()
    frontend_ai._record_provider_usage(str(project), provider, "construction", 1,
                                       run_id="opaque")
    contenu = (project / frontend_ai.USAGE_FILENAME).read_text(encoding="utf-8")
    assert "prompt-client" not in contenu
    assert "reponse-client" not in contenu
    assert "cle-secrete" not in contenu
    assert '"prompt"' not in contenu
    assert '"response"' not in contenu
    assert '"api_key"' not in contenu


def test_la_voie_agent_aussi_est_identifiee(monkeypatch, tmp_path):
    project = tmp_path / "projet"
    project.mkdir()
    (project / frontend_ai.PROMPT_FILENAME).write_text("brief", encoding="utf-8")
    (project / "frontend").mkdir()
    (project / "frontend" / "index.html").write_text("<html></html>", encoding="utf-8")
    fingerprints = iter([{"avant": "1"}, {"apres": "2"}])
    monkeypatch.setattr(frontend_ai, "_fingerprint_protected", lambda _project: {})
    monkeypatch.setattr(frontend_ai, "_fingerprint_frontend",
                        lambda _project: next(fingerprints))
    monkeypatch.setattr(frontend_ai, "run_cli_agent", lambda *args, **kwargs: "ok")
    monkeypatch.setattr(frontend_ai, "activate_asset_manifest", lambda *_args: None)
    monkeypatch.setattr(cli, "check_coherence", lambda _project: (True, [], []))
    monkeypatch.setattr("monl.smoke_test.run_smoke_test",
                        lambda _project, say=None: (True, [], []))

    ok, errors = frontend_ai.generate_with_cli_agent(
        str(project), agent="codex", say=lambda _msg: None)
    assert ok, errors
    event = json.loads((project / frontend_ai.USAGE_FILENAME).read_text())
    assert event["run_id"]
    assert event["provider"] == "agent"
