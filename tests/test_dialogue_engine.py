# Tests of the guided dialogue engine (orchestrator pivot, brick 1). Following
# the project's method: the produced spec is really parsed AND validated by the
# real pipeline, never only reread.

import pytest

from monl.ast_validator import MonlAST
from monl.dialogue_engine import DialogueError, GuidedDialogue
from monl.parser import parse_monl_string

# The scenario is composed of NAMED pieces. It was cut with negative numbers
# (`[:-4]`, `[:-5]`): each question added at the end of the dialogue moved the
# cut and broke eight tests at once, without the magic number ever saying what
# it removed.
SCENARIO_PORTFOLIO_BASE = [
    "11",              # start from scratch (free dialogue)
    "StudioTest", "Un portfolio de studio créatif avec contact.",
    "Project", "title", "1", "imageUrl", "1", "year", "3", "",
    "Message", "author", "1", "content", "2", "email", "7", "",
    "",
    "o", "n",          # Project lisible public, Message non
    "2",               # public creation: Message
    "Admin", "Visitor", "",
    "1", "1",          # Admin manages both entities
    "n", "n",          # no per-record ownership
    "n", "n",          # Visitor reads nothing more
    "n",               # no relation
    "1",               # open registration: 1st offered role
    "0",               # account identifier: none (point 138)
    "o",               # seed
    "n",               # generic images (point 59)
]
LANDING_OUI = ["o"]
LANDING_NON = ["n"]
SCENARIO_PORTFOLIO_TRONC = SCENARIO_PORTFOLIO_BASE + LANDING_OUI

# Brief passed on -> the visual intent is asked (point 53): action expected
# from the visitor, register, placement of images.
INTENTION_PAR_DEFAUT = ["voir les projets et écrire", "2", "1"]
AUCUNE_SECTION = ["n"]                     # point 55
#: The footer destinations (brick 30). The number of offered entries is READ
#: from the source: freezing it here would make it diverge silently at the
#: first added entry.
AUCUN_LIEN = [""] * len(GuidedDialogue.LIENS_PROPOSES) + ["n"]

SCENARIO_PORTFOLIO = (SCENARIO_PORTFOLIO_TRONC + INTENTION_PAR_DEFAUT
                      + AUCUNE_SECTION + AUCUN_LIEN)
#: The same journey refusing the home page: neither intent, nor section, nor
#: link is then asked.
SCENARIO_SANS_LANDING = SCENARIO_PORTFOLIO_BASE + LANDING_NON


def _run(answers):
    it = iter(answers)
    return GuidedDialogue(ask=lambda p: next(it)).run()


def test_express_mode_only_asks_identity_and_description_after_the_template():
    """The recommended journey does not turn the finishing touches into a
    questionnaire.

    The iterator deliberately contains no extra answer: any new question would
    make the test fail with StopIteration.
    """
    answers = iter(["1", "StudioExpress", "Portfolio de céramique contemporaine."])
    spec = GuidedDialogue(ask=lambda p: next(answers), express=True).run()
    normalized = MonlAST(parse_monl_string(spec)).validate_and_audit()
    assert normalized["meta"]["appName"] == "StudioExpress"
    assert normalized["seeds"]
    assert "landing" in spec
    assert "express mode" in spec
    # Express mode deduces an illustration subject from the chosen template; it
    # goes into the brief, no longer into a remote URL.
    assert "The illustrations should evoke: creative-studio" in spec
    assert "loremflickr" not in spec and "picsum" not in spec


def test_express_mode_only_opens_the_unprivileged_role():
    answers = iter(["3", "BoutiqueExpress", "Boutique de mobilier français."])
    spec = GuidedDialogue(ask=lambda p: next(answers), express=True).run()
    normalized = MonlAST(parse_monl_string(spec)).validate_and_audit()
    assert normalized["security"]["self_register_actors"] == ["Customer"]
    assert "Admin selfRegister" not in spec


def test_the_interactive_menu_offers_express_before_customization():
    prompts = []
    answers = iter([
        "1", "1", "StudioExpress", "Portfolio de céramique contemporaine."
    ])

    def ask(prompt):
        prompts.append(prompt)
        return next(answers)

    spec = GuidedDialogue(ask=ask, choose_experience=True).run()
    assert "app StudioExpress" in spec
    experience = next(p for p in prompts if "experience" in p)
    assert experience.index("Quick creation") < experience.index("Detailed customization")


def test_spec_produite_compile_reellement():
    spec = _run(SCENARIO_PORTFOLIO)
    normalized = MonlAST(parse_monl_string(spec)).validate_and_audit()
    assert normalized["meta"]["appName"] == "StudioTest"
    assert set(normalized["schema"]["entities"]) == {"Project", "Message"}
    assert "Project.Read" in normalized["security"]["public"]
    assert "Message.Create" in normalized["security"]["public"]
    # A single write manager per entity -> never a collision.
    assert normalized["seeds"], "the requested seed must be present"


def test_determinism_same_answers_same_spec():
    assert _run(SCENARIO_PORTFOLIO) == _run(SCENARIO_PORTFOLIO)


def test_no_spec_names_a_remote_host():
    """Point 59 settled the RESOLUTION of demo photos (1600×900 rather than
    800×600). The question no longer arises: there is no demo photo at all any
    more.

    A monl application is autonomous and its compiler never calls outside — but
    the first page the prospect opened fetched its images from a third party, and
    therefore did not open offline nor on a metered data plan. The real photo goes
    through `monl assets add`, which checks it at compile time."""
    spec = _run(SCENARIO_PORTFOLIO)
    for hote in ("picsum", "loremflickr", "http://", "https://"):
        assert hote not in spec, f"the spec names a remote host: {hote}"


# ---- The footer destinations (brick 30) ----

def _scenario_with_links(saisies):
    """SCENARIO_PORTFOLIO with only the footer answers changed."""
    entrees = list(saisies) + [""] * len(GuidedDialogue.LIENS_PROPOSES)
    return (SCENARIO_PORTFOLIO_TRONC + INTENTION_PAR_DEFAUT + AUCUNE_SECTION
            + entrees[:len(GuidedDialogue.LIENS_PROPOSES)] + ["n"])


def test_the_dialogue_really_produces_footer_links():
    """Brick 30 had existed since point 144 and NOTHING produced it.

    Neither this dialogue nor any of the ten templates declared a single link:
    every site therefore came out with a footer without a single destination. A
    rule producing nothing is what point 85 forbids the compiler, and the ban
    holds for the dialogue writing the spec.
    """
    spec = _run(_scenario_with_links(
        ["contact@studio.fr", "+33 6 12 34 56 78", "instagram.com/studio"]))

    # Nobody types "mailto:" or "https://": the dialogue completes, and only
    # completes where there is a single reading.
    assert 'link "Email": "mailto:contact@studio.fr"' in spec
    assert 'link "Phone": "tel:+33612345678"' in spec
    assert 'link "Instagram": "https://instagram.com/studio"' in spec
    normalise = MonlAST(parse_monl_string(spec)).validate_and_audit()
    assert [lien["label"] for lien in normalise["landing"]["links"]] == [
        "Email", "Phone", "Instagram"]


def test_an_incomprehensible_address_is_skipped_and_stated():
    """Guessing an address would be worse than skipping it: the link would lead
    somewhere, and nobody would know where."""
    dits = []
    scenario = _scenario_with_links(["pas une adresse du tout"])
    it = iter(scenario)
    spec = GuidedDialogue(ask=lambda p: next(it), say=dits.append).run()

    assert "link " not in spec
    assert any("Unrecognized address" in ligne for ligne in dits), dits
    MonlAST(parse_monl_string(spec)).validate_and_audit()


def test_the_footer_is_not_asked_without_a_home_page():
    """Without a home page to write, these links would have nowhere to go — same
    rule as the visual intent and the sections."""
    spec = _run(SCENARIO_SANS_LANDING)   # must NOT raise StopIteration

    assert "link " not in spec


def test_the_illustration_subject_goes_into_the_brief_not_a_url():
    """The dialogue question KEEPS an effect — otherwise it would be a question
    without consequence, which point 85 forbids the compiler and which holds just
    as much for the dialogue writing the spec.

    The subject cannot be deduced from a free sentence in French without
    interpretation, so it is asked (point 59); what is done with it changed. It
    reaches the interface AI through the brief, the only sentence of the contract
    saying what the site is for."""
    scenario = list(SCENARIO_PORTFOLIO)
    scenario[scenario.index("n", scenario.index("o", 28))] = "o"   # precise subject
    scenario.insert(scenario.index("o", 28) + 2, "cybersecurity")
    spec = _run(scenario)
    assert "The illustrations should evoke: cybersecurity" in spec
    # ALSO written as a comment: without a `landing` block, the spec would have
    # no brief to carry it, and the human reopening the file must find what
    # they asked for.
    assert "# Illustration subject: cybersecurity" in spec
    for hote in ("picsum", "loremflickr", "http://", "https://"):
        assert hote not in spec
    MonlAST(parse_monl_string(spec)).validate_and_audit()


def test_reponse_invalide_redemandee_puis_erreur():
    # Invalid app name 3 times -> DialogueError (the engine never guesses).
    with pytest.raises(DialogueError):
        _run(["11", "9mauvais", "aussi mauvais", "toujours-mauvais"])


def test_relation_emitted_and_validated():
    answers = [
        "11",
        "TopTest", "Un classement communautaire.",
        "Entry", "name", "1", "score", "3", "",
        "Vote", "note", "1", "",
        "",
        "o", "n",      # Entry publique en lecture
        "0",           # no public creation
        "Participant", "",
        # single actor -> implicit manager, no question asked
        "n", "n",      # no per-record ownership
        "o",           # relations?
        "1",           # source Entry
        "1",           # hasMany
        "1",           # cible Vote
        "n",           # no other relation
        "1",           # open registration: 1st offered role
        "0",           # account identifier: none (point 138)
        "n", "n",      # ni seed ni landing
    ]
    spec = _run(answers)
    assert "relation Entry hasMany Vote" in spec
    MonlAST(parse_monl_string(spec)).validate_and_audit()


def test_ownership_creates_owner_entity_and_rules():
    """ownedBy: the dialogue creates the owning entity named like the actor, the
    relation providing the foreign key, and the Update/Delete rules — all
    validated by the real pipeline (pattern of exemples/03, point 5)."""
    answers = [
        "11",
        "ForumTest", "Un forum où chacun gère ses propres sujets.",
        "Topic", "title", "1", "body", "2", "",
        "",
        "n",           # Topic not publicly readable
        "0",           # no public creation
        "Member", "",
        # single actor -> implicit manager
        "o",           # per-record ownership on Topic
        # (the Member entity is created automatically -> new questions:)
        "n",           # ownership on Member itself? no
        "n",           # additional relations? no
        "1",           # open registration: 1st offered role
        "0",           # account identifier: none (point 138)
        "0",           # no upload for Topic
        "n", "n",      # ni seed ni landing
    ]
    it = iter(answers)
    spec = GuidedDialogue(ask=lambda p: next(it)).run()
    assert "entity Member" in spec and "displayName: String" in spec
    assert "relation Member hasMany Topic" in spec
    assert "rule Topic.Update ownedBy Member" in spec
    assert "rule Topic.Delete ownedBy Member" in spec
    # Owned and non-public entity: READING is reserved to the owner too,
    # otherwise any account holder would list the others' records (beta 3).
    assert "rule Topic.Read ownedBy Member" in spec
    normalized = MonlAST(parse_monl_string(spec)).validate_and_audit()
    assert normalized["security"]["ownership"] == {
        "Topic.Read": "Member", "Topic.Update": "Member", "Topic.Delete": "Member"}


def test_shared_management_emits_sharedby_without_collision():
    """sharedBy: two actors share writing — the dialogue emits one workflow per
    actor AND the sharedBy rules, the only legitimate path provided by strict rule
    no. 1 (privilege collision)."""
    answers = [
        "11",
        "ModTest", "Un blog co-géré par deux rôles.",
        "Post", "title", "1", "",
        "",
        "o",           # Post public en lecture
        "0",
        "Admin", "Moderator", "",
        "3",           # shared management (option after the 2 actors)
        "o", "o",      # Admin ET Moderator participent
        # shared management -> no ownership question
        "n", "n",      # no additional reader (already managers)
        # (a single entity: the relations question is skipped)
        "1",           # open registration: 1st offered role
        "0",           # account identifier: none (point 138)
        "n", "n",      # ni seed ni brief
    ]
    it = iter(answers)
    spec = GuidedDialogue(ask=lambda p: next(it)).run()
    assert "rule Post.Create sharedBy Admin, Moderator" in spec
    assert "workflow ManagePostByAdmin for Admin" in spec
    assert "workflow ManagePostByModerator for Moderator" in spec
    MonlAST(parse_monl_string(spec)).validate_and_audit()


# ---- The visual intent reaches the brief (point 53) ----

def _scenario_portfolio(intention):
    """SCENARIO_PORTFOLIO, with only the intent answers changed."""
    return (SCENARIO_PORTFOLIO_TRONC + list(intention)
            + AUCUNE_SECTION + AUCUN_LIEN)


def test_visual_intent_reaches_the_brief():
    """The brief passed to the UI AI must no longer boil down to the description:
    it is the only sentence of the contract saying what the site is for, facing
    routes described down to the field. An interface without intent falls back on
    the lowest common denominator (point 53)."""
    spec = _run(_scenario_portfolio(["parcourir la galerie", "4", "1"]))
    # The `landing` block's DECLARED line, not the header comment: "# Project
    # brief:" contains "brief:" too.
    ligne = next(x for x in spec.splitlines() if x.lstrip().startswith("brief:"))
    assert "parcourir la galerie" in ligne
    assert "bold, graphic register" in ligne        # registre n° 4
    assert "the images carry the site" in ligne     # imagerie n° 1
    # The original description stays at the top of the brief.
    assert ligne.index("Un portfolio") < ligne.index("parcourir la galerie")
    MonlAST(parse_monl_string(spec)).validate_and_audit()


def test_different_registers_give_different_briefs():
    """Otherwise the menus would be decorative."""
    a = _run(_scenario_portfolio(["voir", "1", "3"]))
    b = _run(_scenario_portfolio(["voir", "3", "3"]))
    assert a != b


def test_without_brief_no_intent_question():
    """The intent is only asked if a brief goes to the AI: otherwise these
    answers would serve nobody, and the dialogue would waste three questions of
    the user's."""
    spec = _run(SCENARIO_SANS_LANDING)   # must NOT raise StopIteration
    assert "landing" not in spec
    MonlAST(parse_monl_string(spec)).validate_and_audit()


# ---- Static editorial content (point 55) ----

def test_editorial_sections_emitted_and_validated():
    """The only content of the contract that is not data. Without it, an "about"
    page has no entity, no field, no route to be born from — the AI literally has
    nothing to build it with."""
    scenario = SCENARIO_PORTFOLIO_TRONC + INTENTION_PAR_DEFAUT + [
        # Point 64: each body ends with an empty line — here a single paragraph
        # per section.
        "o", "À propos", "Studio fondé en 2015 à Lyon.", "",
        "o", "Méthode", "Repérage, prise de vue, retouche.", "",
        "n",
    ] + AUCUN_LIEN
    spec = _run(scenario)
    assert 'section "À propos": "Studio fondé en 2015 à Lyon."' in spec
    assert 'section "Méthode": "Repérage, prise de vue, retouche."' in spec
    normalized = MonlAST(parse_monl_string(spec)).validate_and_audit()
    titres = [s["title"] for s in normalized["landing"]["sections"]]
    assert titres == ["À propos", "Méthode"], "the entry order must be kept"


def test_sections_refused_without_brief():
    """Same rule as the visual intent: without a home page to write, these texts
    would have nowhere to go."""
    spec = _run(SCENARIO_SANS_LANDING)
    assert "section " not in spec and "landing" not in spec


def test_a_multi_paragraph_text_survives_to_the_contract():
    """POINT 64: an "about" pasted from a word processor arrived flattened —
    paragraphs glued back without even a space, and the interface AI received a
    wall of text. The grammar still forbids line breaks: the dialogue therefore
    asks for paragraphs one by one, and the contract restores them."""
    import tempfile

    from monl.frontend_contract import build_contract
    from monl.generator import MonlSecureGenerator

    scenario = SCENARIO_PORTFOLIO_TRONC + INTENTION_PAR_DEFAUT + [
        "o", "À propos",
        "Photographe basée à Lyon depuis 2015.",
        "Mon travail mêle rigueur technique et composition.",
        "Chaque projet traduit une idée en image forte.",
        "",                       # end of paragraphs
        "n",                      # no other section
    ] + AUCUN_LIEN
    spec = _run(scenario)
    # In the spec: a single line, marked — it is what the grammar can carry.
    ligne = next(x for x in spec.splitlines() if x.strip().startswith('section'))
    assert ligne.count("¶") == 2, ligne
    assert "\n" not in ligne.strip("\n")

    normalized = MonlAST(parse_monl_string(spec)).validate_and_audit()
    # output_dir: without it, the theme seed lands in the repository.
    with tempfile.TemporaryDirectory() as sortie:
        contrat = build_contract(
            normalized, MonlSecureGenerator(normalized, output_dir=sortie))
    corps = contrat["sections"][0]["body"]
    assert corps.split("\n\n") == [
        "Photographe basée à Lyon depuis 2015.",
        "Mon travail mêle rigueur technique et composition.",
        "Chaque projet traduit une idée en image forte.",
    ], corps
    assert "¶" not in corps, "the separator must never reach the AI"


def test_a_text_without_marker_goes_through_unchanged():
    """A hand-written spec, or one from before point 64, must read exactly as
    before — the marker is an addition, not a format."""
    from monl.frontend_contract import paragraphes
    assert paragraphes("Un seul paragraphe.") == "Un seul paragraphe."
