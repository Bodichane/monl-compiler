"""Régressions de la génération séquentielle avec fournisseur factice réel."""

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


def test_un_morceau_toujours_tronque_n_effectue_pas_une_seconde_generation_complete(project):
    provider = AlwaysTruncated()

    ok, errors = generate_and_verify(str(project), provider, say=lambda _msg: None)

    assert not ok
    assert errors
    assert len(provider.calls) == 3
    assert [target for target, _limit in provider.calls] == ["index.html"] * 3
    # Les paliers sont DÉRIVÉS des constantes, jamais recopiés : figés ici en
    # dur, ils avaient laissé l'échelle monter 8 000 → 12 000 → 18 000 pendant
    # que le code annonçait une borne de 32 000 que rien n'atteignait.
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
    assert "aucune seconde tentative complète" in errors[0]
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


def test_timeout_d_un_morceau_ne_rejoue_pas_les_fichiers_deja_payes(project):
    provider = AppTimeoutAfterValidChunks()

    ok, errors = generate_and_verify(str(project), provider, say=lambda _msg: None)

    assert not ok
    assert "aucune seconde tentative complète" in errors[0]
    assert provider.calls == [
        "index.html", "styles.css",
        "app.js", "app.js", "app.js",
    ]


# ---- Le budget demandé suit le contrat (point 146) ----

def _contrat(tmp_path, nb_routes, nb_entites=3):
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "frontend_contract.json").write_text(json.dumps({
        "routes": [{"method": "GET", "path": f"/r{i}"} for i in range(nb_routes)],
        "entities": {f"E{i}": {} for i in range(nb_entites)},
    }), encoding="utf-8")
    return str(tmp_path)


def test_le_budget_d_app_js_suit_le_nombre_de_routes(tmp_path):
    """monl demandait « environ 1 500 tokens » quel que soit le contrat.

    Mesuré contre le vrai service : le modèle obéit au jeton près — 1 698 de
    sortie pour une boutique à quinze routes — puis monl refuse le fichier
    pour incomplétude. On demandait l'impossible, puis on le rejetait. Les
    frontends complets du dépôt pèsent 26 à 43 Ko, soit 7 000 à 11 000 jetons.
    """
    from monl.frontend_ai import ampleur_du_contrat

    petit = _build_chunk_prompt("brief", "app.js", {},
                                ampleur_du_contrat(_contrat(tmp_path / "a", 2)))
    grand = _build_chunk_prompt("brief", "app.js", {},
                                ampleur_du_contrat(_contrat(tmp_path / "b", 15)))

    assert _vise(grand) > _vise(petit), (_vise(petit), _vise(grand))
    assert _vise(grand) >= 6_000, "un contrat à 15 routes ne tient pas en moins"
    assert "1 500 tokens" not in grand and "1500 tokens" not in grand


def test_le_budget_ne_depasse_jamais_le_plafond_de_l_etage(tmp_path):
    """Demander plus que ce que l'étage peut rendre produirait une troncature
    à chaque construction : le plafond de sortie est la vraie borne."""
    from monl.frontend_ai import DEFAULT_CHUNK_MAX_OUTPUT_TOKENS, ampleur_du_contrat

    enorme = _build_chunk_prompt("brief", "app.js", {},
                                 ampleur_du_contrat(_contrat(tmp_path / "c", 400)))

    assert _vise(enorme) <= DEFAULT_CHUNK_MAX_OUTPUT_TOKENS


def test_la_limite_dure_ne_contredit_plus_le_budget(tmp_path):
    """Elle valait 12 000 caractères pour un fichier de 26 à 43 Ko."""
    from monl.frontend_ai import ampleur_du_contrat

    prompt = _build_chunk_prompt("brief", "app.js", {},
                                 ampleur_du_contrat(_contrat(tmp_path / "d", 15)))
    caracteres = int(re.search(r"termine avant (\d+) caractères", prompt).group(1))

    assert caracteres >= _vise(prompt) * 3, (
        "la limite dure recoupe le budget demandé : le modèle obéit à la plus "
        "petite des deux, et c'est elle qui décide de la complétude")


def test_le_plancher_de_routes_est_ENONCE_au_modele(tmp_path):
    """Le brief disait « n'appeler QUE les routes listées » — un plafond.
    Le refus, lui, porte sur un plancher que rien n'énonçait à l'étage."""
    from monl.frontend_ai import ampleur_du_contrat

    prompt = _build_chunk_prompt("brief", "app.js", {},
                                 ampleur_du_contrat(_contrat(tmp_path / "e", 15)))

    assert "15 routes" in prompt
    assert "REFUSÉ" in prompt


def test_sans_contrat_lisible_le_dimensionnement_ne_casse_pas(tmp_path):
    """Les tests et les appels historiques n'ont pas de contrat sous la main."""
    from monl.frontend_ai import ampleur_du_contrat

    assert ampleur_du_contrat(str(tmp_path / "nulle-part")) is None
    prompt = _build_chunk_prompt("brief", "app.js", {}, None)
    assert "Vise environ" in prompt


def _vise(prompt):
    return int(re.search(r"Vise environ (\d+) tokens", prompt).group(1))
