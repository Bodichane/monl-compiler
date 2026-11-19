# Tests of the template catalog (point 45). The central lock: EACH template,
# with every follow-up question refused THEN every one accepted, must produce a
# spec passing the real parser + the AST audit. A template added to the catalog
# without respecting the compiler's strict rules (collisions, ownedBy without
# relation…) breaks CI immediately.

import re

import pytest

from monl.app_templates import FREE_MODE_LABEL, TEMPLATES
from monl.ast_validator import ASTValidationError, MonlAST
from monl.cli import _contract_signature, compile_project
from monl.dialogue_engine import GuidedDialogue
from monl.parser import parse_monl_string
from tests.support.cas import check_each_case


def _payable_fields(tpl):
    """Reproduces `_ask_payable`'s criterion (points 75 and 79).

    Since point 79, a `Money` on an owned entity is no longer enough: the amount
    must be CALCULATED by the server, so a catalog is needed too — another entity,
    not the owner, carrying a price. Without it, the dialogue no longer asks the
    question, and it is progress: of the three templates carrying an owned
    `Money`, two had no catalog because charging made no sense there (in
    "Classified ads" the seller would pay themselves; "Expense tracking" is a
    personal ledger)."""
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
                # POINT 86: the SOURCE is returned too. The following questions
                # (cart, stock) depend on it, and a harness not knowing them
                # shifts every scripted answer.
                candidats.append((f"{name}.{montants[0]}", source, prix[0]))
                break
    return candidats


def _run_template(index, followup_answer, want_seed, upload_pour=None,
                  prompts=None, account_answers=None):
    """Runs the dialogue on template no. index (1-based) with the same answer to
    every follow-up question. Real execution of the dialogue, never a direct
    assembly of the template — the USER PATH is what is tested."""
    tpl = TEMPLATES[index - 1]
    answers = [str(index), "AppTest", "Une application de démonstration."]
    answers += [followup_answer] * len(tpl["followups"])
    answers += ["n"]                                   # no custom entity
    answers += ["1"]                                   # open registration: 1st offered role
    # POINT 138: account identifier. "Refuse everything" path = none (spec
    # without a `capability auth` block, as before the question); "accept
    # everything" path = phone + calling code, so that the TEN templates prove
    # the emitted block compiles.
    answers += (account_answers if account_answers is not None else
                (["1", "+229"] if followup_answer == "o" else ["0"]))
    upload_entities = [
        name for name, meta in tpl["entities"].items()
        if meta["owned"] and not meta["public_read"]
    ]
    answers += [
        "1" if followup_answer == "o" or name == upload_pour else "0"
        for name in upload_entities
    ]
    candidats_payables = _payable_fields(tpl)
    if candidats_payables:                             # payable question asked (point 75)
        answers += [followup_answer]
        if followup_answer == "o" and len(candidats_payables) > 1:
            answers += ["1"]                           # field to choose: the first
        if followup_answer == "o":
            # POINT 86: two more questions, in this order — multi-item cart,
            # then stock counting. The kept catalog is the first candidate's,
            # which the choice above selects.
            answers += ["o"]                           # panier multi-articles
            _montant, source, prix = candidats_payables[0]
            stocks = [f for f, t in tpl["entities"][source]["fields"]
                      if t == "Integer" and f != prix]
            if stocks:
                answers += ["o"]                       # count the stock
                if len(stocks) > 1:
                    answers += ["1"]                   # which field carries the stock
    if tpl["seeds"]:                                   # seed question asked
        answers += ["o" if want_seed else "n"]
    if want_seed and tpl["seeds"]:                     # image subject (point 59)
        answers += ["n"]
    answers += ["o"]                                   # brief
    # The passed-on brief triggers the visual intent questions (point 53):
    # expected action, register, placement of images.
    answers += ["consulter et contacter", "1", "2"]
    # The template's editorial sections (point 61): their TEXT is asked
    # directly. "Refuse everything" path = leave everything empty.
    for section in tpl.get("sections", []):
        # Point 64: the body is entered paragraph by paragraph, an empty line
        # ends it. Refusing the section = empty first paragraph, and no
        # follow-up is then asked.
        answers += ([f"Texte de la rubrique {section['title']}.", ""]
                    if followup_answer == "o" else [""])
    answers += ["n"]                                   # no extra section
    # Footer destinations (brick 30). The NUMBER of offered entries is read
    # from the source: freezing it here would make it diverge silently, and
    # that is exactly what just broke these ten tests.
    proposees = len(GuidedDialogue.LIENS_PROPOSES)
    if followup_answer == "o":
        saisies = ["contact@exemple.fr", "+33 6 12 34 56 78",
                   "instagram.com/exemple"]
        answers += (saisies + [""] * proposees)[:proposees]
    else:
        answers += [""] * proposees
    answers += ["n"]                                   # no other link
    it = iter(answers)
    ask = ((lambda prompt: (prompts.append(prompt), next(it))[1])
           if prompts is not None else (lambda _prompt: next(it)))
    return GuidedDialogue(ask=ask).run()


def test_each_template_compiles_all_refused():
    table = range(1, len(TEMPLATES) + 1)
    noms = [t["name"] for t in TEMPLATES]

    def cas(index):
        spec = _run_template(index, "n", want_seed=False)
        MonlAST(parse_monl_string(spec)).validate_and_audit()

    check_each_case([(valeur,) for valeur in table], cas, ids=noms)


def test_each_template_compiles_all_accepted():
    table = range(1, len(TEMPLATES) + 1)
    noms = [t["name"] for t in TEMPLATES]

    def cas(index):
        spec = _run_template(index, "o", want_seed=True)
        normalized = MonlAST(parse_monl_string(spec)).validate_and_audit()
        # Every emitted ownedBy rule does have its structure (the validator
        # requires it, but we check explicitly that the dialogue bypassed
        # nothing).
        for ref, owner in normalized["security"]["ownership"].items():
            assert owner in normalized["schema"]["entities"]

    check_each_case([(valeur,) for valeur in table], cas, ids=noms)


def test_each_template_opens_registration_to_a_role(index=3):
    """A spec from the dialogue must stay usable: without a 'selfRegister'
    marker, nobody can create an account on the produced application (regression
    introduced then fixed in beta 3)."""
    spec = _run_template(index, "o", want_seed=True)
    inscriptibles = [ligne for ligne in spec.splitlines() if ligne.startswith("actor ")
                     and ligne.endswith("selfRegister")]
    assert len(inscriptibles) == 1, spec
    normalized = MonlAST(parse_monl_string(spec)).validate_and_audit()
    # The first offered role must be the one writing only on ITS data (here: a
    # shop's customer), never the catalog administrator.
    assert normalized["security"]["self_register_actors"] == ["Customer"], spec


def test_catalog_has_ten_templates_and_free_mode():
    assert len(TEMPLATES) == 10
    assert FREE_MODE_LABEL
    names = [t["name"] for t in TEMPLATES]
    assert len(set(names)) == 10, "duplicated template names"


def test_shop_options_woven_down_to_the_seeds():
    spec = _run_template(3, "o", want_seed=True)   # Online shop
    # stock: standard since point 60; category: still optional.
    assert "category: String" in spec and "stock: Integer" in spec
    assert 'category: "Teapots"' in spec and "stock: 12" in spec
    assert "rule Order.Update ownedBy Customer" in spec
    assert "entity Customer" in spec and "relation Customer hasMany Order" in spec


def test_the_guided_shop_dates_its_orders():
    """POINT 89: no question offers the timestamp — the dialogue emits it with
    the rest of the charging chain. A capability the dialogue does not express
    does not exist for whoever does not write the spec by hand (point 75's
    lesson), and an order book without dates is not a book."""
    spec = _run_template(3, "o", want_seed=True)   # Online shop
    assert "creeLe: DateTime" in spec
    assert "rule Order.creeLe timestamp" in spec
    assert "rule Order.Read sort creeLe" in spec
    # And point 85's refusal must not fire: the field is added at the END, so
    # the "first field required" rule does not target it.
    assert "rule Order.creeLe required" not in spec


def test_the_dialogue_derives_filter_and_sort_both_ways():
    """oneOf becomes a filter, timestamp becomes a sort, without a dedicated
    question."""
    task_index = next(i for i, t in enumerate(TEMPLATES, 1)
                      if t["name"] == "Task management")
    task_prompts = []
    task_rules = [line for line in _run_template(
        task_index, "n", False, prompts=task_prompts).splitlines()
                  if line.startswith("rule ")]
    assert "rule Task.Read filter status" in task_rules
    assert "rule Task.Read filter priority" in task_rules
    assert not any(" sort " in line for line in task_rules)
    assert not any("filtr" in prompt.lower() or "trier" in prompt.lower()
                   for prompt in task_prompts)

    ranking_index = next(i for i, t in enumerate(TEMPLATES, 1)
                         if t["name"] == "Community ranking")
    ranking_rules = [line for line in _run_template(ranking_index, "n", False).splitlines()
                     if line.startswith("rule ")]
    assert "rule Entry.Read sort submittedOn" in ranking_rules
    assert not any(" filter " in line for line in ranking_rules)

    portfolio_rules = [line for line in _run_template(1, "n", False).splitlines()
                       if line.startswith("rule ")]
    assert not any(" filter " in line or " sort " in line
                   for line in portfolio_rules)


def test_several_oneof_stay_filters_with_an_and_where(tmp_path):
    index = next(i for i, t in enumerate(TEMPLATES, 1)
                 if t["name"] == "Task management")
    spec = _run_template(index, "n", False)
    spec_path = tmp_path / "spec.ml"
    spec_path.write_text(spec, encoding="utf-8")
    contract = compile_project(str(spec_path), str(tmp_path))
    route = next(r for r in contract["routes"]
                 if r["method"] == "GET" and r["path"] == "/task")
    assert [item["field"] for item in route["list_query"]["filters"]] == [
        "status", "priority"]
    assert "_filter_where = ' AND '.join(_filter_parts)" in (
        tmp_path / "app.py").read_text(encoding="utf-8")


def test_an_expense_receipt_exercises_the_private_upload(tmp_path):
    """Upload is offered where "private" is the GOAL, not something endured.

    THE PATH SET ASIDE, and it is the heart of the decision. A photo field had
    first been added to "Classified ads". The spec compiled, the ACL was correct —
    and the produced site was unusable: measured against a real server, a BUYER
    gets 403 on the file route. A listing photo must be seen by buyers, and monl
    (rightly) refuses that an uploaded file be publicly readable. The result was
    therefore a catalog whose images nobody sees — worse than no photo at all,
    because the seller believes they added one.

    An expense receipt, however, has NO reason to be seen by anyone else: the
    compiler's constraint and the need coincide.
    """
    index = next(i for i, t in enumerate(TEMPLATES, 1)
                 if t["name"] == "Personal expense tracking")
    prompts = []
    spec = _run_template(index, "n", False, upload_pour="Expense",
                         prompts=prompts)
    depots = [p for p in prompts if "file upload" in p]
    assert len(depots) == 2, depots          # Expense and Budget are eligible
    # The question SAYS what it produces: without this sentence, one picks
    # "Photo" believing others will see it.
    assert all("only be readable by its owner" in p for p in depots), depots

    normalized = MonlAST(parse_monl_string(spec)).validate_and_audit()
    assert "photo: Upload" in spec
    assert ("rule Expense.photo upload max 5242880 types "
            '"image/png", "image/jpeg"') in spec
    assert normalized["security"]["upload_fields"] == [{
        "entity": "Expense", "field": "photo", "max_bytes": 5242880,
        "accepted_types": ["image/png", "image/jpeg"],
    }]
    assert "Expense.Read" in normalized["security"]["ownership"]
    assert "Expense.Update" in normalized["security"]["ownership"]

    spec_path = tmp_path / "spec.ml"
    spec_path.write_text(spec, encoding="utf-8")
    contract = compile_project(str(spec_path), str(tmp_path))
    assert any(route.get("upload", {}).get("field_name") == "photo"
               for route in contract["routes"])
    # The CONTRACT must see the upload, otherwise `monl update` would answer
    # "no interface change" leaving a whole screen to write — the blind spot
    # that recurred EIGHT times (points 88 to 116).
    signature = _contract_signature(contract)
    assert "upload of Expense.photo" in signature[6]
    # This template has neither a closed status nor a timestamp: no list
    # capability can be derived, and requiring one here would make the witness
    # pass for a proof of filtering. It is tested where it exists, below.
    assert not any(k.startswith("list capabilities of ") for k in signature[6])


def test_the_contract_sees_the_derived_filter_and_sort(tmp_path):
    """The delta blind spot, for the ninth time (points 88 to 116).

    A route gaining a filter or a sort changes what an interface must draw — a
    dropdown, a clickable column header. If `_contract_signature` does not see
    them, `monl update` answers "no interface change" leaving the screen to redo.
    """
    index = next(i for i, t in enumerate(TEMPLATES, 1)
                 if t["name"] == "Online shop")
    spec = _run_template(index, "o", True)
    spec_path = tmp_path / "spec.ml"
    spec_path.write_text(spec, encoding="utf-8")
    contract = compile_project(str(spec_path), str(tmp_path))
    signature = _contract_signature(contract)
    listes = [k for k in signature[6] if k.startswith("list capabilities of ")]
    assert listes, "the contract carries no list capability"

    # COUNTER-PROOF: removing the sort rule must CHANGE the signature. A first
    # version compared the modified spec with the original spec — it therefore
    # measured nothing of the signature, and a `replace` not finding its target
    # turned it green. We compile BOTH and compare what the contract carries.
    ligne_de_tri = "rule Order.Read sort creeLe"
    assert ligne_de_tri in spec, "the derived rule changed shape"
    ampute = spec.replace(ligne_de_tri + "\n", "")
    assert ampute != spec
    autre = tmp_path / "ampute"
    autre.mkdir()
    (autre / "spec.ml").write_text(ampute, encoding="utf-8")
    signature_amputee = _contract_signature(
        compile_project(str(autre / "spec.ml"), str(autre)))
    assert signature_amputee[6] != signature[6], (
        "the contract does not follow the sort: monl update would say \"no "
        "interface change\" leaving a screen to redo")


def test_a_public_listing_never_gets_an_upload(tmp_path):
    """Counter-proof of the decision above, on the template that motivated it.

    If an upload reappeared on "Classified ads", it would be private by
    construction — hence invisible to buyers. This witness guards the product
    choice, not only the intent written in a comment.
    """
    index = next(i for i, t in enumerate(TEMPLATES, 1)
                 if t["name"] == "Classified ads")
    spec = _run_template(index, "o", True)
    assert "ListingPhoto" not in spec
    entites = {n for n, _ in re.findall(r"^entity (\w+)()$", spec, re.M)}
    assert "Listing" in entites
    for ligne in spec.splitlines():
        if " upload max " in ligne:
            assert "Listing." not in ligne, ligne


def test_the_upload_question_only_targets_private_rows():
    prompts = []
    dialogue = GuidedDialogue(
        ask=lambda prompt: (prompts.append(prompt), "0")[1])
    entities = {
        "Public": [("title", "String")],
        "Private": [("title", "String")],
    }
    rules = dialogue._ask_uploads(
        entities, ["Public"], {"Public": "User", "Private": "User"})
    assert len(prompts) == 1
    assert "Private" in prompts[0]
    assert "Public" not in prompts[0]
    assert rules == []
    assert entities["Public"] == [("title", "String")]


def test_forcing_a_public_upload_makes_the_compiler_fail():
    """Counter-proof: bypassing the eligibility filter must be refused."""
    dialogue = GuidedDialogue(ask=lambda _prompt: "1")
    entities = {
        "User": [("name", "String")],
        "Public": [("title", "String")],
    }
    rules = dialogue._ask_uploads(entities, [], {"Public": "User"})
    spec = dialogue._emit_spec(
        "PublicUpload", "contre-épreuve", entities,
        [("User", "hasMany", "Public")], ["User"],
        {"User": ["User"], "Public": ["User"]},
        {"User": set(), "Public": set()}, ["Public"], [],
        {"Public": "User"}, False, False, self_register="User",
        extra_rules=rules)
    with pytest.raises(ASTValidationError, match="cannot be public"):
        MonlAST(parse_monl_string(spec)).validate_and_audit()


def test_forum_likes_via_increments():
    spec = _run_template(5, "o", want_seed=True)   # Forum / social network
    assert "rule Like.Create increments Post.likes by 1" in spec
    assert "relation Post hasMany Like" in spec


def test_public_when_templates_declare_the_supervisor():
    """A moderator must keep access to hidden posts."""
    table = [(2, "Article.Read"), (5, "Post.Read")]
    noms = ["blog", "forum"]

    def cas(index, reference):
        spec = _run_template(index, "n", want_seed=False)
        assert f"rule {reference} sharedBy Moderator" in spec

    check_each_case(table, cas, ids=noms)


def test_custom_entity_on_top_of_the_template():
    # Portfolio + custom "Testimonial" entity publicly readable.
    answers = iter([
        "1", "StudioPerso", "Un portfolio avec témoignages.",
        "n",                 # single follow-up question refused (categories)
        "o",                 # custom entity?
        "Testimonial", "author", "1", "quote", "2", "",
        "o",                 # readable without an account
        "n",                 # no other custom entity
        "1",                 # open registration: 1st offered role
        "0",                 # account identifier: none (point 138)
        "o",                 # seeds
        "n",                 # generic images (point 59)
        "o",                 # brief
        "lire les témoignages", "1", "2",   # intention visuelle (point 53)
        "", "",                             # portfolio sections skipped (point 61)
        "n",                                # no extra section (point 55)
        "", "", "", "", "",                 # footer: no link
        "n",                                # no other link (brick 30)
    ])
    spec = GuidedDialogue(ask=lambda p: next(answers)).run()
    assert "entity Testimonial" in spec
    assert "rule Testimonial.Read public" in spec
    MonlAST(parse_monl_string(spec)).validate_and_audit()


def test_catalog_never_mutated_between_two_runs():
    """The deepcopy protects the catalog: two runs of the same template with
    different answers must not contaminate each other."""
    spec_oui = _run_template(3, "o", want_seed=True)
    spec_non = _run_template(3, "n", want_seed=True)
    # The category stays optional (stock has become standard): it is therefore
    # what distinguishes an "all yes" run from an "all no" one.
    assert "category: String" in spec_oui
    assert "category: String" not in spec_non, "the catalog was mutated!"


# ---- Elements that became standard (point 60) ----

def test_standard_elements_are_no_longer_questions():
    """Backed by research (point 60): these elements appear in public surveys of
    essentials for their category. Asking for them put on the user a choice that
    is not one, and produced by default applications missing the obvious."""
    acquis = {
        1: ["entity Message"],                          # contact d'un portfolio
        2: ["author: String", "publishedOn: String"],    # signature et date
        3: ["stock: Integer"],                           # product availability
        4: ["priority: String", "dueDate: String"],      # carte kanban
        6: ["location: String", "entity Inquiry"],       # lieu + contact vendeur
        7: ["description: Text"],                        # service described
    }
    for index, attendus in acquis.items():
        spec = _run_template(index, "n", want_seed=False)   # EVERYTHING refused
        for attendu in attendus:
            assert attendu in spec, (
                f"template {index} ({TEMPLATES[index - 1]['name']}): \"{attendu}\" "
                f"should be standard, it is missing when everything is refused")


def test_editorial_sections_are_asked_not_offered():
    """Point 61: on a template carrying standard sections, the dialogue no longer
    asks WHETHER some are needed — it asks for their text, section by section,
    naming it. This test reads the prompts really asked."""
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
            f"the \"{section['title']}\" section was never asked")
    assert not any("Ajouter du texte de présentation" in p for p in poses), (
        "the old y/n question remains while the template has sections")
    assert 'section "About": "Photographe à Lyon depuis 2015."' in spec
    assert 'section "Services": "Reportage et portrait."' in spec
    MonlAST(parse_monl_string(spec)).validate_and_audit()


def test_a_section_left_empty_is_simply_absent():
    answers = iter(["1", "AppTest", "Un portfolio.", "n", "n", "1", "0", "o", "n", "o",
                    "consulter", "1", "2",
                    "", "Reportage et portrait.", "", "n",
                    "", "", "", "", "", "n"])
    spec = GuidedDialogue(ask=lambda p: next(answers)).run()
    assert "À propos" not in spec
    assert 'section "Services": "Reportage et portrait."' in spec


def test_an_internal_tool_gets_no_imposed_section():
    """Kanban, inventory, expenses: no source gives an expected section for a
    tool without visitors. The dialogue therefore falls back on the generic offer
    rather than inventing an "about"."""
    for nom in ("Task management", "Inventory / stock management",
                "Personal expense tracking"):
        tpl = next(t for t in TEMPLATES if t["name"] == nom)
        assert tpl["sections"] == [], nom


def test_the_dialogue_was_indeed_lightened():
    """The number of follow-up questions went from 16 to 8. This test pins the
    gain: adding a question back requires justifying it is not a standard of its
    category."""
    total = sum(len(t["followups"]) for t in TEMPLATES)
    assert total == 6, f"{total} questions de suivi (6 attendues)"
    # Templates whose every element is standard no longer ask any.
    sans_question = [t["name"] for t in TEMPLATES if not t["followups"]]
    assert "Task management" in sans_question
    assert "Classified ads" in sans_question
    assert "Appointment booking" in sans_question


def test_the_dialogue_can_produce_a_full_cart():
    """POINT 86: the dialogue produced point 77's SINGLE-ITEM form — an order with
    a single item — while the compiler can make a cart since point 82. Four bricks
    were out of reach of whoever does not write the spec by hand: `sumOf`,
    transitive ownership, `min` and stock counting. A capability the dialogue does
    not express does not exist for these users — it is the very argument that
    gave birth to the `payable` question at point 75.

    This test holds the whole chain: without it, we would fall back to a one-item
    shop, or worse to an amount the buyer writes."""
    index = next(i for i, t in enumerate(TEMPLATES, 1) if t["name"] == "Online shop")
    spec = _run_template(index, "o", want_seed=True)
    regles = [li for li in spec.splitlines() if li.startswith("rule ")]

    assert "entity LigneOrder" in spec
    # TRANSITIVE ownership: the line belongs to whoever owns its order.
    assert "rule LigneOrder.Read ownedBy Order" in regles
    # The subtotal is CALCULATED, the total is the SUM, and it is what gets
    # charged.
    assert "rule LigneOrder.sousTotal derivedFrom Product.price by quantite" in regles
    assert "rule Order.total sumOf LigneOrder.sousTotal" in regles
    assert "rule Order.total payable" in regles
    # Stock: a DECLARED floor, and the counting it arms.
    assert "rule Product.stock min 0" in regles
    assert "rule LigneOrder.Create decrements Product.stock by quantite" in regles
    # No server-calculated field is declared "required": the contract would say
    # both "to fill" and "do not send".
    assert "rule Order.total required" not in regles

    normalized = MonlAST(parse_monl_string(spec)).validate_and_audit()
    assert normalized["security"]["aggregated_fields"]
    assert normalized["security"]["transitive_ownership"]


def test_the_dialogue_can_still_produce_a_simple_order():
    """The witness of the test above: answering "no" to the cart must return the
    single-item form, not a broken spec."""
    index = next(i for i, t in enumerate(TEMPLATES, 1) if t["name"] == "Online shop")
    tpl = TEMPLATES[index - 1]
    answers = [str(index), "AppTest", "Une boutique."]
    answers += ["n"] * len(tpl["followups"])
    answers += ["n", "1"]                     # no custom entity; open registration
    answers += ["0"]                          # account identifier: none (point 138)
    answers += ["0"]                          # no upload for Order
    answers += ["o"]                          # encaisser un paiement
    candidats = _payable_fields(tpl)
    if len(candidats) > 1:
        answers += ["1"]
    answers += ["n"]                          # PAS de panier
    _montant, source, prix = candidats[0]
    if [f for f, t in tpl["entities"][source]["fields"] if t == "Integer" and f != prix]:
        answers += ["n"]                      # no stock counting
    answers += ["n"]                          # no seed
    answers += ["n"]                          # no brief
    answers += ["n"]                          # no extra section
    it = iter(answers)
    spec = GuidedDialogue(ask=lambda p: next(it)).run()
    assert "entity LigneOrder" not in spec
    assert "rule Order.total derivedFrom Product.price by quantite" in spec
    MonlAST(parse_monl_string(spec)).validate_and_audit()


class _Arret(Exception):
    """Stop the engine at its first question, without answering it."""


# ─────── POINT 171: "will visitors have an account?", DERIVED ───────

def test_the_account_line_is_derived_not_hand_written():
    """An UNKNOWN template must get its line without it having been written.

    It is the counter-proof, given the very day the witness is written (point
    167bis): a table indexed by template name would turn these two assertions red,
    since "ModeleInvente" would not be in it. A hand-written list silently stops
    bounding at the first addition — point 146.
    """
    avec_role = {
        "name": "ModeleInvente",
        "actors": ["Patron", "Visiteur"],
        "entities": {
            "Fiche": {"manager": "Patron", "owned": False},
            "Demande": {"manager": "Visiteur", "owned": True},
        },
    }
    sans_role = {
        "name": "AutreModeleInvente",
        "actors": ["Patron"],
        "entities": {"Fiche": {"manager": "Patron", "owned": False}},
    }
    assert GuidedDialogue._ligne_de_compte(avec_role) == "self-registration: Visiteur"
    assert (GuidedDialogue._ligne_de_compte(sans_role)
            == "accounts created by the administrator")


def test_each_catalog_template_says_whether_one_registers():
    """No template is chosen without knowing what it implies."""
    formes = 0
    for tpl in TEMPLATES:
        ligne = GuidedDialogue._ligne_de_compte(tpl)
        assert (ligne.startswith("self-registration: ")
                or ligne == "accounts created by the administrator"), (tpl["name"], ligne)
        formes += ligne.startswith("self-registration: ")
    # BOTH forms exist in the catalog: if only one came out, the witness above
    # would pass without settling anything.
    assert 0 < formes < len(TEMPLATES), formes


def test_the_account_line_reaches_the_dialogue_menu():
    """It must be SEEN by the user, and through the REAL path.

    A first version of this witness built the hints dictionary itself then
    checked its own work: it would have stayed green with a dialogue showing
    nothing. We therefore run the real engine and read what it actually put on
    its question.
    """
    dialogue = GuidedDialogue(ask=lambda _p: (_ for _ in ()).throw(_Arret()))
    with pytest.raises(_Arret):
        dialogue.run()
    aides = dialogue.derniere_question["hints"]
    assert dialogue.derniere_question["title"] == \
        "What type of application are you building?"
    assert "self-registration: Customer" in aides["Online shop"]
    assert "accounts created by the" in aides["Portfolio / showcase site"]
    # And the original help was not REPLACED by the account line.
    assert "public catalog" in aides["Online shop"]
