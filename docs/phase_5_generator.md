# 🟢 Phase 5 — Code Generation Engine

> **Historical document.** This page describes a design stage; it does not
> replace the current architecture. See `README.md` and `CODEBASE_AUDIT.md`.

## Goal
The goal of this phase is to design the final transformation engine (the generator). It takes as input the normalized AST validated in Phase 4, then automatically produces infrastructure deliverables (database and backend API) without manually writing business logic code.

## Generated Components (`src/generator.py`)
The generator produces two standalone files ready to use at the project root:
1. **Persistence Layer (`schema.sql`)**:
   - Translate monl semantic types into native SQL types (e.g. `Money` -> `NUMERIC(10,2)`, `Email` -> `VARCHAR(255)`).
   - Generate `CREATE TABLE` queries and automatically manage referential integrity relations by injecting foreign keys (`ALTER TABLE`).
2. **Logic and API Layer (`app.py`)**:
   - Initialize a modern architecture based on **FastAPI**.
   - Generate strict data typing and validation models through **Pydantic** for each entity.
   - Create dynamic, typed CRUD routes, isolated according to permissions and use cases described in `workflows`.

## Validation
The generation test on the `TodoApp` application demonstrates the viability of the pipeline. Generated structures are normalized, standardized, and ready for deployment or production execution.

## ⚠️ Critical Security Warning — Threat Model & Prototype Limitation

Although the generator is named `MonlSecureGenerator`, the current generated API structure (`app.py`) has a major architectural limitation inherited from its prototype status (PoC):

### The illusion of header-based access control
Generated FastAPI routes apply access control by reading the raw value of a custom HTTP header (`x_actor = Header(...)`).
- **Risk**: This header is protected by no cryptographic signature, server session, or authentication mechanism (e.g. signed JWT token). Any user or attacker can impersonate any actor, including `Admin`, simply by changing the header value in their HTTP request.

### Security responsibility
Until strong cryptographic authentication is implemented on the server:
1. **Application security depends entirely on the client**, violating development best practices: the server must never trust data from the client.
2. A direct production deployment in this state would expose all data and critical actions (such as deleting entities) to trivial privilege escalation.

### Requirement for an honest “SecureGenerator” label
Implementing FastAPI middleware to validate and decode a **JWT token cryptographically signed by the server** (containing the verified actor role) is not a convenience improvement. **It is required for the generator's “Secure by default” claim to be technically honest.** As it stands, this `app.py` must be treated only as an architectural mock-up, not as a secure backend ready for production.
