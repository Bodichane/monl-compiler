app AtelierBoutique

# ─────────────────────────────────────────────────────────────────────
# COMPLETE E-COMMERCE SHOP — furniture & design objects.
# Public catalog (shop archetype: price, stock, buy button) + seller
# administration + orders. The demo data fills the storefront from the
# first
# opening, with real product images.
# ─────────────────────────────────────────────────────────────────────

entity Product
    name: String
    description: Text
    imageUrl: String
    category: String

# BRICK 21 (point 100): the product is what is SHOWN, the variant is what is
# SOLD. A chair exists in oak and in walnut: two prices, two stocks, a single
# catalog entry. It is the model a real merchant keeps (one stock per sellable
# reference), and it asks NO new syntax of the compiler — only a relation. It
# stayed out of reach until point 99 for two distinct reasons, both fixed: the
# foreign key of a child of a business table received the id of the creating
# ACCOUNT instead of the product's (point 99), and a 'seed' block could not
# attach a child to its parent (point 100) — the storefront would have opened
# on a catalog where nothing could be ordered.
entity Variant
    finish: String
    price: Money
    stock: Integer

entity Order
    reference: String
    totalAmount: Money
    status: String
    # Brick 16 (point 89): the moment the order was born. Written by the
    # server,
    # never by the client — see the rule below.
    placedAt: DateTime

# An order holds several LINES: that is what distinguishes it from a
# single-item cart. Each line says which product and in what quantity; its
# subtotal is calculated by the server, and the order total is their sum
# (bricks 10, 11 and 12 — points 77, 81 and 82).
entity OrderLine
    quantity: Integer
    subTotal: Money

relation Customer hasMany Order
relation Order hasMany OrderLine
# The variant belongs to its product. This relation names NO owner: it
# is a
# catalog link, and its column carries the product's id — not that of
# the
# seller who created it (point 99).
relation Product hasMany Variant
# What the line carries: this relation is what lets the SERVER read the
# catalog price. It targets the VARIANT and not the product, since the variant
# carries the price and the stock.
relation Variant hasMany OrderLine

actor Customer selfRegister
actor ShopManager

rule Product.name required
rule Product.Read public
rule Variant.Read public
rule Variant.price min 0
# This floor ARMS the availability check of the countdown below (point 86):
# without it, the shop would sell pairs it does not have.
rule Variant.stock min 0
rule Order.Read ownedBy Customer

# TRANSITIVE OWNERSHIP (point 81): a line belongs to whoever owns its
# order.
# Without this rule, monl would refuse to compile — a line nobody owns
# could
# be added to anyone's cart.
rule OrderLine.Read ownedBy Order
rule OrderLine.Update ownedBy Order
rule OrderLine.Delete ownedBy Order

# The quantity is the only number the client supplies, and it is required
# (otherwise the calculation below would operate on nothing).
rule OrderLine.quantity required

# The line subtotal is CALCULATED BY THE SERVER: the product's catalog price
# multiplied by the quantity. It therefore disappears from request bodies, at
# creation as at modification. Without this rule, the client sent the amount
# itself — and `payable` reread it from the database believing it came from a
# safe source: two three-request exploits were enough to charge one cent for
# hundreds of euros of goods (points 77 and 78).
rule OrderLine.subTotal derivedFrom Variant.price by quantity

# The order total is the SUM of its lines, recalculated by the server on every
# line added, modified or deleted (point 82). Summing a subtotal the client
# writes would be the same flaw with one more addition: monl refuses it at
# compile time.
rule Order.totalAmount sumOf OrderLine.subTotal

# BRICK 14 (point 86): stock follows orders. 'decrements' could only remove a
# CONSTANT ('by 3') — it now removes WHAT THE CLIENT ASKED FOR. And it
# refuses
# to go below the floor declared above by 'rule Variant.stock min 0': without
# this safeguard, the shop would show -3 pairs available after charging for
# the eight it did not have. The floor is not wired into the compiler — it is
# DECLARED in the spec, and its presence is what arms the check.
rule OrderLine.Create decrements Variant.stock by quantity

# The named field carries the AMOUNT: so it is the order that gets charged.
# monl derives POST /order/{id}/paiement from it (no body — the amount is
# reread from the database on every call) and POST /paiement/webhook, whose
# signature is checked before any write. Without STRIPE_SECRET_KEY, both
# routes answer 503 naming the variable; the rest of the shop works. Since
# point 79, this rule REQUIRES the amount to be calculated by the server: an
# amount the payer can write makes compilation fail.
rule Order.totalAmount payable

# Brick 16 (point 89): the order's arrival date, written by the server at
# creation and never afterwards. It disappears from request bodies — creation
# AND modification: a date you give yourself attests to nothing, and a book
# where everyone picks their dates no longer says in which order to fulfill.
# ISO 8601 UTC format, to the millisecond: sorting these strings is sorting
# time, without conversion and without ties between two close orders.
rule Order.placedAt timestamp

# BRICK 22 (point 102): the number a human reads and dictates. This field was
# a 'UUID' — that is, until point 101, a free string the CLIENT filled: two
# orders could carry the same "reference", and nothing required providing one
# that looked like anything. Nobody dictates a UUID over the phone. So the
# server assigns it at creation, once, from a counter in the database that
# restarts at 1 every year. It disappears from request bodies (creation AND
# modification) and carries a unique index without 'unique' having to be
# declared: a duplicated number is not a number.
rule Order.reference numbered "CMD-{YYYY}-{NNNN}"

# BRICK 25 (points 96, 98 and 113): the status was still free text, stock did
# not come back on cancellation, and the payment lock then kept everyone from
# moving the order forward.
rule Order.status oneOf "panier", "à régler", "en préparation", "expédiée", "livrée", "annulée"
rule Order.status "annulée" releases OrderLine
rule Order.status writableAfterPayment ShopManager

workflow BrowseShop for Customer
    Read Product
    Read Variant
    Create Order
    Read Order
    Create OrderLine
    Read OrderLine
    Update OrderLine
    Delete OrderLine

workflow ManageShop for ShopManager
    Create Product
    Update Product
    Delete Product
    Create Variant
    Update Variant
    Delete Variant
    Update Order.status

# Demo catalog: 6 products with real images. Price and stock no longer live
# here — they are carried by the variants below.
seed Product
    name: "Chaise Ligne", category: "Assises", description: "Chêne massif et cannage tressé main.", imageUrl: "https://picsum.photos/seed/chaise/700/560"
    name: "Lampe Arc", category: "Luminaires", description: "Laiton brossé, abat-jour orientable.", imageUrl: "https://picsum.photos/seed/lampe/700/560"
    name: "Table Onde", category: "Tables", description: "Édition limitée, plateau en frêne ondé.", imageUrl: "https://picsum.photos/seed/table/700/560"
    name: "Étagère Grid", category: "Rangements", description: "Structure acier modulaire.", imageUrl: "https://picsum.photos/seed/etagere/700/560"
    name: "Fauteuil Coque", category: "Assises", description: "Assise moulée, piètement compas.", imageUrl: "https://picsum.photos/seed/fauteuil/700/560"
    name: "Vase Galet", category: "Objets", description: "Grès émaillé, pièce unique tournée main.", imageUrl: "https://picsum.photos/seed/vase/700/560"

# BRICK 21 (point 100): each block attaches its rows to ONE product, named by
# its name. A rank would have been unreadable and would have shifted at the
# first insertion; monl refuses at compile time a designation that matches
# nothing, or that matches two rows. The 'seed Variant' blocks come AFTER
# 'seed Product' — data is inserted in declared order, and the compiler
# refuses the reverse order rather than silently fixing it.
#
# Stock deliberately varied, as before: one finish sold out (Table Onde in
# walnut), one low in stock (Fauteuil Coque), so the storefront shows both
# cases from the first opening.
seed Variant for Product.name "Chaise Ligne"
    finish: "Chêne naturel", price: 249.90, stock: 12
    finish: "Noyer fumé", price: 289.00, stock: 5

seed Variant for Product.name "Lampe Arc"
    finish: "Laiton brossé", price: 189.00, stock: 4

seed Variant for Product.name "Table Onde"
    finish: "Frêne ondé", price: 1200.00, stock: 2
    finish: "Noyer massif", price: 1450.00, stock: 0

seed Variant for Product.name "Étagère Grid"
    finish: "Acier noir", price: 340.00, stock: 8
    finish: "Acier blanc", price: 340.00, stock: 6

seed Variant for Product.name "Fauteuil Coque"
    finish: "Velours ocre", price: 520.00, stock: 3

seed Variant for Product.name "Vase Galet"
    finish: "Grès émaillé", price: 68.00, stock: 20

landing
    brief: "AtelierBoutique édite du mobilier et des objets design en séries limitées. Parcourez notre catalogue et commandez en ligne."
