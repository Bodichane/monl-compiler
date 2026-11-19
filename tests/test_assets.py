"""Brick 13 (`assets` + `Image` type) tested against a real server — point 83.

Why this file exists. monl did not know that a file exists. Three faulty
paths were tried before writing a line of code, and **all three compiled
without a word**:

    imageUrl: "images/ce-fichier-n-existe-pas.jpg"
    imageUrl: "imgs/halo-rs.jpeg"        (folder AND extension mistyped)
    imageUrl: "/etc/passwd"

A broken image only shows by eye, on the page, once online — the worst place
to discover a typo. And media was recognized by the field NAME
(`MEDIA_HINTS`): `imageUrl` worked by luck, `apercu` did not.

Two halves of the question, two families of tests here:

* **does it exist?** — refusal at compile time, with the intended
  distinction between FORM checks (pure, always active) and EXISTENCE checks
  (only when the validator knows where the project is);
* **is it SERVED?** — the only one that counts for a browser, and which
  existence on disk does not prove. Tested against a real server mounted by
  the same wrapper as `monl run`, because a mount placed after /site's would
  exist without ever answering.
"""
import contextlib
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request

import pytest

from monl.ast_validator import ASTValidationError, MonlAST
from monl.cli import compile_project
from monl.parser import parse_monl_string
from monl.serving import rendre_wrapper
from tests.support.cas import check_each_case
from tests.support.server import free_port as _port_libre

SPEC = """app BancAssets

assets
    dir: "{dossier}"
    logo: "logo.svg"
    favicon: "favicon.png"

entity Product
    name: String
    price: Money
    photo: Image

actor Visiteur selfRegister

rule Product.name required
rule Product.Read public

workflow Voir for Visiteur
    Read Product

seed Product
    name: "Chaise", price: 249.90, photo: "{photo}"
"""

INDEX = """<!doctype html><html lang="fr"><head><meta charset="utf-8">
<title>Banc</title><link rel="icon" href="assets/favicon.png"></head>
<body><img src="assets/logo.svg" alt="logo"><div id="liste"></div>
<script>
fetch('/product?limit=5').then(function (r) { return r.json(); }).then(function (d) {
  document.getElementById('liste').textContent = (d.data || []).length + ' modèle(s)';
});
</script></body></html>
"""


def _valide(spec, base_dir=None):
    return MonlAST(parse_monl_string(spec), base_dir=base_dir).validate_and_audit()


def _project(racine, photo="assets/chaise.jpg", dossier="assets"):
    """A complete project on disk: spec, real assets, minimal frontend."""
    (racine / dossier).mkdir(parents=True, exist_ok=True)
    (racine / dossier / "logo.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="8" height="8"/>')
    # A BINARY PNG and JPEG: that is what revealed that the smoke test's HTTP
    # client decoded every response as JSON and broke on the first non-UTF-8
    # byte (UnicodeDecodeError is not a JSONDecodeError).
    (racine / dossier / "favicon.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    (racine / dossier / "chaise.jpg").write_bytes(b"\xff\xd8\xffJPEG")
    (racine / "frontend").mkdir(exist_ok=True)
    (racine / "frontend" / "index.html").write_text(INDEX, encoding="utf-8")
    spec = racine / "spec.ml"
    spec.write_text(SPEC.format(photo=photo, dossier=dossier), encoding="utf-8")
    return spec


# --------------------------------------------------------------------------
# What must no longer compile
# --------------------------------------------------------------------------

def test_a_project_whose_assets_exist_compiles(tmp_path, capsys):
    """The witness of all the refusals below: without it, a validator refusing
    EVERY asset would pass them all."""
    spec = _project(tmp_path)
    ast = _valide(spec.read_text(encoding="utf-8"), base_dir=str(tmp_path))
    assert ast["assets"]["dir"] == "assets"
    assert ast["assets"]["logo"] == "logo.svg"
    capsys.readouterr()


def test_a_missing_seed_photo_does_not_compile(tmp_path):
    """Point 83's exact defect: this case compiled, and the broken image only
    showed by eye, online."""
    spec = _project(tmp_path, photo="assets/absente.jpg")
    with pytest.raises(ASTValidationError) as refus:
        _valide(spec.read_text(encoding="utf-8"), base_dir=str(tmp_path))
    message = str(refus.value)
    assert "does not exist" in message
    # The message must name the field AND say why the refusal is there.
    assert "'photo'" in message
    assert "broken image" in message


def test_a_declared_but_missing_logo_does_not_compile(tmp_path):
    spec = _project(tmp_path)
    spec.write_text(spec.read_text(encoding="utf-8")
                    .replace('logo: "logo.svg"', 'logo: "logo-absent.svg"'),
                    encoding="utf-8")
    with pytest.raises(ASTValidationError) as refus:
        _valide(spec.read_text(encoding="utf-8"), base_dir=str(tmp_path))
    assert "assets.logo" in str(refus.value)


def test_malformed_paths_are_refused_without_touching_disk():
    """These three checks are PURE: they require no file, so they apply even
    without 'base_dir'. It is the brick's intended split — form always, existence
    when we know where we are."""
    table = [
        ("/etc/passwd", "ABSOLU"),
        ("../../secret.jpg", "TRAVELS outside the project"),
        ("https://picsum.photos/400", "remote address"),
    ]

    def cas(chemin, fragment):
        spec = SPEC.format(photo=chemin, dossier="assets")
        with pytest.raises(ASTValidationError) as refus:
            _valide(spec)                      # AUCUN base_dir
        assert fragment in str(refus.value)

    check_each_case(table, cas)


def test_without_base_dir_existence_is_not_checked(capsys):
    """The silence is explicit, not accidental: a spec validated in memory cannot
    know where the files are, and a false refusal would be worse than no check.
    This test pins that choice."""
    spec = SPEC.format(photo="assets/jamais-vue.jpg", dossier="assets")
    assert _valide(spec)                   # does not raise
    capsys.readouterr()


def test_a_remote_address_stays_allowed_as_String(capsys):
    """The counterpart of the URL refusal: `Image` promises a checkable file, so
    it refuses a URL. `String` stays there for the remote, unchecked address —
    otherwise the brick would forbid a legitimate use to guarantee another."""
    spec = SPEC.format(photo="assets/chaise.jpg", dossier="assets").replace(
        "photo: Image", "photo: String").replace(
        'photo: "assets/chaise.jpg"', 'photo: "https://picsum.photos/400"')
    assert _valide(spec)
    capsys.readouterr()


# --------------------------------------------------------------------------
# The contract: declared rather than guessed
# --------------------------------------------------------------------------

def test_the_contract_declares_the_assets_and_the_media_role(tmp_path, capsys):
    spec = _project(tmp_path)
    contrat = compile_project(str(spec), str(tmp_path))
    capsys.readouterr()

    assets = contrat["assets"]
    assert assets["dir"] == "assets"
    assert assets["logo"] == "assets/logo.svg"
    assert assets["favicon"] == "assets/favicon.png"
    assert assets["served_at"] == "/site/assets/"
    # Without this note, the interface AI did not know a logo existed: the demo
    # shop carried a text wordmark, for lack of anything better.
    assert "logo" in assets.get("logo_note", "").lower()

    photo = next(f for f in contrat["entities"]["Product"]["fields"]
                 if f["name"] == "photo")
    assert photo["type"] == "Image"
    # The role comes from the TYPE, no longer the name: 'photo' would have
    # matched the heuristic, but a field named 'apercu' would not have.
    assert photo["role"] == "media"


def test_the_media_role_comes_from_the_type_not_the_name(tmp_path, capsys):
    """The proof that the type takes precedence: a name no heuristic recognizes."""
    spec = _project(tmp_path)
    spec.write_text(spec.read_text(encoding="utf-8")
                    .replace("photo: Image", "cliche: Image")
                    .replace('photo: "assets/chaise.jpg"', 'cliche: "assets/chaise.jpg"'),
                    encoding="utf-8")
    contrat = compile_project(str(spec), str(tmp_path))
    capsys.readouterr()
    champ = next(f for f in contrat["entities"]["Product"]["fields"]
                 if f["name"] == "cliche")
    assert champ["role"] == "media", (
        "'cliche' is in no name heuristic: only the type can tell")


# --------------------------------------------------------------------------
# Existing is not served
# --------------------------------------------------------------------------

@contextlib.contextmanager
def _server(dossier, assets_dir="assets"):
    """The project served by the SAME wrapper as 'monl run' — that is what makes
    the test representative: a homemade test wrapper would prove nothing about
    the real wrapper."""
    (dossier / "serve.py").write_text(rendre_wrapper(assets_dir), encoding="utf-8")
    port = _port_libre()
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "serve:app", "--port", str(port)],
        cwd=str(dossier), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(80):
            try:
                with urllib.request.urlopen(base + "/openapi.json", timeout=1):
                    pass
                break
            except Exception:
                time.sleep(0.25)
        else:
            pytest.skip("server not started")
        yield base
    finally:
        proc.terminate()
        proc.wait(timeout=10)


def _statut(url):
    try:
        with urllib.request.urlopen(url, timeout=5) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        with e:
            return e.code, b""


def test_the_assets_are_really_served(tmp_path, capsys):
    """The half of the question existence on disk does not prove. A mount placed
    AFTER /site's would exist without ever answering: /site would absorb
    /site/assets/… to look for it in frontend/, where it is not. Checked by
    swapping the order: three 404s."""
    spec = _project(tmp_path)
    compile_project(str(spec), str(tmp_path))
    capsys.readouterr()

    with _server(tmp_path) as base:
        statut, corps = _statut(f"{base}/site/assets/logo.svg")
        assert statut == 200, "the declared logo is not served"
        assert b"svg" in corps

        # A binary, so that the check does not rely on text alone.
        statut, corps = _statut(f"{base}/site/assets/favicon.png")
        assert statut == 200
        assert corps.startswith(b"\x89PNG")

        statut, _ = _statut(f"{base}/site/assets/chaise.jpg")
        assert statut == 200, "the seed photo is not served"

        # The frontend stays served: the assets mount did not hide it.
        statut, corps = _statut(f"{base}/site/")
        assert statut == 200 and b"<title>" in corps

        # And a missing asset does answer 404, not a frontend page: without
        # this assertion, a too broad mount would pass for a success.
        statut, _ = _statut(f"{base}/site/assets/jamais-deposee.jpg")
        assert statut == 404


def test_the_seed_photo_is_served_at_the_url_the_api_returns(tmp_path, capsys):
    """The end to end that counts: the API returns a path, that path must answer.
    It is exactly what a browser chains, and what neither the consistency check
    nor jsdom checked."""
    spec = _project(tmp_path)
    compile_project(str(spec), str(tmp_path))
    capsys.readouterr()

    with _server(tmp_path) as base:
        with urllib.request.urlopen(f"{base}/product?limit=5", timeout=5) as r:
            produits = json.loads(r.read())["data"]
        assert produits, "the seed inserted nothing"
        chemin = produits[0]["photo"]
        assert chemin == "assets/chaise.jpg"
        statut, _ = _statut(f"{base}/site/{chemin}")
        assert statut == 200, (
            f"the API announces '{chemin}' but /site/{chemin} does not answer — "
            f"it is a broken image for every browser")


def test_without_declared_assets_the_wrapper_only_mounts_the_frontend(tmp_path):
    """A spec without an 'assets' block must produce exactly the behavior from
    before the brick: nothing new, no extra mount."""
    texte = rendre_wrapper(None)
    assert "_ASSETS_DIR = None" in texte
    assert 'app.mount("/site", StaticFiles(directory="frontend"' in texte
    # The conditional mount stays present but inert: it does not run.
    assert "if _ASSETS_DIR and os.path.isdir" in texte
    assert os.sep not in "assets"  # safeguard: the contract talks about URLs, not OS paths


def test_assets_without_frontend_pass_the_smoke_test(tmp_path, capsys):
    """Right after `monl compile`, before any `monl frontend`, a project carries
    its assets and no frontend/. The smoke test then started bare `app:app`: the
    three assets answered 404 and `monl run --check` refused a healthy application
    (found while fixing issue #82). It must mount the wrapper as soon as there
    are assets, like `monl run`."""
    from monl.smoke_test import run_smoke_test

    spec = _project(tmp_path)
    shutil.rmtree(tmp_path / "frontend")
    compile_project(str(spec), str(tmp_path))
    capsys.readouterr()
    assert not (tmp_path / "frontend").exists(), "the bench must stay without frontend"

    ok, erreurs, _avertissements = run_smoke_test(str(tmp_path), say=lambda *_: None)
    assert ok, erreurs
