# Generator emission inventory — issue #119, steps 1 to 6

The route rows below are measured from the current source; earlier rows retain
their documented baseline unless marked migrated. Counts are syntactic indicators,
not estimates of generated lines: F = AST JoinedStr nodes (including adjacent
f-strings merged by Python); A = Add expressions/assignments; J = calls to
append/extend/join. They include analysis/list operations and generated-code
expressions as well as actual emission. Implicit adjacent literals are merged
by the parser; C counts adjacent STRING token pairs (ignoring comments and
non-significant newlines), making this implicit concatenation visible. B counts literal
double backslashes in source; Q counts backslash-double-quote pairs.

| Module | Lines | F | A | J | B | Q | C |
|---|---:|---:|---:|---:|---:|---:|---:|
| __init__ | 9 | 0 | 0 | 0 | 0 | 0 | 0 |
| admin_cli (migrated) | 350 | 0 | 0 | 9 | 0 | 0 | 0 |
| calculs (migrated) | 112 | 0 | 0 | 4 | 0 | 0 | 0 |
| core | 303 | 0 | 0 | 9 | 0 | 2 | 0 |
| emitters | 46 | 0 | 0 | 0 | 0 | 0 | 0 |
| modele | 119 | 2 | 1 | 8 | 0 | 0 | 0 |
| paiement (migrated) | 59 | 0 | 0 | 1 | 0 | 0 | 0 |
| pipeline | 171 | 3 | 2 | 7 | 0 | 0 | 1 |
| prealables (migrated) | 83 | 0 | 0 | 1 | 0 | 0 | 0 |
| proprietaire | 298 | 6 | 1 | 1 | 0 | 0 | 0 |
| routes | 40 | 0 | 0 | 0 | 0 | 0 | 0 |
| routes_acces (migrated) | 92 | 0 | 0 | 8 | 0 | 0 | 0 |
| routes_creation (migrated) | 386 | 0 | 0 | 52 | 0 | 0 | 0 |
| routes_lecture (migrated) | 305 | 0 | 0 | 77 | 0 | 0 | 0 |
| routes_lecture_filtree (migrated) | 299 | 0 | 0 | 29 | 0 | 6 | 0 |
| routes_modification (migrated) | 338 | 0 | 0 | 29 | 0 | 6 | 0 |
| routes_orchestration | 60 | 0 | 0 | 9 | 0 | 2 | 0 |
| routes_paiement (migrated) | 394 | 1 | 0 | 7 | 0 | 0 | 4 |
| routes_prestataires | 233 | 0 | 0 | 16 | 0 | 2 | 1 |
| routes_suppression (migrated) | 238 | 0 | 0 | 43 | 0 | 10 | 0 |
| routes_uploads (migrated) | 67 | 0 | 0 | 2 | 0 | 0 | 0 |
| runtime | 90 | 0 | 3 | 0 | 0 | 0 | 0 |
| runtime_annexes (migrated) | 167 | 0 | 0 | 0 | 0 | 0 | 0 |
| runtime_connexion (migrated) | 297 | 0 | 0 | 13 | 0 | 0 | 0 |
| runtime_fonctions_auth (migrated) | 362 | 0 | 0 | 9 | 0 | 0 | 0 |
| runtime_headers | 67 | 0 | 1 | 0 | 0 | 0 | 0 |
| runtime_jetons (migrated) | 226 | 0 | 0 | 0 | 0 | 0 | 0 |
| runtime_migrations (migrated) | 259 | 0 | 0 | 7 | 0 | 0 | 0 |
| runtime_montage (migrated) | 155 | 0 | 0 | 5 | 0 | 0 | 0 |
| runtime_pool (migrated) | 65 | 0 | 0 | 0 | 0 | 0 | 0 |
| runtime_preparation (migrated) | 226 | 0 | 0 | 0 | 0 | 0 | 0 |
| runtime_socle (migrated) | 360 | 0 | 0 | 2 | 0 | 0 | 0 |
| sandbox (migrated) | 35 | 0 | 0 | 2 | 5 | 2 | 0 |
| schemas (migrated) | 214 | 0 | 0 | 25 | 0 | 0 | 0 |
| sql | 100 | 3 | 5 | 2 | 0 | 0 | 0 |
| sql_colonnes | 252 | 4 | 0 | 9 | 0 | 0 | 0 |
| sql_schema | 197 | 6 | 2 | 76 | 0 | 0 | 0 |

Python emitters: sandbox, admin_cli, schemas, runtime and runtime_*,
routes and routes_*, calculs, paiement, prealables. core/pipeline assemble
artifacts; modele/proprietaire calculate metadata and SQL plans; emitters
provides typed interfaces. __init__ only exports the package. sql_schema and
sql_colonnes emit schema components; `src/monl/generator/sql.py` is the typed SQL boundary (point 108).
These SQL modules are outside this Python migration and remain authoritative.

Twenty-two modules are fully migrated. The three step-2 modules together have F=0, A=0,
B=0, Q=0, C=0; their generated Python retains its own runtime f-strings and
operators as literal template content. The four step-3 modules also have
F=0, A=0, B=0, Q=0 and C=0 after issue #142: the four single
backslash-quote pairs in runtime_socle belonged to the discarded TOTP fragment.
The expanded 52-case/732-file corpus covers
all generated artifacts, not only Python, with unchanged baseline hashes.
See point 207 for exclusions, determinism and executed mutation proofs.

Proposed migration order (first four steps delivered):

1. sandbox: smallest Python emitter with escaped quotes and doubled braces;
   Template removes both, preserving exact bytes (17 lines before migration).
2. runtime_annexes: 16 double-backslash occurrences, only one outer f-string;
   then runtime_preparation (7) and runtime_migrations (6), with focused runtime
   witnesses for regexes and migration behavior.
3. admin_cli, runtime_fonctions_auth, runtime_montage, runtime_socle: delivered.
   All measured lines/branches are covered before migration (94 statements,
   42 branches); account recovery with messages closes branch 64→71 in
   runtime_fonctions_auth. Phone with/without prefix and multiple selfRegister
   roles have explicit additional witnesses. No unchanged corpus entry is replaced.
4. routes_uploads, runtime_pool, paiement, prealables, calculs, schemas,
   routes_acces, runtime_jetons, runtime_connexion: delivered. Ten real specs
   are frozen before migration, retaining all 42 previous entries. All measured
   emitter branches are covered except the defensive Upload-without-ACL refusal:
   validated specs cannot reach it. prealables returns metadata; its mutation
   changes downstream emitted access-control bytes. All nine corpus mutations
   fail the byte assertion, not generator collection or syntax. F=A=B=Q=C=0
   for these nine modules. No architecture exception increases or decreases.
5. `routes_suppression`, `routes_creation`, `routes_modification`,
   `routes_lecture`, `routes_lecture_filtree` and `routes_prestataires` are
   delivered. `routes_prestataires` has J=16 line-list additions, Q=2 escaped
   quotes in emitted literals and C=1 adjacent literal pair; A and B are zero.
   `routes_paiement` is delivered: the webhook guards and
   `_generate_payment_routes` emit through `string.Template`. Its one remaining
   JoinedStr is a generation-time refusal message (a compiler diagnostic, not
   emitted code). Its twelve `lines += [...]` extend the line list, the same
   assembly counted as J elsewhere, so no text is concatenated; C=4 are
   adjacent literal pairs. The payment invariants are unchanged (amount read
   from the database, no request body, ownership join inside the existing
   SELECT, signature checked before any write): corpus and golden bytes are
   identical, and `test_paiement`, `test_fedapay` and `test_verrou_paiement`
   pass against real servers.
   `routes_lecture_filtree` and `routes_modification` each have Q=6 escaped
   quotes in emitted literals; J=29 counts their line-list additions.
   `routes_suppression` has Q=10 and J=43 for emitted body lines. These Q/J
   counts describe Python source construction; SQL values remain composed
   through `src/monl/generator/sql.py`.
6. `routes_orchestration` is assembly only (J=9, Q=2 in generated imports) and
   has no f-string emission to convert. `core` has no generated-text assembly;
   `pipeline`'s three f-strings are console diagnostics, while its list additions
   and `join` assemble already emitted sections. `runtime` appends emitted helper
   lines, and `routes` only delegates to route mixins. These are list/module
   assembly operations rather than f-string or string-addition emission, so no
   Template conversion is indicated. Step 6's inspection is complete; there is
   no emitted text concatenation in these orchestration modules to migrate.
   `routes_acces` (J=8) and `routes_uploads` (J=2) also append emitted lines.
   Across the measured `routes_*`, A is zero. Nonzero Q values are the escaped
   quote pairs in generated literals described above. `runtime_headers` remains
   unchanged by decision.

Template is chosen over ast.unparse for sandbox because formatting, comments,
docstrings and trailing newlines must remain byte-identical. Substitution is
one-pass; dollars and braces inside values are not interpreted again. This
step preserves existing input validation behavior and adds no SQL emission.
