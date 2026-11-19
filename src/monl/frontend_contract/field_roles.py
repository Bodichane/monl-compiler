"""The role of each field, and the application's archetype.

The archetype depends on WHO can read, not only on the fields: it is
therefore computed from `_compute_route_map`, never from parallel logic.
At most three "meta" slots (point 35) — a column added by a brick must be
declared AFTER assignment, otherwise it steals one."""

from . import foundations


def _nomme(f, indices):
    return any(h in f["name"].lower() for h in indices)


def _est_titre(f):
    return f["type"] == "String"


def _est_description(f):
    return f["type"] == "Text"


def _est_prix(f):
    return f["type"] == "Money"


def _est_stock(f):
    return f["type"] in ("Integer", "Float") and _nomme(f, foundations.STOCK_HINTS)


def _est_categorie(f):
    return _nomme(f, foundations.CATEGORY_HINTS)


# After the media, one field per role, in the point 35 priority order: each
# role takes the first visible field no earlier role has claimed.
_ROLES_UNIQUES = (("title", _est_titre), ("description", _est_description),
                  ("price", _est_prix), ("stock", _est_stock),
                  ("category", _est_categorie))


def _champ_media(visibles):
    """The declared Image field, else a text field named like a media."""
    media = next((f["name"] for f in visibles if f["type"] == "Image"), None)
    if not media:
        media = next((f["name"] for f in visibles
                      if f["type"] in ("String", "Text")
                      and any(h in f["name"].lower() for h in foundations.MEDIA_HINTS)), None)
    return media


def _ajouter_les_meta(visibles, roles):
    """The remaining visible fields become meta, at most 3."""
    for f in visibles:                       # meta: at most 3 (point 35)
        if f["name"] not in roles and sum(1 for r in roles.values() if r == "meta") < 3:
            roles[f["name"]] = "meta"


def _assign_field_roles(fields):
    """Assigns a role to each VISIBLE field, in the priority order of point 35:
    media, title, description, price, category, then meta (at most 3).
    `hidden` fields get none — they are never rendered, giving them a role
    would invite the AI to display them."""
    # An Upload is not media supplied by the author and is not rendered as a
    # JSON read field: its multipart routes are described separately.
    visibles = [f for f in fields
                if not f["hidden_in_reads"] and f["type"] != "Upload"]
    roles = {}

    # ADDED (brick 13, point 83): the DECLARED type takes precedence over
    # guessing by name. Until then media was recognized only by its name
    # (`MEDIA_HINTS`): `imageUrl` worked by luck, `apercu` or `cliche` did not,
    # and the interface AI then did not make it an image. An 'Image' field says
    # what it is; the heuristic now serves only as a fallback for specs that
    # have not adopted the type yet.
    media = _champ_media(visibles)
    if media:
        roles[media] = "media"
    # The title is the first String that is not already the media: on an entity
    # whose only String is `imageUrl`, taking that field as the title would
    # display a URL as a name (a real defect of the fallback).
    for role, convient in _ROLES_UNIQUES:
        nom = next((f["name"] for f in visibles
                    if f["name"] not in roles and convient(f)), None)
        if nom:
            roles[nom] = role
    _ajouter_les_meta(visibles, roles)
    return roles

def _archetype(roles, lisible, public):
    """Interface shape deduced from the roles present AND from who can read.

    PUBLIC readability is a point 35 condition that the first version of
    this function had dropped — and the defect showed at once: the `Message`
    entity of a contact form (author + content) was advised "large thumbnails
    in a grid". An internal collection is managed, not browsed: it deserves a
    dense table, never a storefront.

    `shop` wins over `gallery`: a price drives the layout far more than an
    image (point 35 already triggered the shop on a Money field). `list` stays
    the fallback — with nothing to show, a gallery would only bring a bare
    grid.

    DELIBERATE DEPARTURE from point 35, which required a title AND (a media OR
    a description): a media ALONE is now enough. A `photo + caption` entity
    without a title field — an ordinary portfolio case — fell back to a list,
    and its image, its only reason to exist, shrank to a table row."""
    if not lisible:
        return "form"
    if not public:
        return "list"
    valeurs = set(roles.values())
    if "price" in valeurs:
        return "shop"
    if "media" in valeurs or ("title" in valeurs and "description" in valeurs):
        return "gallery"
    return "list"

ARCHETYPE_GUIDANCE = {
    "gallery": ("gallery — the media drives the layout: large thumbnails "
                "in a grid, title and category alongside, detail view on "
                "click"),
    "shop": ("shop — the price is the decisive information: it must stay "
             "readable without effort next to each item, with a clear call "
             "to action"),
    "list": ("list — nothing to showcase here, or a collection reserved to "
             "authorized accounts: dense, fast reading, in rows rather than "
             "cards"),
    "form": ("form only — this entity is written but read nowhere: build "
             "no list view, just the input"),
}

# EXPECTED ANATOMY PER SHAPE (point 60) — drawn from public surveys of "what a
# page of this type contains" (product page, blog article, portfolio, kanban
# card, classified ad, booking page). The contract told the AI which DATA
# exists, never what a visitor expects to find on a page of this nature. Two
# sites of the same kind look alike because they meet the same expectations:
# naming them gives the model a landmark, where the list of fields alone left
# it improvising.
ARCHETYPE_ANATOMY = {
    "gallery": {
        "attendus": ["a dominant visual, never a timid thumbnail",
                     "the title readable without hovering",
                     "a detail view that gives context, not just the image enlarged",
                     "a filter or a grouping as soon as there is a category"],
        "voisins": ("an agency's project pages, an online magazine article "
                    "page, a photographer's gallery"),
    },
    "shop": {
        "attendus": ["price and availability visible without scrolling",
                     "an obvious call to action on each item",
                     "several views of the product if the data allows",
                     "the structured description (use, material, dimensions)"],
        "voisins": ("a standard online store front: filterable list, dense "
                    "product page, explicit cart"),
    },
    "list": {
        "attendus": ["scannable rows, aligned in columns",
                     "sorting and search as soon as the list grows",
                     "editing actions within reach, without changing page",
                     "an empty state that explains what to do"],
        "voisins": ("an administration dashboard, an internal management "
                    "grid, a tracking board"),
    },
    "form": {
        "attendus": ["a short form, one field per line",
                     "errors shown at the field concerned",
                     "an explicit confirmation after sending"],
        "voisins": "a contact or request form",
    },
}
