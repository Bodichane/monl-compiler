# Security Model — monl (beta)

This document describes what monl guarantees, what it does not guarantee, and
the deployment settings. It complements `docs/design_decisions.md`.

## Principle: deterministic by default

The normal path is fully deterministic and offline:

    guided dialogue (rules, no AI) → spec .ml → parser → audit → backend

No AI model is involved in producing the backend. The spec is revalidated
by the real parser before it is written, and the static audit refuses to compile
a spec whose access control is inconsistent (a privilege collision not
covered by `sharedBy` / `ownedBy` / `accessibleBy`).

The `custom` blocks in the specification produce safe empty shells in
`sandbox_ai.py`. Their business logic is written by hand by the developer;
no code generation is automated.

## Who can obtain which role

This is the most important boundary in the model, and it is declared in the
spec:

- `actor Client selfRegister` — anyone can create an account with this
  role via `POST /register`.
- `actor Admin` (without a marker) — registration is not possible (403). Accounts
  are created on the machine hosting the database:
  `python3 manage.py adduser patron Admin`.

By default, a role is therefore **not** open for registration: a spec that omits
the marker closes registration instead of opening it. The compiler displays the
selected scope at every compilation, the frontend contract publishes it
(`self_register_actors`, so the interface offers only these roles), and the
smoke test attempts to register a provisioned role at every launch — success
makes the launch fail.

`manage.py` also handles role changes (`setactor`), passwords
(`passwd`), account inventory (`users`), and global revocation
(`revoke-all`, which renews the secret and invalidates all sessions).

For generated B4 projects, `python3 manage.py totp-reset <identifier>` is the
operator recovery path: it clears TOTP and revokes all access and refresh tokens
for that account. Email password resets preserve TOTP. TOTP activation requires
the current password and a valid code, revokes all sessions, and requires a new
login with the second factor. Password reset and `manage.py passwd` also revoke
all account sessions. The additive `token_version` column defaults to zero;
legacy JWTs without this claim remain valid for untouched accounts.

## What is guaranteed in the generated backend

- **No SQL injection through values**: all runtime values go through
  parameterized queries (`?`). Identifiers (tables/columns) are
  constrained by the grammar to `[A-Za-z_][A-Za-z0-9_]*` and interpolated between
  quotes — they cannot carry an injection.
- **Authentication**: passwords hashed with PBKDF2-HMAC-SHA256 (100,000
  iterations, unique salt per account), compared in **constant time**
  (`hmac.compare_digest`) at login. A dummy hash is computed even
  when the identifier is unknown, so response time does not reveal
  which accounts exist. JWT signed with HS256, decoded using an
  explicit algorithm list (no algorithm confusion / `alg:none`),
  revocation by `jti` via `/logout`.
- **Access control**: role (`actor`) and identity (`user_id`) are taken from the real
  account carried by the JWT, never from a free-form client declaration. Rules
  `ownedBy` / `accessibleBy` / `public` / `hidden` / `generated` are enforced at
  the route level.
- **Transactional integrity**: creating a record and its related effects
  (`increments` / `decrements`) are executed in a single transaction
  (one commit, rollback on error).
- **Rate limiting** persisted in the database (shared between workers) on
  `/register` and `/login`, counted and recorded in a single immediate-write
  transaction — a batch of simultaneous requests cannot exceed the quota.
- **Per-record ownership** (`ownedBy`): restricts modification, deletion
  **and reading** (SQL-filtered list, direct access returns 404) —
  for the designated owner actor only. Another role authorized to read
  the entity continues to see everything: this is what allows a manager to
  view all their customers' orders.
- **Referential integrity**: foreign keys are actually enforced
  (`PRAGMA foreign_keys`, disabled by default in SQLite); a violation
  returns 409 instead of 500.
- **Secret hygiene**: `.jwt_secret` is created with 0600 permissions, and
  expired entries are purged from the revoked-token blacklist.
- **Optional authentication hardening** (`capability auth`, see point 124 of
  `docs/design_decisions.md`): account lockout after a declared failure
  window, password reset by email with single-use tokens, rotating refresh
  tokens with replay refusal, and TOTP two-factor authentication. A password
  change, a reset or a TOTP change increments the account's `token_version`,
  which invalidates every token issued before it.

## Deployment settings (environment variables)

These are all the variables the generated backend reads. A variable that
belongs to a brick is only read when the spec uses that brick.
`tests/test_securite_variables.py` compares this list with the compiled code,
in both directions.

**Secrets and environment**
- `MONL_JWT_SECRET`: if set, the JWT secret is read from the environment and
  **never touches disk**. Recommended in production. Otherwise the backend
  uses the `.jwt_secret` file (created with 0600 permissions, never committed).
- `MONL_ENV`: `production` makes startup **fail** when `MONL_JWT_SECRET` is
  missing — a secret recreated on disk at each restart would invalidate all
  sessions.
- `MONL_TOKEN_TTL_HOURS`: access token lifetime in hours (default 2).
  `MONL_TOKEN_TTL_SECONDS` overrides it in seconds when refresh tokens are
  enabled.

**Network exposure**
- `MONL_TRUST_PROXY=1`: enable **only** behind a trusted reverse proxy. Rate
  limiting then reads the first IP in `X-Forwarded-For`. Without it, the
  header is ignored, so a direct client cannot spoof it to bypass the quota.
- `MONL_CORS_ORIGINS`: comma-separated list of allowed origins. CORS is off by
  default (the frontend is served from the same origin, under `/site`), and
  `*` is refused at startup.
- `MONL_SECURITY_HEADERS=off`: disables all global security headers (enabled
  by default). Every response, including `/site`, errors and redirects, carries
  `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`,
  `Referrer-Policy: strict-origin-when-cross-origin` and a CSP. The CSP allows
  local and inline scripts/styles under `/site`; CDN resources are allowed only
  on `/docs` (jsDelivr, FastAPI favicon) and `/redoc` (also Google Fonts and
  the exact ReDoc logo URL).
  HSTS (`max-age=31536000`, without subdomains or preload) is emitted only for
  HTTPS or `X-Forwarded-Proto: https`, never plain HTTP. A reverse proxy must
  overwrite this header rather than forward a client's arbitrary value.
- `MONL_DOCS=off`: disables `/docs`, `/redoc` and `/openapi.json`.
- `MONL_LOG_FORMAT=json`: structured logs.

**Database and files**
- `MONL_DATABASE_URL`: PostgreSQL connection URL. Without it, the backend
  uses the local SQLite file. `MONL_DB_POOL_MIN` and `MONL_DB_POOL_MAX` size
  the PostgreSQL connection pool (defaults 1 and 10).
- `MONL_UPLOADS_DIR`: where runtime uploads are stored (default
  `.monl_uploads`, outside the served `frontend/`).

**Email** (`sends` rule, password reset)
- `MONL_SMTP_HOST`, `MONL_SMTP_PORT`, `MONL_SMTP_USERNAME`,
  `MONL_SMTP_PASSWORD`, `MONL_SMTP_FROM`: the SMTP server used to send
  messages.
- `MONL_PASSWORD_RESET_URL`: optional address of the frontend reset page,
  added to the reset email.

**Payment** (`payable`; a missing key returns 503 naming it, and the rest of
the server keeps working)
- `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`: Stripe provider.
- `MONL_FEDAPAY_SECRET_KEY`, `MONL_FEDAPAY_WEBHOOK_SECRET`: FedaPay provider.
- `MONL_STRIPE_BASE_URL`, `MONL_FEDAPAY_BASE_URL`: provider address. They
  exist so that tests can use a fake provider; leave them unset in
  production.

## The `custom` block: hand-written code

The `custom` blocks are an explicit extension point: at compilation, monl
generates an empty shell for each in `sandbox_ai.py`, which the developer
completes by hand. This code is their responsibility, just like
any application code they write — monl neither analyzes nor generates it.
The generated backend's best practices remain the reference: parameterized SQL
queries, no dynamic execution, no uncontrolled system access.

A dedicated execution sandbox for this code (reduced-privilege subprocess,
container, or WASM) is a GA goal — see `docs/BETA.md`.

## Validation through offensive audit

`tests/test_audit_offensif_exemples.py` compiles and serves each example in
`exemples/` and replays three attacks against it (role spoofing via raw header,
forged JWT, privilege escalation), with the exact expected status codes — `401`, `401`,
`403` — after a counter-proof using a legitimate token. Result across the five
examples: **green**. (Up to point 197, this audit lived in a script
that pytest did not collect: CI did not replay it,
contrary to what this page claimed.)

Two signals that appeared during the in-depth analysis are **false positives**,
reproduced live, not vulnerabilities:

- **`01_portfolio` (StudioNova)** — targeted public creation. The audit targeted
  `Message`, a **public** route (`rule Message.Create public`, contact form):
  there is no authentication to subvert. The `422` came from an invalid `email`
  field in the test payload. With a valid `email` and no
  token, the route returns `200` by design.
- **`02_boutique` (AtelierBoutique)** — `ShopManager` escalation. `ShopManager`
  is not `selfRegister` (provisioned offline): the audit could not
  obtain a token, hence a `401` (failure of **initiation**) confused with a
  `403` (failure of **authorization**). Reproduction with a real offline account:
  `PUT`/`DELETE /orderline` → `403`, transitive ownership → `403`, legitimate
  action `PUT /order/{id}` (status) → `200`.

The tooling was hardened to reflect this model: non-public `Create` target
preferred, “blocked” = any non-2xx response, public routes and non-self-registerable
roles treated as “N/A”.

**Status of static `[CRITICAL_WARNING]` findings.** The static audit flags any
deletion by a non-`Admin` actor (`src/monl/ast_validator/`, `_audit_security_rules`).
This is a deliberately cautious heuristic, not proof of a bug: `monl` cannot
decide its user's deletion policy. In
`02_boutique`, the three findings are indeed covered at runtime by the generated
backend:

| Finding | Runtime safeguards generated |
|---|---|
| `Customer` → `Delete OrderLine` | role `403` (Customer required) + transitive ownership `403` + payment lock `409` (paid order cannot be changed) |
| `ShopManager` → `Delete Product` | role `403` + referential integrity `409` (FK `NO ACTION`: refused while variants remain) |
| `ShopManager` → `Delete Variant` | role `403` + referential integrity `409` (refused while order lines remain) |

**Conclusion**: no vulnerability identified on the
`paiement-et-outillage` branch; the generator did not need to be modified. The only
remaining policy decision is not a flaw but a business policy choice
located on the infrastructure side (deletion of an already ordered product),
flagged by the heuristic — to be decided at deployment, not in the compiler.

## Hosting platform

The hosted platform (`monl-platform`) has its own operating guide,
`docs/EXPLOITATION.md`, and `docs/PLATFORME_ET_MCP.md` covers MCP access.
What it guarantees to account holders:

- Deleting a project or an account removes everything it owns: the hosted
  site is stopped, compiled and private directories are erased (visitor
  databases included), then the database rows. The web route, the operator
  command and the periodic cleanup share the same function.
- Account deletion requires a fresh proof of identity: the password for a
  local account, or a sign-in with the OAuth provider less than ten minutes
  old.
- Recovering an account with a recovery code closes every session and
  revokes every MCP key. Regenerating codes requires the password and closes
  the account's other sessions.
- An expired project can no longer be read, downloaded or served.

## Known beta limitations

- No email address verification: monl checks the form of an identifier,
  never that an inbox receives mail.
- Messages (`sends`, password reset) are sent without a delivery guarantee or
  retries: a failure is logged after the business transaction has committed.
- SQLite is the default database; under heavy multi-worker write load, use
  PostgreSQL (`MONL_DATABASE_URL`).
- `drop` migrations are irreversible without a backup (see
  `docs/MIGRATIONS.md`).
- Hand-written `custom` code runs without a dedicated sandbox (see above).
