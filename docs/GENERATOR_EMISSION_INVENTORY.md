# Generator emission inventory — issue #119, steps 1 and 2

Measured on the source before point 207, except the four migrated rows updated
after step 2 (marked below). Counts are syntactic indicators,
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
| admin_cli | 354 | 1 | 7 | 2 | 3 | 16 | 12 |
| calculs | 116 | 10 | 1 | 3 | 0 | 0 | 0 |
| core | 303 | 0 | 0 | 9 | 0 | 2 | 0 |
| emitters | 46 | 0 | 0 | 0 | 0 | 0 | 0 |
| modele | 119 | 2 | 1 | 8 | 0 | 0 | 0 |
| paiement | 60 | 7 | 0 | 1 | 0 | 4 | 0 |
| pipeline | 171 | 3 | 2 | 7 | 0 | 0 | 1 |
| prealables | 83 | 1 | 0 | 1 | 0 | 0 | 0 |
| proprietaire | 298 | 6 | 1 | 1 | 0 | 0 | 0 |
| routes | 40 | 0 | 0 | 0 | 0 | 0 | 0 |
| routes_acces | 97 | 10 | 6 | 4 | 0 | 2 | 1 |
| routes_creation | 399 | 37 | 8 | 46 | 2 | 22 | 2 |
| routes_lecture | 307 | 46 | 9 | 75 | 0 | 30 | 0 |
| routes_lecture_filtree | 296 | 42 | 27 | 29 | 0 | 12 | 0 |
| routes_modification | 353 | 46 | 12 | 29 | 0 | 34 | 2 |
| routes_orchestration | 55 | 0 | 0 | 9 | 0 | 2 | 0 |
| routes_paiement | 366 | 22 | 12 | 2 | 0 | 18 | 2 |
| routes_prestataires | 235 | 21 | 7 | 9 | 0 | 20 | 2 |
| routes_suppression | 243 | 40 | 13 | 32 | 1 | 26 | 2 |
| routes_uploads | 64 | 14 | 4 | 0 | 0 | 12 | 0 |
| runtime | 90 | 0 | 3 | 0 | 0 | 0 | 0 |
| runtime_annexes (migrated) | 167 | 0 | 0 | 0 | 0 | 0 | 0 |
| runtime_connexion | 283 | 1 | 10 | 5 | 0 | 4 | 1 |
| runtime_fonctions_auth | 348 | 6 | 8 | 0 | 5 | 2 | 0 |
| runtime_headers | 67 | 0 | 1 | 0 | 0 | 0 | 0 |
| runtime_jetons | 206 | 11 | 0 | 0 | 0 | 16 | 0 |
| runtime_migrations (migrated) | 259 | 0 | 0 | 7 | 0 | 0 | 0 |
| runtime_montage | 327 | 3 | 7 | 0 | 6 | 98 | 0 |
| runtime_pool | 63 | 1 | 0 | 0 | 0 | 2 | 37 |
| runtime_preparation (migrated) | 226 | 0 | 0 | 0 | 0 | 0 | 0 |
| runtime_socle | 378 | 5 | 3 | 2 | 7 | 24 | 0 |
| sandbox (migrated) | 35 | 0 | 0 | 2 | 5 | 2 | 0 |
| schemas | 212 | 13 | 1 | 25 | 0 | 0 | 1 |
| sql | 100 | 3 | 5 | 2 | 0 | 0 | 0 |
| sql_colonnes | 252 | 4 | 0 | 9 | 0 | 0 | 0 |
| sql_schema | 197 | 6 | 2 | 76 | 0 | 0 | 0 |

Python emitters: sandbox, admin_cli, schemas, runtime and runtime_*,
routes and routes_*, calculs, paiement, prealables. core/pipeline assemble
artifacts; modele/proprietaire calculate metadata and SQL plans; emitters
provides typed interfaces. __init__ only exports the package. sql_schema and
sql_colonnes emit schema components; sql is the typed SQL boundary (point 108).
These SQL modules are outside this Python migration and remain authoritative.

Four modules are migrated. The three step-2 modules together have F=0, A=0,
B=0, Q=0, C=0; their generated Python retains its own runtime f-strings and
operators as literal template content. Their 39-case/547-file corpus covers
all generated artifacts, not only Python, with unchanged baseline hashes.
See point 207 for exclusions, determinism and executed mutation proofs.

Proposed migration order (first two steps delivered):

1. sandbox: smallest Python emitter with escaped quotes and doubled braces;
   Template removes both, preserving exact bytes (17 lines before migration).
2. runtime_annexes: 16 double-backslash occurrences, only one outer f-string;
   then runtime_preparation (7) and runtime_migrations (6), with focused runtime
   witnesses for regexes and migration behavior.
3. admin_cli, runtime_fonctions_auth, runtime_montage, runtime_socle:
   nested escaping and authentication/startup surfaces need stronger witnesses.
4. routes_uploads, runtime_pool, paiement, prealables, calculs, schemas,
   routes_acces, runtime_jetons, runtime_connexion: bounded emitters, progressing
   from small fragments to models and account state.
5. routes_suppression, routes_creation, routes_modification, routes_lecture,
   routes_lecture_filtree, routes_prestataires, routes_paiement: many assembled
   fragments, branch-heavy behavior and typed SQL integrations. Migrate one
   concern at a time, keeping SQL composition behind sql.py.
6. core/pipeline/runtime/routes/routes_orchestration assembly last; retain the
   existing literal multiline template in runtime_headers unless a measured
   problem requires changing it. Analysis-only modules need no code-template
   conversion.

Template is chosen over ast.unparse for sandbox because formatting, comments,
docstrings and trailing newlines must remain byte-identical. Substitution is
one-pass; dollars and braces inside values are not interpreted again. This
step preserves existing input validation behavior and adds no SQL emission.
