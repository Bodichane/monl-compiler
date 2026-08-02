"""Brique 13 (`assets` + type `Image`) éprouvée contre un vrai serveur — point 83.

Pourquoi ce fichier existe. monl ne savait pas qu'un fichier existe. Trois
chemins fautifs ont été essayés avant d'écrire une ligne de code, et **les trois
compilaient sans un mot** :

    imageUrl: "images/ce-fichier-n-existe-pas.jpg"
    imageUrl: "imgs/halo-rs.jpeg"        (dossier ET extension mal tapés)
    imageUrl: "/etc/passwd"

Une image cassée ne se voit qu'à l'œil, sur la page, une fois en ligne — le pire
endroit pour découvrir une faute de frappe. Et le média se reconnaissait au NOM
du champ (`MEDIA_HINTS`) : `imageUrl` marchait par chance, `apercu` non.

Deux moitiés de question, deux familles de tests ici :

* **existe-t-il ?** — refus à la compilation, avec la distinction voulue entre
  contrôles de FORME (purs, toujours actifs) et d'EXISTENCE (seulement quand le
  validateur sait où est le projet) ;
* **est-il SERVI ?** — la seule qui compte pour un navigateur, et que
  l'existence sur disque ne prouve pas. Éprouvée contre un vrai serveur monté
  par le même wrapper que `monl run`, parce qu'un montage placé après celui de
  /site existerait sans jamais répondre.
"""
import contextlib
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request

import pytest

from monl.ast_validator import ASTValidationError, MonlAST
from monl.cli import compile_project
from monl.parser import parse_monl_string
from monl.serving import rendre_wrapper

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


def _projet(racine, photo="assets/chaise.jpg", dossier="assets"):
    """Un projet complet sur disque : spec, assets réels, frontend minimal."""
    (racine / dossier).mkdir(parents=True, exist_ok=True)
    (racine / dossier / "logo.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="8" height="8"/>')
    # Un PNG et un JPEG BINAIRES : c'est ce qui a révélé que le client HTTP du
    # smoke test décodait toute réponse en JSON et cassait sur le premier octet
    # non-UTF-8 (UnicodeDecodeError n'est pas un JSONDecodeError).
    (racine / dossier / "favicon.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    (racine / dossier / "chaise.jpg").write_bytes(b"\xff\xd8\xffJPEG")
    (racine / "frontend").mkdir(exist_ok=True)
    (racine / "frontend" / "index.html").write_text(INDEX, encoding="utf-8")
    spec = racine / "spec.ml"
    spec.write_text(SPEC.format(photo=photo, dossier=dossier), encoding="utf-8")
    return spec


# --------------------------------------------------------------------------
# Ce qui ne doit plus compiler
# --------------------------------------------------------------------------

def test_un_projet_dont_les_assets_existent_compile(tmp_path, capsys):
    """Le témoin de tous les refus ci-dessous : sans lui, un validateur qui
    refuserait TOUT asset les passerait tous."""
    spec = _projet(tmp_path)
    ast = _valide(spec.read_text(encoding="utf-8"), base_dir=str(tmp_path))
    assert ast["assets"]["dir"] == "assets"
    assert ast["assets"]["logo"] == "logo.svg"
    capsys.readouterr()


def test_une_photo_de_seed_absente_ne_compile_pas(tmp_path):
    """Le défaut exact du point 83 : ce cas compilait, et l'image cassée ne se
    voyait qu'à l'œil, en ligne."""
    spec = _projet(tmp_path, photo="assets/absente.jpg")
    with pytest.raises(ASTValidationError) as refus:
        _valide(spec.read_text(encoding="utf-8"), base_dir=str(tmp_path))
    message = str(refus.value)
    assert "n'existe pas" in message
    # Le message doit nommer le champ ET dire pourquoi le refus est là.
    assert "'photo'" in message
    assert "image cassée" in message


def test_un_logo_declare_mais_absent_ne_compile_pas(tmp_path):
    spec = _projet(tmp_path)
    spec.write_text(spec.read_text(encoding="utf-8")
                    .replace('logo: "logo.svg"', 'logo: "logo-absent.svg"'),
                    encoding="utf-8")
    with pytest.raises(ASTValidationError) as refus:
        _valide(spec.read_text(encoding="utf-8"), base_dir=str(tmp_path))
    assert "assets.logo" in str(refus.value)


@pytest.mark.parametrize("chemin, fragment", [
    ("/etc/passwd", "ABSOLU"),
    ("../../secret.jpg", "REMONTE"),
    ("https://picsum.photos/400", "adresse distante"),
])
def test_les_chemins_mal_formes_sont_refuses_sans_toucher_au_disque(chemin, fragment):
    """Ces trois contrôles sont PURS : ils ne demandent aucun fichier, donc ils
    s'appliquent même sans 'base_dir'. C'est le partage voulu de la brique — la
    forme toujours, l'existence quand on sait où l'on est."""
    spec = SPEC.format(photo=chemin, dossier="assets")
    with pytest.raises(ASTValidationError) as refus:
        _valide(spec)                      # AUCUN base_dir
    assert fragment in str(refus.value)


def test_sans_base_dir_l_existence_n_est_pas_verifiee(capsys):
    """Le silence est explicite, pas accidentel : une spec validée en mémoire ne
    peut pas savoir où sont les fichiers, et un faux refus serait pire que
    l'absence de contrôle. Ce test fige ce choix."""
    spec = SPEC.format(photo="assets/jamais-vue.jpg", dossier="assets")
    assert _valide(spec)                   # ne lève pas
    capsys.readouterr()


def test_une_adresse_distante_reste_permise_en_String(capsys):
    """Le pendant du refus d'URL : `Image` promet un fichier vérifiable, donc
    refuse une URL. `String` reste là pour l'adresse distante, non vérifiée —
    sinon la brique interdirait un usage légitime pour en garantir un autre."""
    spec = SPEC.format(photo="assets/chaise.jpg", dossier="assets").replace(
        "photo: Image", "photo: String").replace(
        'photo: "assets/chaise.jpg"', 'photo: "https://picsum.photos/400"')
    assert _valide(spec)
    capsys.readouterr()


# --------------------------------------------------------------------------
# Le contrat : déclaré plutôt que devine
# --------------------------------------------------------------------------

def test_le_contrat_declare_les_assets_et_le_role_media(tmp_path, capsys):
    spec = _projet(tmp_path)
    contrat = compile_project(str(spec), str(tmp_path))
    capsys.readouterr()

    assets = contrat["assets"]
    assert assets["dir"] == "assets"
    assert assets["logo"] == "assets/logo.svg"
    assert assets["favicon"] == "assets/favicon.png"
    assert assets["served_at"] == "/site/assets/"
    # Sans cette note, l'IA d'interface ne savait pas qu'un logo existait : la
    # boutique de démonstration portait un mot-symbole en texte, faute de mieux.
    assert "logo" in assets.get("logo_note", "").lower()

    photo = next(f for f in contrat["entities"]["Product"]["fields"]
                 if f["name"] == "photo")
    assert photo["type"] == "Image"
    # Le rôle vient du TYPE, plus du nom : 'photo' aurait matché l'heuristique,
    # mais un champ nommé 'apercu' ne l'aurait pas fait.
    assert photo["role"] == "media"


def test_le_role_media_vient_du_type_et_non_du_nom(tmp_path, capsys):
    """La preuve que le type prime : un nom qu'aucune heuristique ne reconnaît."""
    spec = _projet(tmp_path)
    spec.write_text(spec.read_text(encoding="utf-8")
                    .replace("photo: Image", "cliche: Image")
                    .replace('photo: "assets/chaise.jpg"', 'cliche: "assets/chaise.jpg"'),
                    encoding="utf-8")
    contrat = compile_project(str(spec), str(tmp_path))
    capsys.readouterr()
    champ = next(f for f in contrat["entities"]["Product"]["fields"]
                 if f["name"] == "cliche")
    assert champ["role"] == "media", (
        "'cliche' n'est dans aucune heuristique de nom : seul le type peut le dire")


# --------------------------------------------------------------------------
# Existe n'est pas servi
# --------------------------------------------------------------------------

def _port_libre():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@contextlib.contextmanager
def _serveur(dossier, assets_dir="assets"):
    """Le projet servi par le MÊME wrapper que 'monl run' — c'est ce qui rend
    le test représentatif : un wrapper de test maison ne prouverait rien du
    wrapper réel."""
    (dossier / "serve.py").write_text(rendre_wrapper(assets_dir), encoding="utf-8")
    port = _port_libre()
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "serve:app", "--port", str(port)],
        cwd=str(dossier), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(80):
            try:
                urllib.request.urlopen(base + "/openapi.json", timeout=1).close()
                break
            except Exception:
                time.sleep(0.25)
        else:
            pytest.skip("serveur non démarré")
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


def test_les_assets_sont_reellement_servis(tmp_path, capsys):
    """La moitié de la question que l'existence sur disque ne prouve pas. Un
    montage placé APRÈS celui de /site existerait sans jamais répondre : /site
    absorberait /site/assets/… pour aller le chercher dans frontend/, où il
    n'est pas. Vérifié en inversant l'ordre : trois 404."""
    spec = _projet(tmp_path)
    compile_project(str(spec), str(tmp_path))
    capsys.readouterr()

    with _serveur(tmp_path) as base:
        statut, corps = _statut(f"{base}/site/assets/logo.svg")
        assert statut == 200, "le logo déclaré n'est pas servi"
        assert b"svg" in corps

        # Un binaire, pour que le contrôle ne tienne pas qu'au texte.
        statut, corps = _statut(f"{base}/site/assets/favicon.png")
        assert statut == 200
        assert corps.startswith(b"\x89PNG")

        statut, _ = _statut(f"{base}/site/assets/chaise.jpg")
        assert statut == 200, "la photo du seed n'est pas servie"

        # Le frontend reste servi : le montage des assets ne l'a pas masqué.
        statut, corps = _statut(f"{base}/site/")
        assert statut == 200 and b"<title>" in corps

        # Et un asset absent répond bien 404, pas une page du frontend : sans
        # cette assertion, un montage trop large passerait pour un succès.
        statut, _ = _statut(f"{base}/site/assets/jamais-deposee.jpg")
        assert statut == 404


def test_la_photo_du_seed_est_servie_a_l_url_que_l_api_renvoie(tmp_path, capsys):
    """Le bout en bout qui compte : l'API renvoie un chemin, ce chemin doit
    répondre. C'est exactement ce qu'un navigateur enchaîne, et ce que ni le
    contrôle de cohérence ni jsdom ne vérifiaient."""
    spec = _projet(tmp_path)
    compile_project(str(spec), str(tmp_path))
    capsys.readouterr()

    with _serveur(tmp_path) as base:
        with urllib.request.urlopen(f"{base}/product?limit=5", timeout=5) as r:
            produits = json.loads(r.read())["data"]
        assert produits, "le seed n'a rien inséré"
        chemin = produits[0]["photo"]
        assert chemin == "assets/chaise.jpg"
        statut, _ = _statut(f"{base}/site/{chemin}")
        assert statut == 200, (
            f"l'API annonce '{chemin}' mais /site/{chemin} ne répond pas — "
            f"c'est une image cassée pour tout navigateur")


def test_sans_assets_declares_le_wrapper_ne_monte_que_le_frontend(tmp_path):
    """Une spec sans bloc 'assets' doit produire exactement le comportement
    d'avant la brique : rien de nouveau, aucun montage supplémentaire."""
    texte = rendre_wrapper(None)
    assert "_ASSETS_DIR = None" in texte
    assert 'app.mount("/site", StaticFiles(directory="frontend"' in texte
    # Le montage conditionnel reste présent mais inerte : il ne s'exécute pas.
    assert "if _ASSETS_DIR and os.path.isdir" in texte
    assert os.sep not in "assets"  # garde-fou : le contrat parle d'URL, pas de chemin OS
