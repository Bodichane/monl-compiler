"""Le catalogue local sélectionne des structures adaptables au contrat."""

from monl.ui_patterns import render_pattern_block, select_ui_patterns


def test_boutique_recoit_des_patterns_de_page_et_de_media():
    contract = {
        "brief": "Une boutique de mobilier local.",
        "design_skills": ["monl-showcase", "monl-commerce"],
        "sections": [{"title": "Notre atelier", "body": "Fabrication locale."}],
        "faq": [{"question": "Livraison ?", "answer": "Partout au pays."}],
        "entities": {
            "Product": {"archetype": "shop", "fields": [{"role": "media"}]},
        },
        "routes": [],
    }
    patterns = select_ui_patterns(contract, "commerce")
    names = [pattern["name"] for pattern in patterns]
    assert names == ["hero", "catalogue", "editorial", "trust", "faq", "closing-cta"]
    rendered = render_pattern_block(patterns)
    assert "filter-grid" in rendered
    assert 'data-monl-section="catalogue"' in rendered
    assert "invente des données" in rendered


def test_operations_prefere_une_liste_dense():
    contract = {
        "brief": "Un espace de travail pour une équipe.",
        "entities": {"Task": {"archetype": "list", "fields": []}},
        "routes": [],
    }
    patterns = select_ui_patterns(contract, "operations")
    assert next(pattern for pattern in patterns if pattern["name"] == "hero")["variant"] == "workspace-entry"
    assert "catalogue" not in [pattern["name"] for pattern in patterns]
