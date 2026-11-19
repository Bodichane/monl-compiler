"""The contract's constants, and the two tools the whole package borrows.

`paragraphes()` translates back the `¶` separator (point 64): the grammar
forbids line breaks in a STRING_LITERAL, and that is how a `section`
carries several paragraphs without a new brick."""

from ..artifacts import DOCS_DIR
from ..ir import CompilationPlans

CONTRACT_VERSION = 9  # 2: same-origin base_url (51) · 3: roles + archetypes (54)
#                     # 4: declared payment tracking fields (76)
#                     # 5: declared assets — logo, favicon, folder (83)
#                     # 6: declared post-payment write route (113)
#                     # 7: phone calling code passed to the frontend (95)
#                     # 8: selected density design skills
#                     # 9: business rules — publicWhen and oncePer (116)
# The numbers in parentheses refer to docs/design_decisions.md. Those of
# versions 6 and 7 used to designate points 107-109, which are about something
# else (typed SQL emission, access control, Rust spike): corrected here rather
# than left to mislead — this file cites these numbers so they get followed.

# FIELD ROLES AND ARCHETYPES (point 54) — restoring, in the CONTRACT, what
# point 35 derived for the frontend monl used to generate itself, and which the
# pivot (point 41) removed without carrying it over. Without these roles, a
# field is just a `{name, type}`: the UI AI has to guess again from the names
# which one is the title, which one the cover image, whereas monl can deduce it
# deterministically. Same philosophy as for themes: derived from the spec,
# never declared in the business DSL.
MEDIA_HINTS = ("image", "photo", "cover", "couverture", "avatar", "picture",
               "thumbnail", "vignette", "banner", "banniere", "illustration",
               "visuel", "url")

CATEGORY_HINTS = ("category", "categorie", "genre", "kind", "tag", "rubrique",
                  "status", "statut", "etat", "type")

# Availability is an essential of a product page, on a par with the price
# (point 60): relegating it to "meta" made it treated as a detail.
STOCK_HINTS = ("stock", "quantity", "quantite", "inventaire", "disponib",
               "available", "restant")

CONTRACT_FILENAME = "frontend_contract.json"

#: The brief is READ: it goes into `docs/`. The contract, however, stays at the
#: root — it is the project's MACHINE interface, the one a tool opens without
#: knowing anything about the tree.
PROMPT_FILENAME = f"{DOCS_DIR}/FRONTEND_PROMPT.md"

#: The project memory is called AGENTS.md and not CLAUDE.md: the frontend can
#: be written by claude-code, codex or gemini (point 69), and naming the file
#: after only one of them makes it a file the others do not read.
AGENTS_FILENAME = "AGENTS.md"

README_FILENAME = "README.md"

FRONTEND_ARTIFACTS = (CONTRACT_FILENAME, PROMPT_FILENAME,
                      AGENTS_FILENAME, README_FILENAME)

def paragraphs(text):
    """Translates the spec's paragraph separator back into real breaks (point
    64). The grammar forbids line breaks in a STRING_LITERAL: a three-paragraph
    "about" therefore travels on a single, marked line. The contract is the
    first place where this writing constraint stops existing — and the
    interface AI receives structured text instead of an unbroken block.

    Without a marker, the text comes out as is: a contract written before
    point 64, or a hand-written spec, reads exactly as before."""
    return "\n\n".join(p.strip() for p in text.split("¶") if p.strip())

def _coerce_plans(source) -> CompilationPlans:
    """Library compatibility for old calls with a generator."""
    if isinstance(source, CompilationPlans):
        return source
    return source.build_compilation_plans()
