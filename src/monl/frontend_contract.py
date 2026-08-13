# ─────────────────────────────────────────────────────────────────────
# CONTRAT FRONTEND — pivot "monl orchestrateur" (brique 2).
#
# À partir de la spec validée (le DSL reste la SOURCE DE VÉRITÉ), ce module
# produit deux artefacts dans le dossier du projet :
#
#   - frontend_contract.json : description machine-lisible et EXHAUSTIVE de
#     ce que le backend généré expose réellement — routes (méthode, chemin,
#     authentification, acteurs), schémas d'entités (champs, types, requis,
#     hidden/generated/categorized), conventions d'auth (register/login/
#     logout, en-tête Authorization: Bearer), pagination. Rien n'y est
#     deviné : tout est dérivé des mêmes structures que la génération des
#     routes (_compute_route_map du générateur), donc contrat et API ne
#     peuvent pas diverger.
#
#   - FRONTEND_PROMPT.md : brief prêt à donner à une IA spécialisée (Claude,
#     GPT…) pour générer l'interface. Il embarque le contrat, les contraintes
#     (où écrire les fichiers, ne jamais toucher aux artefacts backend) et
#     les conventions d'appel de l'API.
#
# Le frontend produit par l'IA est attendu dans frontend/ (index.html en
# entrée) ; 'monl run' le sert sur /site sans modifier app.py (voir
# cli.py, wrapper serve.py).
# ─────────────────────────────────────────────────────────────────────
import hashlib
import json
import os

from .artifacts import copy_preserved_files, publish_files, staging_directory
from .design_skills import render_skill_block, select_design_skills

# Les noms des colonnes de suivi du paiement viennent de la couche qui les
# crée — les réécrire ici en dur ferait une cinquième copie à faire dériver
# (point 76). Pas de cycle : le générateur n'importe pas ce module.
from .ir import (
    PAYMENT_REF_COLUMN,
    PAYMENT_STATUS_COLUMN,
    CompilationIR,
    CompilationPlans,
)

CONTRACT_VERSION = 9  # 2 : base_url même origine (51) · 3 : rôles + archétypes (54)
#                     # 4 : champs de suivi du paiement déclarés (76)
#                     # 5 : assets déclarés — logo, favicon, dossier (83)
#                     # 6 : route d'écriture après paiement déclarée (113)
#                     # 7 : indicatif téléphone transmis au frontend (95)
#                     # 8 : design skills de densité sélectionnés
#                     # 9 : règles métier — publicWhen et oncePer (116)
# Les numéros entre parenthèses renvoient à docs/design_decisions.md. Ceux des
# versions 6 et 7 désignaient les points 107-109, qui parlent d'autre chose
# (émission SQL typée, contrôle d'accès, spike Rust) : corrigés ici plutôt que
# laissés induire en erreur — ce fichier cite ces numéros pour qu'on les suive.

# RÔLES DE CHAMPS ET ARCHÉTYPES (point 54) — restauration, dans le CONTRAT,
# de ce que le point 35 dérivait pour le frontend que monl générait lui-même,
# et que le pivot (point 41) a supprimé sans le transposer. Sans ces rôles,
# un champ n'est qu'un `{nom, type}` : l'IA UI doit redeviner depuis les noms
# lequel est le titre, lequel est l'image de couverture, alors que monl sait
# le déduire de façon déterministe. Même philosophie qu'aux thèmes : dérivé
# de la spec, jamais déclaré dans le DSL métier.
MEDIA_HINTS = ("image", "photo", "cover", "couverture", "avatar", "picture",
               "thumbnail", "vignette", "banner", "banniere", "illustration",
               "visuel", "url")
CATEGORY_HINTS = ("category", "categorie", "genre", "kind", "tag", "rubrique",
                  "status", "statut", "etat", "type")
# La disponibilité est un essentiel de fiche produit, au même rang que le prix
# (point 60) : la reléguer en « méta » la faisait traiter comme un détail.
STOCK_HINTS = ("stock", "quantity", "quantite", "inventaire", "disponib",
               "available", "restant")


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
                      and any(h in f["name"].lower() for h in MEDIA_HINTS)), None)
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
                  and any(h in f["name"].lower() for h in STOCK_HINTS)), None)
    if dispo:
        roles[dispo] = "stock"
    categorie = next((f["name"] for f in visibles
                      if f["name"] not in roles
                      and any(h in f["name"].lower() for h in CATEGORY_HINTS)), None)
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
    "gallery": ("galerie — le média commande la mise en page : grandes "
                "vignettes en grille, titre et catégorie en accompagnement, "
                "vue de détail au clic"),
    "shop": ("boutique — le prix est l'information décisive : il doit rester "
             "lisible sans effort à côté de chaque article, avec un appel à "
             "l'action clair"),
    "list": ("liste — rien à mettre en vitrine ici, ou collection réservée "
             "aux comptes autorisés : lecture dense et rapide, en rangées "
             "plutôt qu'en cartes"),
    "form": ("formulaire seul — cette entité s'écrit mais ne se lit nulle "
             "part : ne construire aucune vue de liste, juste la saisie"),
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
        "attendus": ["un visuel dominant, jamais une vignette timide",
                     "le titre lisible sans survol",
                     "une vue de détail qui donne le contexte, pas seulement l'image en grand",
                     "un filtre ou un regroupement dès qu'il y a une catégorie"],
        "voisins": ("les pages projet d'une agence, une fiche d'article de "
                    "magazine en ligne, une galerie de photographe"),
    },
    "shop": {
        "attendus": ["prix et disponibilité visibles sans défiler",
                     "un appel à l'action évident sur chaque article",
                     "plusieurs vues du produit si les données le permettent",
                     "la description structurée (usage, matière, dimensions)"],
        "voisins": ("une vitrine de commerce en ligne standard : liste "
                    "filtrable, fiche produit dense, panier explicite"),
    },
    "list": {
        "attendus": ["des rangées scannables, alignées en colonnes",
                     "un tri et une recherche dès que la liste s'allonge",
                     "les actions d'édition à portée, sans changer de page",
                     "un état vide qui explique quoi faire"],
        "voisins": ("un tableau de bord d'administration, une grille de "
                    "gestion interne, un tableau de suivi"),
    },
    "form": {
        "attendus": ["un formulaire court, un champ par ligne",
                     "les erreurs affichées au champ concerné",
                     "une confirmation explicite après envoi"],
        "voisins": "un formulaire de contact ou de demande",
    },
}

CONTRACT_FILENAME = "frontend_contract.json"
PROMPT_FILENAME = "FRONTEND_PROMPT.md"
FRONTEND_ARTIFACTS = (CONTRACT_FILENAME, PROMPT_FILENAME, "CLAUDE.md")


def paragraphes(texte):
    """Retraduit le séparateur de paragraphes de la spec en vrais sauts
    (point 64). La grammaire interdit le retour à la ligne dans un
    STRING_LITERAL : un « à propos » de trois paragraphes voyage donc en une
    seule ligne, marquée. Le contrat est le premier endroit où cette
    contrainte d'écriture cesse d'exister — et l'IA d'interface reçoit du
    texte structuré au lieu d'un bloc sans césure.

    Sans marqueur, le texte ressort tel quel : un contrat écrit avant le
    point 64, ou une spec rédigée à la main, se lit exactement comme avant.
    """
    return "\n\n".join(p.strip() for p in texte.split("¶") if p.strip())


def _coerce_plans(source) -> CompilationPlans:
    """Compatibilité de bibliothèque pour les anciens appels avec générateur."""
    if isinstance(source, CompilationPlans):
        return source
    return source.build_compilation_plans()


def build_contract(normalized_ast: CompilationIR, plans_or_generator):
    """Construit le contrat depuis l'IR et les analyses communes.

    La voie de production transmet ``CompilationPlans``. L'acceptation d'un
    générateur reste volontairement conservée pour les intégrations Python
    historiques ; elle ne fait que construire l'objet de plans une fois.
    """
    plans = _coerce_plans(plans_or_generator)
    app_name = normalized_ast["meta"]["appName"]
    entities = normalized_ast["schema"]["entities"]
    # POINT 91 : la liste des 'rule X.y required' ne sert PLUS à peupler le
    # `required` du contrat — les schémas générés rendent tout champ d'entrée
    # obligatoire, déclaré ou non, et le contrat doit dire ce que le serveur
    # exige. Elle n'est donc plus lue ici : la garder pour « information »
    # rouvrirait la porte à ce qu'on vient de fermer, deux sources pour une
    # même question.
    fk_placements = plans.foreign_key_placements

    # Calculés AVANT les entités : l'archétype dépend de qui peut lire, pas
    # seulement des champs (voir _archetype). Même source de vérité que la
    # génération FastAPI — _compute_route_map, jamais une logique parallèle.
    route_map = plans.route_map
    public_conditions = plans.public_conditions
    lisibles = {plan.base_target for (act, _t), plan in route_map.items()
                if act == "Read"}

    # POINT 79 : un champ 'derivedFrom' est CALCULÉ par le serveur, donc absent
    # des corps de requête — exactement comme un champ 'generated'. Le contrat
    # devait le dire : sans cela il annonçait `total` parmi les champs à
    # envoyer, et une IA d'interface fidèle au contrat aurait bâti un
    # formulaire de prix que le serveur ignore. C'est le défaut du point 76,
    # reproduit sur la brique qui venait de le corriger — la leçon « déclarer
    # ce que le backend fait VRAIMENT » vaut aussi quand une brique retire
    # quelque chose, pas seulement quand elle ajoute une colonne.
    # POINT 82 : même exigence pour 'sumOf'. Le défaut du point 76 s'est déjà
    # reproduit deux fois (points 79 et 81) : le déclarer d'emblée ici plutôt
    # que d'attendre qu'une IA d'interface bâtisse un champ « total » que le
    # serveur recalcule. Un total de panier est le cas où l'écart se voit le
    # plus vite — il change à chaque ligne ajoutée.
    # POINT 89 : quatrième membre de la même famille. Le défaut du point 76 s'est
    # reproduit sur chacune des trois précédentes ; celle-ci arrive déclarée.
    # POINT 102 : cinquième membre de la même famille, déclarée d'emblée elle
    # aussi. Sans ça le contrat annoncerait un « numéro de commande » parmi les
    # champs à saisir, et une IA d'interface fidèle au contrat dessinerait un
    # formulaire que le serveur ignore.
    entity_specs = {}
    for ent, fields in entities.items():
        field_list = []
        entity_model = plans.entity_models[ent]
        for fname, ftype in fields.items():
            policy = entity_model.fields[fname]
            derive = policy.derived_rule
            somme = policy.aggregate_rule
            numero = policy.numbering_rule
            peuple_par_le_serveur = policy.server_generated
            champ = {
                "name": fname,
                "type": ftype,
                # POINT 91 : ce que le SERVEUR exige, pas ce que la spec déclare.
                # Le contrat reflétait `rule X.y required` — or les schémas
                # Pydantic générés rendent obligatoire TOUT champ d'entrée, sans
                # exception (point 85 : « required reste une assertion, les
                # schémas rendent déjà tout champ obligatoire »). Un frontend
                # fidèle au contrat omettait donc les champs non déclarés et
                # récoltait un 422. Vu en vrai : ajouter `email` et `address` à
                # une fiche client a cassé le formulaire d'un site en marche,
                # alors que le contrat les annonçait facultatifs.
                "required": not peuple_par_le_serveur and not policy.upload_rule,
                # hidden : jamais présent dans les réponses de lecture
                "hidden_in_reads": policy.hidden_in_reads,
                # generated, derivedFrom ou sumOf : à NE PAS envoyer, le serveur
                # le peuple lui-même (et l'ignorerait dans le corps de requête)
                "server_generated": peuple_par_le_serveur,
                # categorized : la lecture renvoie un libellé, pas le nombre
                "categorized_in_reads": policy.categorized_in_reads,
                "postpayment_only": policy.postpayment_only,
            }
            # BRIQUE B3 : seules les déclarations de la spec apparaissent.
            # L'absence de ces clés signifie « non filtrable/triable » ; cela
            # garde le contrat des specs historiques inchangé à l'octet.
            if fname in plans.filterable_fields.get(ent, ()):
                valeurs_filtre = (list(policy.allowed_values)
                                   if policy.allowed_values else None)
                if ftype == "Boolean":
                    valeurs_filtre = ["true", "false"]
                champ["filterable"] = True
                champ["filter"] = {
                    "parameter": fname,
                    "kind": "exact",
                    "allowed_values": valeurs_filtre,
                }
            if fname in plans.sortable_fields.get(ent, ()):
                champ["sortable"] = True
            if policy.upload_rule:
                # BRIQUE B1 : le champ est une entrée multipart dédiée, pas
                # une valeur JSON et pas un asset Image. Le contrat expose la
                # limite, les types, le nom exact du champ et les deux routes
                # ajoutées plus bas ; l'IA frontend n'a rien à deviner.
                champ["upload"] = {
                    "field_name": fname,
                    "max_bytes": policy.upload_rule["max_bytes"],
                    "accepted_types": list(policy.upload_rule["accepted_types"]),
                    "storage": "server_disk_reference",
                    "note": ("octets reçus à l'exécution ; le nom de fichier et le "
                             "Content-Type client sont ignorés, le type est établi "
                             "par signature d'octets ; lecture privée selon l'ACL de "
                             "la ligne, en téléchargement octet/octet"),
                }
            # BRIQUE 19 (point 96) : les valeurs permises. Sans elles, l'IA
            # dessine un champ TEXTE et l'utilisateur invente un statut qui
            # récolte un 422 — alors que la liste tient dans un menu déroulant.
            # Même raison que les bornes ci-dessous : le contrat décrit ce que le
            # backend REFUSE autant que ce qu'il accepte.
            choix = policy.allowed_values
            if choix:
                champ["allowed_values"] = list(choix)
            # POINT 85 : les bornes 'min'/'max' donnent un 422 avant tout INSERT.
            # Le contrat DOIT les annoncer : une interface qui les ignore laisse
            # l'utilisateur remplir un formulaire pour se faire refuser au bout,
            # alors qu'elle pouvait le dire tout de suite. Même raison que pour
            # `server_generated` (point 79) — le contrat décrit ce que le backend
            # fait VRAIMENT, y compris ce qu'il REFUSE.
            for nom in ("min", "max"):
                borne = policy.constraints.get(nom)
                if borne:
                    champ[f"{nom}_{'length' if borne['portee'] == 'longueur' else 'value'}"] = \
                        borne["valeur"]
            if policy.constraints.get("unique"):
                champ["unique"] = True
                champ["unique_note"] = ("valeur unique imposée par la base : une "
                                        "création ou une modification en doublon "
                                        "répond 409, pas 422 — le dire à l'utilisateur "
                                        "plutôt que de rejouer la requête.")
            if derive:
                champ["derived_from"] = (f"{derive['source_entity']}."
                                         f"{derive['source_field']}")
                champ["derived_factor"] = derive["factor"]
                champ["note"] = (
                    f"calculé par le serveur : {derive['source_entity']}."
                    f"{derive['source_field']} × {derive['factor']}. Ne pas "
                    f"l'envoyer, et ne pas le calculer côté navigateur pour "
                    f"l'afficher avant création — relire la valeur renvoyée par "
                    f"le serveur, c'est elle qui sera encaissée.")
            if somme:
                champ["summed_from"] = (f"{somme['source_entity']}."
                                        f"{somme['source_field']}")
                champ["note"] = (
                    f"total recalculé par le serveur : somme des "
                    f"{somme['source_entity']}.{somme['source_field']} rattachés. "
                    f"Ne pas l'envoyer. Il change à chaque {somme['source_entity']} "
                    f"ajouté, modifié ou supprimé : relire le "
                    f"{ent} après chaque écriture de ligne plutôt que de tenir un "
                    f"total côté navigateur, qui divergerait.")
            if policy.timestamped:
                champ["created_at"] = True
                champ["note"] = (
                    "instant de création, écrit par le serveur en ISO 8601 UTC "
                    "(ex. '2026-07-31T04:18:22.310+00:00'), et jamais modifié ensuite. "
                    "Ne pas l'envoyer : ni à la création, ni à la modification. "
                    "Il se trie comme du texte — comparer les chaînes suffit, "
                    "inutile de les convertir pour ordonner une liste. "
                    "PEUT ÊTRE VIDE sur les enregistrements créés avant l'ajout "
                    "de la règle : afficher un tiret, jamais la date du jour — "
                    "cette date-là n'a pas été perdue, elle n'a jamais existé.")
            if numero:
                champ["numbered_as"] = numero["format"]
                champ["note"] = (
                    f"numéro lisible attribué par le serveur à la création, sur le "
                    f"gabarit « {numero['format']} », et jamais modifié ensuite. "
                    f"Ne pas l'envoyer : ni à la création, ni à la modification. "
                    f"C'est la référence que l'humain lit et dicte — l'AFFICHER "
                    f"partout où l'enregistrement est identifié (liste, détail, "
                    f"accusé de commande), de préférence avant l'`id` technique, "
                    f"et la rendre copiable. "
                    + ("Il se trie comme du texte, la partie séquence étant "
                       "complétée par des zéros. " if "{N" in numero["format"] else "")
                    + "PEUT ÊTRE VIDE sur les enregistrements créés avant l'ajout "
                      "de la règle : afficher un tiret, jamais un numéro inventé.")
            field_list.append(champ)
        # POINT 88 : une clé étrangère de monl référence l'une de DEUX choses,
        # et le contrat n'en disait qu'une. Celles que la route Create peuple
        # depuis le jeton portent un identifiant de COMPTE (`_monl_users.id`) ;
        # les autres portent l'`id` de la table métier. `schema.sql` écrit
        # d'ailleurs deux `REFERENCES` différents — le contrat, lui, annonçait
        # « references: Customer » dans les deux cas.
        #
        # Ce que ça coûtait : une interface qui suit le contrat joint
        # `order.customer_id` à `customer.id`, alors que la bonne jointure est
        # `customer.customer_id`. Une jointure qui marche À MOITIÉ — juste tant
        # que l'id de compte et l'id de fiche coïncident, c'est-à-dire sur les
        # premiers enregistrements, c'est-à-dire pendant les tests.
        identity_cols = plans.identity_foreign_keys.get(ent, frozenset())
        fks = []
        for p in fk_placements.get(ent, []):
            lien = {"column": p["fk_column"], "references": p["owner_entity"],
                    "unique": p["unique"]}
            if p["fk_column"] in identity_cols:
                lien["references_account"] = True
                # La fiche métier se retrouve par la colonne HOMONYME, qui porte
                # le même identifiant de compte — pas par son `id`.
                lien["note"] = (
                    f"contient un identifiant de COMPTE (celui du titulaire), "
                    f"pas l'`id` d'un enregistrement {p['owner_entity']}. Pour "
                    f"retrouver la fiche : chercher le {p['owner_entity']} dont "
                    f"`{p['fk_column']}` vaut cette même valeur — jamais celui "
                    f"dont `id` la vaut, la correspondance serait fortuite.")
            else:
                lien["references_account"] = False
                lien["note"] = (f"contient l'`id` d'un enregistrement "
                                f"{p['owner_entity']}.")
            fks.append(lien)
        roles = _assign_field_roles(field_list)
        for f in field_list:
            f["role"] = roles.get(f["name"])
        # POINT 76 : les deux colonnes de suivi de la brique 'payable' sont
        # présentes dans toutes les réponses de lecture (le générateur fait un
        # SELECT *) mais n'étaient déclarées NULLE PART dans le contrat. Une IA
        # d'interface qui le suit à la lettre ne pouvait donc pas savoir
        # qu'elles existent, et ne pouvait pas afficher l'état d'un règlement :
        # le bouton de paiement était dessinable, son résultat non.
        #
        # Ajoutées APRÈS l'attribution des rôles, volontairement : passées à
        # _assign_field_roles, elles auraient pris deux des trois emplacements
        # « méta » (point 35) et se seraient fait afficher comme des
        # informations secondaires quelconques, en évinçant de vrais champs de
        # la spec. Elles n'ont donc aucun rôle — ce qu'il faut en faire est dit
        # en toutes lettres dans le brief, pas déduit d'un rôle de mise en page.
        if ent in plans.payable_by_entity:
            # Chaque colonne porte SA propre explication : les décrire d'une
            # seule phrase commune faisait annoncer « 'en_attente' / 'payee' »
            # pour `payment_ref`, qui contient une référence de session — vu en
            # relisant le brief produit, pas le code.
            suivi = (
                (PAYMENT_STATUS_COLUMN,
                 "état du règlement, écrit par le serveur seul : 'en_attente' "
                 "tant que rien n'est encaissé, 'payee' une fois le webhook du "
                 "prestataire reçu — c'est ce champ qui dit si c'est payé"),
                (PAYMENT_REF_COLUMN,
                 "référence de la session chez le prestataire, écrite par le "
                 "serveur seul ; utile pour un rapprochement comptable, sans "
                 "intérêt pour le visiteur. Elle peut être renseignée DÈS "
                 "l'ouverture de la session, avant tout encaissement : ce "
                 "n'est donc pas un indicateur de règlement, c'est "
                 "payment_status qui dit si c'est payé"),
            )
            for colonne, explication in suivi:
                field_list.append({
                    "name": colonne,
                    "type": "String",
                    "required": False,
                    "hidden_in_reads": False,
                    # Jamais fourni par le client : même interdit que 'generated'.
                    "server_generated": True,
                    "categorized_in_reads": False,
                    "payment_tracking": True,
                    "note": explication,
                    "role": None,
                })
        entity_specs[ent] = {
            "fields": field_list, "foreign_keys": fks,
            "client_foreign_keys": _client_supplied_fks(plans, ent),
            "archetype": _archetype(
                roles, ent in lisibles,
                bool(plans.access_policies.get((ent, "Read"), None)
                     and plans.access_policies[(ent, "Read")].public)),
        }

    # Routes — mêmes clés de regroupement que la génération FastAPI réelle
    # (route_map et public sont calculés plus haut, pour les archétypes).
    routes = []
    for (act_type, target), plan in route_map.items():
        base = plan.base_target
        low = base.lower()
        access = plans.access_policies[(base, act_type)]
        is_public = access.public
        actors = sorted(access.actors)
        if act_type == "Create":
            # POINT 90 : sans cette note, une IA d'interface bâtit un tunnel
            # d'achat qui bute en 409 au tout dernier écran — le seul endroit où
            # l'utilisateur a déjà tout rempli. La contrainte doit se voir AVANT,
            # pas se découvrir à la fin.
            requise = plans.required_profiles.get(base)
            note_create = (
                f"PRÉALABLE : l'appelant doit déjà posséder un {requise}. Sinon "
                f"cette route répond 409 sans rien créer. Vérifier au chargement "
                f"(GET /{requise.lower()} renvoie les siens) et proposer la "
                f"création de la fiche AVANT le formulaire, pas après."
                if requise else None)
            # POINT 91 : la création AUSSI est verrouillée — mais seulement par
            # un PARENT réglé, jamais par l'entité elle-même : rien n'empêche
            # d'ouvrir une commande de plus, c'est y AJOUTER une ligne qui
            # remonterait le total déjà encaissé. D'où `inclure_soi=False`.
            # Le contrat le taisait alors que le backend refusait déjà : une IA
            # fidèle dessinait un « + Ajouter un article » sur une commande
            # payée (vérifié sur `exemples/02_boutique.ml`).
            verrou_parent = _verrou_paiement(plans, base, inclure_soi=False)
            message = plans.message_rules_by_trigger.get(base)
            routes.append(_route("POST", f"/{low}", act_type, base, is_public, actors,
                                 request_fields=_creatable_fields(entity_specs.get(base)),
                                 note=_joindre(note_create,
                                               _note_verrou(verrou_parent, creation=True),
                                               _note_message(message))))
            if requise:
                routes[-1]["requires_own"] = requise
            if verrou_parent:
                routes[-1]["payment_locked"] = verrou_parent
        elif act_type == "Read":
            # AJOUT (brique 23, point 106) : un rôle superviseur (declare via
            # 'sharedBy' sur la meme reference que 'accessibleBy') transperce
            # le controle par colonnes. Sans cette note, une IA d'interface
            # appliquerait le filtre de parties au moderateur lui-meme et lui
            # taillerait une vue vide — alors que le backend lui montre tout.
            _sup_lecture = sorted(access.supervisors)
            _note_lecture = _note_superviseurs(_sup_lecture, "lecture")
            list_query = _list_query_contract(plans, base)
            routes.append(_route(
                "GET", f"/{low}", "List", base, is_public, actors,
                note=_joindre(
                    "Paramètres : limit (max 200), offset. Réponse : "
                    "{status, total, limit, offset, data: [...]}.",
                    _note_list_query(list_query), _note_lecture)))
            if list_query:
                routes[-1]["list_query"] = list_query
            routes.append(_route("GET", f"/{low}/{{id}}", "Read", base, is_public, actors,
                                 note=_note_lecture))
            if _sup_lecture:
                routes[-1]["supervisors"] = _sup_lecture
                routes[-2]["supervisors"] = _sup_lecture
        elif act_type == "Update":
            # AJOUT (point 81) : le schéma Pydantic est UNIQUE par entité, donc
            # ces clés étrangères doivent être envoyées (sinon 422) -- mais la
            # route Update de monl ne les écrit pas : un rattachement se fixe à
            # la création. Sans cette note, le contrat laissait croire qu'une
            # interface pouvait déplacer une ligne d'un panier à l'autre, ce que
            # le backend accepte (200) sans rien changer. Même exigence que les
            # points 76 et 79 : le contrat décrit ce que le backend FAIT.
            liens = list(entity_specs.get(base, {}).get("client_foreign_keys", []))
            note_liens = None
            if liens:
                accord = ("doivent figurer dans le corps (schéma unique par entité) mais ne "
                          "sont PAS modifiés" if len(liens) > 1 else
                          "doit figurer dans le corps (schéma unique par entité) mais n'est "
                          "PAS modifié")
                note_liens = (
                    f"{', '.join(liens)} {accord} : un rattachement se fixe à la création. "
                    f"Ne pas proposer de le changer — renvoyer la valeur actuelle.")
            # POINT 91 : quatrième forme de l'angle mort des points 88 à 90. Une
            # route ne change ni de chemin, ni d'acteurs, ni de champs, et gagne
            # pourtant un refus : dès l'encaissement, elle répond 409. Sans cette
            # note, une interface fidèle au contrat dessine un bouton « Modifier »
            # sur une commande payée — et l'utilisateur découvre le refus après
            # avoir rempli le formulaire.
            verrou = _verrou_paiement(plans, base)
            # POINT 98 : la valeur qui LIBÈRE, et l'aller sans retour. Sans
            # cette note, une interface propose « repasser en préparation » sur
            # une commande annulée et découvre un 409 au clic.
            liberation = (plans.release_rules_by_entity.get(base) or [None])[0]
            routes.append(_route("PUT", f"/{low}/{{id}}", act_type, base, is_public, actors,
                                 note=_joindre(note_liens, _note_verrou(verrou),
                                               _note_liberation(liberation)),
                                 request_fields=_creatable_fields(entity_specs.get(base))))
            if verrou:
                routes[-1]["payment_locked"] = verrou
            if liberation:
                routes[-1]["releases_on"] = {
                    "field": liberation["field"], "value": liberation["value"],
                    "releases": liberation["releases"], "terminal": True}
        elif act_type == "Delete":
            verrou = _verrou_paiement(plans, base)
            # AJOUT (brique 23, point 106) : voir le bloc Read — un superviseur
            # de la suppression voit/supprime tous les enregistrements.
            _sup_delete = sorted(access.supervisors)
            routes.append(_route("DELETE", f"/{low}/{{id}}", act_type, base, is_public,
                                 actors,
                                 note=_joindre(_note_verrou(verrou),
                                               _note_superviseurs(_sup_delete, "suppression"))))
            if _sup_delete:
                routes[-1]["supervisors"] = _sup_delete
            if verrou:
                routes[-1]["payment_locked"] = verrou
        elif act_type == "Execute":
            tag = plan.tags[0]
            routes.append(_route("POST", f"/workflow/{tag.lower()}/{target.lower()}",
                                 "Execute", target, is_public, actors))

    # BRIQUE B1 : ces routes ne sont pas des CRUD JSON. Elles sont produites
    # par une déclaration Upload et doivent donc être décrites séparément dans
    # le contrat : nom multipart, limite explicite, types réellement reconnus,
    # dépôt POST et lecture GET privée.
    for upload in plans.upload_fields:
        entite = upload["entity"]
        champ = upload["field"]
        chemin = f"/{entite.lower()}/{{id}}/{champ}"
        for action, method, contract_action, note in (
                ("Update", "POST", "Upload", (
                    f"multipart/form-data obligatoire, champ de fichier '{champ}'. "
                    f"Limite exacte : {upload['max_bytes']} octets. Types acceptés "
                    f"par signature d'octets : {', '.join(upload['accepted_types'])}. "
                    "Le nom de fichier et le Content-Type déclarés par le client "
                    "sont ignorés ; le dépôt remplace l'ancien fichier après "
                    "validation.")),
                ("Read", "GET", "Download", (
                    "réponse octet/octet en téléchargement avec Content-Type "
                    "application/octet-stream et nosniff ; l'ACL de la ligne "
                    "s'applique aussi au fichier, un chemin connu ne suffit pas.")),
        ):
            access = plans.access_policies[(entite, action)]
            route = _route(method, chemin, contract_action, entite, False,
                           sorted(access.actors), note=note)
            route["upload"] = {
                "field_name": champ,
                "max_bytes": upload["max_bytes"],
                "accepted_types": list(upload["accepted_types"]),
                "storage": "server_disk_reference",
            }
            routes.append(route)

    # BRIQUE PAIEMENT (point 74). Ces deux routes ne sortent PAS de
    # route_map — elles ne naissent pas d'un workflow mais d'une règle
    # `payable` — et le contrat les ignorait donc. Conséquence concrète :
    # l'IA d'interface ne pouvait pas dessiner le bouton de règlement, et
    # se le serait de toute façon interdit, puisque le contrat lui défend
    # d'appeler un chemin absent de `routes`. Une brique que le contrat ne
    # décrit pas est une brique sans interface.
    payables = plans.payable_by_entity
    # BRIQUE 2a : la DEVISE fait partie de l'interface. Sans elle, l'IA écrit
    # « € » parce que c'est ce qu'elle a vu partout ailleurs, et une boutique
    # de Cotonou affiche des euros sur des francs CFA. L'exposant voyage avec
    # le code : c'est lui qui dit s'il faut diviser `montant_centimes` par cent
    # (euro) ou pas du tout (franc CFA).
    devise = plans.payment_currency or {"code": "EUR", "exponent": 2}
    # BRIQUE 2b : le prestataire fait partie de l'interface. « Payer par
    # carte » et « Payer par Mobile Money » ne se dessinent pas pareil, et
    # l'IA écrirait « carte bancaire » par défaut faute de le savoir.
    prestataire = plans.payment_provider or "stripe"
    for entite, champ in sorted(payables.items()):
        # POINT 87 : sous propriété transitive, « appartient » se lit à travers
        # l'intermédiaire, et un enregistrement dont l'intermédiaire a disparu
        # répond 404. L'interface doit connaître les deux, sinon elle traite un
        # 404 comme une erreur technique là où c'est une réponse métier.
        chaine = plans.transitive_ownership.get(entite)
        premier = chaine["chain"][0] if chaine else None
        via = (f"Ce {entite} appartient à qui possède son/sa "
               f"{premier} : c'est cette chaîne (de profondeur "
               f"{len(chaine['chain'])} maillon(s)) que le 403 vérifie, et "
               f"un {entite} dont le/la {premier} n'existe plus répond "
               f"404. " if premier else "")
        routes.append(_route(
            "POST", f"/{entite.lower()}/{{id}}/paiement", "Pay", entite,
            False, sorted(plans.actors),
            note=(via + "Ouvre une session de règlement pour cet enregistrement. "
                  "AUCUN corps : le montant est lu dans la base depuis "
                  f"`{champ}`, jamais reçu du client. Réponse : {{status, url, "
                  "session_id, montant_centimes, devise, montant} — rediriger "
                  "le navigateur vers `url`. "
                  # Le nom `montant_centimes` est conservé (point 95 : le
                  # renommer casserait le bouton « Payer » de tout projet
                  # existant), mais il ne veut PAS dire « centimes » partout :
                  # c'est l'unité mineure de la devise. Le dire est la seule
                  # façon d'empêcher une interface de diviser par cent un
                  # montant en francs CFA.
                  + (f"Le règlement passe par **{prestataire}** : "
                     + ("le payeur choisit son opérateur de MOBILE MONEY "
                        "(MTN MoMo, Moov, Wave) sur la page du prestataire — "
                        "ne pas écrire « carte bancaire ». "
                        if prestataire == "fedapay"
                        else "le payeur règle par carte sur la page du "
                             "prestataire. "))
                  + f"Les montants sont en **{devise['code']}** : afficher "
                  f"`montant` tel quel avec ce code, et ne JAMAIS diviser "
                  f"`montant_centimes` par cent sans regarder l'exposant — "
                  + ("cette devise n'a pas de sous-unité, les deux champs "
                     "portent la même valeur. " if devise["exponent"] == 0
                     else f"ici l'exposant vaut {devise['exponent']}. ")
                  + "403 si l'enregistrement appartient à "
                  "quelqu'un d'autre, 409 s'il est déjà réglé, 503 si le "
                  "serveur n'a pas de clé de paiement configurée. "
                  # Point 76 : boucler la boucle. Savoir ouvrir un règlement
                  # ne dit pas comment en montrer l'issue ; c'est le champ de
                  # suivi qui la porte, et il n'est PAS à jour au retour du
                  # prestataire (c'est son webhook qui l'écrit, plus tard).
                  f"L'issue se lit dans `{PAYMENT_STATUS_COLUMN}` de "
                  f"{entite} ('en_attente' / 'payee') : ne pas l'annoncer "
                  "payé au retour de l'utilisateur, le webhook du "
                  "prestataire peut n'être pas encore arrivé.")))
    if payables:
        routes.append(_route(
            "POST", "/paiement/webhook", "Webhook", "Paiement", False, [],
            note=("Appelée par le PRESTATAIRE de paiement, jamais par le "
                  "frontend : elle exige une signature que seul le "
                  "prestataire sait produire. Listée ici pour que la liste "
                  "des routes reste exhaustive, pas pour être appelée.")))

    # BRIQUE writableAfterPayment. Cette route est générée hors de route_map,
    # comme celles de paiement ci-dessus : elle doit donc rejoindre le contrat
    # explicitement. Sinon les champs sont bien marqués `postpayment_only`,
    # mais l'interface n'a aucun chemin autorisé pour les modifier.
    postpayment = plans.postpayment_writable_by_entity
    for entite, config in sorted(postpayment.items()):
        fields = list(config["fields"])
        routes.append(_route(
            "PUT", f"/{entite.lower()}/{{id}}/apres-paiement",
            "UpdateAfterPayment", entite, False, [config["actor"]],
            request_fields=fields,
            note=("Écriture réservée au rôle superviseur après règlement : "
                  f"permet de renseigner {', '.join(f'`{f}`' for f in fields)}. "
                  "Tous les champs sont facultatifs dans le corps ; envoyer "
                  "uniquement ceux qui changent. 404 si l'enregistrement "
                  "n'existe pas, 403 pour tout autre rôle.")))

    # BRIQUE B4 : ces parcours ne viennent d'aucun workflow métier. Ils sont
    # donc ajoutés ici, exactement comme les routes de paiement, et seulement
    # si la spec les déclare. Une spec historique ne gagne ainsi ni route ni
    # octet de contrat par défaut.
    auth_features = dict(plans.auth_features or {})
    auth_actors = sorted(plans.actors)
    if auth_features.get("password_reset"):
        routes.extend([
            _route(
                "POST", "/password-reset/request", "PasswordResetRequest",
                "Authentication", True, [], request_fields=["username"],
                note=("Réponse générique et de durée plancher identique que le "
                      "compte existe ou non ; ne jamais annoncer si un message "
                      "est parti.")),
            _route(
                "POST", "/password-reset/confirm", "PasswordResetConfirm",
                "Authentication", True, [],
                request_fields=["username", "token", "password"],
                note=("Jeton opaque à usage unique et durée limitée : le "
                      "serveur ne le renvoie jamais par une route de lecture ; "
                      "un changement de mot de passe ne change pas le rôle.")),
        ])
    if auth_features.get("refresh_tokens"):
        refresh_route = _route(
            "POST", "/refresh", "Refresh", "Authentication", False,
            auth_actors, request_fields=["refresh_token"],
            note=("Présenter le jeton de rafraîchissement opaque, pas le JWT "
                  "d'accès. Chaque succès le révoque et en émet un nouveau ; "
                  "un jeton révoqué ou expiré répond 401."))
        refresh_route["auth_mode"] = "refresh_token"
        routes.append(refresh_route)
    if auth_features.get("totp"):
        routes.extend([
            _route(
                "POST", "/totp/setup", "TotpSetup", "Authentication", False,
                auth_actors,
                note=("Parcours d'activation authentifié, à afficher une seule "
                      "fois ; ne pas transformer sa réponse en route de lecture.")),
            _route(
                "POST", "/totp/enable", "TotpEnable", "Authentication", False,
                auth_actors, request_fields=["code"],
                note=("Active le double facteur après vérification d'un code "
                      "TOTP courant.")),
        ])

    routes.sort(key=lambda r: (r["entity"], r["path"], r["method"]))

    # POINT 72 : plus AUCUNE identité visuelle calculée. Le contrat décrit ce
    # que monl sait — structure, rôles, routes, contenu, intention déclarée —
    # et rien de ce qu'il devinait : ni palette, ni typographies, ni rayon.
    # La direction de design remonte du dialogue, par le brief.
    landing = normalized_ast.get("landing") or {}

    design_skills = select_design_skills(entity_specs, routes)
    message_contracts = [
        {
            "trigger": f"{rule['trigger_entity']}.{rule['trigger_action']}",
            "recipient": "le compte authentifié, via son identifiant email",
            "subject": rule["subject"],
            "body": paragraphes(rule["body"]),
            "delivery": "tentative asynchrone après commit, sans retry ni garantie de remise",
            "note": ("Après le succès de la création, informer l'utilisateur "
                     "qu'une tentative de message a été lancée. Ne pas "
                     "promettre la remise ; les échecs sont journalisés "
                     "côté serveur."),
        }
        for rule in sorted(
            plans.message_rules_by_trigger.values(),
            key=lambda item: (item["trigger_entity"], item["trigger_action"]))
    ]
    business_rules = {
        "public_when": {
            f"{entity}.{action}": dict(condition)
            for (entity, action), condition in sorted(public_conditions.items())
        },
        "once_per": list(plans.once_per_rules),
    }
    if message_contracts:
        business_rules["messages"] = message_contracts
    # BRIQUE 2a : la devise n'est déclarée QUE s'il y a quelque chose à
    # encaisser. Une spec sans `payable` n'ajoute donc aucune clé, et son
    # contrat reste identique à l'octet — condition pour qu'une brique nouvelle
    # ne réécrive pas les projets qui ne s'en servent pas.
    if plans.payable_by_entity:
        business_rules["payment"] = {
            "provider": prestataire,
            "currency": devise["code"],
            # L'exposant est DONNÉ, pas laissé à déduire : c'est lui qui dit si
            # `montant_centimes` se divise par cent ou pas, et une interface
            # qui devrait connaître la liste des devises sans sous-unité
            # finirait par se tromper sur la moins courante.
            "minor_unit_exponent": devise["exponent"],
        }
    auth_contract = {
        # AJOUT (bêta 3) : seuls les rôles marqués 'selfRegister' dans la
        # spec peuvent être choisis à l'inscription — les autres sont
        # provisionnés hors ligne (manage.py) et renvoient 403 ici.
        # L'interface ne doit donc proposer QUE cette liste.
        "register": {"method": "POST", "path": "/register",
                     "response": {"status": "'success'",
                                  "user_id": "int — l'identifiant du compte créé"},
                     "self_register_actors": list(plans.self_register_actors),
                     "body": {"username": _libelle_identifiant(plans.auth_identifier),
                              "password": "str (8+ caractères)",
                              "actor": f"un rôle parmi {list(plans.self_register_actors)}"},
                     # POINT 95 : le champ reste nommé 'username' SUR LE
                     # FIL (le renommer casserait le formulaire de tout
                     # projet existant) — c'est ici que le contrat dit
                     # ce qu'il doit vraiment contenir, et l'IA qui
                     # étiquette l'écran en conséquence.
                     "identifier_forms": list(plans.auth_identifier or ()),
                     "phone_prefix": plans.auth_phone_prefix,
                     "note": _joindre(
                         ("403 si le rôle demandé n'est pas ouvert à l'inscription libre"
                          if plans.self_register_actors else
                          "aucun rôle ouvert : l'inscription est fermée, "
                          "les comptes sont créés par manage.py"),
                         _note_identifiant(plans.auth_identifier,
                                           plans.auth_phone_prefix))},
        # POINT 76 APPLIQUÉ À L'AUTHENTIFICATION. Le contrat doit dire ce que
        # le backend renvoie VRAIMENT, pas seulement qu'il renvoie quelque
        # chose. `returns` annonçait « un token JWT » sans jamais NOMMER la
        # clé JSON : une IA d'interface devait deviner entre `token`,
        # `access_token` et `jwt`. Trompée, elle envoie
        # `Authorization: Bearer undefined` — et c'est le pire cas de figure :
        # aucune exception JavaScript, aucun appel hors contrat, donc LE SMOKE
        # TEST PASSE et personne ne peut se connecter.
        #
        # Que ce soit un oubli et non un choix se lit dans le brief lui-même :
        # la réponse paginée y est nommée au caractère près depuis toujours
        # (`{status, total, limit, offset, data}`), et la brique B4 nomme son
        # `refresh_token`. Seule la réponse d'origine ne s'était jamais
        # décrite.
        #
        # AUCUNE entrée nouvelle dans `_contract_signature` (cli.py), et c'est
        # délibéré : la seule chose qui fasse varier cette forme est
        # `capability refresh_tokens`, dont la configuration est déjà hachée
        # sous « authentification B4 ». Ajouter un second témoin de la même
        # variation ferait rapporter deux fois le même changement.
        "login": {"method": "POST", "path": "/login",
                  "body": {"username": "str", "password": "str"},
                  "response": {
                      "access_token": "str — le JWT, à placer dans l'en-tête "
                                      "Authorization: Bearer",
                      "token_type": "'bearer'"},
                  "returns": "un token JWT dans le champ `access_token` "
                             "(validité 2 h par défaut, "
                             "réglable par MONL_TOKEN_TTL_HOURS)"},
        "logout": {"method": "POST", "path": "/logout",
                   "response": {"status": "'success'", "detail": "str"}},
        "header": "Authorization: Bearer <token> sur toute route non publique",
        "rate_limit": "5 tentatives / 60 s / IP sur /register et /login",
    }
    if auth_features.get("totp"):
        auth_contract["login"]["body"]["totp_code"] = (
            "str (6 chiffres, requis après activation du double facteur)")
    if auth_features.get("refresh_tokens"):
        auth_contract["login"]["returns"] = (
            "un token JWT d'accès dans `access_token` (validité réglable par "
            "MONL_TOKEN_TTL_SECONDS) et un jeton de rafraîchissement opaque "
            "dans `refresh_token`")
        auth_contract["login"]["response"]["refresh_token"] = (
            "str — jeton OPAQUE de rafraîchissement (ce n'est pas un JWT), "
            "à conserver et à rejouer sur POST /refresh")
    b4_contract = {}
    if auth_features.get("lockout"):
        b4_contract["account_lockout"] = {
            "max_attempts": auth_features["lockout"]["max_attempts"],
            "window_seconds": auth_features["lockout"]["window_seconds"],
            "failure_response": "401 générique, identique à un compte inexistant",
        }
    if auth_features.get("password_reset"):
        b4_contract["password_reset"] = {
            "request_path": "/password-reset/request",
            "confirm_path": "/password-reset/confirm",
            "ttl_seconds": auth_features["password_reset"],
            "single_use": True,
            "invalidated_on_password_change": True,
            "privacy": "réponse générique et durée plancher identique, sans énumération",
        }
    if auth_features.get("refresh_tokens"):
        b4_contract["refresh_tokens"] = {
            "path": "/refresh",
            "ttl_seconds": auth_features["refresh_tokens"],
            "rotation": True,
            "access_token_is_jwt": True,
            "refresh_token_is_jwt": False,
        }
    if auth_features.get("totp"):
        b4_contract["totp"] = {
            "setup_path": "/totp/setup",
            "enable_path": "/totp/enable",
            "step_seconds": 30,
            "replay_protection": True,
        }
    if b4_contract:
        auth_contract["features"] = b4_contract
    contract = {
        # Une spec sans B4 conserve la version et la forme historiques à
        # l'octet ; une spec B4 rend son delta visible au frontend.
        "monl_contract_version": CONTRACT_VERSION + (1 if b4_contract else 0),
        "app": app_name,
        "brief": landing.get("brief"),
        "design_skills": design_skills,
        # Contenu éditorial statique (point 55) : aucune entité, aucune route
        # ne peut le porter — c'est la seule matière du contrat qui ne soit
        # pas une donnée.
        "sections": [{"title": s["title"], "body": paragraphes(s["body"])}
                     for s in (landing.get("sections") or [])],
        # POINT 94 : la FAQ est une LISTE, et le contrat doit le dire. Rendue
        # comme une section, elle redevient le pavé de prose qu'elle était —
        # l'interface ne peut pas deviner une structure qu'on ne lui donne pas.
        "faq": [{"question": q["question"], "answer": paragraphes(q["answer"])}
                for q in (landing.get("faq") or [])],
        "source_of_truth": "spec monl (.ml) — ne jamais modifier le backend à la main",
        # AJOUT (brique 13, point 83) : les assets FOURNIS PAR L'HUMAIN. Le
        # contrat n'en disait rien, donc une IA d'interface ne pouvait pas savoir
        # qu'un logo existait — l'en-tête de la boutique de démonstration était
        # un simple mot en texte, faute de mieux. Chaque fichier nommé ici a été
        # vérifié présent à la compilation : l'IA peut s'y référer sans risque.
        "assets": _assets_contract(plans.assets or {}),
        "api": {
            # MÊME ORIGINE, jamais d'URL absolue : 'monl run' monte frontend/
            # sur /site du serveur qui sert déjà l'API (SERVE_WRAPPER, cli.py),
            # donc l'origine de la page EST celle de l'API. Une base absolue
            # codée en dur (ce champ valait "http://127.0.0.1:8000") casse dès
            # que le port change — 'monl run --port', et le port éphémère du
            # smoke test, qui rejetait alors le frontend pour avoir suivi le
            # contrat à la lettre (point 51 du journal).
            "base_url": "",
            "base_url_note": ("même origine que la page : appeler les routes "
                              "en chemins relatifs (/entite), jamais d'URL "
                              "absolue ni de port codé en dur"),
            "auth": auth_contract,
        },
        "actors": sorted(plans.actors),
        "self_register_actors": list(plans.self_register_actors),
        # Règles métier qui ne se réduisent pas à un simple CRUD : le contrat
        # frontend doit savoir qu'un contenu public est filtré par son statut
        # et qu'un compte ne peut créer qu'une occurrence par combinaison de
        # cibles (like/vote, par exemple).
        "business_rules": business_rules,
        "entities": entity_specs,
        "routes": routes,
        "frontend_rules": {
            "output_dir": "frontend/",
            "entry_point": "frontend/index.html",
            "served_at": "/site (par 'monl run', sans toucher app.py)",
            "forbidden": ["modifier app.py, schema.sql, sandbox_ai.py, landing.html, "
                          "dashboard.html ou la spec .ml",
                          "appeler des chemins d'API absents de 'routes'",
                          "envoyer un champ server_generated à la création"]
                         + (["appeler POST /paiement/webhook : c'est la route "
                             "du prestataire de paiement, elle exige une "
                             "signature et refusera toute requête du navigateur"]
                            if payables else []),
        },
    }
    return contract


_LIBELLES_IDENTIFIANT = {"email": "une adresse e-mail",
                         "phone": "un numéro de téléphone"}


def _libelle_identifiant(formes):
    """Ce que le champ 'username' doit RÉELLEMENT contenir (point 95)."""
    formes = [f for f in (formes or [])
              if f in _LIBELLES_IDENTIFIANT]
    if not formes:
        return "str"
    return "str — " + " ou ".join(_LIBELLES_IDENTIFIANT[f] for f in formes)


def _note_identifiant(formes, phone_prefix=None):
    """Sans cette note, l'IA étiquette « nom d'utilisateur » et laisse un champ
    texte libre : l'utilisateur saisit un pseudo, récolte un 422, et l'écran ne
    lui dit pas pourquoi (point 95)."""
    formes = [f for f in (formes or []) if f in _LIBELLES_IDENTIFIANT]
    if not formes:
        return None
    quoi = " ou ".join(_LIBELLES_IDENTIFIANT[f] for f in formes)
    saisie = ("type=\"email\"" if formes == ["email"]
              else "type=\"tel\"" if formes == ["phone"]
              else "un champ texte acceptant les deux")
    prefix_note = (
        f" Pour le téléphone, l'indicatif déclaré est `{phone_prefix}` : "
        "accepter aussi la notation nationale et l'annoncer près du champ."
        if phone_prefix and "phone" in formes else ""
    )
    return (f"IDENTIFIANT : le champ `username` doit contenir {quoi} — 422 "
            f"sinon. L'étiqueter en conséquence à l'inscription ET à la "
            f"connexion (utiliser {saisie}), jamais « nom d'utilisateur ». "
            f"Le serveur met la valeur sous forme canonique (adresse en "
            f"minuscules, numéro réduit à ses chiffres) : deux écritures de la "
            f"même adresse sont le MÊME compte, et la connexion accepte l'une "
            f"comme l'autre.{prefix_note}")


def _note_liberation(regle):
    """Ce que l'interface doit savoir d'une valeur qui libère (point 98)."""
    if not regle:
        return None
    return (f"LIBÉRATION : passer `{regle['field']}` à « {regle['value']} » rend "
            f"ce que les {regle['releases']} liés avaient décompté (le stock, "
            f"typiquement). L'opération n'a lieu qu'à la TRANSITION : y repasser "
            f"une seconde fois ne rend rien de plus. Et c'est un aller SANS "
            f"retour — toute autre valeur est ensuite refusée en 409, car rien "
            f"ne garantit que ce qui a été rendu soit encore disponible. Ne pas "
            f"proposer de réactiver : proposer d'en créer un nouveau.")


def _verrou_paiement(plans: CompilationPlans, entite, inclure_soi=True):
    """Entité dont l'encaissement FIGE les écritures sur 'entite' — elle-même si
    elle est payable, sinon le parent dont elle alimente le total (point 91).

    `inclure_soi=False` pour la CRÉATION : une entité payable ne se verrouille
    pas elle-même à la création (elle n'existe pas encore), seul un parent déjà
    réglé refuse une ligne de plus.

    Source unique partagée avec le générateur : `_payment_locked_parents` est ce
    qui produit réellement les gardes dans app.py. Recalculer la chaîne ici en
    ferait deux vérités, dont l'une finirait fausse."""
    if inclure_soi and entite in plans.payable_by_entity:
        return entite
    verrous = plans.payment_locked_parents.get(entite, ())
    return verrous[0]["entity"] if verrous else None


def _note_verrou(verrou, creation=False):
    if not verrou:
        return None
    action = ("cette route refuse d'y rattacher un enregistrement de plus"
              if creation else "cette route répond 409 et n'écrit rien")
    return (f"VERROU : dès que le/la {verrou} est réglé (payment_status vaut "
            f"'payee'), {action} — 409. Masquer ou "
            f"désactiver l'action sur un enregistrement payé plutôt que de "
            f"laisser l'utilisateur la découvrir refusée — un montant encaissé "
            f"ne se modifie plus, il se rembourse chez le prestataire.")


def _note_message(regle):
    """Note de contrat pour une notification déclenchée par Create."""
    if not regle:
        return None
    return (
        "NOTIFICATION : après le commit réussi de cette création, une tentative "
        f"asynchrone envoie à l'adresse du compte le sujet « {regle['subject']} ». "
        "Afficher qu'une tentative de message a été lancée, sans promettre la "
        "remise : une panne SMTP n'annule pas l'écriture et est journalisée côté "
        "serveur.")


def _joindre(*notes):
    retenues = [n for n in notes if n]
    return " ".join(retenues) if retenues else None


def _note_superviseurs(supers, action_nom):
    """AJOUT (brique 23, point 106) : le rôle superviseur (declare via
    'sharedBy' sur une action regie par 'accessibleBy') transperce le controle
    par colonnes. Note de contrat : l'IA d'interface doit donner à ce rôle la
    vision/maîtrise de TOUT, et aux autres rôles seulement leurs parties."""
    if not supers:
        return None
    roles = ", ".join(supers)
    return (f"SUPERVISION ({action_nom}) : le rôle {roles} accède à TOUS les "
            f"enregistrements, sans restriction de parties. Les autres rôles "
            f"autorisés ici ne voient/modifient que les enregistrements dont "
            f"ils sont une des parties.")


def _route(method, path, action, entity, is_public, actors, request_fields=None, note=None):
    r = {"method": method, "path": path, "action": action, "entity": entity,
         "auth_required": not is_public, "allowed_actors": actors}
    if request_fields is not None:
        r["request_fields"] = request_fields
    if note:
        r["note"] = note
    return r


def _list_query_contract(plans: CompilationPlans, entity):
    """Contrat explicite des capacités de liste déclarées pour une entité."""
    model = plans.entity_models[entity]
    filters = []
    for field in plans.filterable_fields.get(entity, ()):
        policy = model.fields[field]
        values = list(policy.allowed_values) if policy.allowed_values else None
        if policy.type == "Boolean":
            values = ["true", "false"]
        filters.append({
            "field": field,
            "parameter": field,
            "kind": "exact",
            "allowed_values": values,
        })
    sort_fields = list(plans.sortable_fields.get(entity, ()))
    result = {}
    if filters:
        result["filters"] = filters
    if sort_fields:
        result["sort"] = {
            "parameter": "sort",
            "direction_parameter": "direction",
            "fields": sort_fields,
            "directions": ["asc", "desc"],
        }
    return result


def _note_list_query(query):
    """Texte court transmis à l'IA frontend avec le contrat JSON."""
    if not query:
        return None
    notes = []
    if query.get("filters"):
        filtres = []
        for item in query["filters"]:
            valeurs = item["allowed_values"]
            suffixe = (" parmi " + ", ".join(repr(v) for v in valeurs)
                       if valeurs is not None else " une valeur exacte du type du champ")
            filtres.append(f"paramètre {item['parameter']}{suffixe}")
        notes.append("FILTRAGE exact, seulement sur les champs déclarés : "
                     + "; ".join(filtres))
    if query.get("sort"):
        tri = query["sort"]
        notes.append("TRI : paramètre sort parmi "
                     + ", ".join(tri["fields"])
                     + ", avec direction=asc ou direction=desc. Aucun autre "
                     "champ, opérateur ou langage de recherche n'est accepté.")
    return " ".join(notes)


def _client_supplied_fks(plans: CompilationPlans, entity):
    """Colonnes de clé étrangère que le CLIENT doit envoyer à la création.

    Reproduit À L'IDENTIQUE ce que generator/schemas.py inscrit dans le
    schéma Pydantic — et s'appuie sur ses méthodes, jamais sur une logique
    parallèle. Le contrat les ignorait : il annonçait `POST /comment` avec le
    seul champ `content` alors que le backend exigeait aussi `article_id`,
    et tout frontend fidèle au contrat récoltait un 422 (point 57).

    Deux origines distinctes, même conséquence pour le client :
      - la cible d'un compteur (`increments`/`decrements`) : « j'apprécie CE
        post » est un choix de l'appelant, pas une propriété déduite ;
      - les parents autres que le propriétaire : le propriétaire se peuple
        depuis le JWT, le reste doit être dit (un commentaire et SON article).
    """
    colonnes = []
    owner = plans.incoming_relations.get(entity)
    owners = {
        r["target_entity"] for r in plans.reputation_rules_by_trigger.get(entity, ())
    }
    if owner and owner["source"] in owners:
        colonnes.append(owner["fk_column"])
    colonnes.extend(plans.client_foreign_keys.get(entity, ()))
    return colonnes


def _creatable_fields(entity_spec):
    if not entity_spec:
        return []
    return ([f["name"] for f in entity_spec["fields"]
             if not f["server_generated"] and not f.get("postpayment_only")
             and not f.get("upload")]
            + list(entity_spec.get("client_foreign_keys", [])))


def _assets_contract(assets):
    """Section 'assets' du contrat : où sont les fichiers de l'humain, et
    lesquels sont déclarés. `served_at` dit l'URL réelle, pas le chemin disque —
    c'est celle-là que le navigateur demandera."""
    dossier = assets.get("dir") or "assets"
    contrat = {
        "dir": dossier,
        "served_at": f"/site/{dossier}/",
        "note": (f"Fichiers fournis par l'humain (photos, logo). Les référencer en chemin "
                 f"RELATIF depuis la page : '{dossier}/…'. Ne jamais les modifier ni les "
                 f"déplacer : ils ne sont pas produits par l'IA, et ce dossier vit HORS de "
                 f"frontend/ pour survivre à une reconstruction du frontend."),
    }
    for cle in ("logo", "favicon"):
        if assets.get(cle):
            contrat[cle] = f"{dossier}/{assets[cle]}"
    if "logo" in contrat:
        contrat["logo_note"] = ("Un vrai logo est fourni : l'utiliser dans l'en-tête plutôt "
                                "qu'un mot-symbole en texte.")
    return contrat


def _render_prompt(contract):
    routes_lines = []
    skills_block = render_skill_block(contract.get("design_skills", ["monl-showcase"]))
    for r in contract["routes"]:
        if not r["auth_required"]:
            auth = "public"
        elif r["allowed_actors"]:
            auth = f"JWT ({', '.join(r['allowed_actors'])})"
        else:
            # Point 74 : le webhook de paiement est authentifié, mais pas par
            # un JWT — par une signature du prestataire. Annoncer « JWT () »
            # laisserait croire à une route ouverte à tout compte connecté.
            auth = "signature du prestataire, pas un JWT"

        # Le corps attendu n'apparaissait NULLE PART dans le brief : l'IA
        # devait le déduire de la liste des champs, sans jamais voir les
        # colonnes de rattachement (article_id d'un commentaire). Elle ne
        # pouvait pas les deviner, et le serveur répondait 422 (point 57).
        corps = (f" — corps : `{{{', '.join(r['request_fields'])}}}`"
                 if r.get("request_fields") else "")
        if r.get("upload"):
            upload = r["upload"]
            corps = (f" — multipart/form-data, champ fichier `{upload['field_name']}`, "
                     f"{upload['max_bytes']} octets maximum, types : "
                     f"{', '.join(upload['accepted_types'])}")
        # Point 74 : les notes de route existaient dans le contrat JSON mais
        # n'atteignaient PAS le brief — or c'est le brief que l'IA lit. La
        # forme de la réponse paginée y manquait depuis toujours, et la
        # marche à suivre du règlement y aurait manqué de même.
        note = f" — {r['note']}" if r.get("note") else ""
        routes_lines.append(f"- `{r['method']} {r['path']}` — {r['action']} "
                            f"{r['entity']} — {auth}{corps}{note}")
    entities_lines = []
    ROLE_LABELS = {"title": "TITRE — l'identifie d'un coup d'œil",
                   "media": "MÉDIA — l'image de l'enregistrement",
                   "description": "DESCRIPTION — le texte long",
                   "price": "PRIX",
                   "stock": "DISPONIBILITÉ — à montrer près du prix, pas en note de bas de page",
                   "category": "CATÉGORIE — bon pour un filtre",
                   "meta": "méta — information secondaire"}
    for ent, spec in contract["entities"].items():
        flags = []
        for f in spec["fields"]:
            marks = []
            if f.get("role"):
                marks.append(ROLE_LABELS[f["role"]])
            if f["required"]:
                marks.append("requis")
            if f["hidden_in_reads"]:
                marks.append("jamais renvoyé en lecture")
            if f["server_generated"]:
                marks.append("généré serveur — NE PAS envoyer")
            if f.get("postpayment_only"):
                marks.append("modifiable uniquement via la route après paiement")
            if f.get("upload"):
                upload = f["upload"]
                marks.append(
                    f"Upload multipart via POST/GET sur le champ `{upload['field_name']}`, "
                    f"{upload['max_bytes']} octets maximum ; types : "
                    f"{', '.join(upload['accepted_types'])}. Ne pas l'envoyer en JSON.")
            if f["categorized_in_reads"]:
                marks.append("lu comme libellé de catégorie")
            # BRIQUE 19 (point 96) : l'IA lit le brief, pas le JSON. Y écrire la
            # liste, c'est la différence entre un menu déroulant et un champ
            # texte qui récolte un 422 sur la valeur que l'utilisateur invente.
            if f.get("allowed_values"):
                marks.append("MENU DÉROULANT, valeurs imposées (422 sinon) : "
                             + ", ".join(f"« {v} »" for v in f["allowed_values"]))
            # Point 76 : dire à quoi sert le champ, pas seulement qu'il existe.
            # Sans les valeurs possibles, l'IA doit deviner quoi comparer pour
            # savoir si c'est réglé — et devinera 'paid'.
            if f.get("note"):
                marks.append(f["note"])
            suffix = f" ({'; '.join(marks)})" if marks else ""
            flags.append(f"  - `{f['name']}: {f['type']}`{suffix}")
        forme = ARCHETYPE_GUIDANCE[spec["archetype"]]
        anatomie = ARCHETYPE_ANATOMY[spec["archetype"]]
        attendus = "\n".join(f"  - {a}" for a in anatomie["attendus"])
        # POINT 88 : les colonnes de liaison sortent dans les réponses (SELECT *)
        # mais n'apparaissaient QUE dans le JSON. Or c'est ici que se joue la
        # jointure la plus facile à rater — celle qui rattache un enregistrement
        # à son titulaire — et une page d'administration ne fait presque que ça.
        liaisons = ""
        if spec["foreign_keys"]:
            lignes_liens = [
                f"  - `{li['column']}` → "
                + (f"identifiant de COMPTE. Retrouver la fiche {li['references']} "
                   f"dont `{li['column']}` porte la MÊME valeur — pas celle dont "
                   f"`id` la porte." if li["references_account"]
                   else f"`id` d'un enregistrement {li['references']}.")
                for li in spec["foreign_keys"]
            ]
            liaisons = ("\nColonnes de liaison présentes dans les réponses :\n"
                        + "\n".join(lignes_liens))
        entities_lines.append(
            f"### {ent}\n_Forme conseillée : {forme}._\n"
            f"_Proche de : {anatomie['voisins']}._\n"
            f"Ce qu'un visiteur s'attend à y trouver :\n{attendus}\n"
            + "\n".join(flags) + liaisons)

    brief_line = (f"\n**Brief produit :** {contract['brief']}\n" if contract.get("brief") else "")

    # Contenu éditorial (point 55). Écrit en toutes lettres que ce texte doit
    # être RENDU tel quel : c'est du contenu, pas une consigne de style, et
    # rien d'autre dans le contrat n'en fournit.
    sections_block = ""
    if contract.get("sections"):
        corps = "\n\n".join(f"### {s['title']}\n{s['body']}"
                            for s in contract["sections"])
        sections_block = (
            "\n## Contenu éditorial à publier tel quel\n"
            "Ces textes sont fournis par l'auteur du projet : ils doivent "
            "apparaître dans l'interface, chacun dans sa propre section, avec "
            "le titre donné. Ne pas les réécrire, ne pas les inventer ailleurs "
            "— aucune route d'API ne les sert, ils n'existent qu'ici.\n\n"
            # Point 59 : sans cette phrase, ces textes finissaient derrière un
            # lien de menu, sur une page à part. Un visiteur qui n'ouvre que
            # l'accueil ne les voyait jamais — pour un « à propos », c'est
            # manquer sa raison d'être.
            "**Sur la page d'accueil, pas seulement derrière un lien.** Chaque "
            "section doit être lisible au fil de l'accueil. Un texte long peut "
            "y figurer en version courte et se prolonger sur sa propre page, "
            "mais il ne doit jamais en être absent.\n\n"
            + corps + "\n")

    # POINT 94 : la FAQ, dite comme une LISTE. Rendue dans la même rubrique que
    # les sections, elle redevenait un pavé de prose — c'est exactement le
    # défaut constaté sur SneakerLab, où quatre questions tenaient dans une
    # seule chaîne et sortaient collées en un paragraphe. L'interface était
    # fidèle : c'est le contrat qui ne savait pas dire « questions/réponses ».
    faq_block = ""
    if contract.get("faq"):
        couples = "\n\n".join(f"**{q['question']}**\n{q['answer']}"
                              for q in contract["faq"])
        faq_block = (
            "\n## Questions fréquentes — une LISTE, pas un texte suivi\n"
            "Chaque couple ci-dessous est une question et sa réponse, dans "
            "l'ordre voulu par l'auteur. Les rendre comme des entrées "
            "DISTINCTES et repérables au premier coup d'œil — accordéon, liste "
            "de définitions, ou question en gras suivie de sa réponse. Jamais "
            "en un seul paragraphe : une FAQ dont les questions se touchent ne "
            "se lit pas, et c'est le format qui porte l'information autant que "
            "le texte.\n\n"
            "Ne pas réécrire ces textes, ne pas en ajouter, ne pas les "
            "réordonner.\n\n"
            + couples + "\n")
    # POINT 72 — monl ne décide RIEN du visuel. Il ne calculait pas une
    # palette pour rendre service : il la calculait pour que deux projets ne
    # se ressemblent pas (point 20). Mais ce que le compilateur devine du
    # goût d'un projet, il le devine mal — et une suggestion posée dans le
    # contrat pèse, même annoncée comme facultative. La seule direction
    # légitime est celle que l'auteur a formulée lui-même, dans le dialogue :
    # elle voyage dans le brief, pas dans un bloc de couleurs inventé.
    design_block = """## Direction de design — elle ne vient PAS de monl

Le compilateur n'a **aucun** avis sur le visuel : ni palette, ni typographie,
ni rayon, ni grille, ni mise en page. Il n'en propose pas davantage qu'il n'en
impose — il ne sait pas à quoi ce projet doit ressembler, et il ne fait pas
semblant de le savoir.

La direction est celle que l'auteur a formulée : le **brief** ci-dessus
(intention, registre, place des images), la forme conseillée de chaque entité,
le contenu éditorial. C'est cela qu'il faut servir. Pour le reste — familles
typographiques, gamme chromatique, échelles, rythme, surfaces sombres ou
claires — la décision vous appartient entièrement, c'est votre métier.

Deux exigences seulement, et ce ne sont pas des questions de goût :
- **Contraste** : au moins 4,5:1 entre un texte et son fond (WCAG AA), 3:1
  pour les grands titres. Une interface illisible n'est pas un parti pris.
- **Autonomie** : tout vit dans `frontend/`, aucune ressource distante (voir
  les règles ci-dessous). Les familles déjà présentes sur les machines
  suffisent à porter une identité — c'est leur traitement qui la fait.
"""

    express_block = ""
    if "mode express" in (contract.get("brief") or "").lower():
        express_block = """
## Mode express — compléter la matière éditoriale et visuelle

L'auteur a volontairement fourni un brief court. À partir de celui-ci et de
la catégorie décrite par le contrat :
- rédiger les textes d'interface et de présentation nécessaires (accroche,
  bénéfices, méthode, réassurance, appels à l'action, textes d'états vides) ;
- construire une page dense en blocs réellement utiles, pas une simple liste
  suivie d'un formulaire ;
- créer dans `frontend/` des illustrations `.svg` originales et cohérentes
  lorsque le projet appelle des images. Elles sont locales, accessibles et
  peuvent servir aux blocs éditoriaux ; ne pas embarquer de photo distante ;
- rendre les vraies images et les vraies fiches renvoyées par l'API quand elles
  existent. Ne jamais fabriquer côté navigateur de faux produits, projets,
  rendez-vous ou autres enregistrements qui contrediraient la base.

Cette liberté concerne la rédaction et la présentation seulement. Elle
n'autorise aucune route, donnée métier, permission ou promesse absente du
contrat.
"""

    # POINT 74 : la note de la route le dit déjà, mais c'est ici que l'IA lit
    # ce qui n'est pas négociable. Le règlement est le seul parcours du
    # frontend où une erreur d'interface coûte de l'argent — il mérite sa
    # ligne, pas seulement une mention dans l'inventaire des routes.
    paiement = [r for r in contract["routes"] if r["action"] == "Pay"]
    paiement_block = ""
    if paiement:
        chemins = ", ".join(f"`{r['path']}`" for r in paiement)
        paiement_block = (
            f"\n- Règlement : {chemins} s'appelle **sans aucun corps** — le "
            "montant vient de la base, pas de vous. Rediriger ensuite le "
            "navigateur vers l'`url` renvoyée. Ne JAMAIS appeler "
            "`POST /paiement/webhook` : c'est la route du prestataire, elle "
            "exige une signature et refusera toute requête du navigateur.")

    identifiant_note = contract["api"]["auth"]["register"].get("note")
    identifiant_block = (f"\n- {identifiant_note}" if identifiant_note else "")
    auth_features = contract["api"]["auth"].get("features") or {}
    auth_feature_lines = []
    if "account_lockout" in auth_features:
        lockout = auth_features["account_lockout"]
        auth_feature_lines.append(
            f"- Verrouillage de compte : après {lockout['max_attempts']} échecs "
            f"dans {lockout['window_seconds']} s, afficher l'échec générique "
            "sans tenter de deviner si l'adresse existe.")
    if "password_reset" in auth_features:
        reset = auth_features["password_reset"]
        auth_feature_lines.append(
            f"- Réinitialisation : afficher les deux écrans "
            f"{reset['request_path']} puis {reset['confirm_path']}. "
            "La première réponse est volontairement générique ; le jeton reçu "
            "par le canal de message se rejoue dans le second écran une seule fois "
            "avant expiration.")
    if "refresh_tokens" in auth_features:
        refresh = auth_features["refresh_tokens"]
        auth_feature_lines.append(
            f"- Session : stocker et rejouer le jeton opaque refresh_token sur "
            f"{refresh['path']} ; chaque succès le remplace. Ne jamais l'envoyer "
            "comme Authorization: Bearer, qui reste réservé au JWT d'accès.")
    if "totp" in auth_features:
        totp = auth_features["totp"]
        auth_feature_lines.append(
            f"- Double facteur : proposer l'activation via {totp['setup_path']} "
            f"puis {totp['enable_path']}, et demander totp_code à la connexion "
            "après activation. Un code ne se rejoue pas.")
    auth_feature_block = ("\n" + "\n".join(auth_feature_lines)
                          if auth_feature_lines else "")

    return f"""# Brief frontend — {contract['app']} (généré par monl)
{brief_line}
Vous êtes une IA spécialisée en interfaces. Générez le frontend de
l'application **{contract['app']}** en respectant STRICTEMENT le contrat
ci-dessous. Le backend existe déjà et ne doit pas être modifié.

{design_block}{skills_block}{express_block}
## Règles non négociables
- Écrire tous les fichiers dans `frontend/`, avec `frontend/index.html`
  comme point d'entrée (HTML/CSS/JS statiques, aucun build requis).
- Frontend AUTONOME : aucune librairie CDN, aucun script externe — tout le
  JS/CSS vit dans `frontend/` (c'est ce qui rend le smoke test possible).
- Iconographie : aucune librairie d'icônes (Font Awesome, Material, Lucide,
  Bootstrap Icons…) n'est atteignable, puisque aucun CDN ne l'est — et une
  police d'icônes distante ne le serait pas davantage. Ce qui FONCTIONNE et est
  servi : le SVG écrit EN LIGNE dans le HTML, et les fichiers `.svg` déposés
  dans `frontend/` (extension en liste blanche). monl ne dit pas s'il faut des
  icônes, ni lesquelles, ni dans quel style — il dit seulement par quel moyen
  elles sont possibles, parce que la règle ci-dessus, lue seule, laisse croire
  qu'elles ne le sont pas.
- N'appeler QUE les routes listées plus bas, en chemins RELATIFS —
  `fetch('/entite')`, JAMAIS `fetch('http://127.0.0.1:8000/entite')`. Le
  frontend est servi sur `/site` par le serveur qui porte l'API : l'origine
  est déjà la bonne. Une URL absolue avec un port codé en dur casse au
  premier `monl run --port` et fait échouer le smoke test.
- Authentification : `POST /register` (username, password 8+, actor parmi
  {contract['self_register_actors'] or "AUCUN — inscription fermée, ne pas "
   "construire de formulaire d'inscription"}) → `{{status, user_id}}`,
  `POST /login` → `{{access_token, token_type}}`. Le JWT est dans
  `access_token` — le lire sous CE nom exact, puis l'envoyer en en-tête
  `Authorization: Bearer <access_token>` sur toute route non publique. Lire
  un autre nom ne lève aucune erreur : la requête part avec
  `Bearer undefined` et le serveur répond 401 sans que rien ne dise pourquoi. Les rôles déclarés mais absents de cette liste
  ({[a for a in contract['actors'] if a not in contract['self_register_actors']] or "aucun"})
  sont provisionnés hors ligne : ils se connectent par `/login`, jamais par
  `/register`.{identifiant_block}{auth_feature_block}
- Les routes de liste sont paginées : `?limit=&offset=`, réponse
  `{{status, total, limit, offset, data}}`.
- Ne jamais envoyer un champ marqué « généré serveur » à la création.
- Ne pas modifier `app.py`, `schema.sql`, la spec `.ml` ni les autres
  artefacts monl.{paiement_block}

{sections_block}{faq_block}
## Entités
{chr(10).join(entities_lines)}

## Routes disponibles
{chr(10).join(routes_lines)}

## Contrat machine-lisible complet
Le fichier `frontend_contract.json` (même dossier) contient la version
exhaustive de ce contrat — s'y référer en cas de doute.

---

## Vous lisez ceci dans une conversation (claude.ai, sans clé API) ?
Générez le frontend demandé, puis rendez-le sous une forme téléchargeable :
soit un fichier ZIP contenant les fichiers (index.html à la racine ou dans
un unique sous-dossier), soit un `index.html` AUTONOME (CSS et JS inclus
dans le fichier). L'utilisateur l'installera ensuite avec :
`monl import <fichier téléchargé> <dossier du projet>` — monl
re-vérifiera automatiquement l'ensemble (cohérence + smoke test) et, en cas
d'erreurs, elles vous seront recollées ici pour correction.
"""


PROJECT_CLAUDE_MD_MARKER = "<!-- généré par monl — orchestration frontend -->"

PROJECT_CLAUDE_MD = """{marker}
# {app} — mémoire de projet pour Claude Code

Ce dossier est un projet monl : le backend (app.py, schema.sql,
sandbox_ai.py) est GÉNÉRÉ depuis la spec `spec.ml` (ou le fichier .ml
présent) — la spec est la source de vérité, le backend un artefact scellé.

## Ton rôle ici : le FRONTEND, rien d'autre

- Lis `FRONTEND_PROMPT.md` : c'est le contrat complet (routes, auth,
  champs, direction de design). Version machine-lisible :
  `frontend_contract.json`.
- Écris UNIQUEMENT dans `frontend/`, point d'entrée `frontend/index.html`.
  HTML/CSS/JS statiques, AUTONOMES (aucun CDN, aucun script externe —
  condition de vérifiabilité du smoke test).
- Pour faire ÉVOLUER un frontend existant après un changement de spec,
  lis `FRONTEND_UPDATE_PROMPT.md` (généré par `monl update`) et modifie
  l'existant, ne réécris pas de zéro.

## Interdits absolus

Ne JAMAIS modifier : la spec `.ml`, `app.py`, `schema.sql`,
`sandbox_ai.py`, `frontend_contract.json`, `FRONTEND_PROMPT.md`,
`monl.json`, `.jwt_secret`. Si le backend semble devoir changer, c'est
la SPEC qu'il faut faire évoluer (par l'utilisateur), puis `monl update`.

## Vérifier ton travail

`monl run . --check` (si `monl` est sur le PATH) exécute la
vérification complète : cohérence statique + smoke test comportemental
(serveur éphémère, routes du contrat éprouvées en HTTP réel, ton
`index.html` exécuté dans jsdom). Corrige jusqu'à ce que ce soit vert —
`monl run .` refusera de lancer tant que le smoke test échoue.
"""


def write_project_claude_md(app_name, output_dir):
    """Écrit le CLAUDE.md du PROJET (pas celui du dépôt monl) — c'est lui
    qui cadre une session 'cd projet && claude'. Jamais écrasé s'il a été
    repris en main par l'utilisateur (absence du marqueur)."""
    path = os.path.join(output_dir, "CLAUDE.md")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            if PROJECT_CLAUDE_MD_MARKER not in fh.read():
                return  # CLAUDE.md personnel de l'utilisateur : intouchable
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(PROJECT_CLAUDE_MD.format(marker=PROJECT_CLAUDE_MD_MARKER, app=app_name))


def generate_frontend_contract(normalized_ast: CompilationIR, plans_or_generator, output_dir):
    """Écrit le contrat depuis l'IR et les plans partagés, transactionnellement."""
    contract = build_contract(normalized_ast, plans_or_generator)

    target_dir = os.path.abspath(output_dir)
    with staging_directory(target_dir) as temporary:
        copy_preserved_files(target_dir, temporary, ("CLAUDE.md",))
        contract_path = os.path.join(temporary, CONTRACT_FILENAME)
        with open(contract_path, "w", encoding="utf-8") as fh:
            json.dump(contract, fh, ensure_ascii=False, indent=2, sort_keys=True)
        with open(os.path.join(temporary, PROMPT_FILENAME), "w", encoding="utf-8") as fh:
            fh.write(_render_prompt(contract))
        write_project_claude_md(contract["app"], temporary)
        publish_files(temporary, target_dir, FRONTEND_ARTIFACTS)
    return contract


def contract_sha256(output_dir):
    path = os.path.join(output_dir, CONTRACT_FILENAME)
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()
