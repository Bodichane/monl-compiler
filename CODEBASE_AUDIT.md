# MONL-Compiler consistency, maintainability, and cleanup audit

> **Historical document — figures recorded on August 11, 2026.** This report is
> a snapshot of the audit and its closure, not a reference for the repository's
> current state. For that, consult the README and CI.

Initial audit date: August 11, 2026  
Scope: `src/monl/`, `tests/`, configuration, documentation, and dependencies. Applications generated under `projets/` are outputs/demonstrations and are not considered compiler code.  
State documented here: initial audit, then closure verification after the refactorings performed in the working tree.

## Executive summary

MONL-Compiler is functional and very well covered by behavioral tests: the full suite now has **812 tests, all passing**, with **91.62% coverage**. The conceptual pipeline is sound (Lark → raw dictionary → validation/normalization → deterministic generator → artifacts), and the main audit risks have been addressed: single compilation, named IR result, shared route plan, explicit validation passes, transactional publication, typed errors, and shared test HTTP infrastructure.

The remaining risks are now concentrated in the complete migration of internal dictionaries to the IR, the generator's legacy mixins, and private helpers shared between tools. CRUD, payment, and post-payment routes have separate renderers; the frontend contract consumes `CompilationPlans` and no longer reads the generator's private methods. The tests remain integration tests and depend on local sockets, but their mechanics are shared.

No demonstrated **CRITICAL** defect was found. The **HIGH** issues of double compilation, partial publication, contract coupling, and route monolith have been resolved or greatly reduced; migration of internal representations remains to be completed.

## Method and limitations

- Read all entry points, inventoried classes/functions with AST, and reconstructed internal dependencies.
- Searched for symbols, calls, historical markers, broad exceptions, disk writes, and subprocesses with `rg` and Python `ast` analysis.
- `ruff check src tests`: **clean** after fixing import order.
- `pytest` in the sandbox: result uninterpretable because local sockets are prohibited (`PermissionError`).
- `pytest` outside the sandbox: **812 passed, 1 warning**, with local sockets allowed; the only warning is the intentional JWT warning from the forged-signature test.
- `pytest-cov`: **91.62%** (92% rounded), CI threshold set to 90%.
- `mypy src/monl/ir.py src/monl/errors.py src/monl/generator/emitters.py --strict`: clean.
- `vulture src/monl --min-confidence 90`: no findings.
- Lark `Transformer` methods and generator dispatches were verified to be dynamic; no Vulture findings were removed automatically.

## Actual pipeline

### Low-level path: `python -m monl.main`

```text
fichier source MONL
  → parse_monl_file()
  → parse_monl_string()
  → nettoyage des commentaires seuls
  → Lark LALR + MonlIndenter
  → arbre Lark
  → MonlTransformer
  → dictionnaire AST brut
  → MonlAST(raw, base_dir)
  → `ValidationPipeline` (business, security, content, and UI passes)
  → normalized `CompilationIR`
  → MonlSecureGenerator(normalized)
  → shared `CompilationPlans` + historical internal calculations
  → schema.sql + app.py + sandbox_ai.py + manage.py + .jwt_secret
```

### Product path: `monl compile`, `init`, or `update` command

```text
compile_project()
  → compile_monl()
      → parsing → ValidationPipeline → IR → generator + plans → backend artifacts
  → build_contract(IR, plans already calculated)
  → frontend_contract.json + FRONTEND_PROMPT.md + CLAUDE.md
  → monl.json (state fingerprints)
```

The frontend contract now consumes the `CompilationResult` from the first pass; there is no longer any reparsing, second audit, or second generator instance.

## Current module map

| Module | Current responsibility | Main dependencies | Called by | Produces | Single responsibility? |
|---|---|---|---|---|---|
| `parser.py` | Grammar, indentation, transformation, and syntax diagnostics | Lark | `main`, `cli`, tools, and tests | Raw dictionary | Almost; grammar and diagnostics could be separated, with no urgency |
| `ast_validator.py` | AST facade, specialized validation, asset resolution, and normalization | `os`, `re`, `validation_pipeline` | `main`, `cli`, tools | `CompilationIR` | Still mutable, but orchestration has moved to `ValidationPipeline` |
| `generator/core.py` | Derived state construction, orchestration, files, secret, and semantic helpers | six mixins, SQL | `main`, contract, tests | Artifacts and shared calculations | No |
| `generator/sql_schema.py` | SQLite DDL | implicit `MonlSecureGenerator` state | `core` via mixin | `schema.sql` as a string | Yes, but high implicit coupling |
| `generator/runtime.py` | Generated FastAPI/auth/migrations/rate-limit runtime | implicit state | `core` via mixin | Python lines | Broad responsibility |
| `generator/schemas.py` | Generated Pydantic models | implicit state | `core` via mixin | Python lines | Yes |
| `generator/routes.py` | CRUD, access, business-effect, payment, and post-payment renderers | SQL, implicit state, `RoutePlan` | `core` via mixin | Python lines | Responsibilities separated; some renderers remain verbose |
| `generator/emitters.py` | Composed facade for backend outputs | generator protocol | `core` | `BackendSources` | Yes; mixin migration step |
| `generator/admin_cli.py` | Generated admin CLI | implicit state | `core` via mixin | `manage.py` | Yes |
| `generator/sandbox.py` | Custom-logic stubs | implicit state | `core` via mixin | `sandbox_ai.py` | Yes |
| `frontend_contract.py` | IR/plans→contract projection, UI semantics, prompt, and files | IR, shared plans, design skills | `cli`, tests | JSON, Markdown, CLAUDE.md | Yes for projection; legacy compatibility accepted at boundary |
| `cli.py` | CLI parsing, orchestration, state, diff, coherence, server, frontend, assets, content | almost the entire package | console script | disk/process effects | No |
| `main.py` | Backend compilation API and secondary CLI | parser, validator, generator | `cli`, direct invocation | `CompilationResult` or typed error | Still overlaps with `cli.py` for the historical entry point |
| `dialogue_engine.py` | Questions, dialogue state, templates, and MONL emission | templates via local imports | CLI/TUI/tests | MONL source | No |
| `app_templates.py` | Domain and effect catalog | none | dialogue/tests | Template data | Yes, but large Python data file |
| `assets_tool.py` | Safe textual spec editing and asset management | parser/validator | CLI/tests | spec + files | No, but coherent as a transactional tool |
| `content_tool.py` | CSV ↔ `seed` blocks | `assets_tool` internals | CLI/tests | CSV/spec | No: depends on private APIs |
| `frontend_ai.py` | API providers, frontend import, CLI agents, verification | `ai` extra for requests, CLI/smoke via local imports | CLI/tests | frontend | No |
| `smoke_test.py` | App startup, API calls, and JS/DOM checks | uvicorn, Node/npm | CLI/tests | diagnostic | No, but intentionally cross-cutting tool |
| `serving.py` | FastAPI template for static hosting | none at compiler runtime | CLI/smoke | `serve.py` | Yes |
| `tui.py` | Terminal rendering | stdlib | dialogue/tests | display | Yes |

## Detailed findings

### HIGH-01 — The main pipeline compiled the same source twice — RESOLVED

- **Fichier / symbole :** `src/monl/cli.py:129-159`, `compile_project`; `src/monl/main.py:10-62`, `compile_monl`.
- **Reason:** `compile_project()` first calls `compile_monl()`, which parses, validates, instantiates the generator, and writes the backend. It then processes exactly the same source again, revalidates, and rebuilds a generator to produce the contract.
- **Evidence:** successive calls are visible at `cli.py:142-149`; the first pass is at `main.py:31-45`.
- **Likely impact:** doubled cost and audit logs, two instances that could diverge, difficulty making compilation transactional, and future risk that an impure validator could produce different results.
- **Recommendation:** create a pure service `compile_spec(path, base_dir) -> CompilationModel` that performs parsing/validation/analysis once; two emitters then consume the same result. The CLI layer alone handles display and errors.
- **Confidence:** 100%.
- **Closure status:** `compile_monl()` returns `CompilationResult(ir, generator, plans)` and `compile_project()` reuses this result to produce the backend, contract, and state. The second parse, second audit, and second instance are gone.

### HIGH-02 — The normalized IR had no explicit schema or type — PARTIALLY RESOLVED

- **Fichier / symbole :** `ast_validator.py:2274-2327`, `to_normalized_ast`; `generator/core.py:36-223`, constructeur ; `frontend_contract.py:215-746`, `build_contract`.
- **Reason:** the contract between passes is a nested dictionary whose keys are implicitly known to several modules. The generator then adds a second implicit IR in the form of dozens of mutable attributes.
- **Evidence:** direct accesses such as `normalized_ast["security"][...]`, many defensive `.get(...)` calls, and `getattr(generator, ..., {})` in the contract.
- **Likely impact:** key errors detected late, incomplete changes across validator/generator/frontend, mypy nearly powerless even if installed, and duplicated representations.
- **Recommendation:** gradually introduce `dataclass(frozen=True, slots=True)` or `TypedDict` at boundaries: `ParsedSpec`, `ValidatedSpec`, `EntityModel`, `RouteModel`, `FieldPolicy`. Serialize only at the JSON boundary.
- **Confidence:** 98%.
- **Closure status:** `src/monl/ir.py` now provides `CompilationIR`, `EntityModel`, `RelationModel`, `FieldPolicy`, `AccessPolicy`, `EffectPlan`, `RoutePlan`, and `CompilationResult`. The generator's historical internal attributes and some dictionaries remain to be migrated.

### HIGH-03 — The validator was a mutable object concentrating several domains — PARTIALLY RESOLVED

- **File / symbol at the start of the work:** `src/monl/ast_validator.py`, `MonlAST`; especially the former `_validate_structures` method.
- **Reason:** one class validates types, relations, access, payments, aggregations, numbering, seeds, assets, UI, landing, and capabilities, while progressively building the state consumed by normalization.
- **Initial evidence:** `_validate_structures` exceeded 1,000 lines and initialized many attributes as rules ran; validation order was part of the implicit behavior.
- **Likely impact:** risky changes, temporal invariants, responsibility conflicts, and poor unit testability of passes.
- **Recommendation:** keep a facade, but extract ordered pure passes (`schema`, `relations`, `access`, `effects`, `content`, `presentation`) that return diagnostics and typed enrichments.
- **Confidence:** 99%.
- **Closure status:** `ValidationPipeline` now has 25 named passes in a tested order, and `_validate_structures`/`StructuralValidationPass` have been removed. Specialized methods still live on `MonlAST` to preserve diagnostics and the internal API; extracting them into pure functions remains a later step.

### HIGH-04 — Route generation concentrated too much business logic and text rendering — LARGELY RESOLVED

- **Fichier / symbole :** `generator/routes.py:16-1166`, `_generate_route_lines`; `1168-1462`, paiements et post-paiement.
- **Reason:** the same layer selects routes, reconstructs policies, produces SQL, handles transactions/errors, and assembles Python line by line.
- **Evidence:** main method of 1,151 lines; depends on almost all derived attributes of `MonlSecureGenerator`.
- **Likely impact:** combinatorial branches that are hard to reason about, create/update/delete duplication, and indentation or escaping bugs detected only in generated code.
- **Recommendation:** first produce an action-typed `RoutePlan`, then render each family with small emitters. Do not change behavior until golden tests cover the outputs.
- **Confidence:** 98%.
- **Closure status:** `_generate_route_lines` now assembles separate renderers for CRUD/effects, payment, and post-payment; `Create`, `Read`, `Update`, `Delete`, and `Execute` each have their own method. The methods still generate text, but their responsibility is isolated and `RoutePlan` is shared.

### HIGH-05 — Artifact generation was not atomic as a set — RESOLVED

- **Fichier / symbole :** `generator/core.py:658-722`, `generate_all`; `frontend_contract.py:1219-1241`.
- **Reason:** files are written directly to the project, one at a time. An interruption or error after the first writes can leave a backend and contract from different generations.
- **Evidence:** four successive `open(..., "w")` calls at `core.py:714-717`, then frontend files written separately; `monl.json` state still comes later in `compile_project`.
- **Likely impact:** inconsistent project after disk failure, interruption, or late exception; `check_coherence` can detect but not prevent partial state.
- **Recommendation:** generate in a temporary directory on the same filesystem, verify, then replace artifacts in a coordinated way with a manifest/fingerprints and rollback on failure.
- **Confidence:** 95%.
- **Closure status:** `artifacts.py` stages the backend, contract, and state in a neighboring directory; `publish_files` backs up old versions and restores the project if a replacement fails. Assets and `frontend/` are never touched.

### MEDIUM-01 — Two CLIs and a library API that called `sys.exit` — RESOLVED FOR COMPILATION

- **Fichier / symbole :** `main.py:10-82`; `cli.py:1185-1371`.
- **Reason:** `main.py` remains a compilation function, secondary CLI, and dependency of the official CLI. `compile_monl()` catches every exception and exits the process.
- **Initial evidence:** `except Exception` followed by `sys.exit(1)` at `main.py:59-62`; official console script points to `monl.cli:main` in `pyproject.toml:35`.
- **Likely impact:** a Python caller cannot handle errors cleanly; overlapping responsibilities and harder testing.
- **Recommendation:** make compilation a function that raises typed exceptions; translate to an exit code only in `cli.main`. Then deprecate direct invocation of `monl.main`.
- **Confidence:** 99%.
- **Closure status:** `compile_monl()` raises `MonlError` and `main.py` translates this error only at its CLI boundary. `monl.cli` retains the `SystemExit` behavior of its user commands; `cmd_diff` no longer catches `BaseException`.

### MEDIUM-02 — Generator mixins: physical decomposition without explicit interfaces

- **Fichier / symbole :** `generator/core.py:28-35` et tous les `generator/*_*.py`.
- **Reason:** the mixins reduced the size of the former monolithic file, but each method freely reads the descendant's state. No constructor, protocol, or type documents the prerequisites.
- **Evidence:** six multiple inheritances; mixin modules without imports for the model they consume; comments saying “extracted from the former monolithic module.”
- **Likely impact:** hidden coupling, illusory reuse, runtime attribute errors, limited static analysis.
- **Recommendation:** prefer composition: inject an immutable `CompilationModel` into `SchemaEmitter`, `RuntimeEmitter`, `RouteEmitter`, etc.
- **Confidence:** 96%.
- **Closure status:** `BackendEmitter` now provides a composed facade and immutable `BackendSources` before staging. The mixins remain the historical implementation and still need to be migrated individually.

### MEDIUM-03 — The frontend contract depended on generator internals — RESOLVED IN PRODUCTION

- **Fichier / symbole :** `frontend_contract.py:215-746`, `build_contract`.
- **Reason:** the contract calls `_compute_fk_placements()` and `_compute_route_map()` and reads many private generator attributes. It therefore depends on more than the validated AST.
- **Evidence:** `build_contract` docstring acknowledges that the generator is reused “only for its calculations”; calls to methods prefixed with `_`.
- **Likely impact:** inability to evolve the backend and contract independently; second generator construction; private API becoming contractual.
- **Recommendation:** move FK placements and route plans into a shared analysis pass consumed by both emitters.
- **Confidence:** 100%.
- **Closure status:** `CompilationPlans` carries the route map, FK placements, identity keys, client keys, payment locks, and required policies. Product compilation passes these plans; the legacy API still accepts a generator and converts it at the input boundary.

### MEDIUM-04 — Several concepts have two or three successive representations

- **Fichier / symbole :** `ast_validator.py:2274-2327`, `generator/core.py:36-223`, `frontend_contract.py:215-746`.
- **Reason:** raw rules → validator structures → normalized dict → grouped generator attributes → frontend JSON projection.
- **Evidence:** `public_actions`, `ownership`, hidden, derived, aggregated, timestamped, and numbered fields are converted among lists of strings, tuples, dictionaries, and grouped lists.
- **Likely impact:** repeated conversions, type loss, synchronization defects; comments indicate successive contract fixes for each family of server fields.
- **Recommendation:** one canonical representation per concept in the IR; calculate views/indexes once and make them immutable.
- **Confidence:** 97%.
- **Closure status:** `CompilationPlans` is calculated once in `MonlSecureGenerator`, cached, and consumed by the routes and frontend contract. The historical dictionaries remain exposed to other mixins during migration.

### MEDIUM-05 — Extensive duplication of integration-test infrastructure — LARGELY RESOLVED

- **File / symbol:** at least 22 definitions of `_port_libre`, 11 of `_appel`, 11 `application` fixtures, and 4 fake Stripe providers, spread across `tests/test_*.py`.
- **Reason:** each domain reimplements compilation, free-port selection, uvicorn startup, waiting, registration, login, and requests.
- **Evidence:** AST analysis: `_port_libre` appears in 22 files; the same `subprocess.Popen([..., "uvicorn"...])` patterns and wait loops are repeated.
- **Likely impact:** over 30,000 lines total, a 3 min 47 s suite, robustness fixes needing to be repeated everywhere, and many spurious failures when sockets are prohibited.
- **Recommendation:** shared fixtures in `tests/support/`: `compiled_app`, `UvicornServer`, HTTP client, payment provider, account factory. Keep business scenarios in their files.
- **Confidence:** 100%.
- **Closure status:** `tests/support/server.py` shares port selection, startup, waiting, and uvicorn shutdown. Scenarios remain separate; some specific legacy helpers remain intentionally to limit risk.

### MEDIUM-06 — Reported coverage was not reproducible with the current installation — RESOLVED

- **Fichier / symbole :** `README.md:7-10`, badge 88 % ; `pyproject.toml:39-44`, extra dev.
- **Reason:** `pytest-cov` is declared but absent from the `.venv` environment; no minimum threshold is configured.
- **Evidence:** `pytest --cov=src/monl` fails with “unrecognized arguments”; the suite passes without coverage.
- **Likely impact:** displayed coverage may become outdated without causing CI to fail.
- **Recommendation:** install the actual dev extra in CI, publish `coverage.xml`, set a threshold and/or replace the static badge with one generated by CI.
- **Confidence:** 100%.
- **Closure status:** `pytest-cov` is in the dev extra, CI measures coverage, the threshold is set to 90%, and the latest run reports 92%. README badges now show CI instead of a fixed number.
### MEDIUM-07 — Type checking limited to new boundaries — PARTIALLY RESOLVED

- **File / symbol:** entire `src/monl`; `pyproject.toml`.
- **Reason:** mypy is neither declared nor configured, and public APIs have almost no annotations. Nested dictionaries make structural errors invisible to the linter.
- **Initial evidence:** mypy was absent; signatures such as `build_contract(normalized_ast, generator)` and `MonlAST(raw_json, base_dir=None)` were not annotated.
- **Likely impact:** risky refactorings and defects detected only at runtime.
- **Recommendation:** start with pass boundaries and new types, in gradual mode; do not try to annotate the long generator methods immediately.
- **Confidence:** 100%.
- **Closure status:** `mypy --strict` is enabled in CI on `src/monl/ir.py`, `src/monl/errors.py` and `src/monl/generator/emitters.py`. The gradual migration of historical modules intentionally remains open.

### MEDIUM-08 — `content_tool` imports private helpers from `assets_tool`

- **File / symbol:** `content_tool.py:7-16`.
- **Reason:** `_blocs_seed`, `_charger`, `_litteral` and `_revalider` are private details reused as an intermodule API.
- **Evidence:** direct imports of four names prefixed with `_`.
- **Likely impact:** local refactoring of assets could break CSV import/export; source-manipulation responsibilities are distributed arbitrarily.
- **Recommendation:** extract a public `spec_editing.py` module with parse/revalidate/block ranges/literal emission.
- **Confidence:** 100%.

### MEDIUM-09 — Historical documentation contradicts the current code

- **File / symbol:** `docs/phase_5_generator.md:6-31`, `docs/phase_6_systeme_complet.md:7-17`, `docs/phase_3_parser.md:15`, README badges.
- **Reason:** the documents refer to `src/generator.py`, `src/main.py`, access control via `x_actor`, `01_todo_list.ml` and `02_blog.ml`, whereas the current package, JWT and examples are different.
- **Evidence:** missing paths and a security warning already made false by `generator/runtime.py`, which generates JWT and account verification.
- **Likely impact:** readers are directed to nonexistent commands and may wrongly believe the current backend is an unauthenticated PoC.
- **Recommendation:** move the phases into `docs/history/` with an “archive” banner, or rewrite them; add a CI check for documented paths/commands.
- **Confidence:** 100%.

### MEDIUM-10 — General exceptions and errors are sometimes masked

- **File / symbol:** `main.py:59`, `cli.py:211`, `cli.py:874`, `assets_tool.py:122,138,572`, `tui.py:42`; generated code in `runtime.py` and `routes.py`.
- **Reason:** several `except Exception` clauses, one `except BaseException`, and some `None` returns make different causes indistinguishable.
- **Initial evidence:** `cmd_diff` caught `BaseException` at `cli.py:874`; `_empreintes_regenerees` turns every error into a missing fingerprint; `main` translated everything into a process exit. `cmd_diff` is now limited to `MonlError`.
- **Likely impact:** keyboard interruption swallowed in dry-run, incomplete diagnostics, programming errors presented as user errors. In generated code, some broad catches are transactional and justified, but must remain tested.
- **Recommendation:** define `MonlError` and subtypes (`Parse`, `Validation`, `Generation`, `ProjectState`, `Frontend`), catch only at CLI boundaries; keep transactional catches with an explicit re-raise.
- **Confidence:** 94%.
- **Closure status:** `MonlError` and its categories (`ParseError`, `ValidationError`, `GenerationError`, `ProjectStateError`, `ToolError`, `FrontendError`) now structure the boundaries; `compile_monl` and `cmd_diff` have distinct library and CLI behaviors.

### MEDIUM-11 — The template catalog and dialogue encode rules parallel to the validator

- **File / symbol:** `app_templates.py:67-487`, `dialogue_engine.py:397-1131`, `ast_validator.py`.
- **Reason:** the dialogue knows types, relations, registration, payment and directly constructs MONL text. Fortunately, the validator remains the final authority, but input constraints are duplicated.
- **Evidence:** constants `FIELD_TYPES`, `RELATION_TYPES`, logic `_ensure_ownership_structure`, `_ask_payable`, then complete revalidation of the emitted spec.
- **Likely impact:** a new language rule may be valid in the compiler but unavailable or misrepresented in the dialogue.
- **Recommendation:** expose a small shared semantic catalog (types, capabilities, shape constraints), without trying to generate the entire UI from the grammar.
- **Confidence:** 88%.

### LOW-01 — Dead method `_get_row_column_names`

- **Removal classification:** **SAFE_TO_REMOVE >95%**.
- **File / symbol:** `generator/core.py:947-958`.
- **Reason:** no references in `src` or `tests`; its docstring describes an old tuple conversion, whereas current routes build their responses differently.
- **Evidence:** exact symbol search: only its definition exists.
- **Likely impact:** no behavior; removal of 12 lines and an obsolete comment.
- **Recommendation:** remove after a full test, during the cleanup phase only.
- **Confidence:** 99%.

### LOW-02 — Historical wrapper `run_claude_code`

- **Removal classification:** **LIKELY_REMOVABLE 70–95%**.
- **File / symbol:** `frontend_ai.py:644-649`.
- **Reason:** no internal or test references; `generate_with_claude_code` remains in use and delegates directly to the generic path.
- **Evidence:** exact search: unique definition. The decision documentation says old names are retained for compatibility.
- **Likely impact:** none in the repository, but a possible break for an unknown external consumer.
- **Recommendation:** announce deprecation before removal or check the published public API.
- **Closure status:** the alias is documented as compatibility in `docs/DEPRECATIONS.md` and its docstring points to `run_cli_agent`.
- **Confidence:** 90%.

### LOW-03 — `landing.mode/template` compatibility has no effect

- **Removal classification:** **UNCERTAIN <70%**.
- **File / symbol:** `parser.py:276-279`; `ast_validator.py:2009-2012`.
- **Reason:** syntax is explicitly accepted but ignored, with a warning.
- **Evidence:** comment and loop `for obsolete in ("mode", "template")`.
- **Likely impact:** little simplification; removal would break old specs.
- **Recommendation:** document a deprecation window and measure existing specs before removal.
- **Confidence:** 60%.

### LOW-04 — Old `.yaml` extension still accepted/documented

- **Removal classification:** **UNCERTAIN <70%**.
- **File / symbol:** `main.py:68-69`, tests and documentation.
- **Reason:** historical compatibility without visible specific logic: the content remains MONL.
- **Evidence:** CLI help and tests mention the old extension; the parser reads the content regardless of suffix.
- **Likely impact:** very small technical debt, but format confusion and documentation maintenance.
- **Recommendation:** keep it until a global deprecation policy exists; this is not a cleanup priority.
- **Confidence:** 55%.

### LOW-05 — Ruff reported a single import order issue — RESOLVED

- **Removal classification:** not applicable.
- **File / symbol:** `frontend_contract.py:25-33`.
- **Reason:** local `design_skills` import placed after `generator.core`, contrary to the configured sorting.
- **Evidence:** Ruff `I001`, auto-fixable.
- **Likely impact:** cosmetic, but CI lint should be green.
- **Recommendation:** apply sorting during the cleanup phase.
- **Confidence:** 100%.
- **Closure status:** `ruff check src tests` is green.

### LOW-06 — `requirements.txt` mixed runtime and test dependencies — RESOLVED

- **File / symbol:** `requirements.txt:7-12`; `pyproject.toml:17-23,38-43`.
- **Reason:** `pytest` is in `requirements.txt` but not in the package's runtime dependencies; the two files are described as “synchronized” even though they do not describe the same use.
- **Evidence:** `requirements.txt` adds `pytest`; `pyproject` correctly places it in the `dev` extra.
- **Likely impact:** unnecessarily heavy installations and a misleading comment.
- **Recommendation:** make `pyproject.toml` the single source; optionally keep a generated `requirements-dev.txt`.
- **Confidence:** 100%.
- **Closure status:** `requirements.txt` no longer contains pytest or development tools; `pyproject.toml` carries the `dev` and `ai` extras.

### LOW-07 — `requests` was required only for two frontend providers — RESOLVED

- **Removal classification:** **UNCERTAIN <70%** as a global dependency; it is genuinely used.
- **File / symbol:** `frontend_ai.py:56-155`; `pyproject.toml:22`.
- **Reason:** the deterministic compiler and smoke test do not need it; only Claude/OpenAI API calls import it locally.
- **Evidence:** `requests` imports inside the two factories; the rest uses `urllib`.
- **Likely impact:** additional runtime dependency for all users, even without AI.
- **Recommendation:** consider an `ai` extra or standardize on `urllib`; do not remove it without preserving the providers.
- **Confidence:** 85% on making it optional, 0% on outright removal.
- **Closure status:** `requests` is in `.[ai]` and `.[dev]` for tests; missing the extra now produces an explicit `FrontendAIError`.

### LOW-08 — Compiler dependencies and generated application dependencies are conflated

- **File / symbol:** `pyproject.toml:17-23`.
- **Reason:** FastAPI, uvicorn and PyJWT are not imported by the normal compilation process, but are required to run the artifacts and smoke test. The package installs them all together.
- **Evidence:** their imports appear in generated code strings, the service wrapper or subprocesses, not in the compiler core.
- **Likely impact:** heavier installation but a simple `monl run` experience.
- **Recommendation:** make an explicit product decision: keep the “batteries included” bundle, or separate `compiler`, `runtime` and `ai`. The gain alone does not justify a break.
- **Confidence:** 95%.

### LOW-09 — Refactoring comments and “point” numbers dominate the code

- **File / symbol:** entire `src/monl`, especially `core.py`, `routes.py`, `frontend_contract.py`, `ast_validator.py`.
- **Reason:** long comments recount history (“ADDITION”, “FIX”, points 76/85/103…) rather than the current invariant.
- **Evidence:** very frequent references to `docs/design_decisions.md`, which exceeds 6,000 lines; docstrings mention the old monolith.
- **Likely impact:** cognitive noise, local documentation that ages, current logic harder to extract.
- **Recommendation:** keep non-obvious reasons and invariants in code; move detailed history to linked ADR/changelog entries with stable titles rather than sequential numbers.
- **Confidence:** 96%.

### LOW-10 — The README has static metrics that should be automated

- **File / symbol:** `README.md:7-10`.
- **Initial reason:** “756 tests” badge although 812 pass; “88%” coverage not verified during the initial audit.
- **Closure evidence:** `pytest-cov` run at 92% and README badges now based on CI status.
- **Likely impact:** reduced documentation trust.
- **Recommendation:** badges powered by CI or wording without a fixed number.
- **Confidence:** 100% for the test count, uncertain for the coverage value.
- **Closure status:** the number “812 tests passed in the last audit” remains informative, while the badges and official coverage are delegated to CI.

### INFO-01 — Static reports on Lark and mixins are not dead code

- **File / symbol:** `MonlTransformer` methods in `parser.py:384-695`; `_generate_*` mixin methods.
- **Reason:** Lark calls methods by production name; multiple inheritance resolves methods dynamically on `MonlSecureGenerator`.
- **Evidence:** `MonlTransformer().transform(tree)` and explicit inheritance in `core.py:28-35`; parser/generator tests pass.
- **Likely impact:** automated removal based on a raw Vulture result would break the compiler.
- **Recommendation:** configure Vulture allowlists or suitable decorations/annotations before adding it to CI.
- **Confidence:** 100%.

### INFO-02 — All declared dependencies are justifiable

- **File / symbol:** `pyproject.toml:17-23`.
- **Reason:** Lark parses; FastAPI/PyJWT are required by the produced applications; uvicorn serves and tests; requests serves AI providers.
- **Evidence:** usages found in `parser.py`, `generator/runtime.py`, `cli.py`, `smoke_test.py`, `frontend_ai.py`.
- **Likely impact:** no safe outright removal among base runtime dependencies; `requests` is now optional.
- **Recommendation:** keep essential dependencies and maintain the `.[ai]`/`.[dev]` separation; do not remove a runtime dependency without a distribution change.
- **Confidence:** 100%.

### INFO-03 — Security and business behavior have deep test coverage

- **File / symbol:** `tests/test_*` (payment, access, transitive ownership, stock, aggregation, migrations, attacks, rate limit).
- **Reason:** tests do not only check generated strings: many compile, launch uvicorn and actually query the API and SQLite.
- **Evidence:** 812 passes; attack, concurrency, signed webhook, multi-account isolation, migration, golden artifact and publication rollback scenarios.
- **Likely impact:** a strong safety net for gradual refactoring.
- **Recommendation:** preserve behavioral tests while sharing their infrastructure.
- **Confidence:** 100%.

## Error handling

Positive points:

- `MonlSyntaxError` preserves file, line, column and source excerpt.
- `ASTValidationError`, `AssetsToolError`, `ContentToolError` and `FrontendAIError` already provide domain boundaries.
- Asset operations attempt a restore if revalidation fails.
- Generated routes have many tests for 401/404/409/422/502 statuses and business atomicity.

Gaps:

- `compile_monl` now exposes `MonlError`; untyped internal generation errors are converted to `CompilationGenerationError`.
- Historical CLI commands still contain `sys.exit`, which is now confined to the user boundary.
- Ancillary asset/content tools do not have the same global rollback as project compilation.
- Disk space, permission or encoding errors have no visible dedicated tests.
- Most error tests target the DSL and generated application, less so failures of the orchestrator itself.

## Component-by-component test assessment

| Component | Tests present | Behavioral quality | Main gaps |
|---|---|---|---|
| Parser/diagnostics | Yes | Good: valid syntax and localized errors | No fuzz/property testing; entire grammar in one string is hard to cover structurally |
| Validator | Very many | Excellent on business/security refusals | Separate passes; complete migration of pure functions is still possible |
| SQL/API generator | Very many | Excellent: compilation, inspection and real execution | Global golden test added; fixtures still duplicated |
| Generated runtime/auth | Yes | Very good: JWT, registration, revocation, rate limit | Intentional warning about a short key in one test; high server startup costs |
| Payment/stock/effects | Yes | Very good, including concurrency and fake provider | Infrastructure repeated across several files |
| CLI/orchestration | Yes | Good on dispatch, paths, diff/update | Partial write failures and interruptions have little coverage |
| Frontend contract | Yes | Good on fields, routes, prompt and consistency | Shared plans; legacy compatibility retained at entry |
| Frontend AI/import | Yes | Good: API, CLI agent, zip-slip, protected artifacts | Tests grouped in a 689-line file with imports in sections |
| Assets/content | Yes | Good, restore and consistency tested | Coupling to private helpers; few tests of real filesystem failures |
| Dialogue/TUI/templates | Yes | Good on output and simulated interactions | Risk of duplication with validator's semantic catalog |
| Smoke test | Yes | Good, valid/broken frontend and UUID | Depends on local network, uvicorn, Node/npm/jsdom; non-hermetic test environment |
| Packaging/docs | Minimal | Version/import verified | Links, commands and obsolete documents not checked automatically |
Tests that are probably redundant: several files repeat “nonexistent entity/field,” “duplicate rule,” and “the benchmark spec compiles.” They should not be deleted in bulk: some serve as local characterization tests. Once the passes are separated, these cases can become parameterized at the validator level, while each business test keeps only one or two integration checks.

## Dependencies

| Dependency | Actual use | Recommended decision |
|---|---|---|
| `lark` | Compiler parser | Keep, essential |
| `fastapi` | Generated runtime and static server | Keep if `monl run` remains integrated; otherwise extra `runtime` |
| `uvicorn` | `monl run`, smoke tests, applications | Same decision as FastAPI |
| `PyJWT` | Generated backend authentication | Keep in runtime |
| `requests` | Claude/OpenAI AI providers; many tests | Extra `ai`; included in `dev` for tests, absent from the base runtime |
| `pytest` | Tests only | Remove from runtime `requirements.txt`, keep in extra dev |
| `pytest-cov` | Extra dev + CI | Coverage measured at 92%, threshold set to 90% |
| `ruff` | Lint | Keep in dev/CI |
| Vulture | Extra dev + CI | `vulture src/monl --min-confidence 90`, no current findings |
| mypy | Extra dev + CI | Strict on `src/monl/ir.py`, `errors.py` and `generator/emitters.py`; gradual expansion recommended |
| Node/npm/jsdom | Downloaded/used by frontend smoke tests | Document as a tool dependency; cache and no-JS mode still need clarification |

## Simplified map of the current architecture

```text
                    ┌──────────────────────┐
templates ─────────►│ dialogue_engine/TUI  │
                    └──────────┬───────────┘
                               ▼
                         source spec.ml
                               │
                               ▼
                    ┌──────────────────────┐
                    │ parser + Lark        │
                    │ raw AST dict         │
                    └──────────┬───────────┘
                               ▼
                    ┌──────────────────────┐
assets ────────────►│ MonlAST              │
                    │ validation + audit   │
                    │ normalized dict     │
                    └──────────┬───────────┘
                               ▼
                    ┌──────────────────────┐
                    │ SecureGenerator      │
                    │ derived state + mixins│
                    └──────┬────────┬──────┘
                           │        │
             backend/SQL ◄─┘        └─► frontend_contract + prompt
                    │                         │
                    └──────────┬──────────────┘
                               ▼
                    consistency + smoke + run

cli.py orchestrates the whole process and now reuses the same result
parser → MonlAST → SecureGenerator for a product compilation.
```

## Recommended target architecture

```text
source ─► Parser ─► Typed ParsedSpec
                    │
                    ▼
              ValidationPipeline
        schema → relations → security → business → content/UI
                    │
                    ▼
          Immutable, typed CompilationModel
          ├── EntityModel / FieldPolicy
          ├── RelationPlan / OwnershipPlan
          ├── RoutePlan / EffectPlan
          └── diagnostics
                    │
          ┌─────────┼─────────────┐
          ▼         ▼             ▼
     SqlEmitter  ApiEmitter  FrontendContractEmitter
          └─────────┼─────────────┘
                    ▼
          In-memory/temporary ArtifactSet
                    │
              final validation
                    │
             atomic publication

CLI / dialogue / assets / content remain adapters around this core.
They translate typed errors into messages without carrying business rules.
```

This target does not recommend a full rewrite. It formalizes the boundaries already in place and enables migration one pass at a time.

## The 10 main problems

1. `MonlAST` retains mutable specialized methods despite the explicit pipeline.
2. Partially typed IR: several historical generator attributes remain a second representation.
3. Generator mixins are still coupled through implicit state.
4. General exceptions in some tools and the generated runtime, despite the typed compilation boundary.
5. `content_tool` imports private helpers from `assets_tool`.
6. Historical phase documentation should be archived or rewritten.
7. Historical integration test helpers remain partly duplicated despite shared server support.
8. Historical compatibility (`run_claude_code`, `.yaml`, `landing.mode/template`) is now documented but still active.
9. Advanced filesystem failure tests are still limited to publication rollback.
10. Automated checking of links, commands and documentation examples remains limited.

## Safest removals

| Candidate | Classification | Rationale |
|---|---|---|
| `MonlSecureGenerator._get_row_column_names` | **SAFE_TO_REMOVE >95% — already removed** | Single definition, no internal/test calls, historical comment |
| Unsorted import correction | Not a removal | Purely mechanical Ruff change |
| Runtime `pytest` from `requirements.txt` | **SAFE_TO_REMOVE >95%** from this file only | Already correctly declared in the dev extra; do not remove it from dev |
| `run_claude_code` | **LIKELY_REMOVABLE 70–95%** | No internal usage, but external compatibility is possible |
| `landing.mode/template` | **UNCERTAIN <70%** | No effect, but explicit compatibility with old specs |
| `.yaml` extension | **UNCERTAIN <70%** | Low-cost debt and unknown external users |

There is not enough evidence to remove an entire module. The mixins, private helpers called once, and Transformer methods are live code. The next actual removal candidate is `run_claude_code`, but only after a warning release and a check of the published API.

## Most worthwhile refactorings

1. **Gradually extract `MonlAST` methods** into pure functions/passes behind the existing pipeline.
2. **Extend the typed IR** to policies and attributes still stored in internal dictionaries.
3. **Propagate typed exceptions** and reserve `sys.exit` for the CLI boundary. **Foundation done for compilation; historical tools remain to be addressed.**
4. **Decouple the mixins** in favor of composed emitters once the IR is stable.
5. **Archive historical documentation** and check documented commands in CI. **Banners and policy added.**
6. **Keep test resources explicitly closed**; the latest pass leaves only an intentional JWT warning.
7. **Define deprecation windows** for historical wrappers and syntax. **Policy published.**

## Staged cleanup plan

### Step 0 — Baseline and safeguards — COMPLETE

- Freeze the 812 passing tests as the CI baseline.
- Share integration server startup in `tests/support/server.py`.
- Fix Ruff and check `git diff --check`.
- Actually install `ruff`, `pytest-cov`, Vulture and mypy in the dev/CI extra. **Done.**
- Add Vulture allowlists for the Lark Transformer and document dynamic calls. **No findings at 90%; manual review retained.**
- Produce a few golden files for representative examples before any generation changes. **Done: global backend/contract/state golden.**

### Step 1 — Cleanup without architectural changes — PARTIAL

- Fix Ruff import order. **Done.**
- Remove `_get_row_column_names` after a full test run. **Done.**
- Explicitly deprecate `run_claude_code` if the external API must be preserved. **Policy and docstring added.**
- Separate runtime/dev requirements and fix README metrics. **Done; the `ai` extra is separate.**
- Mark phase documents as archives or update them. **Historical banners added.**

### Step 2 — Share tests — MOSTLY COMPLETE

- Create `tests/support/server.py`. **Done for the uvicorn lifecycle; other support helpers remain to be extracted if the need is confirmed.**
- Migrate one file at a time, without merging business scenarios.
- Add orchestrator interruption and write failure tests. **Rollback and incomplete staging covered.**
- Measure actual coverage and define a realistic threshold. **92%, 90% threshold.**

### Step 3 — Unify compilation — COMPLETE

- Create a function that returns `CompilationResult` (IR + generator + integrated diagnostics). **Done.**
- Have backend and frontend emitters consume the same result. **Done.**
- Remove the double traversal in `compile_project`. **Done.**
- Propagate exceptions; reserve `sys.exit` for the CLI boundary. **Done for `compile_monl`, tests added.**

### Step 4 — Formalize the IR — FOUNDATION COMPLETE, MIGRATION IN PROGRESS

- Introduce types for entities, fields, relations, policies and routes. **Foundation done in `src/monl/ir.py`; `CompilationPlans` is calculated once for the emitters.**
- Migrate `public`, `ownership`, server fields and payments first, as these concepts are currently represented in multiple ways.
- Gradually enable mypy on new modules.
- Keep a serialization adapter compatible with the current JSON.

### Step 5 — Split validation and generation — COMPLETE FOR THE CURRENT SCOPE

- Extract validation passes behind `MonlAST`. **Done: 25 explicit passes and ordering covered by tests.**
- Build `RoutePlan` before any code rendering. **Done and shared by backend/frontend.**
- Split CRUD routes, effects, payment and post-payment into targeted emitters. **Done: five action renderers and two business families.**
- Gradually replace mixins with composition.

### Step 6 — Artifact robustness — COMPLETE

- Generate all files in local staging. **Done.**
- Validate syntax, contract and fingerprints before publication. **Done by the pipeline and `monl.json`.**
- Publish with backup/manifest and restore on failure. **Done.**
- Test interruption, permission denied and simulated disk full. **Replacement rollback and incomplete staging covered; advanced system failures remain optional.**

### Step 7 — Deprecations — POLICY PUBLISHED

- Measure use of `.yaml`, `landing.mode/template` and historical wrappers.
- Publish a deprecation policy compatible with beta status. **Done in `docs/DEPRECATIONS.md`.**
- Remove only after at least one warning release and migration tests.

## Conclusion

The codebase does not need a rewrite or an aggressive purge. Its behavior is solid: **812 tests pass with 91.62% coverage**, lint, targeted mypy and Vulture are green, and integration checks genuinely cover SQLite, HTTP, authentication, payment, security and frontend generation. The cleanup cycle addressed the highest-value risks: a single pipeline, transitional IR, typed compilation errors, explicit validation passes, route renderers, transactional publication, `CompilationPlans`, golden tests and shared server support.

Code removals are still not safe enough to justify an automatic purge. The remaining topics involve gradual migration — internal types, CLI exceptions, mixins and documentation — and are separate from business functionality. They can be handled in small steps protected by the full suite and the CI coverage threshold.
