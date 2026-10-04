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

## Deployment settings (environment variables)

- `MONL_JWT_SECRET`: if set, the JWT secret is read from the
  environment and **never touches disk**. This is the recommended mode in
  production. Otherwise, monl falls back to the `.jwt_secret` file generated
  at compilation (never committed — see `.gitignore`).
- `MONL_TRUST_PROXY=1`: enable **only** if the application runs
  behind a trusted reverse proxy. Rate limiting then reads the first IP in
  `X-Forwarded-For`. Without this setting, the header is ignored (a
  direct client cannot spoof it to bypass the quota).

## The `custom` block: hand-written code

The `custom` blocks are an explicit extension point: at compilation, monl
generates an empty shell for each in `sandbox_ai.py`, which the developer
completes by hand. This code is their responsibility, just like
any application code they write — monl neither analyzes nor generates it.
The generated backend's best practices remain the reference: parameterized SQL
queries, no dynamic execution, no uncontrolled system access.

A dedicated execution sandbox for this code (reduced-privilege subprocess,
container, or WASM) is a GA goal — see `docs/BETA.md`.

## Validation through offensive audit (branch `paiement-et-outillage`)

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

## Known beta limitations

- SQLite database: suitable for prototyping and lightweight deployments; write
  concurrency under heavy multi-worker load remains limited
  (GA goal: PostgreSQL layer). See `docs/BETA.md`.
- Additive migrations only (`ALTER ADD COLUMN`); destructive changes are
  deliberately refused (see `docs/MIGRATIONS.md`).
- Authentication without password reset or email verification (post-beta goal).
- No configurable CORS or HTTP security headers: the frontend is
  served from the same origin as the API (`/site`). An interface hosted
  elsewhere is a deployment matter, not yet handled by the generator (GA goal).
