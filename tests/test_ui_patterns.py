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


def test_service_de_reservation_recoit_un_parcours_reel_sans_contact_fictif():
    contract = {
        "brief": "Un studio qui permet de réserver un rendez-vous.",
        "entities": {"Booking": {"archetype": "list", "fields": []}},
        "routes": [{"action": "Create", "entity": "Booking", "path": "/booking"}],
    }
    names = [pattern["name"] for pattern in select_ui_patterns(contract, "service")]
    assert "booking" in names
    assert "contact" not in names


def test_service_tarife_ne_devient_pas_un_catalogue_par_effet_de_larchetype():
    contract = {
        "brief": "Un atelier qui permet de réserver une prestation.",
        "entities": {"Service": {"archetype": "shop", "fields": []}},
        "routes": [{"action": "Create", "entity": "Booking", "path": "/booking"}],
    }
    names = [pattern["name"] for pattern in select_ui_patterns(contract, "service")]
    assert "catalogue" not in names


def test_boutique_kora_maison_recoit_un_catalogue_sans_parcours_de_reservation():
    contract = {
        "brief": "Une boutique de décoration et d'art de vivre.",
        "entities": {
            "Customer": {"archetype": "list", "fields": []},
            "Order": {"archetype": "list", "fields": []},
            "OrderLine": {"archetype": "list", "fields": []},
            "Product": {"archetype": "shop", "fields": []},
        },
        "routes": [
            {"action": "List", "entity": "Product", "path": "/product"},
            {"action": "Create", "entity": "Product", "path": "/product"},
        ],
    }
    names = [pattern["name"] for pattern in select_ui_patterns(contract, "service")]
    assert "catalogue" in names
    assert "booking" not in names


def test_entite_message_recoit_un_formulaire_de_contact():
    contract = {
        "brief": "Un portfolio de photographe.",
        "entities": {
            "Message": {"archetype": "list", "fields": []},
        },
        "routes": [
            {"action": "List", "entity": "Message", "path": "/message"},
            {"action": "Create", "entity": "Message", "path": "/message"},
        ],
    }
    names = [pattern["name"] for pattern in select_ui_patterns(contract, "operations")]
    assert "contact" in names
