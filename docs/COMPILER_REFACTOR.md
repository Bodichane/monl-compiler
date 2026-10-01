# Compiler Consolidation

This work incorporates improvements from the project review. The reference product is the compiler; CodexShop remains an integration example. Platform or interface-generation features are not extended in this work.

## Completion Criteria

- [x] Extract route and relation analysis into a module independent of emitters.
- [x] Type and isolate `derivedFrom` derivations, sharing their plans between backend and contract.
- [x] Type and isolate `sumOf` aggregations and stock/counter effects.
- [x] Reduce implicit mixin state: composable business analyses and field/access policies, with explicit interfaces.
- [x] Strengthen types at the boundaries of migrated analyses and check them in CI.
- [x] Clarify guarantees and limits in the README, synchronize verification commands and architecture documentation.
- [x] Trim historical comments in refactored areas while preserving invariants and their reasons.
- [x] Check business behavior, output compatibility, and the full suite; document any environment limitations.

The checked boxes describe the scope actually delivered. Final validation was rerun on the current state: Ruff, strict mypy, Vulture, targeted tests, and the full suite. No results about real users or external audits are inferred from local tests.

## Invariants

DSL syntax, HTTP routes, generated schema, and frontend contract remain compatible. Any output difference must be explained and tested. Parent selection, owner isolation, server-side amounts, stock, transactions, and data during an update remain protected by their business tests. Analyses must not depend on emitters or change when input dictionaries are modified after their construction.

## Final Checks

- `python -m pytest tests/ -rs --cov=src/monl --cov-report=term-missing`: full suite passed; PostgreSQL scenarios remain conditional on `MONL_TEST_DATABASE_URL`. Current case count and coverage are published by CI rather than fixed in this document.
- `ruff check src tests`, `mypy --strict` on IR boundaries, and `vulture src/monl --min-confidence 90`: no findings.
- The eight reference specifications (five examples, the demo, and the derivation/aggregation fixtures) produce the same SHA-256 fingerprints of backend and contract sources as before the refactor.
- Every generated Python module is parsed during example regression, and a golden also compares two independent output directories.
- Plans are immutable and independent of input dictionaries after construction; their identities are shared between backend and frontend contract emitters.

The only observed environment limitation is the absence of test PostgreSQL, which explains the skipped scenarios; SQLite paths and compilation checks remain fully exercised.
