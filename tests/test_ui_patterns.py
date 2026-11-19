"""The local catalog selects structures adaptable to the contract."""

from monl.ui_patterns import render_pattern_block, select_ui_patterns


def test_shop_gets_page_and_media_patterns():
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
    assert "invents data" in rendered


def test_operations_prefers_a_dense_list():
    contract = {
        "brief": "Un espace de travail pour une équipe.",
        "entities": {"Task": {"archetype": "list", "fields": []}},
        "routes": [],
    }
    patterns = select_ui_patterns(contract, "operations")
    assert next(pattern for pattern in patterns if pattern["name"] == "hero")["variant"] == "workspace-entry"
    assert "catalogue" not in [pattern["name"] for pattern in patterns]


def test_booking_service_gets_a_real_journey_without_a_fake_contact():
    contract = {
        "brief": "Un studio qui permet de réserver un rendez-vous.",
        "entities": {"Booking": {"archetype": "list", "fields": []}},
        "routes": [{"action": "Create", "entity": "Booking", "path": "/booking"}],
    }
    names = [pattern["name"] for pattern in select_ui_patterns(contract, "service")]
    assert "booking" in names
    assert "contact" not in names


def test_priced_service_does_not_become_a_catalog_through_the_archetype():
    contract = {
        "brief": "Un atelier qui permet de réserver une prestation.",
        "entities": {"Service": {"archetype": "shop", "fields": []}},
        "routes": [{"action": "Create", "entity": "Booking", "path": "/booking"}],
    }
    names = [pattern["name"] for pattern in select_ui_patterns(contract, "service")]
    assert "catalogue" not in names


def test_kora_maison_shop_gets_a_catalog_without_a_booking_journey():
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
