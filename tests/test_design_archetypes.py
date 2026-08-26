"""Chaque branche de la classification d'archétype, éprouvée.

`infer_design_profile` décide du BRIEF envoyé à l'IA d'interface : le motif
de page, les écrans attendus, les motifs d'UI retenus. Une mauvaise
classification ne casse rien — elle produit simplement le mauvais site, ce
qui est plus cher à voir et plus long à corriger.

Trois des cinq branches n'étaient exercées par aucun test : `commerce`,
`operations` et `editorial`. La quatrième — la déduplication des ancres de
section — ne se déclenche que sur deux sections HOMONYMES, cas qu'aucune spec
du dépôt ne produit, et qui donnerait sans elle deux ancres identiques dans
la même page.
"""

from monl.design_system import _declared_section_markers, infer_design_profile


def _contrat(**extra):
    base = {"entities": {}, "routes": [], "design_skills": []}
    base.update(extra)
    return base


def test_la_reservation_prime_sur_le_prix():
    """Un service réservable porte un prix : au seul archétype il ressemble à
    une boutique. Le signal de réservation doit gagner, sinon on dessine un
    panier là où il faut un calendrier."""
    profil = infer_design_profile(_contrat(
        entities={"Creneau": {"archetype": "shop"}},
        sections=[{"title": "Réserver un créneau", "body": "Prenez rendez-vous."}]))
    assert profil["kind"] == "service"
    assert "disponibilité" in profil["pattern"]


def test_une_action_de_paiement_suffit_a_faire_un_commerce():
    profil = infer_design_profile(_contrat(routes=[{"action": "Pay"}]))
    assert profil["kind"] == "commerce"
    assert "Catalogue" in profil["pages"]
    assert "Panier ou récapitulatif" in profil["pages"]


def test_la_competence_operations_donne_un_espace_de_travail():
    profil = infer_design_profile(_contrat(design_skills=["monl-operations"]))
    assert profil["kind"] == "operations"
    assert "Espace de travail par rôle" in profil["pages"]


def test_des_sections_sans_autre_signal_donnent_un_site_editorial():
    profil = infer_design_profile(_contrat(
        sections=[{"title": "Notre atelier", "body": "Depuis 2019."}]))
    assert profil["kind"] == "editorial"
    assert "Hero narratif" in profil["pattern"]


def test_sans_aucun_signal_le_profil_reste_generique():
    """Le témoin : une classification qui rangerait tout quelque part ne
    classerait rien."""
    profil = infer_design_profile(_contrat())
    assert profil["kind"] == "generic"


def test_une_faq_ajoute_son_ecran():
    profil = infer_design_profile(_contrat(faq=[{"question": "Où ?", "answer": "Ici."}]))
    assert "FAQ structurée" in profil["pages"]


def test_le_mot_service_suffit_quand_rien_dautre_ne_parle():
    """La seconde porte vers `service`, celle qui ne s'ouvre que sur le mot
    lui-même : un contrat qui dit « service » sans jamais dire « réserver »,
    et sans section, ni FAQ, ni paiement."""
    # Le texte analysé vient du NOM et du brief, pas des routes : une
    # classification qui lirait les résumés de routes changerait de verdict
    # au moindre reformulage d'API.
    profil = infer_design_profile(_contrat(app="Service de dépannage à domicile"))
    assert profil["kind"] == "service"


def test_deux_sections_homonymes_ne_partagent_pas_leur_ancre():
    """Deux ancres identiques dans une page, c'est un lien interne sur deux qui
    ne mène nulle part — et rien ne le signale. Le cas ne se produit qu'avec
    des titres HOMONYMES, qu'aucune spec du dépôt ne porte : c'est donc ici, et
    nulle part ailleurs, qu'il est éprouvé."""
    marqueurs = _declared_section_markers({"sections": [
        {"title": "Nos ateliers"},
        {"title": "Nos ateliers"},
        {"title": "Nos ateliers"},
    ]})
    assert len(marqueurs) == len(set(marqueurs)) == 3
    assert marqueurs[0] != marqueurs[1] != marqueurs[2]


def test_une_section_sans_titre_reste_ancrable():
    """Le titre est facultatif dans la grammaire ; une ancre vide casserait la
    navigation sans rien dire."""
    marqueurs = _declared_section_markers({"sections": [{}, {}]})
    assert len(marqueurs) == len(set(marqueurs)) == 2
    assert all('data-monl-section="' in m for m in marqueurs)


def test_un_titre_qui_ressemble_deja_a_une_ancre_derivee_ne_la_vole_pas():
    """Le cas que la simple numérotation ne suffit pas à régler.

    Deux sections « Nos ateliers » donnent `nos-ateliers` puis
    `nos-ateliers-2`. Mais si une TROISIÈME section s'intitule déjà « Nos
    ateliers 2 », son ancre naturelle est exactement celle que la seconde
    allait recevoir. Sans la boucle qui remonte le rang, deux sections
    différentes partagent une ancre — et le lien mène à la mauvaise.
    """
    marqueurs = _declared_section_markers({"sections": [
        {"title": "Nos ateliers"},
        {"title": "Nos ateliers 2"},
        {"title": "Nos ateliers"},
    ]})
    assert len(marqueurs) == len(set(marqueurs)) == 3
