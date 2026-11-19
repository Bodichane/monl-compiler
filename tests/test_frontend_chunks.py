"""Regressions of sequential generation with a real fake provider."""

import json
import re

import pytest

from monl.cli import compile_project
from monl.frontend_ai import (
    CHUNK_MAX_RETRIES,
    CHUNK_RETRY_MAX_OUTPUT_TOKENS,
    CHUNK_RETRY_OUTPUT_TOKEN_FACTOR,
    DEFAULT_CHUNK_MAX_OUTPUT_TOKENS,
    USAGE_FILENAME,
    _build_chunk_prompt,
    _generate_chunked_files,
    generate_and_verify,
)

SPEC = """app ChunkRetryApp

entity Item
    label: String

# The back office is provisioned offline; these tests check the generation
# splitting, not a complete public showcase.
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
                 if line.startswith("The target file is exactly: "))
    return line.rsplit(": ", 1)[1]


def test_the_context_keeps_all_selectors_without_replaying_contents():
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


def test_split_generation_reduces_cumulative_input(tmp_path):
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


def test_a_truncated_chunk_is_resumed_without_regenerating_previous_ones(project):
    provider = TruncateStylesOnce()

    ok, errors = generate_and_verify(str(project), provider, say=lambda _msg: None)

    assert ok, errors
    assert [target for target, _limit in provider.calls] == [
        "index.html", "styles.css", "styles.css", "app.js",
    ]
    styles_limits = [limit for target, limit in provider.calls if target == "styles.css"]
    assert styles_limits[1] > styles_limits[0]
    assert provider.calls[-1] == ("app.js", 8_000)
    assert provider.max_output_tokens == 8_000

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


def test_an_always_truncated_chunk_does_not_run_a_second_full_generation(project):
    provider = AlwaysTruncated()

    ok, errors = generate_and_verify(str(project), provider, say=lambda _msg: None)

    assert not ok
    assert errors
    assert len(provider.calls) == 3
    assert [target for target, _limit in provider.calls] == ["index.html"] * 3
    # The steps are DERIVED from the constants, never copied: hard-coded here,
    # they had let the ladder climb 8,000 → 12,000 → 18,000 while the code
    # announced a 32,000 bound nothing reached.
    paliers = [limit for _target_name, limit in provider.calls]
    attendus = [DEFAULT_CHUNK_MAX_OUTPUT_TOKENS]
    while len(attendus) <= CHUNK_MAX_RETRIES:
        suivant = min(int(attendus[-1] * CHUNK_RETRY_OUTPUT_TOKEN_FACTOR),
                      CHUNK_RETRY_MAX_OUTPUT_TOKENS)
        attendus.append(suivant)
    assert paliers == attendus, (paliers, attendus)
    assert paliers[-1] == CHUNK_RETRY_MAX_OUTPUT_TOKENS, (
        "la dernière reprise n'atteint pas la borne déclarée : celle-ci ne "
        "contraint alors rien, et le message d'erreur qui la cite ment")
    assert "no second complete attempt" in errors[0]
    events = [json.loads(line) for line in
              (project / USAGE_FILENAME).read_text(encoding="utf-8").splitlines()]
    assert {event["attempt"] for event in events} == {1}
    assert [(event["attempt"], event["retry"]) for event in events] == [
        (1, 0), (1, 1), (1, 2),
    ]
    assert len({event["run_id"] for event in events}) == 1


class AppTimeoutAfterValidChunks:
    chunked_generation = True
    provider_name = "fake"
    model = "fake-timeout"
    max_output_tokens = 8_000
    last_usage = None

    def __init__(self):
        self.calls = []

    def __call__(self, prompt):
        target = _target(prompt)
        self.calls.append(target)
        self.last_usage = {
            "duration_seconds": 0.1,
            "input_tokens": 100,
            "output_tokens": 10,
            "total_tokens": 110,
        }
        if target == "app.js":
            from monl.frontend_ai import FrontendAIError
            raise FrontendAIError("délai fournisseur dépassé")
        return json.dumps({"files": {target: GOOD_FILES[target]}})


def test_a_chunk_timeout_does_not_replay_already_paid_files(project):
    provider = AppTimeoutAfterValidChunks()

    ok, errors = generate_and_verify(str(project), provider, say=lambda _msg: None)

    assert not ok
    assert "no second complete attempt" in errors[0]
    assert provider.calls == [
        "index.html", "styles.css",
        "app.js", "app.js", "app.js",
    ]


# ---- The requested budget follows the contract (point 149) ----

def _contract(tmp_path, nb_routes, nb_entites=3):
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "frontend_contract.json").write_text(json.dumps({
        "routes": [{"method": "GET", "path": f"/r{i}"} for i in range(nb_routes)],
        "entities": {f"E{i}": {} for i in range(nb_entites)},
    }), encoding="utf-8")
    return str(tmp_path)


def test_the_app_js_budget_follows_the_number_of_routes(tmp_path):
    """monl asked for "about 1,500 tokens" whatever the contract.

    Measured against the real service: the model obeys to the token — 1,698 of
    output for a fifteen-route shop — then monl refuses the file as incomplete.
    We asked for the impossible, then rejected it. The repository's complete
    frontends weigh 26 to 43 KB, that is 7,000 to 11,000 tokens.
    """
    from monl.frontend_ai import ampleur_du_contrat

    petit = _build_chunk_prompt("brief", "app.js", {},
                                ampleur_du_contrat(_contract(tmp_path / "a", 2)))
    grand = _build_chunk_prompt("brief", "app.js", {},
                                ampleur_du_contrat(_contract(tmp_path / "b", 15)))

    assert _vise(grand) > _vise(petit), (_vise(petit), _vise(grand))
    assert _vise(grand) >= 6_000, "un contrat à 15 routes ne tient pas en moins"
    assert "1,500 tokens" not in grand and "1500 tokens" not in grand


def test_the_budget_never_exceeds_the_stage_ceiling(tmp_path):
    """Asking more than the stage can return would produce a truncation on every
    build: the output ceiling is the real bound."""
    from monl.frontend_ai import DEFAULT_CHUNK_MAX_OUTPUT_TOKENS, ampleur_du_contrat

    enorme = _build_chunk_prompt("brief", "app.js", {},
                                 ampleur_du_contrat(_contract(tmp_path / "c", 400)))

    assert _vise(enorme) <= DEFAULT_CHUNK_MAX_OUTPUT_TOKENS


def test_the_hard_limit_no_longer_contradicts_the_budget(tmp_path):
    """It was 12,000 characters for a 26 to 43 KB file."""
    from monl.frontend_ai import ampleur_du_contrat

    prompt = _build_chunk_prompt("brief", "app.js", {},
                                 ampleur_du_contrat(_contract(tmp_path / "d", 15)))
    caracteres = int(re.search(r"finish before (\d+) characters", prompt).group(1))

    assert caracteres >= _vise(prompt) * 3, (
        "la limite dure recoupe le budget demandé : le modèle obéit à la plus "
        "petite des deux, et c'est elle qui décide de la complétude")


def test_the_route_floor_is_STATED_to_the_model(tmp_path):
    """The brief said "call ONLY the listed routes" — a ceiling. The refusal,
    however, is about a floor nothing stated at the stage."""
    from monl.frontend_ai import ampleur_du_contrat

    prompt = _build_chunk_prompt("brief", "app.js", {},
                                 ampleur_du_contrat(_contract(tmp_path / "e", 15)))

    assert "15 routes" in prompt
    assert "REFUSED" in prompt


def test_without_readable_contract_sizing_does_not_break(tmp_path):
    """Tests and historical calls have no contract at hand."""
    from monl.frontend_ai import ampleur_du_contrat

    assert ampleur_du_contrat(str(tmp_path / "nulle-part")) is None
    prompt = _build_chunk_prompt("brief", "app.js", {}, None)
    assert "Aim for about" in prompt


def _vise(prompt):
    return int(re.search(r"Aim for about (\d+) tokens", prompt).group(1))
