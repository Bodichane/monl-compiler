"""Régressions de la génération séquentielle avec fournisseur factice réel."""

import json

import pytest

from monl.cli import compile_project
from monl.frontend_ai import (
    CHUNK_MAX_RETRIES,
    USAGE_FILENAME,
    generate_and_verify,
)

SPEC = """app ChunkRetryApp

entity Item
    label: String

actor Admin selfRegister

rule Item.label required
rule Item.Read public

workflow ManageItem for Admin
    Create Item
    Read Item
"""

GOOD_FILES = {
    "index.html": (
        "<!doctype html><html><head><link rel=\"stylesheet\" href=\"styles.css\">"
        "</head><body><div id=\"l\"></div><script src=\"app.js\"></script>"
        "</body></html>"
    ),
    "styles.css": "body { color: #111; }",
    "app.js": (
        "fetch('/item?limit=5').then(r => r.json()).then(d => {"
        "document.getElementById('l').textContent = d.data.map(i => i.label).join(', ');"
        "});"
    ),
}


@pytest.fixture()
def project(tmp_path):
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    spec_path = project_dir / "spec.ml"
    spec_path.write_text(SPEC, encoding="utf-8")
    compile_project(str(spec_path), str(project_dir))
    return project_dir


def _target(prompt):
    line = next(line for line in prompt.splitlines()
                 if line.startswith("Le fichier cible est exactement : "))
    return line.rsplit(": ", 1)[1]


class TruncateStylesOnce:
    chunked_generation = True
    provider_name = "fake"
    model = "fake-chunks"
    max_output_tokens = 8_000
    last_usage = None

    def __init__(self):
        self.calls = []
        self.truncated = False

    def __call__(self, prompt):
        target = _target(prompt)
        limit = self.max_output_tokens
        self.calls.append((target, limit))
        is_truncated = target == "styles.css" and not self.truncated
        self.truncated = self.truncated or is_truncated
        self.last_usage = {
            "duration_seconds": 0.1,
            "input_tokens": 100,
            "output_tokens": limit if is_truncated else 100,
            "total_tokens": 100 + (limit if is_truncated else 100),
        }
        if is_truncated:
            return '{"files": {"styles.css": "body { color: #111; }"'
        return json.dumps({"files": {target: GOOD_FILES[target]}})


def test_un_morceau_tronque_est_repris_sans_regenerer_les_precedents(project):
    provider = TruncateStylesOnce()

    ok, errors = generate_and_verify(str(project), provider, say=lambda _msg: None)

    assert ok, errors
    assert [target for target, _limit in provider.calls] == [
        "index.html", "styles.css", "styles.css", "app.js",
    ]
    styles_limits = [limit for target, limit in provider.calls if target == "styles.css"]
    assert styles_limits[1] > styles_limits[0]

    events = [json.loads(line) for line in
              (project / USAGE_FILENAME).read_text(encoding="utf-8").splitlines()]
    assert len(events) == len(provider.calls)
    assert all(event["run_id"] for event in events)
    assert [(event["stage"], event["retry"]) for event in events] == [
        ("index.html", 0), ("styles.css", 0),
        ("styles.css", 1), ("app.js", 0),
    ]
    assert events[1]["output_tokens"] == styles_limits[0]


class AlwaysTruncated:
    chunked_generation = True
    provider_name = "fake"
    model = "fake-always-truncated"
    max_output_tokens = 8_000
    last_usage = None

    def __init__(self):
        self.calls = []

    def __call__(self, prompt):
        target = _target(prompt)
        limit = self.max_output_tokens
        self.calls.append((target, limit))
        self.last_usage = {
            "duration_seconds": 0.1,
            "input_tokens": 100,
            "output_tokens": limit,
            "total_tokens": 100 + limit,
        }
        return json.dumps({"files": {target: "incomplet"}})[:-1]


def test_un_morceau_toujours_tronque_laisse_la_deuxieme_tentative_au_calme(project):
    provider = AlwaysTruncated()

    ok, errors = generate_and_verify(str(project), provider, say=lambda _msg: None)

    assert not ok
    assert errors
    assert len(provider.calls) == 2 * (CHUNK_MAX_RETRIES + 1)
    assert [target for target, _limit in provider.calls] == [
        "index.html"
    ] * (CHUNK_MAX_RETRIES + 1) * 2
    events = [json.loads(line) for line in
              (project / USAGE_FILENAME).read_text(encoding="utf-8").splitlines()]
    assert {event["attempt"] for event in events} == {1, 2}
    assert {event["retry"] for event in events} == set(range(CHUNK_MAX_RETRIES + 1))
    assert len({event["run_id"] for event in events}) == 1
