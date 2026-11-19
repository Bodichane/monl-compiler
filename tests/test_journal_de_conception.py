"""The contents list of `docs/design_decisions.md` must point to real headings.

The file has 140 points and its contents list is the only way to navigate
it. **Ten links pointed into the void** when this test was written: the
anchors had been typed without accents (`#132-…-mourait-au-demarrage-a-plusieurs-…`)
where the headings keep them, a heading had been reworded afterwards
("sort" became "sorti"), and another had lost the punctuation that doubled
a dash in its anchor.

None of these ten ever made anything fail: a dead link in Markdown raises
nothing, it just sends you to the top of the page. It is exactly the kind of
error CLAUDE.md forbids to let live — the one that returns green while
checking nothing. A document is kept like code (point 141).
"""

import re
import unicodedata
from pathlib import Path

JOURNAL = Path(__file__).resolve().parent.parent / "docs" / "design_decisions.md"


def ancre_github(titre):
    """The anchor GitHub makes for a section heading.

    Lowercase, punctuation removed, spaces turned into dashes — accented letters
    are KEPT, and that is where the ten links went wrong. Punctuation surrounded
    by spaces ("Brique 29 : le site") leaves two spaces, hence TWO dashes: the
    detail is not cosmetic, it separates a right link from a dead one.
    """
    texte = titre.strip().lower()
    texte = "".join(c for c in texte
                    if c.isalnum() or c in " -_"
                    or unicodedata.category(c).startswith("M"))
    return texte.replace(" ", "-")


def _titles_and_links():
    contenu = JOURNAL.read_text(encoding="utf-8")
    titres = [(m.group(1), m.group(0)[3:])
              for m in re.finditer(r"^## (\d+)\. .+$", contenu, re.M)]
    liens = re.findall(r"\[(\d+)\]\(#([^)]+)\)", contenu)
    return titres, liens


def test_each_contents_link_reaches_a_heading():
    titres, liens = _titles_and_links()
    ancres = {ancre_github(titre) for _, titre in titres}
    pendants = [f"[{num}](#{lien})" for num, lien in liens if lien not in ancres]
    assert not pendants, (
        f"{len(pendants)} lien(s) du sommaire ne mènent nulle part : {pendants}")


# Point 6 is a RESERVED duplicate of point 1, empty, kept so as not to shift
# the numbering of points 7 to 30 — referenced in the README, in CLAUDE.md and
# in code comments. Its absence from the contents list is deliberate: it has no
# content to reach. The exception is WRITTEN here rather than guessed,
# otherwise the test would merely observe it.
SANS_CONTENU = {"6"}


def test_each_journal_point_is_in_the_contents():
    """The counterpart: a point written and never listed is a point nobody
    finds. Both directions are guarded, because both mistakes exist — the
    contents list citing a vanished heading, and the heading the list forgets."""
    titres, liens = _titles_and_links()
    listes = {num for num, _ in liens}
    absents = sorted({num for num, _ in titres} - listes - SANS_CONTENU, key=int)
    assert not absents, f"points absents du sommaire : {absents}"


def test_the_anchor_rule_is_githubs():
    """The witness. Without it, a WRONG anchor algorithm would make both tests
    above green by comparing two errors with each other."""
    assert (ancre_github("137. Brique 29 : le site réclamait six fichiers")
            == "137-brique-29--le-site-réclamait-six-fichiers")
    assert (ancre_github("110. Rust évalué par un spike mesuré, et écarté")
            == "110-rust-évalué-par-un-spike-mesuré-et-écarté")
    assert ancre_github("42. L'apostrophe disparaît") == "42-lapostrophe-disparaît"


RESUME = JOURNAL.parent / "DESIGN_DECISIONS_SUMMARY.md"


def _summary_links():
    return re.findall(r"\[(\d+)\]\(design_decisions\.md#([^)]+)\)",
                      RESUME.read_text(encoding="utf-8"))


def test_the_english_summary_follows_the_journal_contents():
    """The journal stays in French; its English summary is its map.

    A map that forgets a point does not show: it simply gives a shorter page.
    The summary's links must therefore be EXACTLY those of the contents list —
    a point added to the journal without its English line fails, and so does a
    summary link that no longer targets anything (the contents list's links
    being themselves guarded by the test above).
    """
    _, liens = _titles_and_links()
    resume = _summary_links()
    assert liens, "aucun lien lu dans le sommaire : l'extracteur ne regarde plus rien"
    manquants = sorted(set(liens) - set(resume), key=lambda lien: int(lien[0]))
    orphelins = sorted(set(resume) - set(liens), key=lambda lien: int(lien[0]))
    assert not manquants, f"points du journal absents du résumé anglais : {manquants}"
    assert not orphelins, f"liens du résumé anglais hors du sommaire : {orphelins}"
