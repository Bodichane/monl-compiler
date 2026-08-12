"""Sélection et transmission des compétences de design Monl."""

from monl.design_skills import render_skill_block, select_design_skills


def _field(role):
    return {"name": role, "role": role}


def test_le_socle_showcase_est_toujours_selectionne():
    assert select_design_skills({}, []) == ["monl-showcase"]


def test_un_prix_seul_n_invente_pas_un_parcours_commerce():
    entities = {"Offer": {"fields": [_field("title"), _field("price")]}}
    assert "monl-commerce" not in select_design_skills(entities, [])


def test_le_paiement_selectionne_le_parcours_commerce_sans_nom_magique():
    routes = [{"action": "Pay", "allowed_actors": ["Client"]}]
    assert "monl-commerce" in select_design_skills({}, routes)


def test_une_application_dense_selectionne_les_operations():
    entities = {name: {"fields": []} for name in ("Task", "Budget", "Expense")}
    assert "monl-operations" in select_design_skills(entities, [])


def test_le_bloc_ne_prescrit_aucune_identite_visuelle():
    block = render_skill_block(["monl-showcase", "monl-commerce"])
    assert "$monl-showcase" in block and "$monl-commerce" in block
    for forbidden in ("#fff", "Inter", "bleu", "border-radius"):
        assert forbidden not in block
