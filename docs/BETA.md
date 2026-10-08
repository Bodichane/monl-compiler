# Beta status and path to GA

## What release candidate 1.0.0-rc.1 brings

The release candidate strengthens security, declares language version 1 and
its stability contract, and adds the Claude Code plugin. See CHANGELOG.md.

## What beta 0.9.0-beta.10 brought

A beta focused on **correctness**: two continuous improvement agents repeat the
journey of a user from a wheel installed elsewhere and exercise the added
witness tests. What they found has been fixed — the contract finally announces
the key targeted by a counter (a faithful frontend was getting a 422), `monl run
--check` no longer promises nonexistent pages and accepts a project with assets
but no frontend, `monl-platform --help` lists its verbs, and post-payment status
is created in its initial state. Points 191 to 196 of
`docs/design_decisions.md`.

## What beta 0.9.0-beta.9 brought

A **change of direction** (point 162): monl produces the backend and its database,
deterministically and without network calls; everything that requires AI is
done with the user's provider, on their machine. The platform therefore no
longer builds a frontend — its console leads the **guided dialogue** like the
command line, and the **MCP server** lists, compares, and updates a project
without a browser. The archive of a compiled project stores its documents in
`docs/` and names its memory AGENTS.md. The platform is **actually deployed**
(GHCR image, survives restarts), a **security audit** closed five real flaws
there (including the *login CSRF* in the OAuth round trip), the generated
backend gains its **indexes** and a **PostgreSQL pool**, and the compiler becomes
**publishable** through Trusted Publishing. Points 143 to 190 of
`docs/design_decisions.md`.

## What beta 0.9.0-beta.8 brought

The repository moves to the **FSL-1.1-ALv2 license** (automatic switch to
Apache-2.0 two years after each release), and monl gains a **web platform**:
compile through an API, API key, or **MCP server**, with accounts, projects,
backup codes, legal pages, journal, rotating backup, and a command-line
administration panel — never on the web, because a panel would become a target
where one flaw exposes every account. On the compiler side: **FedaPay** joins
Stripe for mobile money, **brick 29** requires every file requested by the
frontend to actually be served, and the test harness **fails instead of
skipping**. Points 125 to 142 of `docs/design_decisions.md`.

## What beta 0.9.0-beta.7 brought

The generated backend is **deployable** (CORS, health checks, structured logs,
container), speaks **PostgreSQL** as well as SQLite, can **migrate** a
non-additive schema without losing data, accepts an **uploaded file**, can
**send a message**, can **filter and sort** on the server without exposing a
query language, and provides **complete authentication** (per-account lock,
reset, rotating refresh tokens, TOTP). Points 117 to 124 of
`docs/design_decisions.md`.

## What beta 0.9.0-beta.6 fixes

This release adds the business capabilities and in-depth access control
developed since beta 5: server-side calculations (`derivedFrom`, `sumOf`),
aggregations (`sumOf`), transitive ownership, stock, timestamps, numbering,
field constraints, enumerated values, required profiles, and locking records
after payment. It also adds frontend editing tools and aligns the version
metadata of the package and compiled projects.

## What beta 0.9.0-beta.5 fixes

A gap in scope, not a fix: the last link in the cycle — the AI that writes the
frontend — only accepted Anthropic, while the module had promised since the
pivot an abstraction “extensible without touching the orchestration loop.” It
now is: any OpenAI-dialect key (`groq`, `openai`, `openrouter`, `deepseek`,
`mistral`, `together`, `xai`, `ollama`, plus a fallback for any other endpoint),
and any command-line agent (`codex`, `gemini`, or `--agent-command`). No
safeguard is relaxed along the way — that is point 69. The compiler itself is
unchanged.

## What beta 0.9.0-beta.4 fixes

Nothing in the compiler: no rule, generated route, or contract differs from
beta 3. This release makes the repository readable to someone discovering it,
now that it is public — `LICENSE` and `CONTRIBUTING.md` added, README rewritten,
`demo/` stops versioning its own output. Two real fixes nonetheless, on the
verification side: the time-channel test no longer depends on machine load (it
failed intermittently in CI), and it no longer leaves an orphan server on
failure. Details in `CHANGELOG.md`.

## What beta 0.9.0-beta.3 fixes

External repository audit: one critical flaw (self-assignment of a privileged
role during signup), five serious flaws (timing-based enumeration, non-atomic
quota, secret with mode 0644, blacklist not purged, foreign keys never
enforced), and one determinism flaw (actor order derived from a `set`). All
fixed and covered by `tests/test_beta3_regressions.py`; details in
`CHANGELOG.md`. The monolithic generator was split into package
`src/monl/generator/`.

## What beta 0.9.0-beta.1 fixes

All blocking flaws identified in the audit have been fixed:

1. **Local generative AI removed.** Complete removal of Ollama and the three
   functions that depended on it (`--nl`, `--prompt`, `--fill-custom` filling
   of `custom` blocks). The compiler is now fully deterministic and offline;
   `custom` blocks are empty shells written by hand. The only AI in the
   lifecycle is the one that builds the frontend (Claude).
2. **Transactional integrity.** Creation + `increments`/`decrements` effects
   in a single transaction (one commit, rollback on error).
3. **Secret hygiene.** The JWT secret can be injected through
   `MONL_JWT_SECRET` (never on disk). No generated artifact or secret is
   included in the distribution archive.
4. **Constant-time comparison** of password fingerprints at login.
5. **Proxy-aware rate limiting** (`MONL_TRUST_PROXY`), without which
   `X-Forwarded-For` is ignored (no spoofing by a direct client).
6. **Packaging.** `pyproject.toml`, dependencies pinned with upper bounds,
   `monl` command via `pip install -e .`.
7. **Documentation**: `docs/SECURITE.md` (security model), this file.

## Beta exit criteria (Definition of Done) — met

- [x] `pip install -r requirements.txt` followed by compiling an `.ml` file
      produces a working backend, with no AI or network dependency.
- [x] Green test suite, including the offensive audit replayed against all
      examples (role spoofing, forged JWT, privilege escalation).
- [x] No secret or generated artifact in the delivered archive.
- [x] Secret injectable through an environment variable.
- [x] Multi-step operations are atomic.

## What has been done since this list was written

- [x] **Packaged as a real Python package** — the code lives in `src/monl/`,
      `pip install -e .` provides the `monl` command, and `import monl` works
      from any directory. The shim and `sys.path.insert` calls are gone; CI
      repeats the installation on every push. See point 65. This was item 7 on
      the list below, and leaving it among the remaining tasks would make work
      already delivered look outstanding.
- [x] **Generalized offensive audit, passing** —
      `tests/test_audit_offensif_exemples.py` replays the three attacks against
      every example (role spoofing, forged JWT, privilege escalation): none
      succeeds. The two signals studied in depth are false positives (public
      route, role not self-assigned), and the static `CRITICAL_WARNING`s are
      covered at runtime (role, ownership, payment lock, referential integrity).
      Details and status in `docs/SECURITE.md`.

## What remains for a “professional tool” GA

In priority order:

1. ~~**Production data layer**~~ — **DONE (workstream A1)**: the same
   `app.py` chooses SQLite or PostgreSQL at startup through
   `MONL_DATABASE_URL`; `psycopg` remains optional in `.[postgres]`. Additive
   migrations, integrity, numbering, and stock count have been tested against
   a real PostgreSQL, and CI starts the service. The PostgreSQL pool is implemented with `MONL_DB_POOL_MIN` /
   `MONL_DB_POOL_MAX` (point 182). Non-additive migrations are implemented
   (point 120): rename, type changes and explicit drops; reversible operations
   support down migrations, while a down migration containing an irreversible
   drop is refused and requires backup recovery (see [MIGRATIONS.md](MIGRATIONS.md)).
2. **Template/AST-based generator**, first step delivered (point 207,
   issue #119): `src/monl/generator/sandbox.py` now emits Python with `string.Template`,
   preserving bytes. Runtime, routes, schemas and admin_cli emitters remain
   to migrate, along with their assembly; see
   [the measured inventory and migration order](GENERATOR_EMISSION_INVENTORY.md).
   SQL continues through the typed `src/monl/generator/sql.py` boundary (point 108).
   Golden tests and a custom-block byte/execution witness guard this step.
   Parser fuzzing is done (point 204): mutated specs compile or get a named
   monl error, checked by `tests/test_fuzzing_parseur.py`.
3. ~~**Deployment-ready**~~ — **DONE (point 118)**: CORS opt-in through
   `MONL_CORS_ORIGINS` (`*` refused at startup), JSON logs with request ID via
   `MONL_LOG_FORMAT=json`, health checks `/health` and `/health/ready`,
   `Dockerfile`/`.dockerignore` generated and preserved, refusal to start if
   `MONL_ENV=production` without `MONL_JWT_SECRET`. Proven by an actual image
   build. **Still open**: integration with a dedicated secrets manager (Vault,
   SSM) — the secret currently comes from the environment, which is the
   contract these managers expect but does not replace them.
4. ~~**Complete auth**~~ — **DONE (point 124)**: PER-ACCOUNT lock (the point 9
   limit was per IP), password reset (unblocked by point 122), refresh tokens
   WITH ROTATION, and offline TOTP two-factor authentication. The lock is not
   an existence oracle: a locked account and a nonexistent account return the
   same response, within 1.28 ms. **Still open**: address verification at
   signup — monl can now send messages, but confirming an address is a flow
   decision (what do we do with an unconfirmed account?) that has not been
   made.
5. ~~**DSL governance**~~ — **DONE (point 200)**: language version,
   keyword/type compatibility ratchet, all repository and plugin examples
   compiled, and [stability and deprecation policy](STABILITY.md).
6. **Execution isolation for `custom` code** (lower-privilege subprocess /
   container / WASM). **Moved down from first place, and why**: this priority
   dates from when `custom` blocks were filled by local AI — a feature removed
   in beta 1. The generator now only writes empty shells that the project
   author completes themselves (`src/monl/generator/sandbox.py`). Isolating
   code the author knowingly wrote is no longer the same security boundary as
   isolating code produced by a model; the item remains relevant for
   multi-tenant execution, it simply is no longer the task that unblocks the
   rest.
7. **Written threat model completed; independent external audit/penetration
   test remains open** (issue #124). The maintained [threat model](THREAT_MODEL.md)
   covers the generated backend and hosting platform with verified test references
   and explicit gaps; the [external audit brief](EXTERNAL_AUDIT.md) is prepared but nothing is commissioned. Internal offensive regression tests and the dated
   `CODEBASE_AUDIT.md` do not establish an independent audit.

## Positioning

The core value is the **deterministic, safe backend intent compiler**. The
only AI in the lifecycle is the one that builds the frontend against a
verified contract. The production data layer has now been proven; GA effort
can therefore focus on the remaining generator, operational integration and
independent review tasks above.
