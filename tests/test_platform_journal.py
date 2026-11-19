"""The log must not be able to write a secret.

The platform holds passwords, session tokens and API keys. A log is precisely
where these values leak: one logs "for debugging", the line goes into the
host's logs, and stays there. These tests check that masking holds by the
field NAME AND by the value's SHAPE — because relying on the name alone lets
through `identifiant=monl_AbC…`, which announces nothing.
"""

import logging

from monl_platform import journal as J


def test_a_field_announcing_a_secret_is_masked():
    ligne = J.evenement("essai", password="hunter2", mot_de_passe="hunter2",
                        session_token="abc", api_key_secret="xyz")
    assert "hunter2" not in ligne
    assert "abc" not in ligne and "xyz" not in ligne
    assert ligne.count(J.MASQUE) == 4


def test_an_api_key_is_masked_even_under_a_harmless_name():
    """The case name-only masking lets through."""
    cle = "monl_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6"
    ligne = J.evenement("essai", identifiant=cle, valeur=cle)
    assert cle not in ligne
    assert ligne == f"essai identifiant={J.MASQUE} valeur={J.MASQUE}"


def test_a_high_entropy_token_is_masked_under_any_name():
    jeton = "T3uc3xWnqbNYoAMPOZ8L5VAC0C0wS7mYoT3P1znKtgM"
    assert J.MASQUE in J.evenement("essai", ref=jeton)


def test_a_token_in_a_logged_url_is_masked():
    jeton = "monl_A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6"
    url = f"GET https://client.example/reset?token={jeton}&next=/compte"
    ligne = J.masquer_texte(url)
    assert jeton not in ligne
    assert "token=[masked]" in ligne
    assert "next=/compte" in ligne
    assert jeton not in J.evenement("sortie_site", url=url)
    assert "token=[masked]" in J.masquer_texte("token=jeton-court")
    assert "Bearer [masked]" in J.masquer_texte("Authorization: Bearer court")


def test_what_is_not_a_secret_passes_as_is():
    """The witness: a masking that masked everything would be unusable."""
    ligne = J.evenement("compilation", projet="a3f9", routes=17, duree_ms=812)
    assert ligne == "compilation projet=a3f9 routes=17 duree_ms=812"


def test_a_field_can_be_called_nom_without_hitting_the_parameter():
    """The most natural field name in French. Before the parameter was
    positional-only, this raised a TypeError — so logging broke exactly where it
    was needed."""
    assert J.evenement("projet", nom="Boutique") == "projet nom=Boutique"


def test_a_multiline_value_cannot_forge_a_fake_line():
    """Without it, a project name containing a line break writes what it wants
    into the log — a forged entry reads like a real one."""
    ligne = J.evenement("projet", nom="innocent\n2026-01-01 ERROR faux evenement")
    assert "\n" not in ligne
    assert ligne.startswith('projet nom="innocent 2026-01-01 ERROR faux evenement"')


def test_the_log_really_writes_to_its_stream(caplog):
    """`evenement` returns a string; it still has to be EMITTED."""
    J.configurer()
    with caplog.at_level(logging.INFO, logger=J.NOM):
        J.journal.propagate = True          # caplog listens to the root
        try:
            J.evenement("demarrage", workspace="/data")
        finally:
            J.journal.propagate = False
    assert "demarrage workspace=/data" in caplog.text


def test_levels_tell_incidents_from_routine():
    assert J.anomalie("debit_depasse", compte="u1")
    assert J.panne("compilation_impossible", projet="p1")


def test_an_account_identifier_stays_readable_hence_cross_checkable():
    """The defect found by starting the server, not by rereading the code.

    An account identifier is a 32-character `uuid4().hex`: the high-entropy rule
    swallowed it, and EVERY line said `compte=[masqué]`. A log that masks the
    account no longer says whether two hundred refused logins come from one
    account or from two hundred.

    The remedy does NOT touch masking — what is passed to it changes.
    """
    identifiant = "a3f91b2c4d5e6f708192a3b4c5d6e7f8"
    assert len(identifiant) == 32

    # Passed whole, it IS masked — and that is right: the rule cannot tell an
    # identifier from a token.
    assert J.MASQUE in J.evenement("connexion", compte=identifiant)

    # Shortened, it goes through and stays the same from one line to the next.
    court = J.court(identifiant)
    assert court == "a3f91b2c"
    premiere = J.evenement("connexion", compte=court)
    seconde = J.evenement("cle_creee", compte=court, cle=J.court("ff00"))
    assert J.MASQUE not in premiere and J.MASQUE not in seconde
    assert premiere == "connexion compte=a3f91b2c"
    assert "compte=a3f91b2c" in seconde


def test_application_events_do_not_mask_the_account():
    """The guarantee at the real call site: `app.py` must pass a short
    identifier, not only `journal.py` must know how to."""
    import re
    from pathlib import Path

    source = Path(__file__).resolve().parent.parent / "src" / "monl_platform" / "app.py"
    texte = source.read_text(encoding="utf-8")
    nus = re.findall(r'(?:compte|cle|projet)=(?!court\()(?:user\["id"\]|'
                     r'cle\["id"\]|key_id|manifest\["id"\])', texte)
    assert not nus, f"identifiers logged without `court()`: {nus}"
