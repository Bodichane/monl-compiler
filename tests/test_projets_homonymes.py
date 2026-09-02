"""Deux projets du même nom doivent avoir deux adresses, pas une collision.

LES DEUX DÉFAUTS, MESURÉS AVANT D'ÉCRIRE UNE LIGNE. Le slug — l'adresse
d'hébergement — était dérivé du seul NOM de l'application, sans jamais
vérifier qu'il était libre :

  (a) MÊME compte, deux projets du même nom → `IntegrityError` sur
      `UNIQUE(user_id, slug)`. `_ensure_builder_project` n'attrape que
      `OSError` et `ValueError` : l'erreur sortait donc en **500**, et le
      second projet ne pouvait jamais démarrer son API.

  (b) DEUX comptes, même nom → accepté, puis `project_for_host` refuse de
      servir en disant « désigne plusieurs projets ». Un inconnu qui nomme son
      projet comme le vôtre rendait votre site injoignable. La recherche par
      slug est GLOBALE — c'est un sous-domaine, elle ne peut pas être par
      compte.

Le remède est le même pour les deux : le slug est choisi LIBRE à la création,
sous le verrou du magasin, et l'unicité globale est tenue par un index plutôt
que par une vérification applicative — une vérification laisse passer deux
écritures concurrentes, un index non.
"""
from __future__ import annotations

import sqlite3
import uuid

import pytest

from monl_platform.hosting import SiteManager
from monl_platform.identity import IdentityStore
from monl_platform.store import PlatformStore


@pytest.fixture
def plateforme(tmp_path):
    store = PlatformStore(tmp_path)
    identites = IdentityStore(store.workspace)
    sites = SiteManager(store, tmp_path / "projets", "localhost")
    return store, identites, sites


def _projet(store, identites, user_id, nom):
    """Crée un projet comme le fait la plateforme, et rend le slug retenu."""
    project_id = uuid.uuid4().hex
    identites.add_project(user_id, project_id, nom)
    slug = store.create_project(user_id, project_id, nom.lower())
    return project_id, slug


def test_un_meme_compte_peut_nommer_deux_projets_pareil(plateforme):
    """(a) Le second ne doit plus faire échouer l'écriture.

    Trois passages dans le dialogue avec le même nom, c'est le cas RÉEL qui a
    fait remonter le défaut : trois lignes « AtelierVitrine » dans la console.
    """
    store, identites, _ = plateforme
    compte = identites.register("un@monl.test", "MotDePasse-123")

    slugs = [_projet(store, identites, compte["id"], "AtelierVitrine")[1]
             for _ in range(3)]

    assert len(set(slugs)) == 3, f"deux projets partagent une adresse : {slugs}"
    assert slugs[0] == "ateliervitrine", (
        "le PREMIER doit garder l'adresse que son nom annonce")


def test_deux_comptes_ne_se_volent_pas_une_adresse(plateforme):
    """(b) Le défaut le plus grave : il vient de quelqu'un d'autre."""
    store, identites, sites = plateforme
    a = identites.register("a@monl.test", "MotDePasse-123")
    b = identites.register("b@monl.test", "MotDePasse-123")

    _, slug_a = _projet(store, identites, a["id"], "AtelierVitrine")
    _, slug_b = _projet(store, identites, b["id"], "AtelierVitrine")

    assert slug_a != slug_b, "un inconnu a pris l'adresse du premier"
    for slug in (slug_a, slug_b):
        projet = sites.project_for_host(f"{slug}.localhost")
        assert projet is not None, f"{slug} ne désigne aucun projet"


def test_lhebergement_reste_sans_ambiguite(plateforme):
    """Chaque adresse désigne UN projet, et le bon.

    Sans cette vérification on saurait que les slugs diffèrent, jamais qu'ils
    mènent au bon endroit — deux adresses distinctes pointant sur la même
    ligne passeraient le témoin précédent.
    """
    store, identites, sites = plateforme
    compte = identites.register("route@monl.test", "MotDePasse-123")

    attendu = {}
    for _ in range(3):
        project_id, slug = _projet(store, identites, compte["id"], "Boutique")
        attendu[slug] = project_id

    for slug, project_id in attendu.items():
        projet = sites.project_for_host(f"{slug}.localhost")
        assert projet["project_id"] == project_id, (
            f"{slug}.localhost mène au mauvais projet")


def test_lunicite_globale_tient_meme_a_deux_ecritures_concurrentes(plateforme):
    """La garantie vit dans un INDEX, jamais dans une vérification préalable.

    Une vérification « ce slug est-il libre ? » suivie d'une écriture laisse
    passer deux appels simultanés qui lisent tous les deux « libre ». On force
    donc l'écriture directe qu'une course produirait, et la base doit la
    refuser d'elle-même.
    """
    store, identites, _ = plateforme
    a = identites.register("c1@monl.test", "MotDePasse-123")
    b = identites.register("c2@monl.test", "MotDePasse-123")
    _, slug = _projet(store, identites, a["id"], "Course")

    autre = uuid.uuid4().hex
    identites.add_project(b["id"], autre, "Course")
    with pytest.raises(sqlite3.IntegrityError), store._connect() as db:
        db.execute(
            "INSERT INTO builder_projects(project_id, user_id, slug, "
            "created_at, model_routes, generate_images) "
            "VALUES (?, ?, ?, datetime('now'), '{}', 0)",
            (autre, b["id"], slug),
        )


def test_une_base_deja_en_doublon_ne_bloque_pas_le_demarrage(tmp_path, capsys):
    """Les bases ANTÉRIEURES portent déjà des doublons — la nôtre en a trois.

    Point 85 mot pour mot : l'index ne peut pas se créer sur une base en
    doublon, et refuser de démarrer immobiliserait un service qui fonctionne.
    Les doublons sont COMPTÉS et NOMMÉS, jamais réécrits en silence : renommer
    changerait l'adresse d'un site déjà en ligne.
    """
    store = PlatformStore(tmp_path)
    identites = IdentityStore(store.workspace)
    a = identites.register("v1@monl.test", "MotDePasse-123")
    b = identites.register("v2@monl.test", "MotDePasse-123")

    # On fabrique l'état d'AVANT : deux comptes, un seul slug.
    for compte in (a, b):
        project_id = uuid.uuid4().hex
        identites.add_project(compte["id"], project_id, "Ancien")
        with store._connect() as db:
            db.execute("DROP INDEX IF EXISTS idx_builder_projects_slug")
            db.execute(
                "INSERT INTO builder_projects(project_id, user_id, slug, "
                "created_at, model_routes, generate_images) "
                "VALUES (?, ?, 'ancien', datetime('now'), '{}', 0)",
                (project_id, compte["id"]),
            )

    capsys.readouterr()
    rouvert = PlatformStore(tmp_path)
    sortie = capsys.readouterr().out
    assert rouvert.list_all_projects(), "la plateforme refuse de démarrer"
    assert "ancien" in sortie.lower(), (
        f"le doublon n'est pas NOMMÉ au démarrage :\n{sortie}")
