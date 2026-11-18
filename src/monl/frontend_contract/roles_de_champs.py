"""Le rôle de chaque champ, et l'archétype de l'application.

L'archétype dépend de QUI peut lire, pas seulement des champs : il se calcule
donc depuis `_compute_route_map`, jamais depuis une logique parallèle.
Trois emplacements « méta » au plus (point 35) — une colonne ajoutée par une
brique doit être déclarée APRÈS l'attribution, sinon elle en vole un."""

from . import fondations


def _assign_field_roles(fields):
    """Attribue un rôle à chaque champ VISIBLE, dans l'ordre de priorité du
    point 35 : média, titre, description, prix, catégorie, puis méta (3 au
    plus). Les champs `hidden` n'en reçoivent aucun — ils ne sont jamais
    rendus, leur donner un rôle inviterait l'IA à les afficher."""
    # Un Upload n'est pas un média fourni par l'auteur et ne se rend pas comme
    # un champ de lecture JSON : ses routes multipart sont décrites à part.
    visibles = [f for f in fields
                if not f["hidden_in_reads"] and f["type"] != "Upload"]
    roles = {}

    # AJOUT (brique 13, point 83) : le type DÉCLARÉ prime sur la devinette par
    # nom. Jusqu'ici le média se reconnaissait uniquement à son nom
    # (`MEDIA_HINTS`) : `imageUrl` marchait par chance, `apercu` ou `cliche` non,
    # et l'IA d'interface n'en faisait alors pas une image. Un champ 'Image' dit
    # ce qu'il est ; l'heuristique ne sert plus que de repli pour les specs qui
    # n'ont pas encore adopté le type.
    media = next((f["name"] for f in visibles if f["type"] == "Image"), None)
    if not media:
        media = next((f["name"] for f in visibles
                      if f["type"] in ("String", "Text")
                      and any(h in f["name"].lower() for h in fondations.MEDIA_HINTS)), None)
    if media:
        roles[media] = "media"
    # Le titre est le premier String qui n'est pas déjà le média : sur une
    # entité dont le seul String est `imageUrl`, prendre ce champ comme titre
    # afficherait une URL en guise de nom (défaut réel du repli).
    titre = next((f["name"] for f in visibles
                  if f["type"] == "String" and f["name"] not in roles), None)
    if titre:
        roles[titre] = "title"
    description = next((f["name"] for f in visibles
                        if f["type"] == "Text" and f["name"] not in roles), None)
    if description:
        roles[description] = "description"
    prix = next((f["name"] for f in visibles
                 if f["type"] == "Money" and f["name"] not in roles), None)
    if prix:
        roles[prix] = "price"
    dispo = next((f["name"] for f in visibles
                  if f["type"] in ("Integer", "Float") and f["name"] not in roles
                  and any(h in f["name"].lower() for h in fondations.STOCK_HINTS)), None)
    if dispo:
        roles[dispo] = "stock"
    categorie = next((f["name"] for f in visibles
                      if f["name"] not in roles
                      and any(h in f["name"].lower() for h in fondations.CATEGORY_HINTS)), None)
    if categorie:
        roles[categorie] = "category"
    for f in visibles:                       # méta : 3 au plus (point 35)
        if f["name"] not in roles and sum(1 for r in roles.values() if r == "meta") < 3:
            roles[f["name"]] = "meta"
    return roles

def _archetype(roles, lisible, public):
    """Forme d'interface déduite des rôles présents ET de qui peut lire.

    La lisibilité PUBLIQUE est une condition du point 35 que la première
    version de cette fonction avait laissée tomber — et le défaut s'est vu
    tout de suite : l'entité `Message` d'un formulaire de contact (auteur +
    contenu) se voyait conseiller « grandes vignettes en grille ». Une
    collection interne se gère, elle ne se parcourt pas : elle mérite un
    tableau dense, jamais une vitrine.

    `shop` l'emporte sur `gallery` : un prix commande la mise en page bien
    plus qu'une image (le point 35 déclenchait déjà la boutique sur un champ
    Money). `list` reste le repli — sans rien à montrer, une galerie
    n'apporterait qu'une grille nue.

    ÉCART ASSUMÉ avec le point 35, qui exigeait un titre ET (un média OU une
    description) : un média SEUL suffit désormais. Une entité `photo + légende`
    sans champ titre — cas banal d'un portfolio — retombait en liste, et son
    image, sa seule raison d'être, se réduisait à une rangée de tableau.
    """
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

# ANATOMIE ATTENDUE PAR FORME (point 60) — relevé sur les recensements
# publics de « ce que contient une page de ce type » (fiche produit,
# article de blog, portfolio, carte kanban, annonce, page de réservation).
# Le contrat disait à l'IA quelles DONNÉES existent, jamais ce qu'un visiteur
# s'attend à trouver sur une page de cette nature. Deux sites du même genre se
# ressemblent parce qu'ils répondent aux mêmes attentes : les nommer donne au
# modèle un repère, là où la seule liste des champs le laissait improviser.
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
