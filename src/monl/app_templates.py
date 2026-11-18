# ─────────────────────────────────────────────────────────────────────
# CATALOGUE DE MODÈLES D'APPLICATIONS — point 45 du journal. Le dialogue
# ne part plus d'une page blanche : il ouvre sur les 10 types
# d'applications les plus construits par les développeurs web. Choisir un
# modèle pré-remplit entités, acteurs, règles et données de démonstration
# RÉALISTES, puis des questions de suivi PROPRES AU MODÈLE affinent
# (catégories ? stock ? commentaires ? likes ?). « Partir de zéro » reste
# disponible et conserve le dialogue libre intact.
#
# Chaque modèle est de la DONNÉE, pas du code : le dialogue les assemble
# via le même émetteur déterministe, et la spec finale repasse par le vrai
# parseur + l'audit AST — un modèle du catalogue ne peut pas produire une
# spec cassée sans casser les tests (chaque modèle est compilé dans
# tests/test_app_templates.py, chemins « tout non » ET « tout oui »).
#
# Structure d'un modèle :
#   name / hint         : ce qu'affiche le menu
#   entities            : {Nom: {"fields": [(champ, Type)],
#                                "manager": acteur, "readers": [acteurs],
#                                "public_read": bool, "public_create": bool,
#                                "owned": bool}}  # ownedBy par le manager
#   actors              : liste d'acteurs
#   relations           : [(source, type, cible)] déclarées en plus de
#                         celles que 'owned' crée automatiquement
#   extra_rules         : lignes de règles émises telles quelles (briques
#                         avancées : increments, hidden, categorized…)
#   seeds               : {Entité: [ {champ: valeur} ]} — données de démo
#                         réalistes (sinon repli sur le seed générique)
#   sections            : [{"title": titre de rubrique, "ask": ce qu'on
#                         attend dedans}] — rubriques éditoriales que les
#                         recensements publics donnent comme attendues sur un
#                         site de ce genre (point 61). Le dialogue en demande
#                         DIRECTEMENT le texte, il ne demande plus s'il en
#                         faut ; une réponse vide passe la rubrique. Liste
#                         vide = outil interne, aucune rubrique standard.
#   followups           : [{"ask": question o/n, "effects": {...}}] où les
#                         effets fusionnent dans le modèle si "o" :
#                         add_fields / add_entities / add_relations /
#                         add_rules / add_seeds
# ─────────────────────────────────────────────────────────────────────

def _img(_seed=None):
    """Champ d'illustration d'une fiche de démonstration : VIDE, et c'est le
    sujet de la brique.

    Ces fiches portaient une URL `picsum.photos` (et `loremflickr` dès qu'un
    sujet était choisi). Le résultat contredisait la promesse la plus nette du
    projet : une application monl est AUTONOME et son compilateur n'appelle
    jamais l'extérieur — mais la toute première page que le prospect ouvrait
    allait chercher ses images chez un tiers. Hors ligne, sur une connexion
    lente ou sur un forfait de données compté, la vitrine s'ouvrait cassée.

    Trois raisons de laisser VIDE plutôt que de mettre autre chose :

    * une image en `data:` URI tiendrait dans le champ, mais mettrait 250
      caractères illisibles dans chaque ligne `seed` de la spec — or la spec
      est faite pour être lue et modifiée à la main, et `monl content export`
      la déverse en CSV ;
    * une photo livrée avec monl serait un choix VISUEL du compilateur, ce que
      le point 72 lui interdit explicitement ;
    * le vrai chemin d'une vraie photo existe déjà et il est documenté :
      `monl assets add <fichier> --for "<fiche>"` (brique 13, point 84), qui
      vérifie le fichier à la compilation au lieu d'espérer un serveur distant.

    Le sujet d'illustration demandé par le dialogue n'est pas perdu : il part
    dans le brief du contrat, pour que l'IA d'interface sache ce que les
    visuels doivent évoquer (voir `_emit_spec`).
    """
    return ""


TEMPLATES = [
    {
        "name": "Portfolio / showcase site",
        "hint": "public project gallery + administration area",
        "actors": ["Admin"],
        "entities": {
            "Project": {"fields": [("title", "String"), ("description", "Text"),
                                   ("imageUrl", "String")],
                        "manager": "Admin", "readers": [], "public_read": True,
                        "public_create": False, "owned": False},
            # ACQUIS (point 60) : « a clear contact method » figure dans toutes
            # les listes d'essentiels d'un portfolio — c'était une question.
            "Message": {"fields": [("author", "String"), ("email", "Email"),
                                   ("content", "Text")],
                        "manager": "Admin", "readers": [], "public_read": False,
                        "public_create": True, "owned": False},
        },
        "relations": [], "extra_rules": [],
        # POINT 61 : « about » et une offre lisible figurent dans toutes les
        # listes d'essentiels d'un portfolio, au même titre que la galerie.
        "sections": [
            {"title": "About",
             "ask": "who you are, since when, what sets your work apart"},
            {"title": "Services",
             "ask": "what you concretely offer, and for whom"},
        ],
        "seeds": {"Project": [
            {"title": "Aurora redesign", "description": "Complete identity for a cosmetics brand.", "imageUrl": _img("aurora")},
            {"title": "Meridian app", "description": "Mobile habit-tracking application.", "imageUrl": _img("meridian")},
            {"title": "Horizon site", "description": "Editorial site for a music festival.", "imageUrl": _img("horizon")},
        ]},
        "followups": [
            {"ask": "Sort the projects by category?",
             "effects": {"add_fields": {"Project": [("category", "String")]},
                         "add_seed_fields": {"Project": {"category": ["Identity", "Product", "Web"]}}}},
        ],
    },
    {
        "name": "Blog",
        "hint": "public articles, readers' comments",
        "actors": ["Author", "Reader", "Moderator"],
        "entities": {
            # ACQUIS (point 60) : l'auteur humanise le billet, la date dit si
            # l'information est encore d'actualité. Les deux sont donnés comme
            # essentiels par l'anatomie d'un article ; la date était une
            # question, l'auteur manquait purement et simplement.
            "Article": {"fields": [("title", "String"), ("content", "Text"),
                                   ("imageUrl", "String"), ("author", "String"),
                                   ("publishedOn", "String"), ("status", "String")],
                        "manager": "Author", "readers": [], "public_read": True,
                        "public_create": False, "owned": False},
            "Report": {"fields": [("reason", "Text"), ("status", "String")],
                        "manager": "Moderator", "readers": [], "public_read": False,
                        "public_create": False, "owned": False},
        },
        "relations": [("Article", "hasMany", "Report")],
        "extra_rules": [
            'rule Article.status oneOf "published", "hidden"',
            'rule Article.Read publicWhen status "published"',
            'rule Article.Read sharedBy Moderator',
            'rule Article.Update sharedBy Author, Moderator',
            'rule Report.status oneOf "open", "resolved", "dismissed"',
            'rule Report.Create sharedBy Reader, Moderator',
        ],
        "extra_workflows": [
            {"name": "SubmitReport", "actor": "Reader",
             "actions": [("Create", "Report")]},
            {"name": "ModerateBlog", "actor": "Moderator",
             "actions": [("Read", "Article"), ("Update", "Article"),
                          ("Read", "Report"), ("Update", "Report"),
                          ("Delete", "Report")]},
        ],
        # POINT 61 : la bio de l'auteur est donnée comme page centrale d'un
        # site d'écriture ; la ligne éditoriale dit au lecteur s'il est au bon
        # endroit — ce qu'aucune liste d'articles ne raconte.
        "sections": [
            {"title": "About the author",
             "ask": "who writes here, and why people should read you"},
            {"title": "Editorial line",
             "ask": "what this blog is about, how often, for which reader"},
        ],
        "seeds": {"Article": [
            {"title": "Why I left frameworks", "content": "Lessons learned after a year of vanilla.", "imageUrl": _img("blog1"), "author": "Camille Roy", "publishedOn": "2026-05-12", "status": "published"},
            {"title": "The sustainable remote-work guide", "content": "Three years apart, what really works.", "imageUrl": _img("blog2"), "author": "Camille Roy", "publishedOn": "2026-06-03", "status": "published"},
            {"title": "Learning in public", "content": "Documenting your progress changes everything.", "imageUrl": _img("blog3"), "author": "Sacha Nedel", "publishedOn": "2026-07-01", "status": "published"},
        ]},
        "followups": [
            {"ask": "Let registered readers comment (each manages their own comments)?",
             "effects": {"add_actors": ["Reader"],
                         "add_entities": {"Comment": {"fields": [("content", "Text")],
                                                      "manager": "Reader", "readers": ["Author"],
                                                      "public_read": True, "public_create": False, "owned": True}},
                         "add_relations": [("Article", "hasMany", "Comment")]}},
        ],
    },
    {
        "name": "Online shop",
        "hint": "public catalog, customers' orders",
        "actors": ["Admin", "Customer"],
        "entities": {
            # ACQUIS (point 60) : la disponibilité figure au-dessus de la ligne
            # de flottaison d'une fiche produit, au même titre que le nom, le
            # prix et l'image. C'était une question.
            "Product": {"fields": [("name", "String"), ("price", "Money"),
                                   ("description", "Text"), ("imageUrl", "String"),
                                   ("stock", "Integer")],
                        "manager": "Admin", "readers": ["Customer"], "public_read": True,
                        "public_create": False, "owned": False},
            "Order": {"fields": [("total", "Money"), ("status", "String")],
                      "manager": "Customer", "readers": ["Admin"], "public_read": False,
                      "public_create": False, "owned": True},
        },
        "relations": [], "extra_rules": [],
        # POINT 61 : livraison/retours et FAQ sont les deux textes que les
        # recensements e-commerce placent au-dessus du reste — ils lèvent les
        # objections d'achat, qu'aucune fiche produit ne peut porter.
        "sections": [
            {"title": "About the shop",
             "ask": "who makes or selects, where the products come from"},
            {"title": "Shipping and returns",
             "ask": "lead times, fees, return conditions"},
            {"title": "Frequently asked questions",
             "ask": "the questions customers ask before buying"},
        ],
        "seeds": {"Product": [
            {"name": "Kyoto teapot", "price": 39.5, "description": "Enameled cast iron, 0.8 L.", "imageUrl": _img("shop1"), "stock": 12},
            {"name": "Duo cup", "price": 18.0, "description": "Handmade stoneware, set of two.", "imageUrl": _img("shop2"), "stock": 40},
            {"name": "Sencha green tea", "price": 12.5, "description": "Spring harvest, 100 g.", "imageUrl": _img("shop3"), "stock": 87},
        ]},
        "followups": [
            {"ask": "Sort the products by category?",
             "effects": {"add_fields": {"Product": [("category", "String")]},
                         "add_seed_fields": {"Product": {"category": ["Teapots", "Cups", "Teas"]}}}},
        ],
    },
    {
        "name": "Task management",
        "hint": "each member manages their own tasks (kanban)",
        "actors": ["Member"],
        "entities": {
            # ACQUIS (point 60) : « title, assignee, due date, and a simple
            # priority signal right on the card » — les deux étaient des
            # questions alors qu'aucune carte kanban ne s'en passe.
            "Task": {"fields": [("title", "String"), ("status", "String"),
                                ("priority", "String"), ("dueDate", "String"),
                                ("assignee", "String")],
                     "manager": "Member", "readers": [], "public_read": False,
                     "public_create": False, "owned": True},
        },
        # POINT 61 : outil interne, ouvert sur un tableau et non sur une page
        # d'accueil. Aucune rubrique standard ne s'impose — le dialogue
        # retombe donc sur l'offre générique plutôt que d'inventer un « à
        # propos » à un kanban d'équipe.
        "relations": [],
        "extra_rules": [
            'rule Task.status oneOf "to do", "in progress", "done"',
            'rule Task.priority oneOf "low", "medium", "high"',
        ],
        "seeds": {}, "sections": [],
        "followups": [
        ],
    },
    {
        "name": "Forum / social network",
        "hint": "posts, comments, likes",
        "actors": ["Member", "Moderator"],
        "entities": {
            "Post": {"fields": [("content", "Text"), ("likes", "Integer"),
                                   ("status", "String")],
                     "manager": "Member", "readers": [], "public_read": True,
                     "public_create": False, "owned": True},
            # Acquis : un signalement ouvre une file de modération ; le
            # modérateur change le statut du post, et publicWhen empêche qu'un
            # post masqué reste lisible par son URL.
            "Report": {"fields": [("reason", "Text"), ("status", "String")],
                        "manager": "Moderator", "readers": [], "public_read": False,
                        "public_create": False, "owned": False},
            # Le like est possédé par son compte : cela permet à oncePer de
            # composer une unicité solide (compte + post), sans fingerprint
            # fourni par le navigateur.
            "Like": {"fields": [("note", "String")],
                      "manager": "Member", "readers": [], "public_read": False,
                      "public_create": False, "owned": True},
        },
        "relations": [("Post", "hasMany", "Like"),
                       ("Member", "hasMany", "Like"),
                       ("Post", "hasMany", "Report")],
        "extra_rules": [
            'rule Post.status oneOf "published", "hidden"',
            'rule Post.Read publicWhen status "published"',
            'rule Post.Read sharedBy Moderator',
            'rule Like.Create increments Post.likes by 1',
            'rule Like.Create oncePer Member, Post',
            'rule Report.status oneOf "open", "resolved", "dismissed"',
            'rule Report.Create sharedBy Member, Moderator',
            'rule Post.Update sharedBy Member, Moderator',
        ],
        "extra_workflows": [
            {"name": "ReportPost", "actor": "Member",
             "actions": [("Create", "Report")]},
            {"name": "ModerateCommunity", "actor": "Moderator",
             "actions": [("Read", "Post"), ("Update", "Post"),
                          ("Read", "Report"), ("Update", "Report"),
                          ("Delete", "Report")]},
        ],
        # POINT 61 : des règles écrites et visibles depuis l'accueil sont le
        # premier levier de modération cité par les guides de communauté ;
        # le « à propos » dit à qui la communauté s'adresse.
        "sections": [
            {"title": "About the community",
             "ask": "who gathers here and around what"},
            {"title": "Community rules",
             "ask": "what is expected, what is forbidden, what happens when someone steps out of line"},
        ],
        "seeds": {"Post": [
            {"content": "First community thread — introduce yourself here.", "likes": 24, "status": "published"},
            {"content": "Which tools do you use every day?", "likes": 51, "status": "published"},
            {"content": "Looking back on Thursday's meetup, thanks everyone!", "likes": 13, "status": "published"},
        ]},
        "followups": [
            {"ask": "Allow comments (each person manages their own)?",
             "effects": {"add_entities": {"Comment": {"fields": [("content", "Text")],
                                                      "manager": "Member", "readers": [], "public_read": True,
                                                      "public_create": False, "owned": True}},
                         "add_relations": [("Post", "hasMany", "Comment")]}},
        ],
    },
    {
        "name": "Classified ads",
        "hint": "public listings, each seller manages their own",
        "actors": ["Seller", "Buyer"],
        "entities": {
            # ACQUIS (point 60) : l'acheteur regarde le lieu pour savoir si
            # l'objet est proche, et attend de pouvoir joindre le vendeur.
            # Les deux étaient des questions.
            "Listing": {"fields": [("title", "String"), ("price", "Money"),
                                   ("description", "Text"), ("imageUrl", "String"),
                                   ("location", "String")],
                        "manager": "Seller", "readers": [], "public_read": True,
                        "public_create": False, "owned": True},
            "Inquiry": {"fields": [("email", "Email"), ("content", "Text")],
                        "manager": "Seller", "readers": [], "public_read": False,
                        "public_create": True, "owned": False},
            # Transaction métier : l'acheteur possède sa demande, son montant
            # est calculé depuis l'annonce, puis le vendeur renseigne la
            # livraison sur la route dédiée après paiement.
            "Purchase": {"fields": [("status", "String"), ("quantity", "Integer"),
                                      ("deliveryAddress", "Text"), ("total", "Money"),
                                      ("deliveryStatus", "String"),
                                      ("trackingNumber", "String")],
                         "manager": "Buyer", "readers": ["Seller"],
                         "public_read": False, "public_create": False, "owned": True},
        },
        # PAS de fiche photo ici : une photo d'annonce doit être vue par les
        # ACHETEURS, et monl refuse (à juste titre) qu'un fichier déposé soit
        # lisible publiquement. Une photo privée sur une annonce publique
        # donnerait un catalogue dont personne ne voit les images — mesuré :
        # l'acheteur récolte 403 sur la route du fichier. Le dépôt reste
        # proposé là où « privé » est le but (un justificatif de dépense).
        "relations": [("Listing", "hasMany", "Purchase")],
        "extra_rules": [
            'rule Purchase.status oneOf "pending", "paid", "cancelled"',
            'rule Purchase.quantity min 1',
            'rule Purchase.deliveryStatus oneOf "to prepare", "shipped", "delivered"',
            'rule Purchase.deliveryStatus writableAfterPayment Seller',
            'rule Purchase.trackingNumber writableAfterPayment Seller',
        ],
        "extra_workflows": [],
        # POINT 61 : une place de marché entre particuliers doit dire ce
        # qu'elle prend en charge et ce qu'elle laisse aux deux parties — les
        # guides de sécurité en font le point de départ de tout le reste.
        "sections": [
            {"title": "How it works",
             "ask": "posting, contacting a seller, closing the deal — in a few sentences"},
            {"title": "Safety tips",
             "ask": "meeting places, payment methods, reporting a listing"},
        ],
        "seeds": {"Listing": [
            {"title": "City bike", "price": 120.0, "description": "Good condition, serviced in May.", "imageUrl": _img("annonce1"), "location": "Lyon"},
            {"title": "Oak desk", "price": 85.0, "description": "140 × 70, collection only.", "imageUrl": _img("annonce2"), "location": "Nantes"},
            {"title": "Film camera", "price": 60.0, "description": "Tested, works.", "imageUrl": _img("annonce3"), "location": "Lille"},
        ]},
        "followups": [
        ],
    },
    {
        "name": "Appointment booking",
        "hint": "public services, customers' bookings",
        "actors": ["Admin", "Client"],
        "entities": {
            # ACQUIS (point 60) : nom, description, durée et prix forment le
            # socle d'une prestation ; « clear descriptions increase conversion
            # and reduce no-shows ». C'était l'unique question du modèle.
            "Service": {"fields": [("name", "String"), ("duration", "Integer"),
                                   ("price", "Money"), ("description", "Text")],
                        "manager": "Admin", "readers": ["Client"], "public_read": True,
                        "public_create": False, "owned": False},
            "Booking": {"fields": [("date", "String"), ("notes", "Text")],
                        "manager": "Client", "readers": ["Admin"], "public_read": False,
                        "public_create": False, "owned": True},
        },
        "relations": [("Service", "hasMany", "Booking")], "extra_rules": [],
        # POINT 61 : la politique d'annulation est donnée comme devant figurer
        # AVEC le formulaire de réservation, pas dans un coin ; horaires et
        # accès sont l'autre information qu'on cherche avant de réserver.
        "sections": [
            {"title": "About",
             "ask": "who you are, your approach, your team"},
            {"title": "Opening hours and access",
             "ask": "opening days and hours, address, how to get there"},
            {"title": "Cancellation policy",
             "ask": "notice to cancel or move, possible fees, how to let you know"},
        ],
        "seeds": {"Service": [
            {"name": "Cut & style", "duration": 45, "price": 38.0, "description": "Shampoo, cut and styling included."},
            {"name": "Coloring", "duration": 90, "price": 72.0, "description": "Full color, professional product."},
            {"name": "Beard care", "duration": 30, "price": 22.0, "description": "Trim, edges and oil treatment."},
        ]},
        "followups": [],
    },
    {
        "name": "Inventory / stock management",
        "hint": "internal items, quantities, locations",
        "actors": ["Admin"],
        "entities": {
            "Item": {"fields": [("name", "String"), ("quantity", "Integer"),
                                ("location", "String")],
                     "manager": "Admin", "readers": [], "public_read": False,
                     "public_create": False, "owned": False},
            "StockReceipt": {"fields": [("quantity", "Integer"), ("reason", "Text"),
                                          ("occurredAt", "DateTime")],
                             "manager": "Admin", "readers": [], "public_read": False,
                             "public_create": False, "owned": False},
            "StockIssue": {"fields": [("quantity", "Integer"), ("reason", "Text"),
                                        ("occurredAt", "DateTime")],
                           "manager": "Admin", "readers": [], "public_read": False,
                           "public_create": False, "owned": False},
        },
        # POINT 61 : outil interne — voir la note du modèle « Gestion de tâches ».
        "relations": [("Item", "hasMany", "StockReceipt"),
                       ("Item", "hasMany", "StockIssue")],
        "extra_rules": [
            'rule Item.quantity min 0',
            'rule StockReceipt.quantity min 1',
            'rule StockReceipt.Create increments Item.quantity by quantity',
            'rule StockReceipt.occurredAt timestamp',
            'rule StockIssue.quantity min 1',
            'rule StockIssue.Create decrements Item.quantity by quantity',
            'rule StockIssue.occurredAt timestamp',
        ],
        "seeds": {"Item": [
            {"name": "Shipping boxes", "quantity": 84, "location": "A-01"},
            {"name": "Thermal labels", "quantity": 240, "location": "A-02"},
            {"name": "USB-C cables", "quantity": 18, "location": "B-04"},
        ]}, "sections": [],
        "followups": [
            {"ask": "Track suppliers (an entity linked to the items)?",
             "effects": {"add_entities": {"Supplier": {"fields": [("name", "String"), ("email", "Email")],
                                                       "manager": "Admin", "readers": [], "public_read": False,
                                                       "public_create": False, "owned": False}},
                         "add_relations": [("Supplier", "hasMany", "Item")]}},
            {"ask": "Add an alert threshold per item?",
             "effects": {"add_fields": {"Item": [("alertThreshold", "Integer")]}}},
        ],
    },
    {
        "name": "Personal expense tracking",
        "hint": "each person sees and manages only their own expenses",
        "actors": ["User"],
        "entities": {
            "Expense": {"fields": [("label", "String"), ("amount", "Money"),
                                   ("spentOn", "String"), ("category", "String")],
                        "manager": "User", "readers": [], "public_read": False,
                        "public_create": False, "owned": True},
            "Budget": {"fields": [("name", "String"), ("limit", "Money"),
                                    ("spent", "Money")],
                       "manager": "User", "readers": [], "public_read": False,
                       "public_create": False, "owned": True},
        },
        # POINT 61 : outil personnel, sans visiteur à convaincre.
        "relations": [("Budget", "hasMany", "Expense")],
        "extra_rules": [
            'rule Expense.amount min 0',
            'rule Budget.limit min 0',
            'rule Budget.spent sumOf Expense.amount',
        ],
        # Un budget personnel sert à piloter les dépenses, pas à encaisser un
        # paiement. Cette décision évite que le détecteur générique transforme
        # les deux montants du suivi en faux catalogue de paiement.
        "accept_payments": False,
        "seeds": {}, "sections": [], "followups": [],
    },
    {
        "name": "Community ranking",
        "hint": "public list, votes that raise the score",
        "actors": ["Participant"],
        "entities": {
            "Entry": {"fields": [("name", "String"), ("tagline", "Text"),
                                 ("score", "Integer"), ("submittedOn", "DateTime")],
                      "manager": "Participant", "readers": [], "public_read": True,
                      "public_create": False, "owned": False},
            "Vote": {"fields": [("note", "String")],
                     "manager": "Participant", "readers": [], "public_read": False,
                     "public_create": False, "owned": False},
        },
        "relations": [("Participant", "hasMany", "Vote"),
                       ("Entry", "hasMany", "Vote")],
        "extra_rules": [
            "rule Vote.Create increments Entry.score by 1",
            "rule Vote.Create oncePer Participant, Entry",
            "rule Entry.submittedOn timestamp",
        ],
        # POINT 61 : un classement n'est crédible que si la règle du vote est
        # écrite — qui peut voter, combien de fois, comment on départage.
        "sections": [
            {"title": "About the ranking",
             "ask": "what is ranked, by whom, for what purpose"},
            {"title": "How voting works",
             "ask": "who can vote, how many times, how a tie is broken"},
        ],
        "seeds": {"Entry": [
            {"name": "Solaris project", "tagline": "3D-printed solar panels.", "score": 128},
            {"name": "Mesh network", "tagline": "Off-grid community internet.", "score": 203},
            {"name": "Repair workshop", "tagline": "Neighbors fixing things together.", "score": 45},
        ]},
        "followups": [],
    },
]

FREE_MODE_LABEL = "Start from scratch (describe my entities freely)"


def apply_effects(template, effects):
    """Fusionne les effets d'une question de suivi acceptée dans le modèle.
    Pure fonction sur des dicts — testable sans dialogue."""
    for ent, fields in effects.get("add_fields", {}).items():
        template["entities"][ent]["fields"].extend(fields)
    for ent, meta in effects.get("add_entities", {}).items():
        template["entities"][ent] = meta
    for actor in effects.get("add_actors", []):
        if actor not in template["actors"]:
            template["actors"].append(actor)
    template["relations"].extend(effects.get("add_relations", []))
    template["extra_rules"].extend(effects.get("add_rules", []))
    for ent, rows in effects.get("add_seeds", {}).items():
        template["seeds"].setdefault(ent, []).extend(rows)
    # Enrichir les lignes de seed existantes avec les nouveaux champs
    # (une valeur réaliste par ligne, dans l'ordre).
    for ent, per_field in effects.get("add_seed_fields", {}).items():
        for field, values in per_field.items():
            # strict=True : un modèle qui fournit 2 valeurs pour 3 lignes de
            # seed doit ÉCHOUER ici, pas produire en silence une ligne à qui
            # il manque un champ que les autres ont (le catalogue est testé
            # modèle par modèle, la CI attrape donc l'erreur immédiatement).
            for row, value in zip(template["seeds"].get(ent, []), values,
                                  strict=True):
                row[field] = value
    return template
