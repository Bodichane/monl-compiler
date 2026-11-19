"""Selection and transmission of the Monl design skills."""

from monl.design_skills import render_skill_block, select_design_skills


def _field(role):
    return {"name": role, "role": role}


def test_the_showcase_base_is_always_selected():
    assert select_design_skills({}, []) == ["monl-showcase"]


def test_a_price_alone_does_not_invent_a_commerce_journey():
    entities = {"Offer": {"fields": [_field("title"), _field("price")]}}
    assert "monl-commerce" not in select_design_skills(entities, [])


def test_payment_selects_the_commerce_journey_without_a_magic_name():
    routes = [{"action": "Pay", "allowed_actors": ["Client"]}]
    assert "monl-commerce" in select_design_skills({}, routes)


def test_a_dense_application_selects_operations():
    entities = {name: {"fields": []} for name in ("Task", "Budget", "Expense")}
    assert "monl-operations" in select_design_skills(entities, [])


def test_the_block_prescribes_no_visual_identity():
    block = render_skill_block(["monl-showcase", "monl-commerce"])
    assert "$monl-showcase" in block and "$monl-commerce" in block
    for forbidden in ("#fff", "Inter", "bleu", "border-radius"):
        assert forbidden not in block
