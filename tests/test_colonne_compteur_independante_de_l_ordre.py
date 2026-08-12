"""Régression du rattachement d'une cible de compteur (point 92).

Avec deux relations entrantes, la relation vers la cible du compteur peut être
déclarée avant ou après celle qui rattache la ligne à son acteur. Les deux
ordres doivent produire le même INSERT et la même ligne liée en base.
"""

import sqlite3

import pytest
import requests

from monl.cli import compile_project
from tests.support.server import uvicorn_server

MOT_DE_PASSE = "MotDePasse123!"


def _spec(relations):
    return f"""app Orphelin

entity Post
    content: Text
    likes: Integer

entity Like
    note: String

actor Member selfRegister

{relations}

rule Post.Read public
rule Like.Create increments Post.likes by 1

workflow Agir for Member
    Create Post
    Read Post
    Create Like
"""


@pytest.mark.parametrize(
    "relations",
    [
        "relation Post hasMany Like\nrelation Member hasMany Like",
        "relation Member hasMany Like\nrelation Post hasMany Like",
    ],
    ids=["cible_du_compteur_en_premier", "acteur_en_premier"],
)
def test_la_cle_de_la_cible_du_compteur_est_ecrite_dans_les_deux_ordres(
        tmp_path, relations):
    """Un like réel ne doit jamais être créé avec ``post_id`` à NULL."""
    spec = tmp_path / "spec.ml"
    spec.write_text(_spec(relations), encoding="utf-8")
    compile_project(str(spec), str(tmp_path))

    with uvicorn_server(str(tmp_path)) as base_url:
        inscription = requests.post(
            f"{base_url}/register", timeout=10,
            json={"username": "membre@x.co", "password": MOT_DE_PASSE,
                  "actor": "Member"},
        )
        assert inscription.status_code == 200, inscription.text
        connexion = requests.post(
            f"{base_url}/login", timeout=10,
            json={"username": "membre@x.co", "password": MOT_DE_PASSE},
        )
        assert connexion.status_code == 200, connexion.text
        en_tete = {"Authorization": "Bearer " + connexion.json()["access_token"]}

        post = requests.post(
            f"{base_url}/post", timeout=10, headers=en_tete,
            json={"content": "Un post", "likes": 0},
        )
        assert post.status_code == 200, post.text
        post_id = post.json()["id"]

        like = requests.post(
            f"{base_url}/like", timeout=10, headers=en_tete,
            json={"note": "bravo", "post_id": post_id},
        )
        assert like.status_code == 200, like.text

        connexion_sqlite = sqlite3.connect(tmp_path / "app.db")
        try:
            ligne = connexion_sqlite.execute(
                "SELECT post_id, member_id FROM like WHERE id = ?",
                (like.json()["id"],),
            ).fetchone()
            compteur = connexion_sqlite.execute(
                "SELECT likes FROM post WHERE id = ?", (post_id,)
            ).fetchone()
        finally:
            connexion_sqlite.close()

    assert ligne == (post_id, 1), ligne
    assert compteur == (1,), compteur
