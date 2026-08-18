"""Preuves du câblage plateforme des modèles et des images, sans réseau."""

import json

import pytest

from monl import cli, frontend_ai
from monl.image_ai import ImageProviderError
from monl.usage import build_usage_report
from monl_platform import builder
from monl_platform.console import CONSOLE_HTML
from monl_platform.paths import project_directory
from monl_platform.quota import TokenQuota
from monl_platform.store import PlatformStore
from monl_platform.worker import BuildWorker

SPEC = """app PlatformGeneration

entity Item
    label: String

actor Visitor selfRegister

rule Item.Read public

workflow Browse for Visitor
    Read Item
"""

SPEC_WITH_IMAGES = """app PlatformGenerationImages

assets
    dir: "media"

entity Project
    title: String
    description: Text

actor Visitor selfRegister

rule Project.Read public

workflow Browse for Visitor
    Read Project

landing
    brief: "Un atelier de céramique contemporaine, calme et tactile."
    section "Notre matière": "Chaque pièce naît d'un geste lent et d'une terre locale."
"""


class FakeTextProvider:
    chunked_generation = True
    provider_name = "fake-text"
    max_output_tokens = 8_000

    def __init__(self, model):
        self.model = model
        self.calls = []
        self.last_usage = None

    def __call__(self, prompt):
        target = next(
            line.rsplit(": ", 1)[1]
            for line in prompt.splitlines()
            if line.startswith("Le fichier cible est exactement : ")
        )
        self.calls.append(target)
        self.last_usage = {
            "duration_seconds": 0.01,
            "input_tokens": 10,
            "output_tokens": 5,
            "total_tokens": 15,
        }
        contents = {
            "index.html": (
                "<!doctype html><html><head><link rel='stylesheet' "
                "href='styles.css'></head><body><script src='app.js'></script>"
                "</body></html>"
            ),
            "styles.css": f"/* {self.model} */\nbody {{ margin: 0; }}",
            "app.js": f"// {self.model}\n",
        }
        return json.dumps({"files": {target: contents.get(target, "")}})


class FakeImageProvider:
    provider_name = "fake-image"
    model = "fake-image-model"

    def __init__(self):
        self.calls = []
        self.last_usage = None

    def __call__(self, prompt):
        self.calls.append(prompt)
        self.last_usage = {"duration_seconds": 0.01, "requests": 1}
        return b"\xff\xd8\xff\xe0fake-image\xff\xd9"


class FailingImageProvider(FakeImageProvider):
    message = "service image indisponible"

    def __call__(self, prompt):
        self.calls.append(prompt)
        self.last_usage = {"duration_seconds": 0.01, "requests": 1}
        raise ImageProviderError(self.message)


@pytest.fixture()
def platform(tmp_path):
    store = PlatformStore(tmp_path / "platform.db")
    account = store.create_account("generation@example.test")
    root = tmp_path / "projects"
    yield store, account, root
    store.close()


def _allow_frontend_verification(monkeypatch):
    monkeypatch.setattr(cli, "check_coherence", lambda _project: (True, [], []))
    monkeypatch.setattr(
        "monl.smoke_test.run_smoke_test",
        lambda _project, say=None: (True, [], []),
    )
    monkeypatch.setattr(frontend_ai, "_design_completeness_errors", lambda *_args: [])


def _build(platform, spec, *, model_routes=None, generate_images=False,
           text_model="model-global", image_provider=None, model_factory=None,
           image_factory=None):
    store, account, root = platform
    project = store.create_project(
        account,
        "site",
        model_routes=model_routes,
        generate_images=generate_images,
    )
    project_directory(root, account, project, create=True).joinpath("spec.ml").write_text(
        spec, encoding="utf-8"
    )
    global_provider = FakeTextProvider(text_model)

    def project_provider(_project, _build):
        return global_provider

    worker = BuildWorker(
        store,
        root,
        quota=TokenQuota(store, root, 100_000),
        provider_factory=project_provider,
        model_provider_factory=model_factory,
        image_provider_factory=image_factory,
        image_provider=image_provider,
        poll_interval=0,
    )
    build_id = store.create_build(project)
    result = worker.run_once()
    assert result["id"] == build_id
    return project, result, global_provider


def test_par_defaut_un_seul_modele_et_aucune_image(platform, monkeypatch):
    _allow_frontend_verification(monkeypatch)
    image_factory_calls = []

    def image_factory(_project, _build):
        image_factory_calls.append(True)
        return FakeImageProvider()

    project, build, provider = _build(
        platform,
        SPEC,
        image_factory=image_factory,
    )

    assert build["state"] == "reussie", build
    assert provider.calls == ["index.html", "styles.css", "app.js"]
    assert image_factory_calls == []
    stored = platform[0].get_project(project)
    assert stored["model_routes"] == {}
    assert stored["generate_images"] is False
    report = build_usage_report(str(platform[2] / "accounts" / str(platform[1]) / "projects" / str(project)))
    assert {item["model"] for item in report["totals"]} == {"model-global"}
    assert report["project_total"]["requests"] is None


def test_deux_constructions_conservent_leurs_snapshots(platform, monkeypatch):
    _allow_frontend_verification(monkeypatch)
    store, account, root = platform
    project = store.create_project(account, "versions")
    project_dir = project_directory(root, account, project, create=True)
    project_dir.joinpath("spec.ml").write_text(SPEC, encoding="utf-8")
    providers = iter((FakeTextProvider("premiere"), FakeTextProvider("seconde")))

    def project_provider(_project, _build):
        return next(providers)

    worker = BuildWorker(
        store,
        root,
        quota=TokenQuota(store, root, 100_000),
        provider_factory=project_provider,
        poll_interval=0,
    )
    first_id = store.create_build(project)
    first = worker.run_once()
    second_id = store.create_build(project)
    second = worker.run_once()

    assert first["id"] == first_id and first["state"] == "reussie"
    assert second["id"] == second_id and second["state"] == "reussie"
    assert first["snapshot_path"] == f"revisions/build-{first_id}"
    assert second["snapshot_path"] == f"revisions/build-{second_id}"
    first_styles = root / "accounts" / str(account) / "projects" / str(project) / first["snapshot_path"] / "frontend" / "styles.css"
    second_styles = root / "accounts" / str(account) / "projects" / str(project) / second["snapshot_path"] / "frontend" / "styles.css"
    assert "premiere" in first_styles.read_text(encoding="utf-8")
    assert "seconde" in second_styles.read_text(encoding="utf-8")


def test_routage_declare_produit_deux_modeles_dans_la_telemetrie(platform, monkeypatch):
    _allow_frontend_verification(monkeypatch)
    routed = {}

    def model_factory(model):
        routed[model] = FakeTextProvider(model)
        return routed[model]

    project, build, _provider = _build(
        platform,
        SPEC,
        model_routes={"styles.css": "model-css"},
        model_factory=model_factory,
    )

    assert build["state"] == "reussie", build
    assert list(routed) == ["model-css"]
    project_dir = platform[2] / "accounts" / str(platform[1]) / "projects" / str(project)
    report = build_usage_report(str(project_dir))
    assert {item["model"] for item in report["totals"]} == {
        "model-global",
        "model-css",
    }


def test_images_demandees_vont_dans_assets_et_restent_des_requetes(platform, monkeypatch):
    _allow_frontend_verification(monkeypatch)
    image = FakeImageProvider()

    project, build, _provider = _build(
        platform,
        SPEC_WITH_IMAGES,
        generate_images=True,
        image_factory=lambda _project, _build: image,
    )

    assert build["state"] == "reussie", build
    project_dir = platform[2] / "accounts" / str(platform[1]) / "projects" / str(project)
    manifest = json.loads(
        (project_dir / "ASSET_MANIFEST.json").read_text(encoding="utf-8").split("\n", 1)[1]
    )
    paths = [item["path"] for item in manifest["generated_assets"]]
    assert paths
    assert all((project_dir / path).is_file() for path in paths)
    assert len(image.calls) == len(paths)

    events = [
        json.loads(line)
        for line in (project_dir / ".monl_ai_usage.jsonl").read_text().splitlines()
    ]
    image_events = [event for event in events if event.get("billing_unit") == "request"]
    assert len(image_events) == len(paths)
    assert all(event["requests"] == 1 for event in image_events)
    assert all("total_tokens" not in event for event in image_events)
    report = build_usage_report(str(project_dir))
    assert report["project_total"]["requests"] == len(paths)
    assert report["project_total"]["total_tokens"] == 45


def test_panne_image_ne_fait_pas_echouer_le_frontend_texte(platform, monkeypatch):
    _allow_frontend_verification(monkeypatch)
    image = FailingImageProvider()

    project, build, provider = _build(
        platform,
        SPEC_WITH_IMAGES,
        generate_images=True,
        image_factory=lambda _project, _build: image,
    )

    assert build["state"] == "reussie", build
    assert len(provider.calls) == 6
    assert build["warning_message"]
    assert "sans images générées" in build["warning_message"]
    assert "Avertissement de construction" in CONSOLE_HTML
    assert not hasattr(builder, "_disable_generated_images")
    project_dir = platform[2] / "accounts" / str(platform[1]) / "projects" / str(project)
    manifest = json.loads(
        (project_dir / "ASSET_MANIFEST.json").read_text(encoding="utf-8").split("\n", 1)[1]
    )
    assert manifest["status"] == "active"
    assert manifest["generated_assets"] == []
    events = [
        json.loads(line)
        for line in (project_dir / ".monl_ai_usage.jsonl").read_text().splitlines()
    ]
    assert any(
        event.get("billing_unit") == "request" and event.get("status") == "error"
        for event in events
    )


def test_reformuler_le_message_image_ne_desarme_pas_le_repli(platform, monkeypatch):
    _allow_frontend_verification(monkeypatch)
    image = FailingImageProvider()
    image.message = "le service a changé de formulation et reste indisponible"

    project, build, _provider = _build(
        platform,
        SPEC_WITH_IMAGES,
        generate_images=True,
        image_factory=lambda _project, _build: image,
    )

    assert build["state"] == "reussie", build
    assert build["warning_message"]
    project_dir = platform[2] / "accounts" / str(platform[1]) / "projects" / str(project)
    manifest = json.loads(
        (project_dir / "ASSET_MANIFEST.json").read_text(encoding="utf-8").split("\n", 1)[1]
    )
    assert manifest["generated_assets"] == []


def test_cible_de_routage_inconnue_est_refusee_en_la_nommant(platform, monkeypatch):
    _allow_frontend_verification(monkeypatch)
    project, build, provider = _build(
        platform,
        SPEC,
        model_routes={"cible-inconnue": "model-css"},
        model_factory=lambda model: FakeTextProvider(model),
    )

    assert build["state"] == "echouee"
    assert "cible-inconnue" in build["error_message"]
    assert provider.calls == []
