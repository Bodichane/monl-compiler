"""The footer has destinations, and two layers say the same thing.

Brick 30 (point 144) allowed DECLARING links; nothing produced them. Neither
the guided dialogue, nor any of the ten templates, nor the platform console
wrote a single one — so every site came out with a footer without a single
destination, which the maintainer saw by eye before any measurement said so.
A rule that produces nothing is what point 85 forbids the compiler; the ban
holds for whatever writes the spec.
"""

import json
import shutil
import subprocess

import pytest

from monl.dialogue_engine import adresse_de_lien
from monl_platform.app import _liens_de_pied
from monl_platform.app_templates import materialize_template
from monl_platform.console import CONSOLE_HTML

#: The inputs that decide. Each is a way someone really writes an address —
#: the last column is what a browser must receive.
CAS = [
    ("contact@atelier.fr", "mailto:contact@atelier.fr"),
    ("instagram.com/atelier", "https://instagram.com/atelier"),
    ("www.exemple.fr", "https://www.exemple.fr"),
    ("https://x.com/atelier", "https://x.com/atelier"),
    ("mailto:a@b.fr", "mailto:a@b.fr"),
    ("tel:+33612345678", "tel:+33612345678"),
    # The number is written WITH spaces: it is the only value of this list that
    # legitimately contains some.
    ("+33 6 12 34 56 78", "tel:+33612345678"),
    ("06 12 34 56 78", "tel:0612345678"),
    ("06.12.34.56.78", "tel:06.12.34.56.78"),
    # What has only one reading is completed; the rest is DISCARDED, never
    # guessed — a link leading elsewhere is worse than a missing link.
    ("pas une adresse", None),
    ("bonjour", None),
    ("", None),
    ("   ", None),
]


def test_an_incomplete_address_is_completed_never_guessed():
    for saisie, attendu in CAS:
        assert adresse_de_lien(saisie) == attendu, saisie


def _fonction_js(nom):
    """Extracts a function from the console script, as served."""
    debut = CONSOLE_HTML.index(f"function {nom}(")
    marqueur = "\n}\n"
    fin = CONSOLE_HTML.index(marqueur, debut) + len(marqueur)
    return CONSOLE_HTML[debut:fin]


def test_console_and_server_complete_identically():
    """Two implementations of the same rule end up diverging.

    The browser's decides what the user sees accepted; the server's decides what
    reaches the spec. If they drift apart, the console announces a saved link the
    server silently discards — a defect neither can see alone.
    """
    node = shutil.which("node")
    if not node:
        pytest.skip("node missing: the two layers cannot be compared")

    script = (
        _fonction_js("adresseDeLien")
        + "\nconst cas = " + json.dumps([saisie for saisie, _ in CAS]) + ";"
        + "\nconsole.log(JSON.stringify(cas.map(function (s) {"
        + " return adresseDeLien(s); })));"
    )
    fini = subprocess.run([node, "-e", script], capture_output=True, text=True,
                          timeout=60)
    assert fini.returncode == 0, fini.stderr
    cote_navigateur = json.loads(fini.stdout.strip())

    assert cote_navigateur == [attendu for _, attendu in CAS]


def test_the_server_discards_what_it_does_not_understand():
    liens = _liens_de_pied([
        {"label": "Instagram", "url": "instagram.com/atelier"},
        {"label": "Bruit", "url": "pas une adresse"},
        {"label": "", "url": "https://exemple.fr"},
        {"label": "instagram", "url": "https://autre.fr"},   # duplicate label
        {"label": 'Guillemet"', "url": "https://exemple.fr"},
        "pas un objet",
    ])

    assert liens == [{"label": "Instagram", "url": "https://instagram.com/atelier"}]


def test_a_platform_project_carries_its_links_to_the_spec():
    """End to end: what the console sends must reach the DSL."""
    spec = materialize_template(
        1, app_name="AtelierTest", description="Un atelier de céramique.",
        links=_liens_de_pied([
            {"label": "Courriel", "url": "contact@atelier.fr"},
            {"label": "Instagram", "url": "instagram.com/atelier"},
        ]),
    )

    assert 'link "Courriel": "mailto:contact@atelier.fr"' in spec
    assert 'link "Instagram": "https://instagram.com/atelier"' in spec


def test_without_links_the_spec_stays_exactly_as_before():
    """Counter-proof: the question must change nothing when unanswered —
    otherwise every existing project would see its spec move."""
    spec = materialize_template(1, app_name="AtelierTest",
                                description="Un atelier de céramique.")

    assert "link " not in spec
