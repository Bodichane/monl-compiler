"""What the whole dialogue reads, and which reads nothing back.

`adresse_de_lien` is the SINGLE SOURCE of address completion on the
Python side (point 146). The web console necessarily has a JavaScript
copy, and the agreement of the two is CHECKED by a test: two
implementations of the same rule always diverge."""

import re

IDENT_RE = re.compile(r"^[A-Za-z][A-Za-z0-9]*$")

# International calling code: '+' then 1 to 4 digits (+229 Benin, +33 France,
# +7 Russia). Checked here rather than left to the compiler, so that the
# mistake shows during the dialogue and not three screens later.
PHONE_PREFIX_RE = re.compile(r"^\+\d{1,4}$")

# Types offered in the menu — a safe subset of the grammar's types (Date/UUID
# excluded from the v1 menu: not very useful without a dedicated input widget).
FIELD_TYPES = ["String", "Text", "Integer", "Float", "Money", "Boolean", "Email", "DateTime"]

# Types that can be seeded deterministically (the 'seed' grammar accepts only
# STRING_LITERAL and SIGNED_NUMBER — no boolean or date).
SEEDABLE_TYPES = {"String", "Text", "Integer", "Float", "Money", "Email"}

RELATION_TYPES = ["hasMany", "hasOne", "belongsTo"]

# POINT 64: paragraph separator in an editorial text. The grammar does not
# accept a line break in a STRING_LITERAL; this character takes its place in
# the spec and exists ONLY there — the frontend contract translates it back
# into a paragraph break (frontend_contract.paragraphes). Chosen because it is
# not typed by accident in prose.
PARAGRAPH_SEP = " ¶ "

# ADDED (point 53): visual intent. The brief passed to the UI AI came down to
# the description sentence — often three words — facing a contract that
# describes the routes down to the field. The AI therefore received the whole
# structure and almost no intent, and rendered the lowest common denominator.
# These two menus capture what no spec can deduce: the desired register and the
# place of images. CLOSED menus (the dialogue stays deterministic and AI-free);
# each entry carries a short label for the screen and a sentence for the brief.
DESIGN_REGISTERS = [
    ("Formal and institutional",
     "restrained, institutional register: readability and trust above all, "
     "few effects, a clear typographic hierarchy"),
    ("Warm and editorial",
     "warm, editorial register: long stretches of text, generous breathing "
     "room, texture and nuance rather than harsh contrasts"),
    ("Dense and functional",
     "dense, functional register: the tool comes before the showcase, "
     "compact information, the user moves fast and comes back often"),
    ("Bold and graphic",
     "bold, graphic register: large typographic scales, strong contrasts, "
     "an assertive visual stance"),
]

DESIGN_IMAGERY = [
    ("Images define the site",
     "the images carry the site (photo, artwork, product): they take up "
     "large areas and drive the layout"),
    ("Text first, supporting images",
     "the text carries the site, images play a supporting role and stay "
     "secondary in the layout"),
    ("No images",
     "no images: everything rests on typography, spacing and "
     "color"),
]

class DialogueError(Exception):
    """Repeated invalid answer or inconsistency — the engine never guesses."""

def adresse_de_lien(saisie):
    """Returns the address as a browser will be able to open it, or None.

    SINGLE SOURCE, shared by the guided dialogue and by the platform's web
    console: two completion rules would eventually diverge, and it is the
    one that decides whether a footer link leads somewhere.

    Nobody types "mailto:" or "https://" spontaneously, and an address without
    a scheme is read as a RELATIVE path: the link then leads to a nonexistent
    page on the site itself. Completing is not guessing as long as there is
    only ONE reading — and the caller SAYS what it completed, which is the
    whole difference from correcting automatically (point 105)."""
    saisie = saisie.strip()
    if not saisie:
        return None
    if saisie.lower().startswith(("https://", "http://", "mailto:", "tel:")):
        return saisie
    # The phone BEFORE refusing spaces: "+33 6 12 34 56 78" is how everyone
    # writes a number, and it is the only value in this list that legitimately
    # contains them.
    compact = saisie.replace(" ", "")
    if re.fullmatch(r"\+?[0-9.\-]{6,20}", compact):
        return "tel:" + compact
    if " " in saisie:
        return None
    if "@" in saisie and "." in saisie.split("@")[-1]:
        return "mailto:" + saisie
    domaine = saisie.split("/")[0]
    if "." in domaine and not domaine.startswith("."):
        return "https://" + saisie
    return None
