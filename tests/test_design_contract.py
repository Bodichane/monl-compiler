"""The compiler decides NOTHING about visuals (point 72).

monl computed a palette and typographic stacks, put them in the contract, and
described them at length in the brief. It was presented as a suggestion — but
a suggestion written in the authoritative document is not neutral: it steers,
and the compiler steers badly, not knowing what this particular project
should look like.

The rule is now clear: **design direction comes from the dialogue**,
formulated by the author, and travels through the brief. The compiler passes
on what it knows — structure, roles, routes, content, declared intent — and
stays silent on the rest.

Proving that a compiler FORBIDS something is easy. Proving that it STAYS
SILENT is much less so, and that is precisely what this file checks: a
silence nothing measures ends up filling again.
"""
import os
import re
import tempfile

from monl.ast_validator import MonlAST
from monl.cli import compile_project
from monl.frontend_ai import build_generation_prompt
from monl.frontend_contract import build_contract
from monl.generator import MonlSecureGenerator
from monl.parser import parse_monl_file

BASE = """app Reparation

entity Piece
    label: String

actor Client selfRegister

workflow Catalogue for Client
    Create Piece
    Read Piece
"""

AVEC_UI = BASE + """
ui Piece
    theme: atelier
    primary: label
"""

AVEC_BRIEF = BASE + """
landing
    brief: "Un atelier de réparation qui veut un registre sobre et technique."
"""

# A hard-coded color, in any form.
HEX = re.compile(r"#[0-9a-fA-F]{3,8}\b")
# The families the compiler proposed in its system stacks.
POLICES = ("Helvetica", "Arial", "Georgia", "Palatino", "Verdana", "Trebuchet",
           "Times New Roman", "Menlo", "Consolas", "SFMono", "ui-monospace")


def _contract(spec_source, workdir):
    chemin = os.path.join(workdir, "spec.ml")
    with open(chemin, "w", encoding="utf-8") as fh:
        fh.write(spec_source)
    ast = MonlAST(parse_monl_file(chemin)).validate_and_audit()
    generateur = MonlSecureGenerator(ast, output_dir=workdir)
    return build_contract(ast, generateur)


def _brief(spec_source, workdir):
    """The brief REALLY SENT to the AI, appendices included.

    POINT 139: this harness only called `_render_prompt()`. It therefore proved
    that the CONTRACT and the base prompt stay silent — not that the final prompt
    does. The design system's palette got past the check through the other pipe:
    `build_generation_prompt()` appends `DESIGN_SYSTEM.md`, `DESIGN_SPEC.md` and
    `ASSET_MANIFEST.json` through `_project_guidance()`, and presents them to the
    AI as "source of truth". Same destination, another pipe — the exact shape of
    the delta blind spot, met thirteen times.

    Measuring the final prompt is the only check worth anything: it is what the
    AI reads. The file already said so at the top — "a silence nothing measures
    ends up filling again".
    """
    chemin = os.path.join(workdir, "spec.ml")
    with open(chemin, "w", encoding="utf-8") as fh:
        fh.write(spec_source)
    # REAL compilation: `build_generation_prompt` reads project files
    # (FRONTEND_PROMPT.md, and everything `_project_guidance` appends). A
    # contract built in memory would not have them, and the check would fall
    # back into the hole it just closed.
    compile_project(chemin, workdir)
    contrat = _contract(spec_source, workdir)
    return contrat, build_generation_prompt(workdir, update_mode=False)


# ----------------------------------------- what the contract no longer says --
def test_the_contract_no_longer_carries_a_design_block():
    """The 'design' block carried palette, typefaces, radius and card style. It
    no longer exists: the contract describes what monl knows, not what it
    guessed."""
    with tempfile.TemporaryDirectory() as workdir:
        contrat = _contract(BASE, workdir)
    assert "design" not in contrat, sorted(contrat)


def test_the_contract_carries_finishing_skills_without_visual_theme():
    """Skills impose depth, not a computed palette."""
    with tempfile.TemporaryDirectory() as workdir:
        contrat, brief = _brief(BASE, workdir)
    assert contrat["design_skills"][0] == "monl-showcase"
    assert "$monl-showcase" in brief
    assert "level of depth and finish" in brief


def test_the_contract_contains_no_hard_coded_color():
    """Removing the key would not be enough if the colors came out elsewhere —
    in a note, an example, a neighboring field."""
    with tempfile.TemporaryDirectory() as workdir:
        contrat = _contract(BASE, workdir)
    trouvees = HEX.findall(str(contrat))
    assert not trouvees, f"couleurs imposées par le compilateur : {trouvees}"


def test_the_brief_prescribes_neither_color_nor_font():
    """The brief is the document the interface AI really reads. That is where
    prescription would most naturally settle back in."""
    with tempfile.TemporaryDirectory() as workdir:
        _contrat_, brief = _brief(BASE, workdir)

    couleurs = HEX.findall(brief)
    assert not couleurs, f"le brief impose des couleurs : {couleurs}"

    citees = [p for p in POLICES if p.lower() in brief.lower()]
    assert not citees, f"le brief impose des familles typographiques : {citees}"


# ------------------------------------------ what the brief must keep saying --
def test_the_brief_passes_on_the_intent_from_the_dialogue():
    """Staying silent on taste does not mean staying silent altogether: what the
    AUTHOR formulated must reach the interface AI intact. It is the only
    legitimate direction."""
    with tempfile.TemporaryDirectory() as workdir:
        contrat, brief = _brief(AVEC_BRIEF, workdir)
    assert "registre sobre et technique" in contrat["brief"]
    assert "registre sobre et technique" in brief


def test_the_brief_keeps_the_two_requirements_that_are_not_taste():
    """Contrast and autonomy are not stylistic choices: one makes the interface
    readable, the other makes it checkable by the smoke test. Confusing them with
    aesthetic prescription would make them fall with it."""
    with tempfile.TemporaryDirectory() as workdir:
        _contrat_, brief = _brief(BASE, workdir)
    assert "4.5:1" in brief and "WCAG" in brief
    assert "no remote resource" in brief


def test_the_brief_says_by_what_means_an_icon_is_possible():
    """POINT 104: the maintainer's finding — no produced site used an icon. It
    was not an AI defect: the brief forbids CDNs and said NOWHERE that inline SVG
    works. Read alone, the autonomy rule reads "no icons possible".

    Stating a MEANS is not prescribing a taste — same boundary as at point 72 for
    WCAG contrast and autonomy."""
    with tempfile.TemporaryDirectory() as workdir:
        _contrat_, brief = _brief(BASE, workdir)
    assert "SVG" in brief
    assert "allowlist" in brief or ".svg" in brief


def test_the_brief_recommends_no_icon_nor_icon_style():
    """The previous test's counter-proof, and point 72's guarantee: monl says by
    what MEANS, never whether some are needed nor which ones. Without this test,
    the line added at point 104 could drift into prescription at the first
    rewrite."""
    with tempfile.TemporaryDirectory() as workdir:
        _contrat_, brief = _brief(BASE, workdir)
    bas = brief.lower()
    # Libraries are only named to say they are OUT OF REACH.
    for interdit in ("icon style", "rounded icons", "filled icons",
                     "recommended icon set", "use icons for",
                     "add an icon"):
        assert interdit not in bas, interdit
    assert "is reachable" in bas or "reachable" in bas


def test_the_brief_says_explicitly_visuals_do_not_come_from_the_compiler():
    """A silent brief would suggest an oversight. It must state the rule,
    otherwise the interface AI will look for the direction it believes missing."""
    with tempfile.TemporaryDirectory() as workdir:
        _contrat_, brief = _brief(BASE, workdir)
    assert "does NOT come from monl" in brief


# ---------------------------------------------------- the ui block is inert --
def test_a_ui_block_stays_accepted_but_without_effect():
    """Same policy as at point 41 for 'landing mode/template': the grammar keeps
    accepting the key so as to break no existing spec, but nothing uses it any
    more. The contract must be STRICTLY identical with and without the block."""
    with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
        sans = _contract(BASE, a)
        avec = _contract(AVEC_UI, b)
    assert sans == avec, "le bloc 'ui' influence encore le contrat"


def test_two_projects_of_opposite_domains_get_the_same_silence():
    """The compiler used to choose its visual system from vocabulary (shop ->
    'market', blog -> 'editorial'). That deduction is gone: two opposite domains
    must now differ only by what they really declare."""
    boutique = BASE.replace("Piece", "Product").replace("Reparation", "Boutique")
    journal = BASE.replace("Piece", "Article").replace("Reparation", "Journal")
    with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
        c1, b1 = _brief(boutique, a)
        c2, b2 = _brief(journal, b)

    assert "design" not in c1 and "design" not in c2
    # The design direction paragraph is the SAME word for word: it no longer
    # depends on any deduction about the domain.
    extrait = "## Design direction — it does NOT come from monl"
    bloc1 = b1[b1.index(extrait):b1.index("## Non-negotiable rules")]
    bloc2 = b2[b2.index(extrait):b2.index("## Non-negotiable rules")]
    assert bloc1 == bloc2, "la direction de design dépend encore du domaine"


def test_the_touch_up_instruction_recalls_the_icon_means():
    """POINT 104, second half — found by RUNNING a touch-up, not by rereading the
    code. Point 104's line was only set on the BUILD brief; the touch-up
    instruction said "same autonomy (no CDN)" and nothing else. A touch-up like
    "make this section more readable" would therefore have hit the same wall.

    It is point 93's lesson on another object: there is only one path to the AI,
    but TWO briefs — and what is written in one does not propagate to the other."""
    from monl.cli import _write_retouche_brief
    with tempfile.TemporaryDirectory() as workdir:
        chemin = _write_retouche_brief(workdir, "la section retours est terne")
        with open(chemin, encoding="utf-8") as fh:
            texte = fh.read()
    # The brief is formatted at 79 columns: looking for a sentence as is would
    # fail at the first line break inserted in the middle.
    continu = " ".join(texte.split())
    assert "SVG" in continu
    assert "not an instruction" in continu, \
        "le rappel doit dire que c'est un MOYEN, jamais une prescription"
