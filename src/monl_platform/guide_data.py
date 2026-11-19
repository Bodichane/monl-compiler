"""Data used to keep the platform guide synchronized with the product."""

from __future__ import annotations

# The grammar's twelve types (`TYPE` in src/monl/parser/lark_grammar.py). A test
# refuses any divergence, in both directions.
TYPES: list[tuple[str, str]] = [
    ("String", "Short single-line text: a name, a reference, a category."),
    ("Text", "Long, multi-line text: a description, a message."),
    ("Integer", "Whole number: a stock, a quantity, a counter."),
    ("Float", "Decimal number, for anything that is not an amount."),
    ("Boolean", "True or false."),
    ("Date", "A day, without a time."),
    ("DateTime", "An instant. The type <code>timestamp</code> requires."),
    ("Email", "Email address."),
    ("UUID", "Technical identifier. For a number a human reads and dictates, "
             "prefer <code>numbered</code>."),
    ("Money", "An amount. Distinct from <code>Float</code>: it is what "
              "<code>payable</code> and <code>sumOf</code> expect."),
    ("Image", "A LOCAL file, declared in the <code>assets</code> block and "
              "checked for presence at compile time. Unavailable on this "
              "platform, which accepts no uploads."),
    ("Upload", "A file the client uploads at runtime."),
]

REGLES_ACCES: list[tuple[str, str]] = [
    ("rule Entity.Action ownedBy Actor",
     "Only the owner acts. The filter <b>also covers reads</b> — list and "
     "direct access. The ownership column is filled from the token at "
     "creation, never supplied by the client."),
    ("rule Line.Action ownedBy Order",
     "<b>Transitive</b> ownership: this line belongs to whoever owns its "
     "order. The chain must lead back to an account."),
    ("rule Entity.Action public",
     "Removes authentication from one specific action. A gallery can be read "
     "without an account; writing stays closed."),
    ("rule Article.Read publicWhen status \"published\"",
     "<b>Conditional</b> public read: filtered list, 404 on detail. Enforced in "
     "the API — hidden content does not stay readable through its URL."),
    ("rule Message.Read accessibleBy sender_id, recipient_id",
     "Reserved to the parties the record names: this is private messaging. At "
     "least two columns, otherwise <code>ownedBy</code> is enough."),
    ("rule Entity.Action sharedBy Role, Other",
     "Opens the same route to several roles. Placed on an action already "
     "governed by <code>ownedBy</code> or <code>accessibleBy</code>, it names "
     "the <b>supervisor</b>: they see and edit everything, the others stay in "
     "their own records."),
    ("rule Vote.Create oncePer Participant, Entry",
     "An account acts only once per target. Uniqueness rests on a composite "
     "database index, never on an application check — that is what also "
     "protects against two simultaneous requests."),
    ("rule Order.Create requiresOwn Profile",
     "The caller must already own a profile to create this. Responds 409 and "
     "says what to create first: an order that cannot be assigned to anyone "
     "cannot be shipped."),
]

REGLES_CHAMPS: list[tuple[str, str]] = [
    ("rule Product.price min 0",
     "Input bound, <b>422 before any INSERT</b>. Value for numbers, length for "
     "text."),
    ("rule Product.name max 120", "The upper bound, same mechanism."),
    ("rule Member.nickname unique",
     "Unique database index: a duplicate responds 409, on creation as on "
     "update."),
    ("rule Product.name required",
     "A checked assertion: the field must exist. A rule that names a missing "
     "field makes compilation fail."),
    ("rule Order.status oneOf \"cart\", \"shipped\"",
     "One value from a list, on a text field. The error message lists the "
     "allowed values, and the contract asks for a dropdown menu."),
]

REGLES_SERVEUR: list[tuple[str, str]] = [
    ("rule Message.author generated",
     "The server writes a stable pseudonym per account. The field disappears "
     "from the request body: a free field guarantees no identity."),
    ("rule Order.placedAt timestamp",
     "Creation instant, ISO 8601 UTC, written once. Absent from request bodies "
     "— creation <b>and</b> update: a date you give yourself proves nothing."),
    ("rule Order.reference numbered \"ORD-{YYYY}-{NNNN}\"",
     "The number a human reads and dictates. The counter lives in a system "
     "table: a number is never reassigned, even after deletion."),
    ("rule Line.subtotal derivedFrom Product.price by quantity",
     "Calculated from a linked row, and <b>recalculated</b> on update. Without "
     "it, the client writes the amount they will be charged."),
    ("rule Order.total sumOf Line.subtotal",
     "Sum of the child rows, recalculated on every write — creation, update "
     "<b>and deletion</b>. Never adjusted by addition: an adjusted sum drifts "
     "out of sync."),
    ("rule Member.email hidden",
     "Removed from every read response, for everyone. It stays in the "
     "database and stays writable."),
    ("rule Message.likes categorized: \"quiet\" below 10, \"viral\" otherwise",
     "Replaces a number with a label on read. The last tier is always "
     "<code>otherwise</code>: coverage is complete."),
]

REGLES_COMMERCE: list[tuple[str, str]] = [
    ("rule Line.Create decrements Product.stock by quantity",
     "Deducts <b>the quantity requested</b>. A <code>min 0</code> declared on "
     "the stock arms the availability check: without it, a counter keeps the "
     "right to go below zero. Returned on deletion."),
    ("rule Like.Create increments Message.likes by 1",
     "The counterpart, for counters."),
    ("rule Order.total payable",
     "Opens <code>POST /order/{id}/paiement</code> and "
     "<code>POST /paiement/webhook</code>. The amount is reread <b>from the "
     "database</b> on every call — the route accepts no request body. Requires "
     "a server-calculated amount: a total the payer can write makes "
     "compilation fail."),
    ("rule Order.status \"cancelled\" releases Line",
     "Reaching this value returns the stock, once, and the state becomes "
     "terminal."),
    ("rule Order.status writableAfterPayment Seller",
     "A settled record freezes. This rule reopens <b>one</b> field, through a "
     "dedicated route reserved to the named role — never to the owner."),
]

CONTENU: list[tuple[str, str]] = [
    ("seed Entity", "Demo dataset, written once and only into an empty "
     "table. An empty storefront cannot be judged."),
    ("seed Child for Parent.field \"value\"",
     "Attaches the child by naming its parent by a <b>value</b>, never by a "
     "position: a number cannot be read and shifts on the first insertion."),
    ("landing / brief", "What the application does, in one sentence. It is "
     "the starting point of the interface brief."),
    ("section \"Title\": \"Text\"",
     "An editorial section. The <code>¶</code> separator splits it into "
     "paragraphs, since the grammar forbids line breaks in a string."),
    ("question \"Q\": \"A\"", "An FAQ pair. The declared order is kept."),
    ("capability auth / identifier: email, phone",
     "Constrains the <b>form</b> of the account identifier, and above all "
     "normalizes it: without a canonical form, one capital letter is enough to "
     "create a second account. <code>phone_prefix: \"+229\"</code> makes "
     "“97…” and “+22997…” equivalent."),
    ("actor Customer selfRegister",
     "Only roles marked this way can sign up through "
     "<code>POST /register</code>. The others are provisioned offline with the "
     "generated <code>manage.py</code> — letting people pick their role at "
     "sign-up would be privilege escalation in one HTTP call."),
]

ROUTES_API: list[tuple[str, str, str]] = [
    ("GET", "/health", "Service status."),
    ("GET", "/ready", "Availability of persistent storage."),
    ("GET", "/api/version", "Compiler and frontend contract version."),
    ("GET", "/api/templates", "The ten business templates of the guided dialogue."),
    ("GET", "/api/examples", "The catalog of example specifications."),
    ("GET", "/api/examples/{example_id}", "An example’s specification, as text."),
    ("POST", "/api/dialogue", "The next question of the guided dialogue, or its complete spec."),
    ("GET", "/auth/fournisseurs", "OAuth providers actually configured."),
    ("POST", "/api/auth/register", "Creates an account and opens a session."),
    ("POST", "/api/auth/login", "Opens a session with email and password."),
    ("POST", "/api/auth/logout", "Revokes the browser session."),
    ("DELETE", "/api/auth/account", "Deletes the account, its keys and its projects. Requires the password in the body, and the deletion is irreversible."),
    ("GET", "/api/auth/recovery-codes", "How many recovery codes remain usable."),
    ("POST", "/api/auth/recovery-codes", "Current password required, except for OAuth. Replaces the eight codes and closes the other sessions, without revoking MCP keys."),
    ("POST", "/api/auth/recover", "Regains control of an account: address, recovery code and new password. The code is consumed, every session ends and MCP keys are revoked."),
    ("GET", "/api/auth/me", "Account of the active session."),
    ("GET", "/api/projects", "Projects of the signed-in account."),
    ("DELETE", "/api/projects/{project_id}", "Deletes a project and its archive."),
    ("GET", "/api/keys", "The account’s MCP keys, without their secret."),
    ("POST", "/api/keys", "Creates an MCP key shown only once."),
    ("DELETE", "/api/keys/{key_id}", "Permanently revokes an MCP key."),
    ("POST", "/api/validate", "The real parser and audit, without writing anything."),
    ("POST", "/api/compile", "Compiles into the private folder and returns a manifest (201), ready for /start."),
    ("GET", "/api/projects/{project_id}", "Manifest and summary of a compilation."),
    ("GET", "/api/projects/{project_id}/contract", "The complete frontend contract."),
    ("GET", "/api/projects/{project_id}/download", "ZIP archive, without the JWT secret. Opened by the session OR by an MCP key as Bearer."),
    ("POST", "/api/projects/{project_id}/compiler", "Compiles the project’s spec into its private folder (201)."),
    ("POST", "/api/projects/{project_id}/serve", "Starts the compiled API (explicit alias)."),
    ("POST", "/api/projects/{project_id}/start", "Starts the compiled API to try it."),
    ("POST", "/api/projects/{project_id}/stop", "Stops the started API."),
    ("GET", "/api/models", "Catalog of the ten application templates."),
    ("GET", "/api/telechargements", "Artifacts actually available for download."),
    ("GET", "/api/telechargements/{name}", "Downloads a published artifact."),
    ("GET", "/mcp", "MCP configuration and access-key management."),
    ("POST", "/mcp", "MCP HTTP transport, authenticated by Bearer key."),
]

OUTILS_MCP: list[tuple[str, str]] = [
    ("monl_list_templates", "Discover the business templates."),
    ("monl_validate_spec", "The errors of the real parser and audit."),
    ("monl_compile_backend", "Compile a project ready for /start, and receive its identifier."),
    ("monl_list_projects", "Find your projects and their download address."),
    ("monl_inspect_contract", "Read the manifest and the complete contract."),
    ("monl_diff_spec", "What a new spec would change, without writing anything."),
    ("monl_update_backend", "Recompile an existing project and receive the delta."),
]

LIMITES: list[tuple[str, str]] = [
    ("No file supplied at compile time",
     "A file sent at <b>runtime</b> works: declare an <code>Upload</code> "
     "field, and the produced backend receives it, checks its type from the "
     "byte signature and stores it outside the site. What is missing here is "
     "depositing a file <b>before</b> compilation — an <code>assets</code> "
     "block, or an <code>Image</code> value in a <code>seed</code>: the "
     "compiler checks that it exists, nothing on this page lets you put it "
     "there, so compilation fails. Use <code>String</code> for a remote "
     "address, or the local compiler with <code>monl assets add</code>."),
    ("Bounded retention",
     "Projects live in persistent storage and then expire after 30 days by "
     "default. Download the archive before that deadline."),
    ("Isolated, bounded compilations",
     "Each compilation runs in a subprocess limited in time, CPU, memory and "
     "files — never in the platform’s interpreter."),
    ("The secret does not travel",
     "The archive never contains <code>.jwt_secret</code>: the backend "
     "generates one on first start, on the machine that hosts it."),
]
