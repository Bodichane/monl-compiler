"""Régressions de la génération séquentielle avec fournisseur factice réel."""

import json

import pytest

from monl.cli import compile_project
from monl.frontend_ai import (
    USAGE_FILENAME,
    _build_chunk_prompt,
    _generate_chunked_files,
    generate_and_verify,
)

SPEC = """app ChunkRetryApp

entity Item
    label: String

# Le back-office est provisionné hors ligne ; ces tests vérifient le découpage
# de génération, pas une vitrine publique complète.
actor Admin

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


def test_le_contexte_conserve_tous_les_selecteurs_sans_rejouer_les_contenus():
    html = (
        '<main id="app" class="shell dark" data-page="home">'
        '<h1 class="hero-title">Prose éditoriale à ne pas recopier</h1>'
        '<section id="cards" class="grid cards" data-kind="items">'
        '<button class="action primary" data-action="save">Enregistrer</button>'
        '</section></main>'
    )
    css = (
        ".shell { color: #111; }\n"
        ".dark .hero-title, #cards .grid.cards { font-weight: 700; }\n"
        "@media (max-width: 700px) { .action.primary { display: block; } }"
    )
    files = {
        "index.html": html,
        "styles.css": css,
        "app.js": "const prose = 'ce JavaScript ne doit pas être recopié';",
        "illustration.svg": "<svg xmlns=\"http://www.w3.org/2000/svg\"><path /></svg>",
    }

    styles_prompt = _build_chunk_prompt("brief", "styles.css", files)
    app_prompt = _build_chunk_prompt("brief", "app.js", files)

    for prompt in (styles_prompt, app_prompt):
        assert 'id="app"' in prompt
        assert 'class="shell dark"' in prompt
        assert 'data-page="home"' in prompt
        assert 'id="cards"' in prompt
        assert 'class="grid cards"' in prompt
        assert 'data-kind="items"' in prompt
        assert 'data-action="save"' in prompt
        assert "Prose éditoriale" not in prompt
        assert "illustration.svg" in prompt
        assert "<svg" not in prompt

    assert ".shell" in app_prompt
    assert ".dark .hero-title, #cards .grid.cards" in app_prompt
    assert ".action.primary" in app_prompt
    assert "color: #111" not in app_prompt
    assert "ce JavaScript ne doit pas être recopié" not in app_prompt


def test_la_generation_decoupee_reduit_l_entree_cumulee(tmp_path):
    generated = {
        "index.html": (
            '<main id="app" class="shell dark" data-page="home">'
            '<p class="editorial">' + "prose " * 300 + "</p></main>"
        ),
        "styles.css": ".shell { color: #111; }\n" + "/* CSS */\n" * 100,
        "app.js": "const prose = '" + "texte " * 300 + "';",
    }

    class CountingProvider:
        chunked_generation = True
        provider_name = "fake-measurement"
        model = "fake"
        max_output_tokens = 8_000
        last_usage = None

        def __init__(self):
            self.prompts = []

        def __call__(self, prompt):
            self.prompts.append(prompt)
            target = _target(prompt)
            self.last_usage = {
                "duration_seconds": 0.0,
                "input_tokens": 1,
                "output_tokens": 1,
                "total_tokens": 2,
            }
            return json.dumps({"files": {target: generated[target]}})

    provider = CountingProvider()
    _generate_chunked_files(
        str(tmp_path), provider, "brief", "construction", 1,
        lambda _msg: None, run_id="measure",
    )

    legacy_states = (
        {},
        {"index.html": generated["index.html"]},
        {"index.html": generated["index.html"], "styles.css": generated["styles.css"]},
    )
    legacy_total = 0
    marker = "## Fichiers déjà générés — à respecter\n"
    for prompt, state in zip(provider.prompts, legacy_states, strict=True):
        prefix = prompt.split(marker, 1)[0] + marker
        context = "\n\n".join(
            f"### frontend/{path}\n```\n{state[path]}\n```"
            for path in ("index.html", "styles.css", "app.js")
            if path in state
        ) or "(aucun fichier généré pour le moment)"
        legacy_total += len(prefix + context)

    assert sum(map(len, provider.prompts)) < legacy_total


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


def test_un_morceau_toujours_tronque_n_effectue_pas_une_seconde_generation_complete(project):
    provider = AlwaysTruncated()

    ok, errors = generate_and_verify(str(project), provider, say=lambda _msg: None)

    assert not ok
    assert errors
    assert len(provider.calls) == 5
    assert [target for target, _limit in provider.calls] == ["index.html"] * 5
    assert [limit for _target_name, limit in provider.calls] == [
        8_000, 12_000, 18_000, 27_000, 32_000,
    ]
    assert "plafond maximal de sortie" in errors[0]
    assert "aucune seconde tentative complète" in errors[0]
    events = [json.loads(line) for line in
              (project / USAGE_FILENAME).read_text(encoding="utf-8").splitlines()]
    assert {event["attempt"] for event in events} == {1, 2}
    assert [(event["attempt"], event["retry"]) for event in events] == [
        (1, 0), (1, 1), (1, 2), (2, 0), (2, 1),
    ]
    assert len({event["run_id"] for event in events}) == 1
