"""The example specifications served by the platform.

Why they live HERE, and not in the repository's `exemples/`. The installed
package contains only Python: a `wheel` carries neither `exemples/*.ml`
nor any data file, so a platform installed by `pip` would serve an empty
catalog. It is exactly the defect that made `app.py` disappear from the
repository — something missing that raises no error. The specs are
therefore code, and the test really COMPILES them: what matters is not
that they look like the repository's examples, it is that none can rot
silently.

Each one is short on purpose: it teaches one family of rules, it does not
demonstrate everything. `exemples/` stays the complete, commented
reference.

None declares `assets`: the platform offers no way to drop a file BEFORE
compilation, and a declared but missing asset makes it fail (brick 13). An
online showcase therefore shows its images through `String`, never
through an `Image` value. The file sent at RUNTIME is another matter, and
it works: see brick 32 (`Upload`)."""

from __future__ import annotations

from typing import Any

VITRINE = """app WorkshopShowcase

# The simplest case: a catalog everyone reads and only the workshop changes.
# `public` removes authentication from READING, and from reading alone —
# creating, updating and deleting stay reserved to the Admin.

entity Project
    title: String
    summary: Text
    category: String
    imageUrl: String

actor Admin

rule Project.title required
rule Project.Read public

workflow Manage for Admin
    Create Project
    Read Project
    Update Project
    Delete Project

# The `seed` block fills the database on first start, and only once: an
# empty showcase cannot be judged.
seed Project
    title: "North Counter", category: "Fittings", summary: "Solid oak and brushed brass.", imageUrl: ""
    title: "Fault Bookcase", category: "Storage", summary: "Asymmetric made-to-measure modules.", imageUrl: ""
    title: "Wave Table", category: "Tables", summary: "Rippled ash top, limited edition.", imageUrl: ""

landing
    brief: "Workshop Showcase presents a cabinetmaker's work: made-to-measure furniture and interior fittings."
    section "The workshop": "We design and build in the same place. Every piece is unique."
"""

RENDEZ_VOUS = """app AppointmentBook

# Ownership: everyone sees ONLY their own requests. `ownedBy` filters reading
# as much as writing — the list included, which is the classic trap of a
# hand-written access check.

entity Client
    name: String
    phone: String

entity Request
    reason: Text
    slot: String
    status: String
    submittedAt: DateTime

actor Practitioner
actor Visitor selfRegister

relation Visitor hasMany Client
relation Visitor hasMany Request

# Without an enforced form, two spellings of the same number make two accounts.
capability auth
    identifier: phone
    phone_prefix: "+229"

rule Client.name required
rule Client.Read ownedBy Visitor
rule Client.Update ownedBy Visitor

rule Request.Read ownedBy Visitor
rule Request.Update ownedBy Visitor
rule Request.Delete ownedBy Visitor
rule Request.Read sharedBy Practitioner
rule Request.Update sharedBy Practitioner

# No appointment without a profile: a request that cannot be tied to anyone
# cannot be honored.
rule Request.Create requiresOwn Client

# The status is a value FROM A LIST: otherwise the client declares itself
# "honored". The date is written by the server.
rule Request.status oneOf "submitted", "confirmed", "honored", "cancelled"
rule Request.submittedAt timestamp

workflow Book for Visitor
    Create Client
    Read Client
    Update Client
    Create Request
    Read Request
    Update Request
    Delete Request

workflow Handle for Practitioner
    Read Request
    Update Request

landing
    brief: "Appointment Book lets everyone submit a request and follow its status."
    question "How do I cancel?": "Open the request from your space and set its status to cancelled."
"""

BOUTIQUE = """app LittleShop

# The whole commerce chain. The point to remember: NO amount is written by
# the client. The subtotal is computed from the catalog price
# (`derivedFrom`), the total is the sum of the lines (`sumOf`), and that
# total is what gets charged.

entity Product
    name: String
    description: Text
    price: Money
    stock: Integer

entity Order
    reference: String
    total: Money
    status: String
    placedAt: DateTime

entity OrderLine
    quantity: Integer
    subtotal: Money

relation Customer hasMany Order
relation Order hasMany OrderLine
relation Product hasMany OrderLine

actor Customer selfRegister
actor Seller

rule Product.name required
rule Product.Read public
rule Product.price min 0
rule Product.stock min 0

# A line belongs to whoever owns its order: ownership crosses one step
# (`ownedBy Order`, not `ownedBy Customer`).
rule Order.Read ownedBy Customer
rule OrderLine.Read ownedBy Order
rule OrderLine.Update ownedBy Order
rule OrderLine.Delete ownedBy Order

rule OrderLine.quantity required
rule OrderLine.quantity min 1
rule OrderLine.subtotal derivedFrom Product.price by quantity
rule Order.total sumOf OrderLine.subtotal

# `min 0` on the stock ARMS the check: without it, twelve pairs are sold to
# fifty customers. It is the only declarative way to tell a stock from a
# counter that is allowed to go below zero.
rule OrderLine.Create decrements Product.stock by quantity

rule Order.total payable
rule Order.placedAt timestamp
rule Order.reference numbered "ORD-{YYYY}-{NNNN}"
rule Order.status oneOf "cart", "paid", "shipped", "cancelled"
rule Order.status "cancelled" releases OrderLine
rule Order.status writableAfterPayment Seller

workflow Buy for Customer
    Read Product
    Create Order
    Read Order
    Create OrderLine
    Read OrderLine
    Update OrderLine
    Delete OrderLine

workflow Run for Seller
    Create Product
    Read Product
    Update Product
    Delete Product
    Update Order.status

seed Product
    name: "Sewn notebook", price: 14.00, stock: 40, description: "96 pages, 100gsm ivory paper."
    name: "School fountain pen", price: 29.50, stock: 12, description: "Steel nib, resin body."
    name: "Midnight Blue ink", price: 9.90, stock: 60, description: "30 ml bottle."

landing
    brief: "Little Shop sells stationery: notebooks, pens and inks."
"""

COMMUNAUTE = """app CommonThread

# A thread where people post under a pseudonym. Three ideas: the pseudonym is
# GENERATED by the server (nobody picks their identity), an account upvotes a
# post only once, and a hidden post stops being readable through its URL.

entity Member
    handle: String

entity Post
    content: Text
    author: String
    status: String
    upvotes: Integer
    score: Integer
    publishedAt: DateTime

entity Upvote
    note: String

entity Report
    reason: String

relation Member hasMany Post
relation Member hasMany Upvote
relation Post hasMany Upvote
relation Member hasMany Report
relation Post hasMany Report

actor Member selfRegister
actor Moderator

# `generated` removes the field from the request body: the server writes a
# stable pseudonym per account into it. A free field guarantees no identity.
rule Post.author generated
rule Post.content required
rule Post.status oneOf "published", "hidden"

# CONDITIONAL public read: the list is filtered and the detail answers 404
# as long as the status is not "published". The moderator sees everything —
# otherwise they could not reopen what they have just hidden.
rule Post.Read publicWhen status "published"
rule Post.Read sharedBy Moderator
rule Post.Update sharedBy Moderator
rule Post.Delete sharedBy Moderator
rule Post.publishedAt timestamp

# The counter becomes a label when read: it shows a trend, not an exact
# number.
rule Post.upvotes categorized: "quiet" below 10, "followed" below 100, "viral" otherwise

# Uniqueness rests on a composite index, never on an application check — it
# is what also protects two simultaneous requests.
rule Upvote.Create oncePer Member, Post
rule Upvote.Create increments Post.upvotes by 1
# A report targets a POST, once per account: 'Member' is also the actor, and
# a counter on its profiles would hit a random profile.
rule Report.Create oncePer Member, Post
rule Report.Create decrements Post.score by 10

workflow Join for Member
    Create Member

workflow Publish for Member
    Create Post
    Read Post

workflow React for Member
    Create Upvote
    Create Report

workflow Moderate for Moderator
    Read Post
    Update Post
    Delete Post

landing
    brief: "Common Thread is a discussion thread where people post under a pseudonym."
"""

EXAMPLES: list[dict[str, Any]] = [
    {
        "id": "vitrine",
        "name": "Public showcase",
        "summary": "A catalog everyone can read and only the workshop can change.",
        "teaches": ["public", "seed", "landing"],
        "result": {"entities": 1, "routes": 5, "files": 16},
        "spec": VITRINE,
    },
    {
        "id": "rendez-vous",
        "name": "Appointment book",
        "summary": "Everyone sees only their own requests; the practitioner sees them all.",
        "teaches": ["ownedBy", "sharedBy", "requiresOwn", "oneOf", "timestamp",
                    "capability auth"],
        "result": {"entities": 2, "routes": 9, "files": 16},
        "spec": RENDEZ_VOUS,
    },
    {
        "id": "boutique",
        "name": "Shop and payment",
        "summary": "Cart, counted stock and payment — no amount written by the client.",
        "teaches": ["derivedFrom", "sumOf", "decrements", "min", "payable",
                    "numbered", "releases", "writableAfterPayment"],
        "result": {"entities": 3, "routes": 17, "files": 16},
        "spec": BOUTIQUE,
    },
    {
        "id": "communaute",
        "name": "Community feed",
        "summary": "Pseudonymous posting, one like per account, real moderation.",
        "teaches": ["generated", "publicWhen", "oncePer", "increments",
                    "categorized", "decrements"],
        "result": {"entities": 4, "routes": 8, "files": 16},
        "spec": COMMUNAUTE,
    },
]

BY_ID = {example["id"]: example for example in EXAMPLES}


def catalogue() -> list[dict[str, Any]]:
    """The examples WITHOUT their spec: enough to populate a gallery."""
    return [
        {key: value for key, value in example.items() if key != "spec"}
        for example in EXAMPLES
    ]


def spec_of(example_id: str) -> str:
    """An example's spec, or KeyError if the identifier is unknown."""
    return BY_ID[example_id]["spec"]
