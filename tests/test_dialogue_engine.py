# Tests du moteur de dialogue guidé (pivot orchestrateur, brique 1).
# Conformément à la méthode du projet : la spec produite est réellement
# parsée ET validée par le vrai pipeline, jamais seulement relue.
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from dialogue_engine import GuidedDialogue, DialogueError  # noqa: E402
from parser import parse_monl_string  # noqa: E402
from ast_validator import MonlAST  # noqa: E402

SCENARIO_PORTFOLIO = [
    "11",              # partir de zéro (dialogue libre)
    "StudioTest", "Un portfolio de studio créatif avec contact.",
    "Project", "title", "1", "imageUrl", "1", "year", "3", "",
    "Message", "author", "1", "content", "2", "email", "7", "",
    "",
    "o", "n",          # Project lisible public, Message non
    "2",               # création publique : Message
    "Admin", "Visitor", "",
    "1", "1",          # Admin gère les deux entités
    "n", "n",          # pas de propriété par enregistrement
    "n", "n",          # Visitor ne lit rien de plus
    "n",               # pas de relation
    "1",               # inscription libre : 1er rôle proposé
    "o", "o",          # seed + landing
]


def _run(answers):
    it = iter(answers)
    return GuidedDialogue(ask=lambda p: next(it)).run()


def test_spec_produite_compile_reellement():
    spec = _run(SCENARIO_PORTFOLIO)
    normalized = MonlAST(parse_monl_string(spec)).validate_and_audit()
    assert normalized["meta"]["appName"] == "StudioTest"
    assert set(normalized["schema"]["entities"]) == {"Project", "Message"}
    assert "Project.Read" in normalized["security"]["public"]
    assert "Message.Create" in normalized["security"]["public"]
    # Un seul gestionnaire d'écriture par entité -> jamais de collision.
    assert normalized["seeds"], "le seed demandé doit être présent"


def test_determinisme_memes_reponses_meme_spec():
    assert _run(SCENARIO_PORTFOLIO) == _run(SCENARIO_PORTFOLIO)


def test_champ_image_seede_avec_une_vraie_url():
    spec = _run(SCENARIO_PORTFOLIO)
    assert "https://picsum.photos/seed/demo1/800/600" in spec


def test_reponse_invalide_redemandee_puis_erreur():
    # Nom d'app invalide 3 fois -> DialogueError (le moteur ne devine jamais).
    with pytest.raises(DialogueError):
        _run(["11", "9mauvais", "aussi mauvais", "toujours-mauvais"])


def test_relation_emise_et_validee():
    answers = [
        "11",
        "TopTest", "Un classement communautaire.",
        "Entry", "name", "1", "score", "3", "",
        "Vote", "note", "1", "",
        "",
        "o", "n",      # Entry publique en lecture
        "0",           # pas de création publique
        "Participant", "",
        # un seul acteur -> gestionnaire implicite, aucune question posée
        "n", "n",      # pas de propriété par enregistrement
        "o",           # des relations ?
        "1",           # source Entry
        "1",           # hasMany
        "1",           # cible Vote
        "n",           # pas d'autre relation
        "1",           # inscription libre : 1er rôle proposé
        "n", "n",      # ni seed ni landing
    ]
    spec = _run(answers)
    assert "relation Entry hasMany Vote" in spec
    MonlAST(parse_monl_string(spec)).validate_and_audit()


def test_ownership_cree_entite_proprietaire_et_regles():
    """ownedBy : le dialogue crée l'entité propriétaire homonyme de l'acteur,
    la relation qui fournit la clé étrangère, et les règles Update/Delete —
    le tout validé par le vrai pipeline (motif de exemples/03, point 5)."""
    answers = [
        "11",
        "ForumTest", "Un forum où chacun gère ses propres sujets.",
        "Topic", "title", "1", "body", "2", "",
        "",
        "n",           # Topic pas public en lecture
        "0",           # pas de création publique
        "Member", "",
        # un seul acteur -> gestionnaire implicite
        "o",           # propriété par enregistrement sur Topic
        # (l'entité Member est créée automatiquement -> nouvelles questions :)
        "n",           # propriété sur Member lui-même ? non
        "n",           # relations supplémentaires ? non
        "1",           # inscription libre : 1er rôle proposé
        "n", "n",      # ni seed ni landing
    ]
    it = iter(answers)
    spec = GuidedDialogue(ask=lambda p: next(it)).run()
    assert "entity Member" in spec and "displayName: String" in spec
    assert "relation Member hasMany Topic" in spec
    assert "rule Topic.Update ownedBy Member" in spec
    assert "rule Topic.Delete ownedBy Member" in spec
    # Entité possédée et non publique : la LECTURE est réservée au propriétaire
    # elle aussi, sans quoi tout titulaire d'un compte listerait les
    # enregistrements des autres (bêta 3).
    assert "rule Topic.Read ownedBy Member" in spec
    normalized = MonlAST(parse_monl_string(spec)).validate_and_audit()
    assert normalized["security"]["ownership"] == {
        "Topic.Read": "Member", "Topic.Update": "Member", "Topic.Delete": "Member"}


def test_gestion_partagee_emet_sharedby_sans_collision():
    """sharedBy : deux acteurs se partagent l'écriture — le dialogue émet un
    workflow par acteur ET les règles sharedBy, la seule voie légitime prévue
    par la règle stricte n° 1 (collision de privilèges)."""
    answers = [
        "11",
        "ModTest", "Un blog co-géré par deux rôles.",
        "Post", "title", "1", "",
        "",
        "o",           # Post public en lecture
        "0",
        "Admin", "Moderator", "",
        "3",           # gestion partagée (option après les 2 acteurs)
        "o", "o",      # Admin ET Moderator participent
        # gestion partagée -> pas de question de propriété
        "n", "n",      # aucun lecteur supplémentaire (déjà gestionnaires)
        # (une seule entité : la question des relations est sautée)
        "1",           # inscription libre : 1er rôle proposé
        "n", "n",      # ni seed ni brief
    ]
    it = iter(answers)
    spec = GuidedDialogue(ask=lambda p: next(it)).run()
    assert "rule Post.Create sharedBy Admin, Moderator" in spec
    assert "workflow ManagePostByAdmin for Admin" in spec
    assert "workflow ManagePostByModerator for Moderator" in spec
    MonlAST(parse_monl_string(spec)).validate_and_audit()
