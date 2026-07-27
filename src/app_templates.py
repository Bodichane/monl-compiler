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

def _img(seed):
    """Image de démonstration, SANS sujet : le modèle du catalogue est chargé
    avant le dialogue, il ignore encore de quoi parle le projet. Le dialogue
    réécrit ces URL avec le mot-clé choisi (voir image_topic_url).

    1600×900, pas 800×600 (point 59) : un hero occupe toute la largeur d'un
    conteneur de ~1120 px, doublée sur un écran haute densité. La source
    était donc agrandie près de trois fois — l'image paraissait molle.
    """
    return f"https://picsum.photos/seed/{seed}/1600/900"


def image_topic_url(sujet, index):
    """URL d'une image RELATIVE AU SUJET du projet (point 59).

    `picsum` ne sait rendre que des photos au hasard : un blog de
    cybersécurité s'illustrait de paysages. `loremflickr` accepte un mot-clé,
    et son paramètre `lock` fige le tirage — sans lui, chaque rechargement
    changerait l'image et le rendu cesserait d'être reproductible, ce que le
    déterminisme du compilateur interdit.
    """
    mot = "".join(c for c in sujet.lower() if c.isalnum() or c in "-,") or "abstract"
    return f"https://loremflickr.com/1600/900/{mot}?lock={index}"


TEMPLATES = [
    {
        "name": "Portfolio / site vitrine",
        "hint": "galerie publique de projets + zone d'administration",
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
            {"title": "À propos",
             "ask": "qui vous êtes, depuis quand, ce qui distingue votre travail"},
            {"title": "Services",
             "ask": "ce que vous proposez concrètement, et pour qui"},
        ],
        "seeds": {"Project": [
            {"title": "Refonte Aurora", "description": "Identité complète pour une marque de cosmétiques.", "imageUrl": _img("aurora")},
            {"title": "App Meridian", "description": "Application mobile de suivi d'habitudes.", "imageUrl": _img("meridian")},
            {"title": "Site Horizon", "description": "Site éditorial pour un festival de musique.", "imageUrl": _img("horizon")},
        ]},
        "followups": [
            {"ask": "Classer les projets par catégorie ?",
             "effects": {"add_fields": {"Project": [("category", "String")]},
                         "add_seed_fields": {"Project": {"category": ["Identité", "Produit", "Web"]}}}},
        ],
    },
    {
        "name": "Blog",
        "hint": "articles publics, commentaires des lecteurs",
        "actors": ["Author"],
        "entities": {
            # ACQUIS (point 60) : l'auteur humanise le billet, la date dit si
            # l'information est encore d'actualité. Les deux sont donnés comme
            # essentiels par l'anatomie d'un article ; la date était une
            # question, l'auteur manquait purement et simplement.
            "Article": {"fields": [("title", "String"), ("content", "Text"),
                                   ("imageUrl", "String"), ("author", "String"),
                                   ("publishedOn", "String")],
                        "manager": "Author", "readers": [], "public_read": True,
                        "public_create": False, "owned": False},
        },
        "relations": [], "extra_rules": [],
        # POINT 61 : la bio de l'auteur est donnée comme page centrale d'un
        # site d'écriture ; la ligne éditoriale dit au lecteur s'il est au bon
        # endroit — ce qu'aucune liste d'articles ne raconte.
        "sections": [
            {"title": "À propos de l'auteur",
             "ask": "qui écrit ici, et pourquoi on devrait vous lire"},
            {"title": "Ligne éditoriale",
             "ask": "de quoi parle ce blog, à quel rythme, pour quel lecteur"},
        ],
        "seeds": {"Article": [
            {"title": "Pourquoi j'ai quitté les frameworks", "content": "Retour d'expérience après un an de vanilla.", "imageUrl": _img("blog1"), "author": "Camille Roy", "publishedOn": "2026-05-12"},
            {"title": "Le guide du télétravail durable", "content": "Trois ans de distance, ce qui marche vraiment.", "imageUrl": _img("blog2"), "author": "Camille Roy", "publishedOn": "2026-06-03"},
            {"title": "Apprendre en public", "content": "Documenter ses progrès change tout.", "imageUrl": _img("blog3"), "author": "Sacha Nedel", "publishedOn": "2026-07-01"},
        ]},
        "followups": [
            {"ask": "Permettre aux lecteurs inscrits de commenter (chacun gère ses commentaires) ?",
             "effects": {"add_actors": ["Reader"],
                         "add_entities": {"Comment": {"fields": [("content", "Text")],
                                                      "manager": "Reader", "readers": ["Author"],
                                                      "public_read": True, "public_create": False, "owned": True}},
                         "add_relations": [("Article", "hasMany", "Comment")]}},
        ],
    },
    {
        "name": "Boutique en ligne",
        "hint": "catalogue public, commandes des clients",
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
            {"title": "À propos de la boutique",
             "ask": "qui fabrique ou sélectionne, d'où viennent les produits"},
            {"title": "Livraison et retours",
             "ask": "délais, frais, conditions de retour"},
            {"title": "Questions fréquentes",
             "ask": "les questions que les clients posent avant d'acheter"},
        ],
        "seeds": {"Product": [
            {"name": "Théière Kyoto", "price": 39.5, "description": "Fonte émaillée, 0,8 L.", "imageUrl": _img("shop1"), "stock": 12},
            {"name": "Tasse Duo", "price": 18.0, "description": "Grès artisanal, lot de deux.", "imageUrl": _img("shop2"), "stock": 40},
            {"name": "Thé vert Sencha", "price": 12.5, "description": "Récolte de printemps, 100 g.", "imageUrl": _img("shop3"), "stock": 87},
        ]},
        "followups": [
            {"ask": "Classer les produits par catégorie ?",
             "effects": {"add_fields": {"Product": [("category", "String")]},
                         "add_seed_fields": {"Product": {"category": ["Théières", "Tasses", "Thés"]}}}},
        ],
    },
    {
        "name": "Gestion de tâches",
        "hint": "chaque membre gère ses propres tâches (kanban)",
        "actors": ["Member"],
        "entities": {
            # ACQUIS (point 60) : « title, assignee, due date, and a simple
            # priority signal right on the card » — les deux étaient des
            # questions alors qu'aucune carte kanban ne s'en passe.
            "Task": {"fields": [("title", "String"), ("status", "String"),
                                ("priority", "String"), ("dueDate", "String")],
                     "manager": "Member", "readers": [], "public_read": False,
                     "public_create": False, "owned": True},
        },
        # POINT 61 : outil interne, ouvert sur un tableau et non sur une page
        # d'accueil. Aucune rubrique standard ne s'impose — le dialogue
        # retombe donc sur l'offre générique plutôt que d'inventer un « à
        # propos » à un kanban d'équipe.
        "relations": [], "extra_rules": [], "seeds": {}, "sections": [],
        "followups": [
        ],
    },
    {
        "name": "Forum / réseau social",
        "hint": "publications, commentaires, appréciations",
        "actors": ["Member"],
        "entities": {
            "Post": {"fields": [("content", "Text"), ("likes", "Integer")],
                     "manager": "Member", "readers": [], "public_read": True,
                     "public_create": False, "owned": True},
        },
        "relations": [], "extra_rules": [],
        # POINT 61 : des règles écrites et visibles depuis l'accueil sont le
        # premier levier de modération cité par les guides de communauté ;
        # le « à propos » dit à qui la communauté s'adresse.
        "sections": [
            {"title": "À propos de la communauté",
             "ask": "qui se retrouve ici et autour de quoi"},
            {"title": "Règles de la communauté",
             "ask": "ce qui est attendu, ce qui est interdit, ce qui arrive en cas d'écart"},
        ],
        "seeds": {"Post": [
            {"content": "Premier fil de la communauté — présentez-vous ici.", "likes": 24},
            {"content": "Quels outils utilisez-vous au quotidien ?", "likes": 51},
            {"content": "Retour sur le meetup de jeudi, merci à tous !", "likes": 13},
        ]},
        "followups": [
            {"ask": "Activer les likes (chaque like fait monter le compteur du post) ?",
             "effects": {"add_entities": {"Like": {"fields": [("note", "String")],
                                                   "manager": "Member", "readers": [], "public_read": False,
                                                   "public_create": False, "owned": False}},
                         "add_relations": [("Post", "hasMany", "Like")],
                         "add_rules": ["rule Like.Create increments Post.likes by 1"]}},
            {"ask": "Permettre les commentaires (chacun gère les siens) ?",
             "effects": {"add_entities": {"Comment": {"fields": [("content", "Text")],
                                                      "manager": "Member", "readers": [], "public_read": True,
                                                      "public_create": False, "owned": True}},
                         "add_relations": [("Post", "hasMany", "Comment")]}},
        ],
    },
    {
        "name": "Petites annonces",
        "hint": "annonces publiques, chaque vendeur gère les siennes",
        "actors": ["Seller"],
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
        },
        "relations": [], "extra_rules": [],
        # POINT 61 : une place de marché entre particuliers doit dire ce
        # qu'elle prend en charge et ce qu'elle laisse aux deux parties — les
        # guides de sécurité en font le point de départ de tout le reste.
        "sections": [
            {"title": "Comment ça marche",
             "ask": "publier, contacter un vendeur, conclure — en quelques phrases"},
            {"title": "Conseils de sécurité",
             "ask": "lieux de rencontre, moyens de paiement, signalement d'une annonce"},
        ],
        "seeds": {"Listing": [
            {"title": "Vélo de ville", "price": 120.0, "description": "Bon état, révisé en mai.", "imageUrl": _img("annonce1"), "location": "Lyon"},
            {"title": "Bureau en chêne", "price": 85.0, "description": "140 × 70, à venir chercher.", "imageUrl": _img("annonce2"), "location": "Nantes"},
            {"title": "Appareil photo argentique", "price": 60.0, "description": "Testé, fonctionne.", "imageUrl": _img("annonce3"), "location": "Lille"},
        ]},
        "followups": [
        ],
    },
    {
        "name": "Réservation de rendez-vous",
        "hint": "prestations publiques, réservations des clients",
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
            {"title": "À propos",
             "ask": "qui vous êtes, votre approche, votre équipe"},
            {"title": "Horaires et accès",
             "ask": "jours et heures d'ouverture, adresse, comment venir"},
            {"title": "Politique d'annulation",
             "ask": "délai pour annuler ou déplacer, frais éventuels, comment prévenir"},
        ],
        "seeds": {"Service": [
            {"name": "Coupe & coiffage", "duration": 45, "price": 38.0, "description": "Shampoing, coupe et coiffage inclus."},
            {"name": "Coloration", "duration": 90, "price": 72.0, "description": "Couleur complète, produit professionnel."},
            {"name": "Soin barbe", "duration": 30, "price": 22.0, "description": "Taille, contours et soin à l'huile."},
        ]},
        "followups": [],
    },
    {
        "name": "Inventaire / gestion de stock",
        "hint": "articles internes, quantités, emplacements",
        "actors": ["Admin"],
        "entities": {
            "Item": {"fields": [("name", "String"), ("quantity", "Integer"),
                                ("location", "String")],
                     "manager": "Admin", "readers": [], "public_read": False,
                     "public_create": False, "owned": False},
        },
        # POINT 61 : outil interne — voir la note du modèle « Gestion de tâches ».
        "relations": [], "extra_rules": [], "seeds": {}, "sections": [],
        "followups": [
            {"ask": "Suivre les fournisseurs (entité liée aux articles) ?",
             "effects": {"add_entities": {"Supplier": {"fields": [("name", "String"), ("email", "Email")],
                                                       "manager": "Admin", "readers": [], "public_read": False,
                                                       "public_create": False, "owned": False}},
                         "add_relations": [("Supplier", "hasMany", "Item")]}},
            {"ask": "Ajouter un seuil d'alerte par article ?",
             "effects": {"add_fields": {"Item": [("alertThreshold", "Integer")]}}},
        ],
    },
    {
        "name": "Suivi de dépenses personnelles",
        "hint": "chacun ne voit et ne gère que ses dépenses",
        "actors": ["User"],
        "entities": {
            "Expense": {"fields": [("label", "String"), ("amount", "Money"),
                                   ("spentOn", "String")],
                        "manager": "User", "readers": [], "public_read": False,
                        "public_create": False, "owned": True},
        },
        # POINT 61 : outil personnel, sans visiteur à convaincre.
        "relations": [], "extra_rules": [], "seeds": {}, "sections": [],
        "followups": [
            {"ask": "Classer les dépenses par catégorie ?",
             "effects": {"add_fields": {"Expense": [("category", "String")]}}},
        ],
    },
    {
        "name": "Classement communautaire",
        "hint": "liste publique, votes qui font monter le score",
        "actors": ["Participant"],
        "entities": {
            "Entry": {"fields": [("name", "String"), ("tagline", "Text"),
                                 ("score", "Integer")],
                      "manager": "Participant", "readers": [], "public_read": True,
                      "public_create": False, "owned": False},
            "Vote": {"fields": [("note", "String")],
                     "manager": "Participant", "readers": [], "public_read": False,
                     "public_create": False, "owned": False},
        },
        "relations": [("Entry", "hasMany", "Vote")],
        "extra_rules": ["rule Vote.Create increments Entry.score by 1"],
        # POINT 61 : un classement n'est crédible que si la règle du vote est
        # écrite — qui peut voter, combien de fois, comment on départage.
        "sections": [
            {"title": "À propos du classement",
             "ask": "ce qui est classé, par qui, dans quel but"},
            {"title": "Comment fonctionne le vote",
             "ask": "qui peut voter, combien de fois, comment on départage une égalité"},
        ],
        "seeds": {"Entry": [
            {"name": "Projet Solaris", "tagline": "Panneaux solaires imprimés en 3D.", "score": 128},
            {"name": "Réseau Maillage", "tagline": "Internet communautaire hors réseau.", "score": 203},
            {"name": "Atelier Récup", "tagline": "Réparation d'objets entre voisins.", "score": 45},
        ]},
        "followups": [],
    },
]

FREE_MODE_LABEL = "Partir de zéro (décrire librement mes entités)"


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
