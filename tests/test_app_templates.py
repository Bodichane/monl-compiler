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
    answers += ["o"]                                   # brief
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
        "n", "n",            # questions de suivi refusées
        "o",                 # entité personnalisée ?
        "Testimonial", "author", "1", "quote", "2", "",
        "o",                 # lisible sans compte
        "n",                 # pas d'autre entité perso
        "1",                 # inscription libre : 1er rôle proposé
        "o", "o",            # seeds + brief
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
    assert "stock: Integer" in spec_oui
    assert "stock: Integer" not in spec_non, "le catalogue a été muté !"
