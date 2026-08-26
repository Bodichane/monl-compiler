# Tests du catalogue de modèles (point 45). Le verrou central : CHAQUE
# modèle, avec toutes les questions de suivi refusées PUIS toutes acceptées,
# doit produire une spec qui passe le vrai parseur + l'audit AST. Un modèle
# ajouté au catalogue sans respecter les règles strictes du compilateur
# (collisions, ownedBy sans relation…) casse immédiatement la CI.

import pytest

from monl.app_templates import FREE_MODE_LABEL, TEMPLATES
from monl.ast_validator import MonlAST
from monl.dialogue_engine import GuidedDialogue
from monl.parser import parse_monl_string


def _champs_payables(tpl):
    """Reproduit le critère de `_ask_payable` (points 75 et 79).

    Depuis le point 79, un `Money` sur une entité possédée ne suffit plus : le
    montant doit être CALCULÉ par le serveur, donc il faut aussi un catalogue —
    une autre entité, qui ne soit pas le propriétaire, portant un prix. Sans
    lui, le dialogue ne pose plus la question, et c'est un progrès : sur les
    trois modèles qui portaient un `Money` possédé, deux n'avaient aucun
    catalogue parce que l'encaissement n'y avait aucun sens (dans « Petites
    annonces » le vendeur se paierait lui-même ; « Suivi de dépenses » est un
    registre personnel)."""
    if not tpl.get("accept_payments", True):
        return []
    candidats = []
    for name, meta in tpl["entities"].items():
        if not meta["owned"]:
            continue
        montants = [f for f, t in meta["fields"] if t == "Money"]
        if not montants:
            continue
        for source, m2 in tpl["entities"].items():
            if source == name or source == meta["manager"] or tpl["entities"][source]["owned"]:
                continue
            prix = [f for f, t in m2["fields"] if t in ("Money", "Float", "Integer")]
            if prix:
                # POINT 86 : la SOURCE est retournée aussi. Les questions qui
                # suivent (panier, stock) en dépendent, et un harnais qui ne les
                # connaît pas décale toutes les réponses scriptées.
                candidats.append((f"{name}.{montants[0]}", source, prix[0]))
                break
    return candidats


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
    # POINT 138 : identifiant de compte. Chemin « tout refuser » = aucun
    # (spec sans bloc `capability auth`, comme avant la question) ; chemin
    # « tout accepter » = téléphone + indicatif, pour que les DIX modèles
    # prouvent que le bloc émis compile.
    answers += (["1", "+229"] if followup_answer == "o" else ["0"])
    candidats_payables = _champs_payables(tpl)
    if candidats_payables:                             # question payable posée (point 75)
        answers += [followup_answer]
        if followup_answer == "o" and len(candidats_payables) > 1:
            answers += ["1"]                           # champ à choisir : le premier
        if followup_answer == "o":
            # POINT 86 : deux questions de plus, dans cet ordre — panier
            # multi-articles, puis décompte de stock. Le catalogue retenu est
            # celui du premier candidat, que le choix ci-dessus sélectionne.
            answers += ["o"]                           # panier multi-articles
            _montant, source, prix = candidats_payables[0]
            stocks = [f for f, t in tpl["entities"][source]["fields"]
                      if t == "Integer" and f != prix]
            if stocks:
                answers += ["o"]                       # décompter le stock
                if len(stocks) > 1:
                    answers += ["1"]                   # quel champ porte le stock
    if tpl["seeds"]:                                   # question seed posée
        answers += ["o" if want_seed else "n"]
    if want_seed and tpl["seeds"]:                     # sujet des images (point 59)
        answers += ["n"]
    answers += ["o"]                                   # brief
    # Le brief transmis déclenche les questions d'intention visuelle
    # (point 53) : action attendue, registre, place des images.
    answers += ["consulter et contacter", "1", "2"]
    # Rubriques éditoriales du modèle (point 61) : leur TEXTE est demandé
    # directement. Chemin « tout refuser » = tout laisser vide.
    for section in tpl.get("sections", []):
        # Point 64 : le corps se saisit paragraphe par paragraphe, une ligne
        # vide le termine. Refuser la rubrique = premier paragraphe vide,
        # et aucune relance n'est alors posée.
        answers += ([f"Texte de la rubrique {section['title']}.", ""]
                    if followup_answer == "o" else [""])
    answers += ["n"]                                   # pas de section en plus
    # Destinations du pied de page (brique 30). Le NOMBRE d'entrées proposées
    # est lu sur la source : le figer ici le ferait diverger en silence, et
    # c'est exactement ce qui vient de casser ces dix tests.
    proposees = len(GuidedDialogue.LIENS_PROPOSES)
    if followup_answer == "o":
        saisies = ["contact@exemple.fr", "+33 6 12 34 56 78",
                   "instagram.com/exemple"]
        answers += (saisies + [""] * proposees)[:proposees]
    else:
        answers += [""] * proposees
    answers += ["n"]                                   # pas d'autre lien
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
    inscriptibles = [ligne for ligne in spec.splitlines() if ligne.startswith("actor ")
                     and ligne.endswith("selfRegister")]
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


def test_la_boutique_guidee_date_ses_commandes():
    """POINT 89 : aucune question ne propose l'horodatage — le dialogue l'émet
    avec le reste de la chaîne d'encaissement. Une capacité que le dialogue
    n'exprime pas n'existe pas pour qui n'écrit pas la spec à la main (leçon du
    point 75), et un carnet de commandes sans dates n'est pas un carnet."""
    spec = _run_template(3, "o", want_seed=True)   # Boutique en ligne
    assert "creeLe: DateTime" in spec
    assert "rule Order.creeLe timestamp" in spec
    # Et le refus du point 85 ne doit pas se déclencher : le champ est ajouté en
    # QUEUE, donc la règle « premier champ requis » ne le vise pas.
    assert "rule Order.creeLe required" not in spec


def test_forum_likes_via_increments():
    spec = _run_template(5, "o", want_seed=True)   # Forum / réseau social
    assert "rule Like.Create increments Post.likes by 1" in spec
    assert "relation Post hasMany Like" in spec


@pytest.mark.parametrize(
    ("index", "reference"),
    [(2, "Article.Read"), (5, "Post.Read")],
    ids=["blog", "forum"],
)
def test_les_modeles_public_when_declarent_le_superviseur(index, reference):
    """Un modérateur doit garder accès aux publications masquées."""
    spec = _run_template(index, "n", want_seed=False)
    assert f"rule {reference} sharedBy Moderator" in spec


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
        "0",                 # identifiant de compte : aucun (point 138)
        "o",                 # seeds
        "n",                 # images génériques (point 59)
        "o",                 # brief
        "lire les témoignages", "1", "2",   # intention visuelle (point 53)
        "", "",                             # rubriques du portfolio passées (point 61)
        "n",                                # pas de section en plus (point 55)
        "", "", "", "", "",                 # pied de page : aucun lien
        "n",                                # pas d'autre lien (brique 30)
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


def test_les_rubriques_editoriales_sont_demandees_pas_proposees():
    """Point 61 : sur un modèle qui porte des rubriques standard, le dialogue
    ne demande plus S'IL en faut — il en demande le texte, rubrique par
    rubrique, en la nommant. Ce test lit les invites réellement posées."""
    poses = []

    def ask(prompt):
        poses.append(prompt)
        return next(it)

    tpl = TEMPLATES[0]                                   # Portfolio
    answers = ["1", "AppTest", "Un portfolio.", "n", "n", "1", "0", "o", "n", "o",
               "consulter", "1", "2",
               "Photographe à Lyon depuis 2015.", "",
               "Reportage et portrait.", "",
               "n",
               "contact@studio.fr", "", "", "", "",   # pied de page
               "n"]
    it = iter(answers)
    spec = GuidedDialogue(ask=ask).run()
    for section in tpl["sections"]:
        assert any(section["title"] in p for p in poses), (
            f"la rubrique « {section['title']} » n'a jamais été demandée")
    assert not any("Ajouter du texte de présentation" in p for p in poses), (
        "l'ancienne question o/n subsiste alors que le modèle a des rubriques")
    assert 'section "À propos": "Photographe à Lyon depuis 2015."' in spec
    assert 'section "Services": "Reportage et portrait."' in spec
    MonlAST(parse_monl_string(spec)).validate_and_audit()


def test_une_rubrique_laissee_vide_est_simplement_absente():
    answers = iter(["1", "AppTest", "Un portfolio.", "n", "n", "1", "0", "o", "n", "o",
                    "consulter", "1", "2",
                    "", "Reportage et portrait.", "", "n",
                    "", "", "", "", "", "n"])
    spec = GuidedDialogue(ask=lambda p: next(answers)).run()
    assert "À propos" not in spec
    assert 'section "Services": "Reportage et portrait."' in spec


def test_un_outil_interne_ne_se_voit_imposer_aucune_rubrique():
    """Kanban, inventaire, dépenses : aucune source ne donne de rubrique
    attendue pour un outil sans visiteur. Le dialogue retombe donc sur
    l'offre générique plutôt que d'inventer un « à propos »."""
    for nom in ("Gestion de tâches", "Inventaire / gestion de stock",
                "Suivi de dépenses personnelles"):
        tpl = next(t for t in TEMPLATES if t["name"] == nom)
        assert tpl["sections"] == [], nom


def test_le_dialogue_a_bien_ete_allege():
    """Le nombre de questions de suivi est passé de 16 à 8. Ce test fige le
    gain : y rajouter une question demande de justifier qu'elle n'est pas un
    standard de sa catégorie."""
    total = sum(len(t["followups"]) for t in TEMPLATES)
    assert total == 6, f"{total} questions de suivi (6 attendues)"
    # Les modèles dont chaque élément est standard n'en posent plus aucune.
    sans_question = [t["name"] for t in TEMPLATES if not t["followups"]]
    assert "Gestion de tâches" in sans_question
    assert "Petites annonces" in sans_question
    assert "Réservation de rendez-vous" in sans_question


def test_le_dialogue_sait_produire_un_panier_complet():
    """POINT 86 : le dialogue produisait la forme MONO-ARTICLE du point 77 —
    une commande à un seul article — alors que le compilateur sait faire un
    panier depuis le point 82. Quatre briques étaient hors d'atteinte de qui
    n'écrit pas la spec à la main : `sumOf`, la propriété transitive, `min` et
    le décompte de stock. Une capacité que le dialogue n'exprime pas n'existe
    pas pour ces utilisateurs — c'est l'argument même qui avait fait naître la
    question `payable` au point 75.

    Ce test tient la chaîne entière : sans elle, on retomberait sur une
    boutique à un article, ou pire sur un montant que l'acheteur écrit."""
    index = next(i for i, t in enumerate(TEMPLATES, 1) if t["name"] == "Boutique en ligne")
    spec = _run_template(index, "o", want_seed=True)
    regles = [li for li in spec.splitlines() if li.startswith("rule ")]

    assert "entity LigneOrder" in spec
    # Propriété TRANSITIVE : la ligne appartient à qui possède sa commande.
    assert "rule LigneOrder.Read ownedBy Order" in regles
    # Le sous-total est CALCULÉ, le total est la SOMME, et c'est lui qu'on encaisse.
    assert "rule LigneOrder.sousTotal derivedFrom Product.price by quantite" in regles
    assert "rule Order.total sumOf LigneOrder.sousTotal" in regles
    assert "rule Order.total payable" in regles
    # Le stock : un plancher DÉCLARÉ, et le décompte qu'il arme.
    assert "rule Product.stock min 0" in regles
    assert "rule LigneOrder.Create decrements Product.stock by quantite" in regles
    # Aucun champ calculé par le serveur n'est déclaré « requis » : le contrat
    # dirait à la fois « à remplir » et « à ne pas envoyer ».
    assert "rule Order.total required" not in regles

    normalized = MonlAST(parse_monl_string(spec)).validate_and_audit()
    assert normalized["security"]["aggregated_fields"]
    assert normalized["security"]["transitive_ownership"]


def test_le_dialogue_sait_encore_produire_une_commande_simple():
    """Le témoin du test ci-dessus : répondre « non » au panier doit rendre la
    forme mono-article, pas une spec cassée."""
    index = next(i for i, t in enumerate(TEMPLATES, 1) if t["name"] == "Boutique en ligne")
    tpl = TEMPLATES[index - 1]
    answers = [str(index), "AppTest", "Une boutique."]
    answers += ["n"] * len(tpl["followups"])
    answers += ["n", "1"]                     # pas d'entité perso ; inscription libre
    answers += ["0"]                          # identifiant de compte : aucun (point 138)
    answers += ["o"]                          # encaisser un paiement
    candidats = _champs_payables(tpl)
    if len(candidats) > 1:
        answers += ["1"]
    answers += ["n"]                          # PAS de panier
    _montant, source, prix = candidats[0]
    if [f for f, t in tpl["entities"][source]["fields"] if t == "Integer" and f != prix]:
        answers += ["n"]                      # pas de décompte de stock
    answers += ["n"]                          # pas de seed
    answers += ["n"]                          # pas de brief
    answers += ["n"]                          # pas de section en plus
    it = iter(answers)
    spec = GuidedDialogue(ask=lambda p: next(it)).run()
    assert "entity LigneOrder" not in spec
    assert "rule Order.total derivedFrom Product.price by quantite" in spec
    MonlAST(parse_monl_string(spec)).validate_and_audit()
