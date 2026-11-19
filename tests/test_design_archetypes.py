"""Every branch of the archetype classification, tested.

`infer_design_profile` decides the BRIEF sent to the interface AI: the page
pattern, the expected screens, the UI patterns kept. A wrong classification
breaks nothing — it simply produces the wrong site, which is costlier to
notice and longer to fix.

Three of the five branches were exercised by no test: `commerce`,
`operations` and `editorial`. The fourth — deduplication of section anchors —
only fires on two HOMONYMOUS sections, a case no spec of the repository
produces, and which without it would give two identical anchors in one page.
"""

from monl.design_system import _declared_section_markers, infer_design_profile


def _contrat(**extra):
    base = {"entities": {}, "routes": [], "design_skills": []}
    base.update(extra)
    return base


def test_booking_takes_precedence_over_price():
    """A bookable service carries a price: by archetype alone it looks like a
    shop. The booking signal must win, otherwise a cart is drawn where a
    calendar is needed."""
    profil = infer_design_profile(_contrat(
        entities={"Creneau": {"archetype": "shop"}},
        sections=[{"title": "Réserver un créneau", "body": "Prenez rendez-vous."}]))
    assert profil["kind"] == "service"
    assert "availability" in profil["pattern"]


def test_a_payment_action_is_enough_to_make_commerce():
    profil = infer_design_profile(_contrat(routes=[{"action": "Pay"}]))
    assert profil["kind"] == "commerce"
    assert "Catalog" in profil["pages"]
    assert "Cart or summary" in profil["pages"]


def test_the_operations_skill_gives_a_workspace():
    profil = infer_design_profile(_contrat(design_skills=["monl-operations"]))
    assert profil["kind"] == "operations"
    assert "Workspace per role" in profil["pages"]


def test_sections_without_other_signal_give_an_editorial_site():
    profil = infer_design_profile(_contrat(
        sections=[{"title": "Notre atelier", "body": "Depuis 2019."}]))
    assert profil["kind"] == "editorial"
    assert "Narrative hero" in profil["pattern"]


def test_without_any_signal_the_profile_stays_generic():
    """The witness: a classification that put everything somewhere would
    classify nothing."""
    profil = infer_design_profile(_contrat())
    assert profil["kind"] == "generic"


def test_a_faq_adds_its_screen():
    profil = infer_design_profile(_contrat(faq=[{"question": "Où ?", "answer": "Ici."}]))
    assert "Structured FAQ" in profil["pages"]


def test_the_word_service_is_enough_when_nothing_else_speaks():
    """The second door to `service`, the one that only opens on the word itself:
    a contract saying "service" without ever saying "book", and with no
    section, no FAQ, no payment."""
    # The analyzed text comes from the NAME and the brief, not the routes: a
    # classification reading route summaries would change its verdict at the
    # slightest API rewording.
    profil = infer_design_profile(_contrat(app="Service de dépannage à domicile"))
    assert profil["kind"] == "service"


def test_two_homonymous_sections_do_not_share_their_anchor():
    """Two identical anchors in a page mean one internal link out of two leads
    nowhere — and nothing reports it. The case only happens with HOMONYMOUS
    titles, which no spec of the repository carries: so it is tested here, and
    nowhere else."""
    marqueurs = _declared_section_markers({"sections": [
        {"title": "Nos ateliers"},
        {"title": "Nos ateliers"},
        {"title": "Nos ateliers"},
    ]})
    assert len(marqueurs) == len(set(marqueurs)) == 3
    assert marqueurs[0] != marqueurs[1] != marqueurs[2]


def test_a_section_without_title_stays_anchorable():
    """The title is optional in the grammar; an empty anchor would break
    navigation silently."""
    marqueurs = _declared_section_markers({"sections": [{}, {}]})
    assert len(marqueurs) == len(set(marqueurs)) == 2
    assert all('data-monl-section="' in m for m in marqueurs)


def test_a_title_already_like_a_derived_anchor_does_not_steal_it():
    """The case plain numbering is not enough to settle.

    Two "Nos ateliers" sections give `nos-ateliers` then `nos-ateliers-2`. But
    if a THIRD section is already titled "Nos ateliers 2", its natural anchor is
    exactly the one the second was about to get. Without the loop that raises
    the rank, two different sections share an anchor — and the link leads to
    the wrong one.
    """
    marqueurs = _declared_section_markers({"sections": [
        {"title": "Nos ateliers"},
        {"title": "Nos ateliers 2"},
        {"title": "Nos ateliers"},
    ]})
    assert len(marqueurs) == len(set(marqueurs)) == 3
