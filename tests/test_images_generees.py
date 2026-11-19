"""Real proofs of the image provider and of its frontend wiring."""

import base64
import json
from io import BytesIO

import pytest
from section_helpers import manifest_sections

from monl import cli, image_ai
from monl.cli import compile_project
from monl.frontend_ai import _image_prompt, generate_and_verify
from monl.image_ai import (
    YANDEXART_MAX_PROMPT_CHARS,
    ImageProviderError,
    optimize_image_bytes,
    yandexart_provider,
)
from monl.usage import build_usage_report

SPEC = """app AtelierImage

assets
    dir: "media"

entity Project
    title: String
    description: Text

# The visitor role is provisioned offline in this image generation test; the
# minimal frontend does not promise an account journey.
actor Visitor

rule Project.Read public

workflow Browse for Visitor
    Read Project

landing
    brief: "Un atelier de céramique contemporaine, calme et tactile."
    section "Notre matière": "Chaque pièce naît d'un geste lent et d'une terre locale."
"""

SPEC_SANS_SECTIONS = SPEC.replace(
    "    description: Text\n",
    "    description: Text\n    price: Money\n    image: Image\n",
).replace(
    '    section "Notre matière": "Chaque pièce naît d\'un geste lent et d\'une terre locale."\n',
    "",
)

JPEG_BYTES = b"\xff\xd8\xff\xe0monl-test-image\xff\xd9"
VERBOSE_BRIEF = (
    "Boutique de céramique artisanale, ton éditorial sobre — utiliser "
    "immédiatement le parcours principal attendu pour cette catégorie ; "
    "registre affirmé et graphique : grandes échelles typographiques, "
    "contrastes marqués, parti pris visuel assumé ; les images portent le "
    "site (photo, œuvre, produit) : elles occupent de grandes surfaces et "
    "commandent la mise en page ; mode express : l’IA frontend rédige les "
    "textes de présentation manquants, crée une page dense en blocs utiles et "
    "produit des illustrations SVG locales cohérentes, sans inventer de donnée, "
    "de route ni de fonctionnalité. Les illustrations doivent évoquer : products."
)


def _manifest(project):
    lines = (project / "docs/ASSET_MANIFEST.json").read_text(encoding="utf-8").splitlines()
    return json.loads("\n".join(lines[1:]))


def _frontend_from_manifest(project):
    manifest = _manifest(project)
    images = [item["path"] for item in manifest["generated_assets"]]
    sections = manifest_sections(manifest)
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


class AspectRatioImageProvider:
    provider_name = "fake-image-aspect-ratio"
    model = "fake-image-aspect-ratio-model"

    def __init__(self):
        self.aspect_ratios = []
        self.last_usage = None

    def __call__(self, prompt, *, aspect_ratio=None):
        del prompt
        self.aspect_ratios.append(aspect_ratio)
        self.last_usage = {"duration_seconds": 0.01, "requests": 1}
        return JPEG_BYTES


class FailingImageProvider:
    provider_name = "fake-image-failing"
    model = "fake-image-failing-model"
    max_prompt_chars = YANDEXART_MAX_PROMPT_CHARS

    def __init__(self):
        self.prompts = []
        self.last_usage = None

    def __call__(self, prompt):
        self.prompts.append(prompt)
        raise ImageProviderError("YandexART unavailable for this build")


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


class ReusingTextProvider(FakeTextProvider):
    def __call__(self, prompt):
        self.prompts.append(prompt)
        manifest = _manifest(self.project)
        paths = [item["path"] for item in manifest["generated_assets"]]
        sections = manifest_sections(manifest)
        images = "".join(
            f'<img src="{path}" alt="visuel du projet">'
            f'<img src="{path}" alt="visuel dupliqué">'
            for path in paths
        )
        self.last_usage = {
            "duration_seconds": 0.02,
            "input_tokens": 30,
            "output_tokens": 20,
            "total_tokens": 50,
        }
        return json.dumps({"files": {"index.html": sections + images}})


def _project(tmp_path):
    project = tmp_path / "projet"
    project.mkdir()
    spec = project / "spec.ml"
    spec.write_text(SPEC, encoding="utf-8")
    compile_project(str(spec), str(project))
    return project


def _project_without_sections(tmp_path):
    project = tmp_path / "projet-sans-sections"
    project.mkdir()
    spec = project / "spec.ml"
    spec.write_text(SPEC_SANS_SECTIONS, encoding="utf-8")
    compile_project(str(spec), str(project))
    return project


def _verbose_project(tmp_path):
    project = tmp_path / "projet-bavard"
    project.mkdir()
    spec = project / "spec.ml"
    spec.write_text(SPEC.replace(
        "Un atelier de céramique contemporaine, calme et tactile.",
        VERBOSE_BRIEF), encoding="utf-8")
    compile_project(str(spec), str(project))
    return project


def test_no_image_by_default_even_if_the_brief_mentions_one(tmp_path):
    project = _project(tmp_path)
    manifest = _manifest(project)

    assert manifest["generated_assets"] == []
    assert not (project / "media" / "generated").exists()


def test_explicit_option_produces_bytes_in_assets_and_references_them(tmp_path):
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
    assert (
        "`media/generated/hero.jpg` — role: main banner of the first screen — "
        "single use required: render this file only once — "
        "detail: exact HTML block: `data-monl-section=\"hero\"`"
        in text.prompts[0]
    )
    assert (
        "`media/generated/editorial.jpg` — role: secondary thumbnail for the story or the "
        "proof — single use required: render this file only once — "
        "detail: exact HTML block: `data-monl-section=\"notre-matiere\"`"
        in text.prompts[0]
    )
    # The image prompt is now a dedicated composition; it no longer copies the
    # instruction block meant for the code model.
    assert all("Subject:" in prompt for prompt in images.prompts)
    assert all("Chaque pièce naît" in prompt for prompt in images.prompts)


def test_matching_by_role_and_single_use_without_section(tmp_path):
    project = _project_without_sections(tmp_path)
    images = FakeImageProvider()
    text = FakeTextProvider(project)

    ok, errors = generate_and_verify(
        str(project), text, image_provider=images, generate_images=True,
        say=lambda _message: None,
    )

    assert ok, errors
    manifest = _manifest(project)
    assert manifest["unique_section_markers"]["index.html"] == []
    generated = manifest["generated_assets"]
    assert len(generated) == 2
    prompt_lines = text.prompts[0].splitlines()
    for item in generated:
        line = next(line for line in prompt_lines if item["path"] in line)
        assert line.startswith(
            f"- `{item['path']}` — role: {item['role']} — single use "
            "required: render this file only once"
        )
        assert line.count(item["path"]) == 1
    assert "bloc HTML distinct à choisir" not in text.prompts[0]
    assert "distinct HTML block to choose" not in text.prompts[0]


def test_verification_refuses_reuse_even_without_section(tmp_path):
    project = _project_without_sections(tmp_path)
    images = FakeImageProvider()
    text = ReusingTextProvider(project)

    ok, errors = generate_and_verify(
        str(project), text, image_provider=images, generate_images=True,
        say=lambda _message: None,
    )

    assert not ok
    assert len([error for error in errors
                if "generated asset reused" in error]) == 2
    assert all(
        f"`{item['path']}` — role: {item['role']} — single use required"
        in text.prompts[0]
        for item in _manifest(project)["generated_assets"]
    )


def test_reuse_is_reported_once_per_asset(tmp_path):
    project = _project(tmp_path)
    images = FakeImageProvider()
    text = ReusingTextProvider(project)

    ok, errors = generate_and_verify(
        str(project), text, image_provider=images, generate_images=True,
        say=lambda _message: None,
    )

    assert not ok
    reuse_errors = [error for error in errors
                    if "generated asset reused" in error]
    assert len(reuse_errors) == 2
    assert sum("media/generated/hero.jpg" in error for error in reuse_errors) == 1
    assert sum("media/generated/editorial.jpg" in error for error in reuse_errors) == 1


def test_image_prompt_fits_a_verbose_project_under_the_ceiling_and_keeps_substance(
        tmp_path):
    project = _verbose_project(tmp_path)
    prompt = _image_prompt(
        str(project), {"role": "main banner of the first screen"},
        max_chars=YANDEXART_MAX_PROMPT_CHARS)

    assert len(prompt) <= YANDEXART_MAX_PROMPT_CHARS
    assert "céramique artisanale" in prompt
    assert "products" in prompt
    assert "main banner of the first screen" in prompt
    assert "registre affirmé et graphique" in prompt
    assert "media/generated/hero.jpg" not in prompt
    assert "frontend" not in prompt.lower()
    assert "route" not in prompt.lower()
    assert "fonctionnalité" not in prompt.lower()
    assert "feature" not in prompt.lower()
    assert "illustrations svg" not in prompt.lower()


def test_image_prompt_reduction_cuts_neither_word_nor_sentence(tmp_path):
    project = _verbose_project(tmp_path)
    contract_path = project / "frontend_contract.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    contract["brief"] = (
        "Atelier de céramique — registre sobre; ton Première phrase complète.; "
        "ton " + "motlong " * 300 + "; ton Deuxième phrase complète."
    )
    contract_path.write_text(json.dumps(contract, ensure_ascii=False), encoding="utf-8")

    prompt = _image_prompt(
        str(project), {"role": "visuel de récit"},
        max_chars=YANDEXART_MAX_PROMPT_CHARS)

    assert len(prompt) <= YANDEXART_MAX_PROMPT_CHARS
    assert "Première phrase complète." in prompt
    assert "Deuxième phrase complète." not in prompt
    assert not prompt.splitlines()[0].endswith("motlon")


def test_yandexart_locally_refuses_a_prompt_above_its_ceiling(
        monkeypatch):
    monkeypatch.setenv("YANDEX_API_KEY", "cle-image")
    monkeypatch.setenv("YANDEX_FOLDER_ID", "folder-image")

    import requests
    monkeypatch.setattr(
        requests, "post", lambda *_args, **_kwargs: pytest.fail("no HTTP expected"))

    provider = yandexart_provider()
    with pytest.raises(ImageProviderError, match="YandexART prompt is too long"):
        provider("x" * (YANDEXART_MAX_PROMPT_CHARS + 1))


def test_image_failure_lets_the_frontend_be_written_then_the_manifest_refuses(
        tmp_path):
    project = _project(tmp_path)
    images = FailingImageProvider()
    text = FakeTextProvider(project)
    messages = []

    ok, errors = generate_and_verify(
        str(project), text, image_provider=images, generate_images=True,
        say=messages.append,
    )

    assert not ok
    assert len(text.prompts) == 1
    assert (project / "frontend" / "index.html").is_file()
    assert any("Image not generated" in message for message in messages)
    assert any("generated asset missing" in error for error in errors)


def test_the_role_declares_the_ratio_and_the_provider_receives_it(tmp_path):
    project = _project(tmp_path)
    images = AspectRatioImageProvider()
    text = FakeTextProvider(project)

    ok, errors = generate_and_verify(
        str(project), text, image_provider=images, generate_images=True,
        say=lambda _message: None,
    )

    assert ok, errors
    generated = _manifest(project)["generated_assets"]
    assert generated[0]["role"] == "main banner of the first screen"
    assert generated[0]["aspect_ratio"] == {"width": 16, "height": 9}
    assert "aspect_ratio" not in generated[1]
    assert images.aspect_ratios == [{"width": 16, "height": 9}, None]


def test_missing_yandexart_key_names_the_variable_without_breaking_text(tmp_path, monkeypatch):
    monkeypatch.delenv("YANDEX_API_KEY", raising=False)
    monkeypatch.setenv("YANDEX_FOLDER_ID", "folder-test")

    with pytest.raises(ImageProviderError) as error:
        yandexart_provider()
    assert "YANDEX_API_KEY" in str(error.value)
    assert error.value.status_code == 503

    project = _project(tmp_path)
    text = FakeTextProvider(project)
    text.last_usage = None
    # The option not being requested, the missing image provider is never built
    # and the text path stays usable.
    content = ("<html><body>" + manifest_sections(_manifest(project))
               + "</body></html>")
    def text_provider(_prompt):
        return json.dumps({"files": {"index.html": content}})
    text_provider.provider_name = "fake-text"
    text_provider.model = "fake-text-model"
    text_provider.last_usage = {"duration_seconds": 0.01,
                                "input_tokens": 1, "output_tokens": 1,
                                "total_tokens": 2}
    ok, errors = generate_and_verify(str(project), text_provider, say=lambda _m: None)
    assert ok, errors


def test_yandexart_preset_returns_bytes_and_its_authentication(monkeypatch):
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


def test_yandexart_sends_the_aspect_ratio_in_generation_options(monkeypatch):
    monkeypatch.setenv("YANDEX_API_KEY", "cle-image")
    monkeypatch.setenv("YANDEX_FOLDER_ID", "folder-image")
    monkeypatch.setenv("MONL_IMAGE_POLL_INTERVAL", "0.001")
    image = base64.b64encode(JPEG_BYTES).decode("ascii")
    calls = []

    class Response:
        status_code = 200
        text = ""

        def json(self):
            return {"id": "operation-image"}

    class DoneResponse(Response):
        def json(self):
            return {"done": True, "response": {"image": image}}

    def post(url, headers=None, json=None, timeout=None):
        calls.append((url, headers, json, timeout))
        return Response()

    def get(url, headers=None, timeout=None):
        del url, headers, timeout
        return DoneResponse()

    import requests
    monkeypatch.setattr(requests, "post", post)
    monkeypatch.setattr(requests, "get", get)

    provider = yandexart_provider()
    assert provider(
        "matière de l'atelier", aspect_ratio={"width": 16, "height": 9}
    ) == JPEG_BYTES
    assert calls[0][2]["generationOptions"]["aspectRatio"] == {
        "widthRatio": 16,
        "heightRatio": 9,
    }
    assert provider("matière carrée") == JPEG_BYTES
    assert "aspectRatio" not in calls[1][2]["generationOptions"]


def test_yandexart_accepts_the_width_ratio_form(monkeypatch):
    monkeypatch.setenv("YANDEX_API_KEY", "cle-image")
    monkeypatch.setenv("YANDEX_FOLDER_ID", "folder-image")
    monkeypatch.setenv("MONL_IMAGE_POLL_INTERVAL", "0.0001")
    image = base64.b64encode(JPEG_BYTES).decode("ascii")

    class Response:
        status_code = 202
        text = ""

        def json(self):
            return {"id": "operation-image"}

    class DoneResponse(Response):
        status_code = 200

        def json(self):
            return {"done": True, "response": {"image": image}}

    import requests
    monkeypatch.setattr(requests, "post", lambda *_args, **_kwargs: Response())
    monkeypatch.setattr(requests, "get", lambda *_args, **_kwargs: DoneResponse())

    provider = yandexart_provider()
    assert provider("matière de l'atelier", aspect_ratio={
        "widthRatio": 4, "heightRatio": 3,
    }) == JPEG_BYTES


def test_yandexart_refuses_a_missing_folder(monkeypatch):
    monkeypatch.setenv("YANDEX_API_KEY", "cle-image")
    monkeypatch.delenv("YANDEX_FOLDER_ID", raising=False)

    with pytest.raises(ImageProviderError, match="YANDEX_FOLDER_ID"):
        yandexart_provider()


@pytest.mark.parametrize(
    ("aspect_ratio", "message"),
    [
        ("16:9", "Aspect ratio must be an object"),
        ({"width": 16}, "Aspect ratio must declare width/height"),
        ({"width": True, "height": 9}, "Aspect ratio dimensions must be positive integers"),
    ],
)
def test_yandexart_refuses_an_invalid_aspect_ratio(
        monkeypatch, aspect_ratio, message):
    monkeypatch.setenv("YANDEX_API_KEY", "cle-image")
    monkeypatch.setenv("YANDEX_FOLDER_ID", "folder-image")
    import requests
    monkeypatch.setattr(requests, "post", lambda *_args, **_kwargs:
                        pytest.fail("the invalid ratio must be refused before HTTP"))

    provider = yandexart_provider(model="art://folder-image/modele-special")
    assert provider.model == "modele-special"
    with pytest.raises(ImageProviderError, match=message):
        provider("matière de l'atelier", aspect_ratio=aspect_ratio)


@pytest.mark.parametrize(
    ("status", "payload", "json_error", "message"),
    [
        (500, {"error": "panne"}, False, "YandexART : 500"),
        (200, None, True, "YandexART returned invalid JSON"),
        (200, {}, False, "operation without an ID"),
    ],
)
def test_yandexart_refuses_an_unusable_initial_response(
        monkeypatch, status, payload, json_error, message):
    monkeypatch.setenv("YANDEX_API_KEY", "cle-image")
    monkeypatch.setenv("YANDEX_FOLDER_ID", "folder-image")

    class Response:
        status_code = status
        text = "réponse de test"

        def json(self):
            if json_error:
                raise ValueError("json invalide")
            return payload

    import requests
    monkeypatch.setattr(requests, "post", lambda *_args, **_kwargs: Response())

    with pytest.raises(ImageProviderError, match=message):
        yandexart_provider()("matière de l'atelier")


def test_yandexart_reports_an_initial_http_failure(monkeypatch):
    monkeypatch.setenv("YANDEX_API_KEY", "cle-image")
    monkeypatch.setenv("YANDEX_FOLDER_ID", "folder-image")
    import requests

    def post(*_args, **_kwargs):
        raise requests.RequestException("service hors ligne")

    monkeypatch.setattr(requests, "post", post)
    with pytest.raises(ImageProviderError, match="is inaccessible"):
        yandexart_provider()("matière de l'atelier")


@pytest.mark.parametrize(
    ("status", "payload", "json_error", "message"),
    [
        (503, {"error": "panne"}, False, "operation read returned 503"),
        (200, None, True, "invalid operation status"),
        (200, {"error": {"message": "quota dépassé"}}, False, "quota dépassé"),
        (200, {"done": True}, False, "without returning image data"),
    ],
)
def test_yandexart_refuses_an_unusable_operation_state(
        monkeypatch, status, payload, json_error, message):
    monkeypatch.setenv("YANDEX_API_KEY", "cle-image")
    monkeypatch.setenv("YANDEX_FOLDER_ID", "folder-image")
    monkeypatch.setenv("MONL_IMAGE_POLL_INTERVAL", "0.0001")

    class Response:
        status_code = status
        text = "état de test"

        def json(self):
            if json_error:
                raise ValueError("json invalide")
            return payload

    class ResponseForPost:
        status_code = 202
        text = ""

        def json(self):
            return {"id": "operation-image"}

    import requests
    monkeypatch.setattr(requests, "post", lambda *_args, **_kwargs:
                        ResponseForPost())
    monkeypatch.setattr(requests, "get", lambda *_args, **_kwargs: Response())

    with pytest.raises(ImageProviderError, match=message):
        yandexart_provider()("matière de l'atelier")


def test_yandexart_reports_an_http_failure_while_polling(monkeypatch):
    monkeypatch.setenv("YANDEX_API_KEY", "cle-image")
    monkeypatch.setenv("YANDEX_FOLDER_ID", "folder-image")
    monkeypatch.setenv("MONL_IMAGE_POLL_INTERVAL", "0.0001")
    import requests

    class Response:
        status_code = 202
        text = ""

        def json(self):
            return {"id": "operation-image"}

    def get(*_args, **_kwargs):
        raise requests.RequestException("connexion interrompue")

    monkeypatch.setattr(requests, "post", lambda *_args, **_kwargs: Response())
    monkeypatch.setattr(requests, "get", get)
    with pytest.raises(ImageProviderError, match="unable to read operation"):
        yandexart_provider()("matière de l'atelier")


@pytest.mark.parametrize("raw, message", [
    ("pas-un-nombre", "must be a positive number"),
    ("0", "must be a positive number"),
])
def test_yandexart_refuses_an_invalid_polling_setting(monkeypatch, raw, message):
    monkeypatch.setenv("YANDEX_API_KEY", "cle-image")
    monkeypatch.setenv("YANDEX_FOLDER_ID", "folder-image")
    monkeypatch.setenv("MONL_IMAGE_POLL_TIMEOUT", raw)

    class Response:
        status_code = 202
        text = ""

        def json(self):
            return {"id": "operation-image"}

    import requests
    monkeypatch.setattr(requests, "post", lambda *_args, **_kwargs: Response())
    with pytest.raises(ImageProviderError, match=message):
        yandexart_provider()("matière de l'atelier")


def test_yandexart_reports_the_timeout(monkeypatch):
    monkeypatch.setenv("YANDEX_API_KEY", "cle-image")
    monkeypatch.setenv("YANDEX_FOLDER_ID", "folder-image")
    monkeypatch.setenv("MONL_IMAGE_POLL_TIMEOUT", "1")
    ticks = iter((0, 0, 2))
    monkeypatch.setattr(image_ai.time, "monotonic", lambda: next(ticks))

    class Response:
        status_code = 202
        text = ""

        def json(self):
            return {"id": "operation-image"}

    import requests
    monkeypatch.setattr(requests, "post", lambda *_args, **_kwargs: Response())

    with pytest.raises(ImageProviderError, match="operation timed out"):
        yandexart_provider()("matière de l'atelier")


def test_a_real_jpeg_image_is_reencoded_without_losing_its_dimensions():
    # No more `importorskip`: Pillow is declared in the `dev` extra, hence
    # present wherever the tests run. The skip made this test look executed in
    # CI while it checked nothing (point 140).
    from PIL import Image as image_module
    source = image_module.effect_noise((1024, 1024), 100).convert("RGB")
    original_buffer = BytesIO()
    source.save(original_buffer, format="JPEG", quality=95)
    original = original_buffer.getvalue()

    optimized, notice = optimize_image_bytes(original)

    assert notice is None
    assert len(optimized) < len(original)
    with image_module.open(BytesIO(optimized)) as decoded:
        assert decoded.format == "JPEG"
        assert decoded.size == (1024, 1024)


def test_missing_pillow_keeps_the_image_and_does_not_block_the_build(tmp_path, monkeypatch):
    monkeypatch.setattr(image_ai, "_pillow_image_class", lambda: None)
    project = _project(tmp_path)
    images = FakeImageProvider()
    text = FakeTextProvider(project)
    messages = []

    ok, errors = generate_and_verify(
        str(project), text, image_provider=images, generate_images=True,
        say=messages.append,
    )

    assert ok, errors
    paths = [item["path"] for item in _manifest(project)["generated_assets"]]
    assert all((project / path).read_bytes() == JPEG_BYTES for path in paths)
    assert any("Pillow is unavailable" in message for message in messages)


def test_image_request_measured_without_tokens_and_usage_does_not_count_it_free(tmp_path):
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
    assert "30" in usage_line and "2 image request(s)" in usage_line
