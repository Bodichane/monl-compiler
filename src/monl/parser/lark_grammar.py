"""The Lark grammar of the monl DSL.

THIS FILE EXCEEDS 400 LINES, ON PURPOSE. It is not code: it is ONE
declarative artifact — a string, and the comments that explain why each
production has the shape it has. Cutting it into two halves would have no
boundary to follow: Lark ignores rule order, so the cut would be
arbitrary, and it would harm exactly what the 400-line rule protects —
being able to read in one go what reads in one go.

Add nothing here that is not the grammar."""

# monl grammar v6 - Support for multi-line descriptions (Bug #1)
grammar = r"""
    ?start: app
    
    app: "app" NAME _NL block*
    
    ?block: entity | relation | actor | rule | workflow | custom_block | ui_block | landing_block | capability_block | seed_block | assets_block | migration_block | _NL
    
    entity: "entity" NAME _NL _INDENT attribute+ _DEDENT
    attribute: NAME ":" TYPE _NL
    
    relation: "relation" NAME RELATION_TYPE NAME _NL
    
    # FIX (beta 3, privilege escalation flaw): an actor is NOT freely
    # registrable by default. Without the 'selfRegister' marker, accounts
    # with this role are provisioned offline (manage.py) — otherwise anyone
    # could register by choosing the application's most privileged role.
    # E.g.:
    #   actor Customer selfRegister
    #   actor ShopManager
    actor: "actor" NAME SELF_REGISTER? _NL
    SELF_REGISTER: "selfRegister"
    
    # FIX (post-v6): the "rule" rule is split into 3 named productions. Reason: in
    # the previous grammar, the keywords "restrictedTo"/"sharedBy" were anonymous
    # literals filtered by Lark before transformation, which kept the rule() method
    # from knowing which kind of rule it was handling (the "restrictedTo" keyword
    # never reached the Transformer). Consequence: rule["type"] was never
    # "restrictedTo", so the related security audit in ast_validator.py never fired.
    # Same class of bug as the one already fixed on the "custom" block in v3.
    ?rule: constraint_rule | restriction_rule | postpayment_rule | sharing_rule | ownership_rule | access_rule | visibility_rule | conditional_visibility_rule | uniqueness_rule | masking_rule | decrement_rule | increment_rule | categorization_rule | generation_rule | payable_rule | derivation_rule | aggregation_rule | timestamp_rule | numbering_rule | requirement_rule | oneof_rule | release_rule | upload_rule | send_rule | filter_rule | sort_rule

    constraint_rule: "rule" REFERENCE VALIDATION_TYPE _NL
                   | "rule" REFERENCE VALIDATION_TYPE INT _NL
    # ADDED (brick 19, point 96): one value FROM A LIST. Named "the next obvious
    # brick" at points 91 and 92, and for good reason: on an UNPAID order, the
    # client set `status: "delivered"` and the server accepted it. A status is
    # not text, it is one state among a few — and a shoe size is not a free
    # string.
    #   rule Order.status oneOf "cart", "preparing", "shipped"
    oneof_rule: "rule" REFERENCE "oneOf" STRING_LITERAL ("," STRING_LITERAL)* _NL
    # ADDED (brick 20, point 98): reaching a VALUE undoes an effect. The only
    # live bug the comparison with a classic shop had left (point 96):
    # cancelling an order set it to "cancelled" and kept its lines — so the
    # stock stayed consumed. Deleting the lines returned it (point 92), but
    # erased the history; a merchant wants both. `oneOf` was the prerequisite:
    # a state had to be nameable.
    #   rule Order.status "cancelled" releases OrderLine
    release_rule: "rule" REFERENCE STRING_LITERAL "releases" NAME _NL
    # BRICK B1: an Upload is a file sent at runtime by the client. It
    # deliberately does not share Image's semantics: Image is an asset path
    # supplied at compile time, while Upload is an opaque reference column with
    # a generated multipart route. The limit and the types are mandatory: a
    # declaration that produces no observable refusal (size/type) would be empty
    # convenience syntax. The real type is determined on the backend by byte
    # signature, never by the extension or name supplied by the client.
    upload_rule: "rule" REFERENCE "upload" "max" INT "types" STRING_LITERAL ("," STRING_LITERAL)* _NL
    # BRICK B2: a message leaves after a successful business creation. The '¶'
    # separator structures the body into paragraphs; inventing a multi-line grammar
    # here would cross the indentation boundary again.
    #   rule Order.Create sends "Order received" "Your order¶is being processed"
    send_rule: "rule" REFERENCE "sends" STRING_LITERAL STRING_LITERAL _NL
    # BRICK B3: explicit read capabilities, without a query language. Each
    # field is declared separately; the client never chooses an operator or
    # an expression. E.g.:
    #   rule Order.Read filter status
    #   rule Order.Read sort placedAt
    # The direction is one of the route's two fixed values (asc/desc), not an
    # SQL fragment sent by the client.
    filter_rule: "rule" REFERENCE "filter" NAME _NL
    sort_rule: "rule" REFERENCE "sort" NAME _NL
    restriction_rule: "rule" REFERENCE "restrictedTo" NAME _NL
    postpayment_rule: "rule" REFERENCE "writableAfterPayment" NAME _NL
    sharing_rule: "rule" REFERENCE "sharedBy" NAME ("," NAME)* _NL
    # ADDED (post-v6, roadmap): "ownedBy" restricts an Update/Delete action to
    # the record belonging to the current actor alone, through the existing FK
    # relation between the entity and the owning actor. E.g.:
    #   relation User hasMany Todo
    #   rule Todo.Update ownedBy User
    ownership_rule: "rule" REFERENCE "ownedBy" NAME _NL

    # ADDED (roadmap, capability ecosystem -- "two-party access" brick):
    # 'ownedBy' covers a single owner only; private messaging needs both
    # sender AND recipient to reach the same record. 'accessibleBy' lists
    # the entity's
    # COLUMNS (at least two, enforced by the grammar -- with one,
    # 'ownedBy' is enough) that each contain an authorized user id. A
    # distinct named Lark production, as for decrement_rule/increment_rule
    # (same Lark filtering trap, see CLAUDE.md).
    access_rule: "rule" REFERENCE "accessibleBy" NAME ("," NAME)+ _NL
    # ADDED (roadmap, portfolio use case): "public" removes the
    # authentication requirement for one specific action (e.g. reading
    # articles without an account, sending a contact message without an
    # account). E.g.:
    #   rule Project.Read public
    #   rule Message.Create public
    visibility_rule: "rule" REFERENCE "public" _NL
    # Conditional publication: a resource can be public only in a specific
    # business state. Example:
    #   rule Article.Read publicWhen status "published"
    # The condition is applied on the API side (list AND detail), never only
    # in the frontend: moderated content must not stay reachable through its
    # id.
    conditional_visibility_rule: "rule" REFERENCE "publicWhen" NAME STRING_LITERAL _NL
    # A vote or a like is often unique per account and per target. A composite
    # rule beats a fingerprint field supplied by the client: the relation
    # columns are determined by the server and the SQLite index also protects
    # concurrent requests.
    uniqueness_rule: "rule" REFERENCE "oncePer" NAME ("," NAME)+ _NL

    # ADDED (roadmap, capability ecosystem -- brick 2): "hidden" removes a
    # FIELD (not an action) from every read response of its entity -- list
    # and detail -- without removing it from the database or preventing its
    # use in writes. Use case: a social network where posts are public but
    # their author must never appear in the API response. Unlike
    # "restrictedTo" (which requires a specific actor), "hidden" masks for
    # EVERYONE, authenticated actors included -- that is the substantive
    # difference between "confidential" and "anonymous". E.g.:
    #   rule Post.author hidden
    masking_rule: "rule" REFERENCE "hidden" _NL

    # ADDED (roadmap, capability ecosystem -- brick 3): "decrements" triggers,
    # when a record of an entity is created (typically a report), the decrement
    # of a numeric field on the linked entity it depends on (through an
    # existing relation, e.g. "Member hasMany Report"). E.g.:
    #   rule Report.Create decrements Post.score
    #   rule Report.Create decrements Post.score by 10
    # The default amount (without "by N") is 1.
    #
    # ADDED (roadmap, capability ecosystem -- brick 4): "increments", symmetric
    # to "decrements" for likes/appreciations. E.g.:
    #   rule Like.Create increments Post.likes
    # DELIBERATELY two separate named Lark productions rather than a single
    # rule parameterized by a shared keyword: "decrements"/"increments" are
    # anonymous string literals, filtered by Lark before reaching the
    # Transformer (same trap already met and fixed for
    # "restrictedTo"/"sharedBy", see above) -- an earlier single-rule attempt
    # had therefore silently labeled every "increments" as "decrements" and was
    # removed rather than left half done.
    # ADDED (brick 14, point 86): "by" accepts a FIELD NAME as well as an
    # integer. 'by 1' always removes the same thing (a reputation, a like); 'by
    # quantity' removes WHAT THE CLIENT ASKED FOR — that was what a shop needed
    # to count down its stock. Two distinct alternatives rather than a shared
    # terminal: INT and NAME are not read the same way, and the transformer
    # must know which one it received.
    decrement_rule: "rule" REFERENCE "decrements" REFERENCE _NL
                   | "rule" REFERENCE "decrements" REFERENCE "by" INT _NL
                   | "rule" REFERENCE "decrements" REFERENCE "by" NAME _NL
    increment_rule: "rule" REFERENCE "increments" REFERENCE _NL
                   | "rule" REFERENCE "increments" REFERENCE "by" INT _NL
                   | "rule" REFERENCE "increments" REFERENCE "by" NAME _NL

    # ADDED (roadmap, capability ecosystem -- brick 5): "categorized" replaces a numeric
    # field (Integer/Float) with a category label in every read response -- on the same
    # principle as "hidden" (removes a field), but substituting it with derived data rather
    # than deleting it outright. Triggering use case: likes shown as categories
    # ("few"/"popular"/"viral") rather than as an exact number. Each tier is either "below"
    # (strict, exclusive threshold) or "otherwise" (fallback tier, only one allowed,
    # necessarily last -- see ast_validator.py for the full validation). E.g.:
    #   rule Post.likes categorized: "few" below 10, "popular" below 100, "viral" otherwise
    categorization_rule: "rule" REFERENCE "categorized" ":" category_clause ("," category_clause)* _NL
    ?category_clause: category_below | category_otherwise
    category_below: STRING_LITERAL "below" INT
    category_otherwise: STRING_LITERAL "otherwise"

    # ADDED (roadmap, capability ecosystem -- continuation of brick 1,
    # "capability auth"): "generated" removes a String field from the
    # request body expected by its entity's Create route -- the server
    # fills it alone, from a stable anonymous pseudonym generated once per
    # account at registration (see /register in generator.py), never
    # supplied or controllable by the client. Triggering use case: an
    # "author" field whose integrity must be guaranteed (unlike an "author"
    # as free String filled by hand by the client, see
    # docs/design_decisions.md point 29). E.g.:
    #   rule Post.author generated
    generation_rule: "rule" REFERENCE "generated" _NL

    # ADDED (roadmap, capability ecosystem -- payment brick, point 74):
    #   rule Order.total payable
    # names the field that carries the AMOUNT, hence the entity to charge. A
    # separate named production, as for 'increments'/'decrements': a shared
    # keyword would reopen the Lark filtering trap of point 27.
    payable_rule: "rule" REFERENCE "payable" _NL

    # ADDED (roadmap, capability ecosystem -- brick 10, point 77):
    #   rule Order.total derivedFrom Product.price by quantity
    # the field named on the left is CALCULATED BY THE SERVER from a field of a
    # linked row, multiplied by a field of the entity itself. It disappears
    # from request bodies (creation AND modification): that is the whole point
    # of the brick. Without it, `payable` reread from the database an amount
    # the client had written there -- two proven exploits, see point 77. A
    # separate named production, like 'increments'/'decrements' and 'payable':
    # a shared keyword would reopen the Lark filtering trap of point 27.
    derivation_rule: "rule" REFERENCE "derivedFrom" REFERENCE "by" NAME _NL

    # ADDED (roadmap, capability ecosystem -- brick 12, point 82):
    #   rule Order.total sumOf Line.subtotal
    # the field named on the left is the SUM of a field of all child rows.
    # Recalculated by the server on every write of a row (creation, modification,
    # deletion), so absent from request bodies like a 'derivedFrom' field. This
    # is the brick that makes a multi-item order priceable -- `derivedFrom` can
    # only read ONE linked row. A separate named production, same reason as above
    # (Lark trap, point 27).
    aggregation_rule: "rule" REFERENCE "sumOf" REFERENCE _NL

    # ADDED (roadmap, capability ecosystem -- brick 16, point 89):
    #   rule Order.placedAt timestamp
    # the named field carries the record's CREATION instant, written by the
    # server and never afterwards. Absent from request bodies like a 'generated'
    # field: a date you can give yourself attests to nothing. A separate named
    # production, same reason as above (Lark trap, point 27).
    timestamp_rule: "rule" REFERENCE "timestamp" _NL

    # ADDED (brick 22, point 102):
    #   rule Order.reference numbered "CMD-{YYYY}-{NNNN}"
    # the named field carries a READABLE NUMBER, assigned by the server at
    # creation and never afterwards. Same family as 'timestamp': absent from
    # request bodies, for creation as for modification. The keyword is not
    # 'reference' — it would be confused with the name almost always given to the
    # field, and 'rule Order.reference reference …' does not read.
    numbering_rule: "rule" REFERENCE "numbered" STRING_LITERAL _NL

    # ADDED (roadmap, capability ecosystem -- brick 17, point 90):
    #   rule Order.Create requiresOwn Customer
    # the caller must ALREADY own a record of the named entity to be able to
    # create this one. Born from a finding on a real shop: two orders carried an
    # account with no customer record at all, so no name or address — orders that
    # cannot be shipped. A separate named production, same reason as above (Lark
    # trap, point 27).
    requirement_rule: "rule" REFERENCE "requiresOwn" NAME _NL

    # ADDED (roadmap, visual rendering control): optional "ui" block to
    # override what the generator guesses automatically. E.g.:
    #   ui Project
    #       theme: market
    #       primary: title
    #       order: title, price, stock
    # REMOVED (roadmap, on explicit request): monl no longer generates a CRUD
    # back office per entity (see generate_all).
    # POINT 72: "theme" has no effect either — the compiler decides NOTHING
    # about visuals, so it no longer has a theme to pin. The three keys stay
    # ACCEPTED by the grammar so as to break no existing spec (same policy as
    # point 41 for 'landing mode/template'), but none influences anything.
    # Design direction comes from the dialogue, and travels through the
    # brief.
    ui_block: "ui" NAME _NL _INDENT ui_prop+ _DEDENT
    ?ui_prop: ui_theme | ui_primary | ui_order
    ui_theme: "theme" ":" NAME _NL
    ui_primary: "primary" ":" NAME _NL
    ui_order: "order" ":" NAME ("," NAME)* _NL

    # ADDED (roadmap, capability ecosystem -- brick 1): "capability" block,
    # deliberately as simple as possible for now -- a plain declaration,
    # without sub-properties. Goal of this first brick: prove that the concept
    # of "capability" holds throughout the pipeline (grammar -> validator ->
    # normalized AST -> generator) WITHOUT changing any existing behavior.
    # Authentication (register/login/JWT) is already generated systematically
    # for every app -- this block only makes it explicit/declared rather than
    # implicit in the code. Future capabilities (field masking, two-party
    # access...) are the ones that will really change behavior; this one serves
    # as a safe template, tested on the portfolio, before going further.
    # ADDED (point 95): 'capability auth' gains its FIRST function, after being
    # purely declarative since brick 1. The indented block is OPTIONAL — every
    # spec written before this point keeps compiling identically, which is the
    # condition for a dormant brick to wake up without breaking what exists.
    #   capability auth
    #       identifier: email, phone
    capability_block: "capability" NAME _NL [_INDENT capability_prop+ _DEDENT]
    ?capability_prop: capability_identifier | capability_phone_prefix | capability_lockout | capability_password_reset | capability_refresh_tokens | capability_totp | capability_verify_email | capability_verify_resend | capability_currency | capability_provider
    capability_identifier: "identifier" ":" NAME ("," NAME)* _NL
    # ADDED (point 95, found while exercising the brick on a real site): '06 12
    # 34 56 78' and '+33612345678' are the SAME number, and made two accounts.
    # monl cannot guess it — the calling code depends on the country, and
    # nothing in a spec says it. So it makes it DECLARED, failing which the
    # promise "two spellings = one account" would be false in the most common
    # case.
    #       phone_prefix: "+33"
    capability_phone_prefix: "phone_prefix" ":" STRING_LITERAL _NL
    # BRICK B4: declarative authentication options. Durations are in seconds
    # and no default value is injected into a spec that does not ask for the
    # capability.
    #   lockout: 5 in 300
    #   password_reset: 900
    #   refresh_tokens: 2592000
    #   totp
    capability_verify_email: "verify_email" ":" INT _NL
    capability_verify_resend: "verify_resend" ":" INT "in" INT _NL
    capability_lockout: "lockout" ":" INT "in" INT _NL
    capability_password_reset: ("password_reset" | "passwordReset") ":" INT _NL
    capability_refresh_tokens: ("refresh_tokens" | "refreshTokens") ":" INT _NL
    capability_totp: "totp" _NL | "totp" ":" "true" _NL
    # BRICK 2a: the payment CURRENCY, declared on 'capability payment'. It exists
    # because the code froze 'eur' and multiplied every amount by 100 — yet the
    # CFA franc has NO minor unit: billing 5,000 XOF would have sent 500,000 to
    # the provider. This is not a display preference, it is the unit money is
    # collected in.
    #   capability payment
    #       currency: XOF
    capability_currency: "currency" ":" NAME _NL
    # BRICK 2b: the payment PROVIDER. Stripe does not operate in West Africa,
    # where money goes through mobile money behind an aggregator.
    #   capability payment
    #       provider: fedapay
    #       currency: XOF
    capability_provider: "provider" ":" NAME _NL

    # Optional "landing" block: passes a marketing brief (title, tone, intent)
    # to the frontend contract, to steer the interface AI. It is plain text
    # data — monl generates no page itself. Only the "brief" key has an effect.
    # The "mode" and "template" keys are accepted for compatibility with old
    # specs but have no effect (the audit emits a warning). Without a "landing"
    # block, "/" redirects to "/docs" (FastAPI's Swagger/OpenAPI
    # documentation).
    # ADDED (point 55): repeatable "section" — the only place in the contract
    # where EDITORIAL content can live. Everything else describes DATA; an
    # "about" page has no entity, no field, no route to be born from, so the
    # interface AI had nothing to build it with.
    #   landing
    #       brief: "…"
    #       section "About": "Photographer based in Lyon since 2015…"
    # ADDED (roadmap, brick 13 -- point 83): optional "assets" block, which
    # declares the files supplied by the HUMAN (logo, icon, photos) and the
    # folder where they live. It exists because monl did not know an asset
    # existed: a wrong image path compiled silently, and `monl frontend`
    # renamed frontend/ -- thereby mislaying the photos dropped there.
    #   assets
    #       dir: "assets"
    #       logo: "logo.svg"
    #       favicon: "favicon.png"
    assets_block: "assets" _NL _INDENT assets_prop+ _DEDENT
    ?assets_prop: assets_dir | assets_logo | assets_favicon
    assets_dir: "dir" ":" STRING_LITERAL _NL
    assets_logo: "logo" ":" STRING_LITERAL _NL
    assets_favicon: "favicon" ":" STRING_LITERAL _NL

    # A non-additive migration must be NAMED and run explicitly. The spec
    # describes the target state; the operation keeps enough information to
    # check its precondition and, when possible, undo it.
    migration_block: "migration" NAME _NL _INDENT migration_operation+ _DEDENT
    ?migration_operation: rename_migration | alter_migration | drop_migration
    rename_migration: "rename" REFERENCE "to" NAME _NL
    alter_migration: "alter" REFERENCE "from" TYPE "to" TYPE _NL
    drop_migration: "drop" REFERENCE _NL

    landing_block: "landing" _NL _INDENT landing_prop+ _DEDENT
    ?landing_prop: landing_mode | landing_template | landing_brief | landing_section
                 | landing_question | landing_link
    landing_mode: "mode" ":" NAME _NL
    landing_template: "template" ":" STRING_LITERAL _NL
    landing_brief: "brief" ":" STRING_LITERAL _NL
    landing_section: "section" STRING_LITERAL ":" STRING_LITERAL _NL
    # ADDED (point 94): repeatable "question" — an FAQ is a LIST of pairs, and
    # `section` could only say a title and a text. The four questions of
    # `projets/SneakerLab` therefore fit in ONE string, and the interface
    # rendered them stuck together in a single paragraph: it was faithful, it
    # was the content model that could not say "an FAQ". FLAT form, like
    # `section`: an FAQ is the collection of the block's `question` entries.
    # An indented sub-block would have added a level to the only grammar where
    # indentation has already cost two bugs (point 6).
    #   landing
    #       question "How do I choose my size?": "Our pairs fit…"
    landing_question: "question" STRING_LITERAL ":" STRING_LITERAL _NL

    # BRICK 30: repeatable "link" — a site's OUTGOING address. A footer
    # without social networks, legal notice or contact is the last place
    # where a product site gives itself away as a mockup. Yet monl cannot
    # GUESS them: an invented Instagram address leads to someone else's page.
    # Same trade-off as points 83 and 86 — monl makes people DECLARE what it
    # cannot know, then requires it. FLAT form and ORDER preserved, like
    # `section` and `question`.
    #   landing
    #       link "Instagram": "https://instagram.com/atelier-horizon"
    #       link "Write to us": "mailto:hello@atelier-horizon.example"
    landing_link: "link" STRING_LITERAL ":" STRING_LITERAL _NL

    workflow: "workflow" NAME "for" NAME _NL _INDENT action+ _DEDENT
    
    ?action: crud_action | execute_action
    crud_action: ACTION_TYPE NAME _NL
               | ACTION_TYPE REFERENCE _NL
    execute_action: "Execute" NAME _NL

    custom_block: "custom" NAME _NL _INDENT (input_prop | output_prop | description_prop)+ _DEDENT
    input_prop: "input" ":" io_param ("," io_param)* _NL
    output_prop: "output" ":" io_param _NL
    description_prop: "description" ":" STRING_LITERAL _NL

    # ADDED (frontend roadmap, "I want complete sites"): 'seed' block —
    # pre-filled demo data, inserted at startup if the table is empty
    # (idempotent). A data-driven app looks empty without data; this block makes
    # a portfolio, a shop or a social feed show real items from the first
    # opening. One line = one record ('field: value' pairs). Values can be
    # strings (with public image URLs), integers or decimals. E.g.:
    #   seed Project
    #       title: "Aurora Redesign", imageUrl: "assets/aurora.jpg", year: 2024
    #
    # BRICK 21 (point 100): a CHILD seed names its parent row. Without this
    # form, a child entity of a business table could not appear in demo data --
    # its foreign key is not a declared field, so the validator refused it. The
    # parent is named by a FIELD and a VALUE, never by a rank: a row number says
    # nothing when read, and shifts as soon as a row is inserted in the middle.
    # E.g.:
    #   seed Variant for Product.name "Line Chair"
    #       finish: "Natural oak", price: 249.90, stock: 12
    seed_block: "seed" NAME seed_parent? _NL _INDENT seed_row+ _DEDENT
    seed_parent: "for" NAME "." NAME STRING_LITERAL
    seed_row: seed_pair ("," seed_pair)* _NL
    seed_pair: NAME ":" seed_value
    ?seed_value: STRING_LITERAL | SIGNED_NUMBER

    io_param: NAME ":" TYPE
            | REFERENCE

    TYPE: "String" | "Text" | "Integer" | "Float" | "Boolean" | "Date" | "DateTime" | "Email" | "UUID" | "Money" | "Image" | "Upload"
    RELATION_TYPE: "hasMany" | "belongsTo" | "hasOne"
    ACTION_TYPE: "Create" | "Read" | "Update" | "Delete"
    VALIDATION_TYPE: "required" | "unique" | "min" | "max"
    
    NAME: /[a-zA-Z_][a-zA-Z0-9_]*/
    REFERENCE: /[a-zA-Z_][a-zA-Z0-9_]*\.[a-zA-Z_][a-zA-Z0-9_]*/
    
    # BUG FIX v6 #1: add the /s flag to allow line breaks inside quotes
    STRING_LITERAL: /"(?:[^"\\]|\\.)*"/s
    
    _NL: /(\r?\n[\t ]*)+/
    COMMENT: /#[^\n]*/
    
    %declare _INDENT _DEDENT

    %import common.INT
    %import common.SIGNED_NUMBER
    %import common.WS_INLINE
    %ignore WS_INLINE
    %ignore COMMENT
"""
