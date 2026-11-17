# Generator emission inventory — issue #119, steps 1 to 5 (partial)

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
| routes_lecture_filtree (migrated) | 299 | 0 | 20 | 29 | 0 | 6 | 0 |
| routes_modification (migrated) | 338 | 0 | 12 | 29 | 0 | 6 | 0 |
| routes_orchestration | 60 | 0 | 0 | 9 | 0 | 2 | 0 |
| routes_paiement (partiel) | 380 | 17 | 12 | 3 | 0 | 16 | 2 |
| routes_prestataires (partiel) | 234 | 14 | 7 | 9 | 0 | 2 | 1 |
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
5. routes_suppression, routes_creation, routes_modification, routes_lecture
   and routes_lecture_filtree are delivered. Their F/B/C counts are zero.
   `routes_paiement` is partially delivered: the
   webhook size and signature guards are complete Template-emitting functions,
   while `_generate_payment_routes` retains 17 JoinedStr nodes. Its remaining
   A=12 builds line lists and SQL/query fragments, J=3 assembles emitted lines,
   Q=16 are escaped quotes in emitted Python/SQL text, and C=2 are adjacent
   literal pairs. The payment migration deliberately stops at the completed
   guards for this tour; the rest of step 5 is not claimed delivered.
   `routes_lecture_filtree` has A=20 query/API line composition and Q=6 escaped
   quote pairs in emitted literals. `routes_modification` has A=12 list/query
   composition and Q=6 escaped quote pairs. `routes_prestataires` is also
   partially delivered, with F=14 still present. These A/Q/J counts are
   syntactic, include assembly or analysis, and do not by themselves mean
   unsafe SQL; dynamic SQL remains composed through `src/monl/generator/sql.py`.
6. `routes_orchestration` is assembly only (J=9, Q=2 in generated imports);
   `core`, `pipeline`, `runtime` and `routes` have no measured JoinedStr
   emission and are not migrated. The step-6 orchestration migration remains
   outstanding. `runtime_headers` remains unchanged by decision. Analysis-only
   modules need no code-template conversion.

Template is chosen over ast.unparse for sandbox because formatting, comments,
docstrings and trailing newlines must remain byte-identical. Substitution is
one-pass; dollars and braces inside values are not interpreted again. This
step preserves existing input validation behavior and adds no SQL emission.
