# Tests du catalogue de modèles (point 45). Le verrou central : CHAQUE
# modèle, avec toutes les questions de suivi refusées PUIS toutes acceptées,
# doit produire une spec qui passe le vrai parseur + l'audit AST. Un modèle
# ajouté au catalogue sans respecter les règles strictes du compilateur
# (collisions, ownedBy sans relation…) casse immédiatement la CI.
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from app_templates import TEMPLATES, FREE_MODE_LABEL  # noqa: E402
from dialogue_engine import GuidedDialogue  # noqa: E402
from parser import parse_monl_string  # noqa: E402
from ast_validator import MonlAST  # noqa: E402


def _run_template(index, followup_answer, want_seed):
    """Déroule le dialogue sur le modèle n° index (1-based) avec la même
    réponse à toutes les questions de suivi. Exécution réelle du dialogue,
    jamais un assemblage direct du modèle — c'est le CHEMIN UTILISATEUR
    qui est testé."""
    tpl = TEMPLATES[index - 1]
    answers = [str(index), "AppTest", "Une application de démonstration."]
    answers += [followup_answer] * len(tpl["followups"])
    answers += ["n"]                                   # pas d'entité perso
    answers += ["1"]                                   # inscription libre : 1er rôle proposé
    if tpl["seeds"]:                                   # question seed posée
        answers += ["o" if want_seed else "n"]
    if want_seed and tpl["seeds"]:                     # sujet des images (point 59)
        answers += ["n"]
    answers += ["o"]                                   # brief
    # Le brief transmis déclenche les questions d'intention visuelle
    # (point 53) : action attendue, registre, place des images.
    answers += ["consulter et contacter", "1", "2"]
    answers += ["n"]                                   # pas de section éditoriale
    it = iter(answers)
    return GuidedDialogue(ask=lambda p: next(it)).run()


@pytest.mark.parametrize("index", range(1, len(TEMPLATES) + 1),
                         ids=[t["name"] for t in TEMPLATES])
def test_chaque_modele_compile_tout_refuse(index):
    spec = _run_template(index, "n", want_seed=False)
    MonlAST(parse_monl_string(spec)).validate_and_audit()


@pytest.mark.parametrize("index", range(1, len(TEMPLATES) + 1),
                         ids=[t["name"] for t in TEMPLATES])
def test_chaque_modele_compile_tout_accepte(index):
    spec = _run_template(index, "o", want_seed=True)
    normalized = MonlAST(parse_monl_string(spec)).validate_and_audit()
    # Toute règle ownedBy émise a bien sa structure (le validateur l'exige,
    # mais on vérifie explicitement que le dialogue n'a rien contourné).
    for ref, owner in normalized["security"]["ownership"].items():
        assert owner in normalized["schema"]["entities"]


def test_chaque_modele_ouvre_l_inscription_a_un_role(index=3):
    """Une spec issue du dialogue doit rester utilisable : sans marqueur
    'selfRegister', personne ne peut créer de compte sur l'application
    produite (régression introduite puis corrigée en bêta 3)."""
    spec = _run_template(index, "o", want_seed=True)
    inscriptibles = [l for l in spec.splitlines() if l.startswith("actor ")
                     and l.endswith("selfRegister")]
    assert len(inscriptibles) == 1, spec
    normalized = MonlAST(parse_monl_string(spec)).validate_and_audit()
    # Le premier rôle proposé doit être celui qui n'écrit que sur SES données
    # (ici : le client d'une boutique), jamais l'administrateur du catalogue.
    assert normalized["security"]["self_register_actors"] == ["Customer"], spec


def test_catalogue_a_dix_modeles_et_le_mode_libre():
    assert len(TEMPLATES) == 10
    assert FREE_MODE_LABEL
    names = [t["name"] for t in TEMPLATES]
    assert len(set(names)) == 10, "noms de modèles dupliqués"


def test_boutique_options_tissees_jusqu_aux_seeds():
    spec = _run_template(3, "o", want_seed=True)   # Boutique en ligne
    # stock : acquis depuis le point 60 ; category : encore optionnelle.
    assert "category: String" in spec and "stock: Integer" in spec
    assert 'category: "Théières"' in spec and "stock: 12" in spec
    assert "rule Order.Update ownedBy Customer" in spec
    assert "entity Customer" in spec and "relation Customer hasMany Order" in spec


def test_forum_likes_via_increments():
    spec = _run_template(5, "o", want_seed=True)   # Forum / réseau social
    assert "rule Like.Create increments Post.likes by 1" in spec
    assert "relation Post hasMany Like" in spec


def test_entite_personnalisee_en_plus_du_modele():
    # Portfolio + entité perso "Testimonial" lisible publiquement.
    answers = iter([
        "1", "StudioPerso", "Un portfolio avec témoignages.",
        "n",                 # unique question de suivi refusée (catégories)
        "o",                 # entité personnalisée ?
        "Testimonial", "author", "1", "quote", "2", "",
        "o",                 # lisible sans compte
        "n",                 # pas d'autre entité perso
        "1",                 # inscription libre : 1er rôle proposé
        "o",                 # seeds
        "n",                 # images génériques (point 59)
        "o",                 # brief
        "lire les témoignages", "1", "2",   # intention visuelle (point 53)
        "n",                                # pas de section éditoriale (point 55)
    ])
    spec = GuidedDialogue(ask=lambda p: next(answers)).run()
    assert "entity Testimonial" in spec
    assert "rule Testimonial.Read public" in spec
    MonlAST(parse_monl_string(spec)).validate_and_audit()


def test_catalogue_jamais_mute_entre_deux_executions():
    """Le deepcopy protège le catalogue : deux exécutions du même modèle
    avec des réponses différentes ne doivent pas se contaminer."""
    spec_oui = _run_template(3, "o", want_seed=True)
    spec_non = _run_template(3, "n", want_seed=True)
    # La catégorie reste optionnelle (le stock, lui, est devenu un acquis) :
    # c'est donc elle qui distingue une exécution « tout oui » d'une « tout non ».
    assert "category: String" in spec_oui
    assert "category: String" not in spec_non, "le catalogue a été muté !"


# ---- Éléments devenus des acquis (point 60) ----

def test_les_elements_standards_ne_sont_plus_des_questions():
    """Recherche à l'appui (point 60) : ces éléments figurent dans les
    recensements publics d'essentiels de leur catégorie. Les demander faisait
    porter à l'utilisateur un choix qui n'en est pas un, et produisait par
    défaut des applications amputées de l'évident."""
    acquis = {
        1: ["entity Message"],                          # contact d'un portfolio
        2: ["author: String", "publishedOn: String"],    # signature et date
        3: ["stock: Integer"],                           # disponibilité produit
        4: ["priority: String", "dueDate: String"],      # carte kanban
        6: ["location: String", "entity Inquiry"],       # lieu + contact vendeur
        7: ["description: Text"],                        # prestation décrite
    }
    for index, attendus in acquis.items():
        spec = _run_template(index, "n", want_seed=False)   # TOUT refusé
        for attendu in attendus:
            assert attendu in spec, (
                f"modèle {index} ({TEMPLATES[index - 1]['name']}) : « {attendu} » "
                f"devrait être acquis, il manque quand tout est refusé")


def test_le_dialogue_a_bien_ete_allege():
    """Le nombre de questions de suivi est passé de 16 à 8. Ce test fige le
    gain : y rajouter une question demande de justifier qu'elle n'est pas un
    standard de sa catégorie."""
    total = sum(len(t["followups"]) for t in TEMPLATES)
    assert total == 8, f"{total} questions de suivi (8 attendues)"
    # Les modèles dont chaque élément est standard n'en posent plus aucune.
    sans_question = [t["name"] for t in TEMPLATES if not t["followups"]]
    assert "Gestion de tâches" in sans_question
    assert "Petites annonces" in sans_question
    assert "Réservation de rendez-vous" in sans_question
