# monl-compiler

**A compiler that turns a declarative specification into a complete,
deterministic and safe backend.**

[![CI](https://github.com/Bodichane/monl-compiler/actions/workflows/ci.yml/badge.svg)](https://github.com/Bodichane/monl-compiler/actions/workflows/ci.yml)
[![Version](https://img.shields.io/badge/version-0.9.0--beta.6-blue)](CHANGELOG.md)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](pyproject.toml)
[![Tests](https://img.shields.io/badge/tests-CI-brightgreen)](tests/)
[![Coverage](https://img.shields.io/badge/coverage-CI-brightgreen)](#quality-and-verification)
[![License](https://img.shields.io/badge/license-FSL--1.1--ALv2-blue)](LICENSE)

You describe an application's intent in a dedicated DSL; monl-compiler generates
its database, REST API, authentication and access control — then produces a
contract the frontend must respect. **The specification is the single source of
truth**: you do not maintain infrastructure code by hand.

A guided dialogue helps you write that specification without knowing the syntax.
Its express mode asks only for the type of site, its name and a one-sentence
description; monl-compiler then prepares the structure, the demo data and a full
editorial brief. The only use of AI is at the very end of the chain, to build the
frontend from the contract guaranteed by the compiler — **never** for the
backend, the permissions or the business logic.

---

## Table of contents

- [Quick start](#quick-start)
- [Why monl-compiler?](#why-monl-compiler)
- [Architecture](#architecture)
- [Commands](#commands)
- [The specification](#the-specification)
- [The generated backend](#the-generated-backend)
- [Your files: photos, logo, favicon](#your-files-photos-logo-favicon)
- [Replacing content without opening the DSL](#replacing-content-without-opening-the-dsl)
- [The frontend: contract and specialized AI](#the-frontend-contract-and-specialized-ai)
- [Quality and verification](#quality-and-verification)
- [Repository structure](#repository-structure)
- [Documentation](#documentation)

---

## Quick start

`monl` opens the guided dialogue. Choose a category, then **Quick AI creation**:
three answers are enough to produce the specification, the backend and the
frontend contract. This first step stays deterministic, with no model and no
network call. The AI then intervenes only to design the interface.

```bash
pip install .
monl
monl frontend MonProjet --provider codex
monl run MonProjet
```

API-based frontend providers need the optional extra:
`pip install 'monl-compiler[ai]'`. Local agents and `monl import` do not need it.

The **Detailed customization** path remains available to choose every option,
role, editorial content and visual intent. Without a local agent or an API key,
open `FRONTEND_PROMPT.md` in the AI of your choice, then install the resulting
ZIP or HTML file with `monl import`.

> **Ubuntu / Debian.** The system Python is protected (PEP 668): prefer
> `pipx install .` over `pip install . --break-system-packages`.

The full journey, interface included, is detailed in
[QUICKSTART.md](QUICKSTART.md).

## Why monl-compiler?

| | Classic framework<br><sub>Django, Rails, FastAPI…</sub> | AI generator<br><sub>v0, Bolt, code assistants</sub> | **monl-compiler** |
|---|---|---|---|
| **Infrastructure code** | written and maintained by hand | produced once, then yours to carry | **derived from the spec, never maintained** |
| **Two identical compilations** | not applicable | different result every time | **the same backend, to the byte** |
| **Access control** | checked route by route, by vigilance | whatever the model understood | **checked at compile time: a privilege collision fails to compile** |
| **Schema / API / rules consistency** | three places to keep in sync | no guarantee | **a single source, propagated on recompile** |
| **Security** | depends on the author | hoped for | **acquired by construction: parameterized queries, role from the real account, secret outside the code** |
| **Role of AI** | none | writes everything, backend included | **confined to the frontend, framed by a contract and a smoke test** |
| **Schema evolution** | migrations to write | yours to carry by hand | **additive and non-destructive, data preserved** |

**What you write:** a one-page specification. **What you change afterwards:** the
same page. The produced code recompiles; it is never a starting point to tweak.

## Architecture

<img alt="Express or detailed dialogue and CSV content into spec.ml; compilation and audit into backend and contract; frontend written by an AI then the whole verified by monl run" src="docs/images/architecture-clair.svg" width="100%">

The dialogue produces the specification; the compiler derives **both** the
backend and the frontend contract from it; the AI writes the interface against
that contract; `monl run` verifies that the three stay consistent before
launching the application.

## Commands

| Command | What it does |
|---|---|
| `monl` | Guided dialogue → `spec.ml` + backend + frontend contract |
| `monl compile <spec.ml> --output <dir>` | Compiles an existing specification |
| `monl frontend <App>` | The AI writes the interface into `frontend/` |
| `monl import <zip\|html\|folder> <App>` | Installs a frontend obtained without an API key |
| `monl run <App>` | Checks consistency, runs the smoke test, then launches |
| `monl update <App>` | Recompiles after a spec change, preserves the data |
| `monl assets add <file> --for "<record>"` | Installs a photo and declares it in the spec |
| `monl assets list <App>` | What the spec declares, what is present, what is stray |
| `monl content export <App>` | Exports the demo records to `content/*.csv` |
| `monl content import <App>` | Replaces the records from the CSVs, then revalidates the whole spec |

Each project compiles into its own folder via `--output`, so as not to overwrite
the previous one. Specifications use the `.ml` extension.

## The specification

A spec describes **entities** (tables and fields), **actors** (roles) and access
**rules**. The compiler derives the schema, the CRUD routes and the access
control from it. Identifiers are constrained by the grammar, which rules out any
injection through table or column names.

**Access control is expressed at the record level, reads included:**

| Rule | Effect |
|---|---|
| `rule Entite.Action ownedBy Acteur` | Only the owner (auto-populated relation on creation) can act — **the filtering also covers reads**, listing and direct access |
| `rule Entite.Action accessibleBy col1, col2` | Reserved to the parties referenced by the record (private messaging: sender and recipient) |
| `rule Entite.Action public` | Removes authentication from a specific action (public gallery, contact form) |
| `rule Article.Read publicWhen status "published"` | Public read **under condition**: filtered list, detail returns 404. A `sharedBy` on the same reference exempts moderators; the owner always finds their own |
| `rule Vote.Create oncePer Participant, Entry` | Composite unique index: an account can only perform the action once per target |

**Field constraints are enforced, not just declared:**

| Rule | Effect |
|---|---|
| `rule Produit.prix min 0` | Input bound — **422 before any INSERT**. Value on number types, length on text types |
| `rule Membre.pseudo unique` | Unique index in the database — a duplicate returns 409, on creation as on update |
| `rule Produit.nom required` | Verified assertion: the field must exist (schemas already make every field mandatory) |
| `rule Ligne.Create decrements Produit.stock by quantite` | Deducts **the requested quantity**, and refuses with 409 to go below the declared `min` |
| `rule Commande.passeeLe timestamp` | Creation date written by the **server** (ISO 8601 UTC), absent from request bodies — creation as update |
| `rule Commande.statut oneOf "panier", "expédiée"` | Refuses any other value on creation as on update |
| `rule Commande.statut "annulée" releases Ligne` | Returns the stock once when the order is cancelled |
| `rule Commande.statut writableAfterPayment Admin` | Reserves this field to a dedicated authenticated route; the computed totals stay inaccessible |

Other markers refine fields and behavior: `hidden`, `generated`, `categorized`,
`derivedFrom` / `sumOf` (amounts computed by the server), `payable` (payment,
below), plus an idempotent `seed` block that pre-fills the database at startup. A
rule with no effect is **refused at compile time** rather than silently ignored —
and so is a rule that names a nonexistent field: a constraint that matches nothing
suggests a protection that does not exist.

<details>
<summary><b>Collecting payment: <code>rule Commande.total payable</code></b></summary>

<br>

The rule names the field that carries the **amount**; the entity that contains it
is the one being charged. monl-compiler derives from it two tracking columns and
two routes — `POST /commande/{id}/paiement`, which opens a settlement session, and
`POST /paiement/webhook`, which receives the provider's confirmation.

**The amount comes from the database, never from the client.** The settlement
route accepts no request body: it re-reads the field on every call. A cart that
sends its own price is a cart you can negotiate. The webhook, for its part,
verifies the provider's signature before writing anything — it is the only place
in the generated backend where an unauthenticated third party touches the
database.

Six situations are refused **at compile time** rather than when collecting:
nonexistent entity or field, non-numeric field, combination with `hidden` (an
unreadable amount cannot be verified by whoever pays it), two `payable` fields on
the same entity (nothing says which one to charge), and `public` creation (a
payment requires an identified caller).

The keys (`STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`) come from the environment,
like the JWT secret. When absent, the routes return 503 **naming the missing
variable** and the rest of the server works normally: a freshly compiled project
launches and can be tested offline.

</details>

<details>
<summary><b>Registration: why a role is not obtained in a single HTTP call</b></summary>

<br>

An actor is not self-registrable by default. `actor Client selfRegister` opens
`POST /register` to that role; an `actor Admin` without a marker can only be
obtained by offline provisioning (`manage.py`, generated alongside the backend).
Letting the client choose their role at registration would be a privilege
escalation in a single HTTP call.

</details>

**Five reference specifications**, commented, in [`exemples/`](exemples/): a
one-page `.ml` file per application — portfolio, shop, social network, kanban,
leaderboard — from which monl-compiler derives everything else.

<details>
<summary><b>Visual direction: it does not come from the compiler</b></summary>

<br>

monl-compiler has **no** opinion on the visuals — no palette, no typography, no
grid. It does not know what a project should look like; it only knows table names.
The direction is the one the author states in the dialogue (visual register, place
of images): it travels in the brief, and it is the interface AI that serves it.

Only two requirements remain, and they are not matters of taste: **contrast**
(WCAG AA), which makes the interface readable, and the frontend's **autonomy**,
which makes it verifiable by the smoke test.

</details>

## The generated backend

**Accounts and roles.** `POST /register` only accepts roles marked
`selfRegister`; any other is refused (403). Privileged accounts are created with
the generated `manage.py`, on the machine that hosts the database:
`python3 manage.py adduser <user> <role>`. The same command manages role,
password, account listing and global session revocation.

**Authentication.** A user registry specific to each application (table
`_monl_users`, passwords in PBKDF2-HMAC-SHA256, unique salt per account,
constant-time comparison). Flow: `POST /register` → `POST /login` (JWT token) →
`POST /logout` (revocation before expiry). **The role and identity carried by the
token come from the real account**, never from a client declaration.

**JWT secret.** Randomly generated at the first compilation, stored in
`.jwt_secret` (never versioned). In production, `MONL_JWT_SECRET` takes precedence
and lets you ship a project with no secret on disk.

**Multi-workers.** Token revocation and rate limiting (5 attempts / 60 s / IP on
`/register` and `/login`) are persisted in the database, hence shared:
`uvicorn app:app --workers N` does not multiply the quotas. Behind a trusted
reverse proxy, `MONL_TRUST_PROXY=1` makes the real IP be read from
`X-Forwarded-For`; without this setting the header is ignored, to prevent any
spoofing.

**Migrations.** Recompiling into the same folder, keeping `app.db`, adds the
columns via `ALTER TABLE ADD COLUMN` without touching the data. Destructive
changes are not automated, by design — see [docs/MIGRATIONS.md](docs/MIGRATIONS.md).

**Served routes.** `/docs` (Swagger, always available) · `/` (redirects to
`/docs`) · `/site` (the interface, if `frontend/` exists and the app is launched
by `monl run`).

## Your files: photos, logo, favicon

A broken image is only seen by eye, online — the worst place to discover a typo.
The files you provide are therefore declared in the spec, and the compiler
**refuses to compile if they are not there**:

```monl
assets
    dir: "assets"
    logo: "logo.svg"

entity Produit
    photo: Image          # a LOCAL file, verified present
```

`Image` designates a project file: a URL is refused there, because monl makes no
network call and could assert nothing about a remote address — `String` remains
for that case, unverified. The folder lives **outside `frontend/`**, which is
renamed on every rebuild of the frontend.

To avoid writing these paths by hand:

```bash
monl assets add ~/photos/IMG_4821.jpg --for "Halo RS"   # → assets/halo-rs.jpg
monl assets add ~/logo.svg --logo
monl assets list                                        # present, missing, orphaned
```

The command copies the file, renames it to a slug, writes the declaration — then
has **the compiler revalidate the resulting spec before saving it**. On refusal,
neither the spec nor the folder is modified. It never deletes a file: replacing a
photo flags the old one as orphaned, it does not erase it.

## Replacing content without opening the DSL

The demo seed lets you see an interface immediately, but it is not meant to become
the real catalog. A human can replace texts, prices and photo names with a
spreadsheet:

```bash
monl content export MonProjet
# edit content/Produit.csv and drop the photos into assets/
monl content import MonProjet
monl update MonProjet
```

Each CSV keeps the order of the fields and records. `LISEZMOI.txt` explains, in
French, the allowed values, the mandatory fields, the bounds and the expected
images. An empty cell is omitted: it is the real compiler that decides whether it
was mandatory. Invalid numbers, missing files, suspicious paths and ambiguous
blocks are refused before any write. The import replaces the entity's whole
content; it never silently merges two sources of truth.

## The frontend: contract and specialized AI

The interface is written by an AI, from two documents that every compilation
produces:

- `frontend_contract.json` — a machine-readable description of the routes meant
  for the interface, of the authentication and of the field rules, derived from
  the same spec as the backend;
- `FRONTEND_PROMPT.md` — a brief ready to hand to an interface AI: structure,
  roles, content and declared intent, with no visual prescription.

The AI writes into `frontend/` (entry point `index.html`), which `monl run` serves
on `/site` without ever touching the backend. Several paths, same guardrails:

| Path | Command | Authentication |
|---|---|---|
| Manual | drop the files into `frontend/` | — |
| Copy-paste | `monl import <zip\|html\|folder> <App>` | none |
| Local agent | `monl frontend <App> --provider claude-code\|codex\|gemini` | the agent's subscription |
| Any agent | `monl frontend <App> --agent-command "<cmd> {instruction}"` | the agent's |
| Anthropic API | `monl frontend <App> --provider claude` | `ANTHROPIC_API_KEY` |
| Third-party API | `monl frontend <App> --provider groq --model <id>` | `GROQ_API_KEY`, etc. |

**Any key will do.** The OpenAI-dialect providers — `groq`, `openai`,
`openrouter`, `deepseek`, `mistral`, `together`, `xai`, `ollama` — are preset,
each reading its own environment variable. For an endpoint absent from this list,
`--provider openai-compatible` with `MONL_AI_BASE_URL` and `MONL_AI_API_KEY`.
Outside the Anthropic path, `--model` is required: monl hardcodes no model
identifier, catalogs changing too fast for a fixed value to stay true. The key is
always read from the environment, never as an argument — the shell would archive
it.

Common guardrails: allowlisted extensions, zip-slip protection, self-contained
frontend with no CDN, and systematic re-verification.

### No API key, no credit card, no network

**The compiler never calls the outside.** `monl compile` produces `app.py`,
`schema.sql`, `manage.py`, the contract and the brief entirely offline: the
parser, the validator and the generator contain no network call. The whole
backend — routes, database, JWT, access control, payment, back office — is
obtained without an account anywhere.

The AI only intervenes at the frontend step, and that step has a path **with no
key at all**:

```bash
monl compile boutique.ml --output ./Boutique   # offline
# paste the contents of Boutique/FRONTEND_PROMPT.md into any
# browser-accessible assistant, retrieve the result…
monl import interface.zip ./Boutique           # same guardrails, same verification
monl run ./Boutique
```

`monl import` is not a back door: the source comes from a conversation, so it is
treated as untrusted input — extension allowlist, zip-slip refusal, CDN refusal,
mandatory `index.html`, then a consistency check and smoke test, exactly like an
API response.

Depending on what you have at hand, there also remain: `--provider ollama` for a
fully local model, command-line agents that authenticate by subscription rather
than by key, and the OpenAI-dialect providers, several of which offer a free tier.
monl favors none of them and resells none: it consumes no token on its own
account.

> **What is proven, and what is not.** The offline journey, the copy-paste path
> and the Anthropic path are tested end-to-end against a real server. The `codex`
> and `gemini` presets are written and covered at the plumbing level, but have not
> been tested against the real binaries — using them means being the guinea pig.

**Before any launch**, `monl run` runs a behavioral smoke test on an ephemeral
server with a fresh database: each route of the contract is exercised over real
HTTP and, if Node.js is present, `frontend/index.html` is run in jsdom against
that server. Any exception or any off-contract call blocks the launch
(`--skip-smoke` to override knowingly).

## Quality and verification

| | |
|---|---|
| **832 tests passing at the last audit** | Unit checks and ephemeral servers for the HTTP journeys; the official number is the one published by CI |
| **Coverage published by CI** | `pytest --cov=src --cov-report=term-missing` |
| **Offensive audit** | Role spoofing, forged JWT, privilege escalation |
| **Architecture boundaries** | Six import contracts verified by a test, not by memory |
| **Lint** | `ruff check src tests` — zero findings, exceptions justified in `pyproject.toml` |
| **CI** | Python 3.10, 3.12 and 3.14 on every push; `main` protected by these checks |

```bash
python3 -m pytest tests/ -q --cov=src --cov-report=term-missing
```

```bash
ruff check src tests
```

```bash
python3 -m mypy src/monl/ir.py src/monl/errors.py src/monl/generator/emitters.py --strict
vulture src/monl --min-confidence 90
```

monl-compiler depends on no AI model and makes no network call: dialogue,
specification and backend generation are entirely deterministic. `custom` blocks
produce safe empty shells in `sandbox_ai.py`, whose business logic is written by
hand — no code generation is automated.

## Repository structure

| Folder | Content |
|---|---|
| `src/monl/` | The package: parser, validator, dialogue, frontend contract, CLI |
| `src/monl/generator/` | The backend generator, one layer per module |
| `exemples/` | Five one-page `.ml` specifications, compiled on every test |
| `demo/` | The StudioNova demo: its specification and its frontend |
| `tests/` | Regression, offensive audit, architecture boundaries |
| `docs/` | Design decisions, security, migrations |

## Documentation

| File | Content |
|---|---|
| [QUICKSTART.md](QUICKSTART.md) | The full journey, in three steps |
| [docs/design_decisions.md](docs/design_decisions.md) | The project log: 115 entries, each with its *why* |
| [docs/SECURITE.md](docs/SECURITE.md) | Security model |
| [docs/MIGRATIONS.md](docs/MIGRATIONS.md) | Schema evolution without loss |
| [docs/BETA.md](docs/BETA.md) | Beta status and roadmap |
| [docs/DEPRECATIONS.md](docs/DEPRECATIONS.md) | Historical compatibilities and removal policy |
| [CHANGELOG.md](CHANGELOG.md) | Version history |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Working method, repository rules, pre-PR checklist |

## License

**FSL-1.1-ALv2** — *Functional Source License*, with an automatic switch to
**Apache-2.0 two years after each version's publication**
([LICENSE](LICENSE)).

You can use monl-compiler freely, including in a professional context, modify it,
redistribute it, and **use it to deliver applications to your clients**. The only
restriction is *competing* use: turning it into a commercial product or service
that substitutes for monl-compiler. The applications *produced* from your own
specifications belong to you.

The details (in French): [LICENSE-FAQ.md](LICENSE-FAQ.md).

Bug reports and feedback are welcome in the *issues*.

---

**monl-compiler 0.9.0-beta.7**
