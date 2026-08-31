"""Le dépôt de fichier né du DIALOGUE, exercé en HTTP réel (point 173).

`tests/test_uploads.py` éprouve la brique sur une spec écrite à la main. Ce
banc-ci part de l'autre bout : les réponses d'un usager au dialogue guidé, la
spec qui en sort, le serveur qu'elle produit, et un vrai fichier déposé.

C'est la distinction que ce projet réapprend à chaque brique : **compiler
n'est pas se comporter**. La chaîne dialogue → spec → serveur n'avait jamais
été parcourue en entier pour cette brique, et son auteur l'avait dit en
toutes lettres — « non mesuré ».
"""

import contextlib
import io
import os
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
import requests

from monl.app_templates import TEMPLATES
from monl.ast_validator import MonlAST
from monl.generator import MonlSecureGenerator
from monl.parser import parse_monl_string
from tests.support.server import uvicorn_server
from tests.test_app_templates import _run_template

# Un PNG minuscule mais VALIDE : le backend vérifie la signature d'octets, pas
# l'extension ni le type annoncé par le client.
PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010802000000907753"
    "de0000000c4944415408d763f8cfc00000030101003c2d0b0b0000000049454e"
    "44ae426082"
)


@pytest.fixture(scope="module")
def serveur_depuis_le_dialogue():
    """Compile ce que le dialogue produit, et le fait vraiment tourner."""
    index = next(i for i, t in enumerate(TEMPLATES, 1)
                 if t["name"] == "Suivi de dépenses personnelles")
    with contextlib.redirect_stdout(io.StringIO()):
        spec = _run_template(index, "n", False, upload_pour="Expense")
    assert "rule Expense.photo upload max" in spec, spec

    with TemporaryDirectory(prefix="monl-depot-dialogue-") as dossier:
        with contextlib.redirect_stdout(io.StringIO()):
            ast = MonlAST(parse_monl_string(spec)).validate_and_audit()
            MonlSecureGenerator(ast, output_dir=dossier).generate_all()
        stockage = Path(dossier).parent / f"{Path(dossier).name}.uploads"
        env = os.environ.copy()
        env.pop("MONL_DATABASE_URL", None)
        env["MONL_JWT_SECRET"] = "depot-dialogue-secret-32-octets-minimum"
        env["MONL_UPLOADS_DIR"] = str(stockage)
        with uvicorn_server(dossier, env=env) as base:
            yield base


def _compte(base, nom):
    inscription = requests.post(
        f"{base}/register",
        json={"username": nom, "password": "motdepasse8", "actor": "User"},
        timeout=10)
    assert inscription.status_code == 200, inscription.text
    connexion = requests.post(
        f"{base}/login",
        json={"username": nom, "password": "motdepasse8"}, timeout=10)
    assert connexion.status_code == 200, connexion.text
    return {"Authorization": f"Bearer {connexion.json()['access_token']}"}


@pytest.fixture(scope="module")
def deux_comptes(serveur_depuis_le_dialogue):
    """DEUX comptes, sans quoi « le fichier est-il privé ? » ne se pose pas.

    Avec un seul, la question devient « puis-je lire mon propre fichier ? »,
    à laquelle un serveur sans aucun contrôle répondrait oui. C'est le piège
    nommé aux points 81, 90 et 116.
    """
    base = serveur_depuis_le_dialogue
    return base, _compte(base, "alice"), _compte(base, "bob")


def _budget(base, entetes, nom):
    """Une dépense appartient à un budget : la clé étrangère est CLIENTE.

    C'est la brique 11 (propriété transitive) : la colonne n'est pas déduite
    du jeton, donc le client la fournit — et le serveur la vérifie.
    """
    reponse = requests.post(
        f"{base}/budget", json={"name": nom, "limit": 500.0, "spent": 0.0},
        headers=entetes, timeout=10)
    assert reponse.status_code in (200, 201), reponse.text
    return reponse.json()["id"]


def _depense(base, entetes, libelle):
    budget = _budget(base, entetes, f"budget-{libelle}")
    reponse = requests.post(
        f"{base}/expense",
        json={"label": libelle, "amount": 12.5, "spentOn": "2026-08-31",
              "category": "Repas", "budget_id": budget},
        headers=entetes, timeout=10)
    assert reponse.status_code in (200, 201), reponse.text
    return reponse.json()["id"]


def test_un_justificatif_se_depose_et_se_relit(deux_comptes):
    base, alice, _bob = deux_comptes
    identifiant = _depense(base, alice, "Déjeuner client")

    depot = requests.post(
        f"{base}/expense/{identifiant}/photo",
        files={"photo": ("recu.png", PNG, "image/png")},
        headers=alice, timeout=10)
    assert depot.status_code in (200, 201), depot.text

    relecture = requests.get(
        f"{base}/expense/{identifiant}/photo", headers=alice, timeout=10)
    assert relecture.status_code == 200, relecture.text
    assert relecture.content == PNG, "les octets rendus ne sont pas ceux déposés"


def test_le_justificatif_dun_autre_reste_inaccessible(deux_comptes):
    """La promesse annoncée par la question du dialogue, vérifiée.

    Le dialogue dit « le fichier ne sera lisible que par son propriétaire ».
    Une phrase n'est pas une garantie : c'est ce refus-ci qui l'est.
    """
    base, alice, bob = deux_comptes
    identifiant = _depense(base, alice, "Note d'hôtel")
    depot = requests.post(
        f"{base}/expense/{identifiant}/photo",
        files={"photo": ("recu.png", PNG, "image/png")},
        headers=alice, timeout=10)
    assert depot.status_code in (200, 201), depot.text

    vol = requests.get(
        f"{base}/expense/{identifiant}/photo", headers=bob, timeout=10)
    assert vol.status_code in (403, 404), vol.status_code
    assert PNG not in vol.content

    sans_compte = requests.get(f"{base}/expense/{identifiant}/photo", timeout=10)
    assert sans_compte.status_code == 401, sans_compte.status_code


def test_les_limites_declarees_par_le_dialogue_mordent_reellement(deux_comptes):
    """5 Mio et deux types d'image : écrits par le dialogue, appliqués ici.

    Le type est déterminé par la SIGNATURE D'OCTETS et jamais par le nom ni
    par le type annoncé — un SVG rebaptisé `.png` doit être refusé.
    """
    base, alice, _bob = deux_comptes
    identifiant = _depense(base, alice, "Taxi")

    trop_gros = requests.post(
        f"{base}/expense/{identifiant}/photo",
        files={"photo": ("gros.png", PNG + b"x" * (5 * 1024 * 1024), "image/png")},
        headers=alice, timeout=30)
    assert trop_gros.status_code == 413, trop_gros.status_code

    deguise = requests.post(
        f"{base}/expense/{identifiant}/photo",
        files={"photo": ("faux.png", b"<svg>x</svg>", "image/png")},
        headers=alice, timeout=10)
    assert deguise.status_code == 415, deguise.status_code
