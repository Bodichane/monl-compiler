# Tests du moteur de dialogue guidé (pivot orchestrateur, brique 1).
# Conformément à la méthode du projet : la spec produite est réellement
# parsée ET validée par le vrai pipeline, jamais seulement relue.
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from ast_validator import MonlAST
from dialogue_engine import DialogueError, GuidedDialogue
from parser import parse_monl_string

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
    "o",               # seed
    "n",               # images génériques (point 59)
    "o",               # landing
    # Brief transmis -> l'intention visuelle est demandée (point 53) :
    # action attendue du visiteur, registre, place des images.
    "voir les projets et écrire", "2", "1",
    "n",               # aucune section éditoriale (point 55)
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


def test_champ_image_seede_en_resolution_suffisante():
    """1600×900, pas 800×600 (point 59) : un hero occupe toute la largeur d'un
    conteneur d'environ 1120 px, doublée sur un écran haute densité. La source
    était agrandie près de trois fois, et l'image paraissait molle."""
    spec = _run(SCENARIO_PORTFOLIO)
    assert "https://picsum.photos/seed/demo1/1600/900" in spec
    assert "800/600" not in spec


def test_sujet_d_images_choisi_remplace_les_photos_au_hasard():
    """`picsum` ne rend que des photos arbitraires : un blog de cybersécurité
    s'illustrait de paysages. Le sujet ne peut pas être déduit d'une phrase
    libre en français sans interprétation — donc on le demande (point 59)."""
    scenario = list(SCENARIO_PORTFOLIO)
    scenario[scenario.index("n", scenario.index("o", 28))] = "o"   # sujet précis
    scenario.insert(scenario.index("o", 28) + 2, "cybersecurity")
    spec = _run(scenario)
    assert "loremflickr.com/1600/900/cybersecurity" in spec
    assert "picsum" not in spec
    # `lock` fige le tirage : sans lui le rendu changerait à chaque
    # rechargement, ce que le déterminisme du compilateur interdit.
    assert "?lock=" in spec
    MonlAST(parse_monl_string(spec)).validate_and_audit()


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


# ---- L'intention visuelle atteint le brief (point 53) ----

def _scenario_portfolio(intention):
    """SCENARIO_PORTFOLIO, dont on ne change que les réponses d'intention."""
    return SCENARIO_PORTFOLIO[:-4] + list(intention) + ["n"]


def test_intention_visuelle_arrive_dans_le_brief():
    """Le brief transmis à l'IA UI ne doit plus se réduire à la description :
    c'est la seule phrase du contrat qui dise à quoi sert le site, face à des
    routes décrites au champ près. Une interface sans intention retombe sur le
    dénominateur commun (point 53)."""
    spec = _run(_scenario_portfolio(["parcourir la galerie", "4", "1"]))
    ligne = next(x for x in spec.splitlines() if "brief:" in x)
    assert "parcourir la galerie" in ligne
    assert "affirmé et graphique" in ligne          # registre n° 4
    assert "les images portent le site" in ligne    # imagerie n° 1
    # La description d'origine reste en tête du brief.
    assert ligne.index("Un portfolio") < ligne.index("parcourir la galerie")
    MonlAST(parse_monl_string(spec)).validate_and_audit()


def test_registres_differents_donnent_des_briefs_differents():
    """Sans quoi les menus seraient décoratifs."""
    a = _run(_scenario_portfolio(["voir", "1", "3"]))
    b = _run(_scenario_portfolio(["voir", "3", "3"]))
    assert a != b


def test_sans_brief_aucune_question_d_intention():
    """L'intention n'est demandée que si un brief part vers l'IA : sinon ces
    réponses n'auraient personne à qui servir, et le dialogue ferait perdre
    trois questions à l'utilisateur."""
    # [:-4] retire les 3 réponses d'intention ET le « oui » au brief ; la
    # réponse « seed » reste en place, on ne rajoute donc que le refus.
    sans_landing = SCENARIO_PORTFOLIO[:-5] + ["n"]
    spec = _run(sans_landing)          # ne doit PAS lever StopIteration
    assert "landing" not in spec
    MonlAST(parse_monl_string(spec)).validate_and_audit()


# ---- Contenu éditorial statique (point 55) ----

def test_sections_editoriales_emises_et_validees():
    """Le seul contenu du contrat qui ne soit pas une donnée. Sans lui,
    une page « à propos » n'a aucune entité, aucun champ, aucune route d'où
    naître — l'IA n'a littéralement rien pour la construire."""
    scenario = SCENARIO_PORTFOLIO[:-1] + [
        # Point 64 : chaque corps se termine par une ligne vide — ici un
        # seul paragraphe par rubrique.
        "o", "À propos", "Studio fondé en 2015 à Lyon.", "",
        "o", "Méthode", "Repérage, prise de vue, retouche.", "",
        "n",
    ]
    spec = _run(scenario)
    assert 'section "À propos": "Studio fondé en 2015 à Lyon."' in spec
    assert 'section "Méthode": "Repérage, prise de vue, retouche."' in spec
    normalized = MonlAST(parse_monl_string(spec)).validate_and_audit()
    titres = [s["title"] for s in normalized["landing"]["sections"]]
    assert titres == ["À propos", "Méthode"], "l'ordre de saisie doit être conservé"


def test_sections_refusees_si_aucun_brief():
    """Même règle que l'intention visuelle : sans page d'accueil à écrire,
    ces textes n'auraient nulle part où aller."""
    spec = _run(SCENARIO_PORTFOLIO[:-5] + ["n"])
    assert "section " not in spec and "landing" not in spec


def test_un_texte_en_plusieurs_paragraphes_survit_jusqu_au_contrat():
    """POINT 64 : un « à propos » collé depuis un traitement de texte
    arrivait aplati — paragraphes recollés sans même une espace, et l'IA
    d'interface recevait un mur de texte. La grammaire interdit toujours le
    retour à la ligne : le dialogue demande donc les paragraphes un à un, et
    le contrat les rétablit."""
    import tempfile

    from frontend_contract import build_contract
    from generator import MonlSecureGenerator

    scenario = SCENARIO_PORTFOLIO[:-1] + [
        "o", "À propos",
        "Photographe basée à Lyon depuis 2015.",
        "Mon travail mêle rigueur technique et composition.",
        "Chaque projet traduit une idée en image forte.",
        "",                       # fin des paragraphes
        "n",                      # pas d'autre section
    ]
    spec = _run(scenario)
    # Dans la spec : une seule ligne, marquée — c'est ce que la grammaire
    # sait porter.
    ligne = next(x for x in spec.splitlines() if x.strip().startswith('section'))
    assert ligne.count("¶") == 2, ligne
    assert "\n" not in ligne.strip("\n")

    normalized = MonlAST(parse_monl_string(spec)).validate_and_audit()
    # output_dir : sans lui, la graine de thème atterrit dans le dépôt.
    with tempfile.TemporaryDirectory() as sortie:
        contrat = build_contract(
            normalized, MonlSecureGenerator(normalized, output_dir=sortie))
    corps = contrat["sections"][0]["body"]
    assert corps.split("\n\n") == [
        "Photographe basée à Lyon depuis 2015.",
        "Mon travail mêle rigueur technique et composition.",
        "Chaque projet traduit une idée en image forte.",
    ], corps
    assert "¶" not in corps, "le séparateur ne doit jamais atteindre l'IA"


def test_un_texte_sans_marqueur_traverse_inchange():
    """Une spec écrite à la main, ou antérieure au point 64, doit se lire
    exactement comme avant — le marqueur est un ajout, pas un format."""
    from frontend_contract import paragraphes
    assert paragraphes("Un seul paragraphe.") == "Un seul paragraphe."
