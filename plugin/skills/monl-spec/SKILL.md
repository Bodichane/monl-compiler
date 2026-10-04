---
name: monl-spec
description: Describe an application in a monl specification (.ml), compile it into a deterministic FastAPI + SQLite + JWT backend, and verify it against a real server. Use when asked to create, modify, or verify an application's backend with monl, or to write or fix a .ml file.
when_to_use: '"create an API for me…", "a backend with accounts and roles", "add a field or rule to my monl spec", "why does monl reject my spec"; « crée-moi une API pour… », « un backend avec comptes et rôles », « ajoute un champ/une règle à ma spec monl », « pourquoi monl refuse ma spec ».'
argument-hint: "[what the application should do]"
---

# Write and compile a monl specification

The monl compiler turns a declarative spec into a complete backend: a SQL
schema, a REST API, JWT authentication, access control, and a frontend
contract. The compiler is **deterministic and uses no AI**: your job is to
write a correct spec; its job is to reject anything that does not hold up.

User request: $ARGUMENTS

## 1. Find the command

In order, keep the first command that responds:

```bash
monl --version                                      # installed with pip
uvx --from monl-compiler==1.0.0rc1 monl --version   # otherwise, without installing anything
```

If neither responds, suggest `pip install monl-compiler==1.0.0rc1` to the
user; do not install it automatically. Below, `monl` means the selected
command.

## 2. Learn the language from examples, not memory

The language has no separate reference: its examples are compiled by the test
suite on every change, so they cannot lie. The plugin carries an exact copy.

1. Read `${CLAUDE_PLUGIN_ROOT}/reference/exemples/README.md`: it explains what
   each example demonstrates.
2. Read the entire example closest to the user's need
   (`${CLAUDE_PLUGIN_ROOT}/reference/exemples/*.ml`). Each example explains in
   comments **why** each rule is there.
3. If syntax is unclear, the grammar is authoritative:
   `${CLAUDE_PLUGIN_ROOT}/reference/grammaire.py`. Do not invent keywords that
   are not in it.

## 3. Write the spec in the user's project

Write `spec.ml` at the project root (or wherever the user requests) — never in
the plugin directory. When copying an example, also copy
`${CLAUDE_PLUGIN_ROOT}/reference/exemples/assets/` beside the spec so its
local images remain available. `monl update` will reread the file at that location.

Three questions to settle with the user instead of guessing:
- **Who has an account, and who signs up independently?** Only `selfRegister`
  roles can sign up online; the others are created with the generated
  `manage.py`.
- **Who can see and change what?** `ownedBy`, `sharedBy`, `accessibleBy`,
  `public`: this is a security choice, so the user must make it.
- **Is a payment collected?** `payable` requires the amount to be calculated
  by the server (`derivedFrom` or `sumOf`): an amount written by the client is
  deliberately rejected at compile time.

## 4. Compile and read rejections

```bash
monl compile spec.ml --output backend
```

A rejection exits with code 1 and a line marked `❌` that names the offending
rule and explains why. **Fix the spec; never work around a rejection** (for
example, by removing an inconvenient security rule) without the user's
explicit agreement: every rejection protects against a real defect.

## 5. Prove it by running it

```bash
monl run backend --check
```

This checks consistency across the spec, backend, and contract, then runs a
smoke test against an ephemeral server with a fresh database. Until this
command passes, the task is not finished — do not report it as done.

To start the application: `monl run backend` (API at `/`, documentation at
`/docs`).

## 6. Evolve it

- `monl diff backend`: shows what a change to `spec.ml` would do to the
  contract, **without writing anything**. Show it to the user before applying.
- `monl update backend`: recompiles and reports the delta (routes, fields,
  access, locks). Then rerun `monl run backend --check`.

## 7. The interface

The compiled backend contains `AGENTS.md`, `frontend_contract.json`, and
`docs/FRONTEND_PROMPT.md`. To build the interface, read them first, then
apply the `monl-showcase`, `monl-design-system`, `monl-ui-patterns`, and
`monl-commerce` or `monl-operations` skills as appropriate for the business.
Never modify `app.py`, `schema.sql`, or `manage.py`: they are sealed by a
fingerprint, and `monl run --check` detects changes.
