# ─────────────────────────────────────────────────────────────────────
# CATALOG OF APPLICATION TEMPLATES — point 45 of the journal. The dialogue no
# longer starts from a blank page: it opens on the 10 kinds of applications web
# developers build most. Choosing a template pre-fills entities, actors, rules
# and REALISTIC demo data, then follow-up questions SPECIFIC TO THE TEMPLATE
# refine it (categories? stock? comments? likes?). "Start from scratch" stays
# available and keeps the free dialogue intact.
#
# Each template is DATA, not code: the dialogue assembles them through the same
# deterministic emitter, and the final spec goes back through the real parser +
# the AST audit — a catalog template cannot produce a broken spec without
# breaking the tests (each template is compiled in tests/test_app_templates.py,
# "all no" AND "all yes" paths).
#
# Structure of a template:
#   name / hint         : what the menu shows
#   entities            : {Name: {"fields": [(field, Type)],
#                                "manager": actor, "readers": [actors],
#                                "public_read": bool, "public_create": bool,
#                                "owned": bool}}  # ownedBy the manager
#   actors              : list of actors
#   relations           : [(source, type, target)] declared in addition to
#                         those 'owned' creates automatically
#   extra_rules         : rule lines emitted as is (advanced bricks:
#                         increments, hidden, categorized…)
#   seeds               : {Entity: [ {field: value} ]} — realistic demo
#                         data (otherwise fallback on the generic seed)
#   sections            : [{"title": section title, "ask": what is
#                         expected in it}] — editorial sections that public
#                         surveys list as expected on a site of this kind
#                         (point 61). The dialogue asks DIRECTLY for their
#                         text, it no longer asks whether one is needed; an
#                         empty answer skips the section. Empty list =
#                         internal tool, no standard section.
#   followups           : [{"ask": y/n question, "effects": {...}}] where
#                         the effects merge into the template on "y":
#                         add_fields / add_entities / add_relations /
#                         add_rules / add_seeds
# ─────────────────────────────────────────────────────────────────────

def _img(_seed=None):
    """Illustration field of a demo item: EMPTY, and that is the point of the
    brick.

    These items carried a `picsum.photos` URL (and `loremflickr` as soon as a
    subject was chosen). The result contradicted the project's clearest
    promise: a monl application is SELF-CONTAINED and its compiler never calls
    the outside world — yet the very first page the prospect opened fetched
    its images from a third party. Offline, on a slow connection or on a
    metered data plan, the showcase opened broken.

    Three reasons to leave it EMPTY rather than put something else:

    * a `data:` URI image would fit in the field, but would put 250
      unreadable characters in every `seed` line of the spec — yet the spec is
      made to be read and edited by hand, and `monl content export` dumps it
      to CSV;
    * a photo shipped with monl would be a VISUAL choice of the compiler,
      which point 72 explicitly forbids;
    * the real path for a real photo already exists and is documented:
      `monl assets add <file> --for "<item>"` (brick 13, point 84), which
      checks the file at compile time instead of hoping for a remote server.

    The illustration subject asked by the dialogue is not lost: it goes into
    the contract's brief, so the interface AI knows what the visuals must
    evoke (see `_emit_spec`)."""
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
            # ACQUIRED (point 60): "a clear contact method" appears in every
            # list of a portfolio's essentials — it used to be a question.
            "Message": {"fields": [("author", "String"), ("email", "Email"),
                                   ("content", "Text")],
                        "manager": "Admin", "readers": [], "public_read": False,
                        "public_create": True, "owned": False},
        },
        "relations": [], "extra_rules": [],
        # POINT 61: "about" and a readable offer appear in every list of a
        # portfolio's essentials, on a par with the gallery.
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
            # ACQUIRED (point 60): the author humanizes the post, the date says
            # whether the information is still current. Both are given as
            # essentials by the anatomy of an article; the date was a question,
            # the author was simply missing.
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
        # POINT 61: the author's bio is given as a central page of a writing
        # site; the editorial line tells readers whether they are in the right
        # place — which no list of posts tells.
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
            # ACQUIRED (point 60): availability sits above the fold of a
            # product page, on a par with the name, the price and the image. It
            # used to be a question.
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
        # POINT 61: shipping/returns and FAQ are the two texts e-commerce
        # surveys place above the rest — they remove purchase objections, which
        # no product page can carry.
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
            # ACQUIRED (point 60): "title, assignee, due date, and a simple
            # priority signal right on the card" — both were questions while no
            # kanban card does without them.
            "Task": {"fields": [("title", "String"), ("status", "String"),
                                ("priority", "String"), ("dueDate", "String"),
                                ("assignee", "String")],
                     "manager": "Member", "readers": [], "public_read": False,
                     "public_create": False, "owned": True},
        },
        # POINT 61: an internal tool, opening on a board and not on a home
        # page. No standard section is called for — the dialogue therefore
        # falls back on the generic offer rather than inventing an "about" for
        # a team kanban.
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
            # Acquired: a report opens a moderation queue; the moderator
            # changes the post's status, and publicWhen prevents a hidden post
            # from staying readable through its URL.
            "Report": {"fields": [("reason", "Text"), ("status", "String")],
                        "manager": "Moderator", "readers": [], "public_read": False,
                        "public_create": False, "owned": False},
            # The like is owned by its account: this lets oncePer compose a
            # solid uniqueness (account + post), without a fingerprint supplied
            # by the browser.
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
        # POINT 61: written rules visible from the home page are the first
        # moderation lever cited by community guides; the "about" says who the
        # community is for.
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
            # ACQUIRED (point 60): the buyer looks at the location to know
            # whether the item is nearby, and expects to be able to reach the
            # seller. Both were questions.
            "Listing": {"fields": [("title", "String"), ("price", "Money"),
                                   ("description", "Text"), ("imageUrl", "String"),
                                   ("location", "String")],
                        "manager": "Seller", "readers": [], "public_read": True,
                        "public_create": False, "owned": True},
            "Inquiry": {"fields": [("email", "Email"), ("content", "Text")],
                        "manager": "Seller", "readers": [], "public_read": False,
                        "public_create": True, "owned": False},
            # Business transaction: the buyer owns their request, its amount is
            # calculated from the ad, then the seller fills in the delivery on
            # the dedicated route after payment.
            "Purchase": {"fields": [("status", "String"), ("quantity", "Integer"),
                                      ("deliveryAddress", "Text"), ("total", "Money"),
                                      ("deliveryStatus", "String"),
                                      ("trackingNumber", "String")],
                         "manager": "Buyer", "readers": ["Seller"],
                         "public_read": False, "public_create": False, "owned": True},
        },
        # NO photo field here: an ad's photo must be seen by BUYERS, and monl
        # (rightly) refuses to make an uploaded file publicly readable. A
        # private photo on a public ad would give a catalog whose images nobody
        # sees — measured: the buyer gets 403 on the file route. Uploading
        # stays offered where "private" is the purpose (an expense receipt).
        "relations": [("Listing", "hasMany", "Purchase")],
        "extra_rules": [
            'rule Purchase.status oneOf "pending", "paid", "cancelled"',
            'rule Purchase.quantity min 1',
            'rule Purchase.deliveryStatus oneOf "to prepare", "shipped", "delivered"',
            'rule Purchase.deliveryStatus writableAfterPayment Seller',
            'rule Purchase.trackingNumber writableAfterPayment Seller',
        ],
        "extra_workflows": [],
        # POINT 61: a marketplace between individuals must say what it takes
        # care of and what it leaves to the two parties — safety guides make it
        # the starting point of everything else.
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
            # ACQUIRED (point 60): name, description, duration and price form
            # the foundation of a service; "clear descriptions increase
            # conversion and reduce no-shows". It was the template's only
            # question.
            "Service": {"fields": [("name", "String"), ("duration", "Integer"),
                                   ("price", "Money"), ("description", "Text")],
                        "manager": "Admin", "readers": ["Client"], "public_read": True,
                        "public_create": False, "owned": False},
            "Booking": {"fields": [("date", "String"), ("notes", "Text")],
                        "manager": "Client", "readers": ["Admin"], "public_read": False,
                        "public_create": False, "owned": True},
        },
        "relations": [("Service", "hasMany", "Booking")], "extra_rules": [],
        # POINT 61: the cancellation policy is given as having to appear WITH
        # the booking form, not in a corner; opening hours and access are the
        # other information one looks for before booking.
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
        # POINT 61: internal tool — see the note of the "Task management"
        # template.
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
        # POINT 61: personal tool, with no visitor to convince.
        "relations": [("Budget", "hasMany", "Expense")],
        "extra_rules": [
            'rule Expense.amount min 0',
            'rule Budget.limit min 0',
            'rule Budget.spent sumOf Expense.amount',
        ],
        # A personal budget serves to steer expenses, not to collect a payment.
        # This decision prevents the generic detector from turning the
        # tracker's two amounts into a fake payment catalog.
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
        # POINT 61: a ranking is only credible if the voting rule is written —
        # who can vote, how many times, how ties are broken.
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
    """Merges the effects of an accepted follow-up question into the template.
    A pure function on dicts — testable without a dialogue."""
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
    # Enrich the existing seed rows with the new fields (one realistic value
    # per row, in order).
    for ent, per_field in effects.get("add_seed_fields", {}).items():
        for field, values in per_field.items():
            # strict=True: a template that supplies 2 values for 3 seed rows
            # must FAIL here, not silently produce a row missing a field the
            # others have (the catalog is tested template by template, so CI
            # catches the error immediately).
            for row, value in zip(template["seeds"].get(ent, []), values,
                                  strict=True):
                row[field] = value
    return template
