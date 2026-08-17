"""Preuves réelles du fournisseur d'images et de son branchement frontend."""

import base64
import json

import pytest

from monl import cli
from monl.cli import compile_project
from monl.frontend_ai import generate_and_verify
from monl.image_ai import ImageProviderError, yandexart_provider
from monl.usage import build_usage_report

SPEC = """app AtelierImage

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

JPEG_BYTES = b"\xff\xd8\xff\xe0monl-test-image\xff\xd9"


def _manifest(project):
    lines = (project / "ASSET_MANIFEST.json").read_text(encoding="utf-8").splitlines()
    return json.loads("\n".join(lines[1:]))


def _frontend_from_manifest(project):
    manifest = _manifest(project)
    markers = manifest["required_markers"]["index.html"]
    images = [item["path"] for item in manifest["generated_assets"]]
    sections = "\n".join(f"<section {marker}></section>" for marker in markers)
    pictures = "\n".join(
        f'<img src="{path}" alt="visuel du projet">' for path in images
    )
    return f"<!doctype html><html><body>{sections}{pictures}</body></html>"


class FakeImageProvider:
    provider_name = "fake-image"
    model = "fake-image-model"

    def __init__(self):
        self.prompts = []
        self.last_usage = None

    def __call__(self, prompt):
        self.prompts.append(prompt)
        self.last_usage = {"duration_seconds": 0.01, "requests": 1}
        return JPEG_BYTES


class FakeTextProvider:
    provider_name = "fake-text"
    model = "fake-text-model"

    def __init__(self, project):
        self.project = project
        self.prompts = []
        self.last_usage = None

    def __call__(self, prompt):
        self.prompts.append(prompt)
        assert "media/generated/hero.jpg" in prompt
        assert "Un atelier de céramique contemporaine" in prompt
        self.last_usage = {
            "duration_seconds": 0.02,
            "input_tokens": 30,
            "output_tokens": 20,
            "total_tokens": 50,
        }
        return json.dumps({"files": {"index.html": _frontend_from_manifest(self.project)}})


def _project(tmp_path):
    project = tmp_path / "projet"
    project.mkdir()
    spec = project / "spec.ml"
    spec.write_text(SPEC, encoding="utf-8")
    compile_project(str(spec), str(project))
    return project


def test_aucune_image_par_defaut_meme_si_le_brief_en_parle(tmp_path):
    project = _project(tmp_path)
    manifest = _manifest(project)

    assert manifest["generated_assets"] == []
    assert not (project / "media" / "generated").exists()


def test_option_explicite_produit_des_octets_dans_assets_et_les_reference(tmp_path):
    project = _project(tmp_path)
    images = FakeImageProvider()
    text = FakeTextProvider(project)

    ok, errors = generate_and_verify(
        str(project), text, image_provider=images, generate_images=True,
        say=lambda _message: None,
    )

    assert ok, errors
    manifest = _manifest(project)
    paths = [item["path"] for item in manifest["generated_assets"]]
    assert paths == ["media/generated/hero.jpg", "media/generated/editorial.jpg"]
    assert all((project / path).read_bytes() == JPEG_BYTES for path in paths)
    assert not any((project / "frontend" / path).exists() for path in paths)
    assert all(path in text.prompts[0] for path in paths)
    assert all("Brief de l'auteur" in prompt for prompt in images.prompts)
    assert all("Chaque pièce naît" in prompt for prompt in images.prompts)


def test_cle_yandexart_absente_nomme_la_variable_sans_casser_le_texte(tmp_path, monkeypatch):
    monkeypatch.delenv("YANDEX_API_KEY", raising=False)
    monkeypatch.setenv("YANDEX_FOLDER_ID", "folder-test")

    with pytest.raises(ImageProviderError) as error:
        yandexart_provider()
    assert "YANDEX_API_KEY" in str(error.value)
    assert error.value.status_code == 503

    project = _project(tmp_path)
    text = FakeTextProvider(project)
    text.last_usage = None
    # L'option n'étant pas demandée, le fournisseur image absent n'est jamais
    # construit et la voie texte reste exploitable.
    content = "<html><body>" + "".join(
        f"<section {marker}></section>"
        for marker in _manifest(project)["required_markers"]["index.html"]
    ) + "</body></html>"
    def text_provider(_prompt):
        return json.dumps({"files": {"index.html": content}})
    text_provider.provider_name = "fake-text"
    text_provider.model = "fake-text-model"
    text_provider.last_usage = {"duration_seconds": 0.01,
                                "input_tokens": 1, "output_tokens": 1,
                                "total_tokens": 2}
    ok, errors = generate_and_verify(str(project), text_provider, say=lambda _m: None)
    assert ok, errors


def test_prereglage_yandexart_rend_des_octets_et_son_authentification(monkeypatch):
    monkeypatch.setenv("YANDEX_API_KEY", "cle-image")
    monkeypatch.setenv("YANDEX_FOLDER_ID", "folder-image")
    monkeypatch.setenv("MONL_IMAGE_POLL_INTERVAL", "0.001")
    image = base64.b64encode(JPEG_BYTES).decode("ascii")
    calls = {}

    class Response:
        status_code = 200
        text = ""

        def __init__(self, payload):
            self.payload = payload

        def json(self):
            return self.payload

    def post(url, headers=None, json=None, timeout=None):
        calls["post"] = (url, headers, json, timeout)
        return Response({"id": "operation-image"})

    def get(url, headers=None, timeout=None):
        calls["get"] = (url, headers, timeout)
        return Response({"done": True, "response": {"image": image}})

    import requests
    monkeypatch.setattr(requests, "post", post)
    monkeypatch.setattr(requests, "get", get)

    provider = yandexart_provider()
    assert provider("matière de l'atelier") == JPEG_BYTES
    assert calls["post"][0].endswith("/foundationModels/v1/imageGenerationAsync")
    assert calls["post"][1]["Authorization"] == "Api-Key cle-image"
    assert calls["post"][2]["modelUri"] == "art://folder-image/yandex-art/latest"
    assert calls["post"][2]["generationOptions"]["mimeType"] == "image/jpeg"
    assert calls["get"][0].endswith("/operations/operation-image")


def test_mesure_image_requete_sans_jetons_et_usage_ne_la_compte_pas_gratuite(tmp_path):
    project = _project(tmp_path)
    images = FakeImageProvider()
    text = FakeTextProvider(project)
    ok, errors = generate_and_verify(
        str(project), text, image_provider=images, generate_images=True,
        say=lambda _message: None,
    )
    assert ok, errors

    events = [json.loads(line) for line in
              (project / ".monl_ai_usage.jsonl").read_text(encoding="utf-8").splitlines()]
    image_events = [event for event in events if event.get("billing_unit") == "request"]
    assert len(image_events) == 2
    assert {event["run_id"] for event in image_events} == {events[-1]["run_id"]}
    assert all(event["requests"] == 1 for event in image_events)
    assert all(name not in image_events[0] for name in (
        "input_tokens", "output_tokens", "total_tokens"))

    prices = tmp_path / "prices.json"
    prices.write_text(json.dumps({
        "currency": "RUB",
        "prices": {
            "fake-image": {"fake-image-model": {"per_request": 2.5}},
            "fake-text": {"fake-text-model": {
                "input_per_million_tokens": 100,
                "output_per_million_tokens": 200,
            }},
        },
    }), encoding="utf-8")
    report = build_usage_report(str(project), str(prices))
    assert report["project_total"]["requests"] == 2
    assert report["project_total"]["input_tokens"] == 30
    assert report["project_total"]["cost"] > 0
    assert report["project_total"]["cost"] != 0
    usage_line = cli._usage_total_line(report["project_total"], "RUB")
    assert "30" in usage_line and "2 requête(s) d'image" in usage_line
