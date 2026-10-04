# Changelog

## 1.0.0-rc.1 — A verifiable promise

This first release candidate declares language version 1 and the interfaces
promised for 1.0. Security changes cover both the platform and generated
backends, with executable witnesses. The repository documentation is now
in English. Design points 197 to 200 accompany this release.

### Security

- **Platform revocation reaches every access method**: security changes revoke
  sessions and API/MCP access as appropriate. Project and account deletion
  removes owned resources and stops hosted sites; deletion requires
  reauthentication.
- **Generated backends require the password for TOTP changes**. `token_version`
  invalidates existing tokens after password changes, password resets and
  TOTP changes. `manage.py totp-reset` provides operator recovery.
- **The offensive audit of the examples remains active** (point 197), replayed
  by CI against real servers with explicit expected responses and token and
  session-cookie witnesses.
- **SECURITE.md describes the delivered backend**, including its limits.

### A spec can be refused

- **Counters cannot target an entity sharing an actor's name** (point 199).
  Account identifiers do not identify rows in that entity. Compilation refuses
  `increments`/`decrements` on such a target; the social example now targets
  the post score and limits reports to one per account and post.

### Commands and stability

- **`monl init` exits without a traceback** on EOF, interruption or three
  invalid answers.
- **SQLite WAL activation waits at startup** within the busy timeout instead
  of failing at once when two workers start on a fresh database. The platform
  reports the error when that timeout expires; a generated backend keeps its
  rule of never failing startup and stays on SQLite's default journal.
- **Language version 1 is explicit** in the CLI and `monl.json` (point 200).
  A grammar ratchet guards vocabulary changes; STABILITY.md defines the
  promised interfaces, breaking-change policy and deprecation period.

### Claude Code and documentation

- **Claude Code plugin** (point 198): `claude plugin marketplace add
  Bodichane/monl-compiler` then `claude plugin install monl-compiler@monl-compiler`.
  The `monl-spec` skill takes a need to a backend verified by the command line;
  the five interface skills follow.
- **The plugin moves to this version after publication**; its manifest and
  compiler pins retain the published beta until then.
- **Repository documentation is in English**.

1721 tests, 23 declared skips (all unrequested PostgreSQL integration tests),
clean `ruff`. Across the three golden specs, changing the compiler version
changes only `compiler_version` in `monl.json`. The wheel was built, checked
with `twine check`, installed in a fresh venv outside the repository and
exercised end to end (compile, backend, platform) before tagging.

## 0.9.0-beta.10 — What the user gets

A short beta, born from two continuous improvement agents added to the repository
(`.claude/agents/`): **first-user** repeats the journey of someone who does not
have the repository — wheel installed in a fresh venv, compilation, delivered
backend, platform, MCP, lost account then deleted — and **counter-proof**
checks that an added test really bites. Every defect they found became an issue,
then a fix with its witness. Six design points, 191 to 196.

1634 tests, 16 declared skips (all unrequested PostgreSQL integration tests),
clean `ruff`. Between beta.9 and beta.10 compiled from the same code, `diff -r`
shows only one line, `compiler_version` in `monl.json`; the output changes in
this version come from point 191, which documents them.

### A spec can be refused

- **The post-payment status starts in its first state** (point 191). A
  `writableAfterPayment` field carrying a `oneOf` receives the FIRST declared
  value on creation, instead of `NULL` outside its own lifecycle. If this first
  value also triggers `releases`, compilation now refuses and asks you to
  declare the initial state first. Earlier rows remain `NULL` and are counted
  at startup (point 89).

### What the user gets was accurate

- **The contract announces the key targeted by a counter** (point 195). When
  the relation targeted by `increments`/`decrements` was not the first incoming
  relation, the contract omitted it: `POST /orderline` without `variant_id`,
  `POST /like` without `post_id` — any frontend faithful to the contract got a
  422. The contract reads from the same source as the schema, and an invariant
  compares the 39 POST/PUT routes in the repository specs against the actual
  emitted Pydantic schema, in both directions. `monl update` on an existing
  project therefore announces these fields: the contract becomes accurate.
- **`monl run --check` on an assets project without a frontend** no longer
  refuses a healthy application: the smoke test mounts the wrapper whenever
  there are assets, as `monl run` does (point 195).
- **`monl run --check` no longer announces nonexistent pages** (point 196):
  « landing, /app » were promised, 404s served. The dead `/app` prefix is also
  removed from consistency checks, which now flag a frontend that calls it.
- **`monl-platform --help` lists `admin` and `backup`** (point 196), derived
  from the table used by dispatch.

### The platform

- **Visual redesign** of sign-in, the console, and the home page.
- **Four behaviors of the sign-in page** are finally guarded by a test
  (point 193) — including the OAuth provider button, now built with the DOM.

### The tests

- **Hosting tests no longer leave orphaned servers** (point 192): every test
  that starts a `serve:app` goes through a manager whose `finally` stops
  everything, and a witness verifies that the PID has disappeared.
- **Two hollow witnesses fixed** (point 194), proven hollow by the
  counter-proof agent: an assertion that stopped at the headers, and a tilt
  measured on a zero-size card.

## 0.9.0-beta.9 — The direction, and production deployment

Beta 8 opened a platform; this one deploys it for real, and first changes what
it promises. **Maintainer decision (point 162): monl produces the backend and
its database — deterministic, audited, with no network call — and everything
that requires AI is done with the user's provider, on their machine.** The web
console no longer builds a frontend; it does what the command line does:
guided dialogue → contract + database. Forty-eight design points, 143 to 190.

1606 tests, 16 declared skips (all unrequested PostgreSQL integration tests),
clean `ruff`. The compiler changes its output only where a point says so:
between beta.8 and beta.9 compiled from the same code, `diff -r` shows only one
line, `compiler_version` in `monl.json`.

### Breaking change

- **The platform no longer builds interfaces** (point 162). The AI builder is
  removed — `builder`, `worker`, the build queue and its routes, quotas,
  `/api/usage`, and the eight AI settings in `create_app`. In production it
  returned 503 because no provider was connected; and when our key paid for it,
  every account opened a bill. Hosting now serves the **compiled** directory,
  frontend optional. The command-line `monl frontend` is unchanged.
- **The archive of a compiled project is organized** (point 176): documents
  intended for interface AI go into `docs/` (`docs/FRONTEND_PROMPT.md` and the
  visual direction), project memory is called `AGENTS.md` instead of `CLAUDE.md`,
  and `sandbox_ai.py` is no longer produced without a `custom` block (point 175).
  `frontend_contract.json` remains at the root.

### The loop closes without a browser

- **Guided dialogue on the web** (point 163): the console replays the
  deterministic engine on every request, with no hidden state.
- **MCP**: `monl_list_projects`, `monl_diff_spec`, `monl_update_backend`,
  and a downloadable archive with the key — an agent compiles, retrieves, and
  updates a project without ever opening the site.
- **Sign-in with GitHub or Google** (point 145): an identity verified by a
  third party, and still no message sent by monl. The sign-in page offers the
  backup code route.

### Ready for real users, and in production

- **Four blockers found by being the first user** (point 164), including a
  platform **that could not be deployed from an ordinary `pip install`**:
  `favicon.ico` was not included in the package, and CI, installed in editable
  mode, could not see it. The site fits at 375 pixels (point 165).
- **The container path executed** (point 166) under the actual compose
  restrictions, then **the production deployment tested** (point 185) — GHCR
  image, `scripts/deploy_platform.sh`, backup probe that no longer leaks its
  file descriptors.
- **The platform comes back after a restart** (point 189): compose declared
  `unless-stopped`, which `podman-restart.service` does not restart.

### Security: a static audit, five real defects, all fixed

- HTTP bodies **bounded even without `Content-Length`** and recompilation
  admission limited (point 186).
- **OAuth `state` is bound to the browser** that started the flow — ending the
  *login CSRF* that signed a visitor into an attacker's account (point 187).
- **Hosted site cap** (20 total, 3 per account) and payment webhook body
  bounded (point 188).
- The platform **refuses to start** if it declares HTTPS with an insecure
  session cookie, and a hosted site that crashes finally leaves a trace,
  `site.log`, read by `monl-platform admin journal` and never by a web route
  (point 172).

### Compiler

- **Performance**: indexes on what a route queries (foreign keys, `filter`,
  then `accessibleBy` and `publicWhen` by invariant), token decoded once,
  **PostgreSQL connection pool — 28.7 ms → 5.1 ms** per authenticated request
  (points 181 to 183).
- `upload`, `filter`, and `sort` are **finally written by guided dialogue**
  (point 173), and `required` text must be **filled in**, not merely present
  (point 179).
- Stock release follows the field that payment took from it.
- Compiler and IR plans consolidated; validator made a package (points 152
  to 155).

### Publication

- **The compiler is publishable** (points 167 and 169): complete metadata,
  license as `LicenseRef-FSL-1.1-ALv2`, and a **Trusted Publishing** workflow —
  a `v*` tag tests the tag's commit on three Python versions, builds once,
  uploads to TestPyPI then to PyPI after approval. No long-lived secret. See
  `docs/PUBLICATION.md`.

### Brand

- New logo: monochrome mark and MONL COMPILER lockup (point 177).

### Tooling

- Measured complexity becomes a **ratchet** (point 170), the platform coverage
  gate no longer depends on a file list (point 184), and **an invariant
  protects all documentation** against silent staleness (point 190).

## 0.9.0-beta.8 — The platform, and the right to open it to the public

A beta that changes almost nothing in the compiler and a lot in what surrounds
it. The repository moved to the **FSL-1.1-ALv2 license** (automatic switch to
Apache-2.0 two years after each release), and monl gained a **web platform**:
compile through an API, with a key, or through an MCP server, with accounts,
projects, and a command-line administration panel. Eighteen design points,
125 to 142.

The license switch has the biggest consequences: free, professional, and
commercial use remain fully allowed, including delivering applications to
clients. Only *competing* use — making a monl-compiler again — is reserved, and
that restriction ends after two years.

1113 tests, clean `ruff`, compiler coverage at 90%. The compiler itself is
**unchanged byte for byte** for any spec that does not request the new bricks:
golden tests prove it; only `monl.json` changes because it seals the version
number.

### A web platform, from portal to administration panel

- **Compile without installing anything**: `POST /api/compile` and
  `/api/validate`, web console, guide, example catalog, compiled project
  download.
- **MCP server** (`/mcp`) and revocable **API keys**, to connect an agent to the
  compiler rather than to a console.
- **Accounts**: registration, sessions, account and data deletion.
- **Eight backup codes** provided once at registration. “We'll send you a
  link” is the rejected approach: it would begin with “monl can send a message,”
  and the privacy policy promises the opposite.
- **`monl-platform admin`** — eight commands for accounts and projects. The web
  panel is deliberately refused: it would need its own authentication and
  become a target where a vulnerability exposes every account, while anyone
  with the shell already has the database.
- **Log, rotating backup, and periodic purge**, plus a read-only container
  image and a backup companion on a separate volume.
- **Legal pages** — terms, privacy, notices. `legal.py` invents no identity:
  missing information gets a visible marker on the served page, guarded by a
  test. The list of retained data is checked against the actual SQLite schema —
  a policy out of sync is worse than none; it makes claims.
### Accept payments by mobile money (points 126 to 128, 131)

- **FedaPay** joins Stripe: the provider becomes pluggable, the payment
  currency and its exponent are declared, and webhook matching is
  proven rather than assumed.

### Compiler: four bricks and a safeguard (points 135 to 139)

- **Design system and pattern library**, and a manifest that becomes
  evidence rather than intention.
- **Brick 29 — every local file requested by the frontend must be served.**
  A site built for 48 rubles referenced six SVGs, none of which were
  delivered, while `monl run --check` was green on both sides: a missing file
  raises no exception, jsdom receives the 404 and continues.
- **`capability auth` is connected to the guided dialogue**, and `phone_prefix`
  works outside Europe: a Beninese number is written without a leading zero, so
  `"+229"` produced nothing and login failed after a successful registration.
- **The compiler no longer chooses the palette**, through the remaining pipe
  available to it.

### The test harness fails instead of skipping (point 140)

- `uvicorn_server` converted a server crash into `pytest.skip`: twenty-one
  integration files could verify nothing while showing green. The socket is
  now bound by the parent and passed to the child, so a port collision is
  impossible rather than retried. **On its very first run, the fix found a test
  file that no longer ran at all** — `python-multipart` was missing, despite
  being declared. A skip does not say «nothing to check here»; it says «I did not
  check».
- The coverage threshold had changed scope without anyone deciding to do so:
  `--cov=src` instead of `--cov=src/monl`.

### Documentation

- README and architecture diagram switched back to French.
- `docs/EXPLOITATION.md` — operating procedure, checked against the code by
  two tests in both directions: a dead variable will not be configured, and a
  documented but ignored variable will be configured for nothing.
- Ten links in the contents of `docs/design_decisions.md` pointed nowhere
  without anything checking them; a safeguard now keeps them valid.

## 0.9.0-beta.7 — Production-ready

Two groups of work completed end to end: what blocked deployment (deployment,
data layer, migrations) and what the generated backend could not do (uploads,
email, filtering/sorting, full authentication). Eight design points, 117 to 124,
each tested against a real server — and a real PostgreSQL — before being
integrated.

891 tests, clean `ruff`, and golden tests unchanged for any spec that does not
request the new bricks: none of this changes an existing project that does not
ask for it.

- Library functions now raise a common `MonlError` family; conversion to an
  exit code remains at the CLI boundary.
- `CompilationPlans` is computed only once per generator and becomes the
  canonical catalog shared by the backend renderers and the frontend contract.
- Golden tests lock down the deterministic artifacts of a representative
  compilation, including the contract and project state.
- `requests` is moved into the optional `.[ai]` extra, and historical
  compatibility is documented in `docs/DEPRECATIONS.md`.

### Bricks 27 and 28 set right (point 116)

- **`publicWhen` no longer hides content from those who should see it.** A
  `sharedBy` on the same reference names the supervisor roles, and the owner
  always gets their records back. Before this fix, hiding content ALSO removed
  it from the moderator who had just hidden it, and from its author.
- **`oncePer` sometimes refused without protecting anything.** A composite
  index placed on a column that the `Create` route never writes let all
  duplicates through; generation now refuses this case and names the relation
  to move. Its 409 no longer steals the `unique` message.
- **`monl update` sees both rules.** They lived in `business_rules`, which the
  contract signature did not read: the delta returned «no interface changes».
  Contract version 9.
- **The suite passes on a fresh clone.** `tests/test_projets_metier.py` read
  `projets/`, which git ignores: six tests failed in CI. The specs are now in
  the test file.
- Both bricks are tested against a real server
  (`tests/test_publication_conditionnelle.py`, `tests/test_unicite_composite.py`)
  and compiled from `exemples/03_reseau_social.ml`.

### The counter column no longer depends on relation order (point 117)

- **Data correction.** An entity with two incoming relations, where the
  counter's relation was declared first, created its rows with the target's
  foreign key set to `NULL`: the counter increased, but the record did not know
  what it counted. Reversing the two relations was enough to fix everything —
  an order-dependent bug, invisible in the spec that gave rise to it.
- `_counter_fk_columns` now derives this column from `_decrement_fk_column`
  for each rule, and the Pydantic schema, client foreign keys, and `INSERT` all
  read it: written exactly once, never zero times.
- Silent fallback to the first incoming relation becomes an explicit
  generation error.
- **The catalog declares the read supervisor**: the Blog and Community models
  provided one-way moderation, leaving the moderator unable to see what they
  had just hidden.

### Full authentication (point 124)

- Four DECLARATIVE capabilities under `capability auth`: `lockout: N in S`,
  `password_reset: S`, `refresh_tokens: S`, `totp`. A spec that requests none
  produces byte-identical artifacts.
- **ACCOUNT-BASED locking**, where the point 9 limit was IP-based: a distributed
  attacker could bypass it, and a user behind a shared NAT was punished for
  others.
- **The lock is not an existence oracle**: a locked account and a nonexistent
  account return the same response, and the median time difference is 1.28 ms
  out of 47 ms. A lock that announced «account locked» would not protect an
  account; it would publish the list of accounts. And during the lock, the
  CORRECT password is refused.
- **Password reset**, enabled by point 122: identical response for a known or
  unknown address, single-use token tied to the account, and the old password
  stops working immediately.
- **Refresh tokens with ROTATION**: `/refresh` returns a fresh pair and rejects
  the old one — a theft becomes a detectable incident rather than permanent
  access. A refresh token is not valid as an access token.
- **TOTP two-factor authentication** (RFC 6238, pure computation, therefore
  offline): replay of a code is refused, including within its own window; the
  secret is never exposed by any read route.
- No existing account is broken: users can still log in and are COUNTED at
  startup, without inventing any activation (point 89).
- `manage.py` gains `unlock` and continues to work from any directory.

### Filter and sort on the server, without a query language (point 123)

- `rule Entite.Read filter <champ>` and `rule Entite.Read sort <champ>`. What
  can be filtered or sorted is DECLARED; the client chooses neither the field,
  the operator, nor the expression. The red line in `CLAUDE.md` holds.
- **A filter is an oracle**: filtering or sorting on a `hidden` or `categorized`
  field is refused at compilation. Counting the rows returned for each value
  reads a field that brick 2 removes from all responses, and recovers the exact
  number that brick 5 replaces with a label — a leak through the TOTAL, not
  through a response.
- **Two bounds that do not overlap**: the filter value is typed by the `Literal`
  from `oneOf` (422 before any query), then bound with `sql.bind()`. The sort
  column name is selected from a dictionary built at compilation — never
  concatenated — and the direction is fixed SQL.
- **The filter ADDS to access control; it does not replace it**: with two
  accounts, one account's filtered list never shows a row belonging to the
  other.
- `limit`/`offset` are unchanged; a spec without filtering or sorting produces
  byte-identical artifacts, and the SQL boundary tests (point 108) remain green
  without being loosened.
- What the brick does NOT offer, and says so: no text search, no automatic
  index, no performance promise on an unindexed column.

### monl can send a message (point 122)

- The capability NAMED as a prerequisite since point 95: `rule Entite.Create
  sends "<sujet>" "<corps>"`. Not password reset, not address verification — the
  ability to send, and nothing more.
- **The refusal that comes with the brick**: a spec that wants to write without
  declaring `capability auth` + `identifier: email` has no address to write to.
  A free-form business field named `email` is not an account address, and the
  refusal message says so.
- **The address is the ACCOUNT identifier**, which prevents header injection
  upstream: an identifier cannot contain whitespace, so no client can forge a
  hidden recipient (verified, 422 at registration).
- The body is structured with the `¶` from point 64 — no multiline syntax was
  invented.
- **A sending failure never rolls back a business write and is never swallowed**:
  the route returns 200 in under 4 ms even when SMTP is dead, and the trace
  names the entity, identifier, and cause. Secrets come from the environment;
  a missing variable is NAMED — the same invariants as `payable` (points 74-75).
- What the brick does NOT promise, and says so: no retries, no persistent queue,
  no delivery guarantee.
- A spec without a message produces byte-identical artifacts; the smoke test
  stays green offline.

### The end user can upload a file (point 121)

- **`Upload` is not `Image`.** Brick 13 refers to what the AUTHOR provides at
  compilation and the compiler verifies is present; `Upload` refers to bytes
  the CLIENT sends at runtime, which the compiler knows nothing about.
  Combining them would mean checking that a file exists before it is uploaded.
- `rule Entite.champ upload max <octets> types "…", "…"` — the limit and
  types are REQUIRED: guessing a limit would mean guessing wrong.
- **The type is determined by byte signature**, never by the name or the
  client's `Content-Type`, and the client's name is never a path. HTML and SVG
  are refused; reading returns `application/octet-stream` with `nosniff` and
  `Content-Disposition: attachment` — an uploaded file must never be able to
  execute on the same origin.
- **The ACL applies to the FILE, not just the row**: knowing the reference is
  not enough; a third party receives 404. That is the lesson of point 116.
- The bytes live outside `frontend/` (which `monl frontend` silently renames),
  outside the sealed artifacts, and are ignored by git and Docker.
- A spec without an upload produces byte-identical artifacts.

### Non-additive migrations are named, applied manually, and reversible (point 120)

- **The engine no longer guesses.** A rename was seen as a deletion followed
  by an addition: the old column remained full, the new one arrived empty, and
  nothing reported it. A type change was not applied at all. A removed column
  stayed indefinitely without being reported.
- **A declarative and NAMED syntax**: `migration <nom>` with `rename`,
  `alter … from … to …`, and `drop`, applied with `monl migrate PROJET --name
  <nom>` and undone with `--down`.
- **A destructive change is never applied automatically at startup.** The
  server REFUSES to start, naming the column and the command to run, instead of
  swallowing the failure and serving a half-migrated database.
- **A history table**, `_monl_migrations`, records each operation with the
  fingerprint of the resulting schema. Rolling back a `drop` is refused: it
  cannot be undone without a backup, and pretending otherwise would be worse
  than offering nothing.
- Additive migration remains automatic: it destroys nothing. A database
  created by the previous compiler starts without losing anything — verified.
- **A flaw found in review**: `manage.py` exited with a fifteen-line traceback
  that buried the diagnosis. It now names the remedy and the directory.
### The data layer chooses its dialect at startup (point 119)

- **PostgreSQL alongside SQLite.** `MONL_DATABASE_URL` absent: SQLite,
  behavior strictly unchanged. `postgresql://`: psycopg v3. The choice is
  made at STARTUP and not at compilation, so that the same sealed artifact
  runs in development and production without being recompiled. `psycopg` is
  an optional dependency (`.[postgres]`), and its absence with a DSN is
  named explicitly.
- **The `?` → `%s` translation is safe because of point 108**: no client value
  ever enters the text of a query, so the translated text contains only fixed
  SQL. Without this invariant, the translation would be a vulnerability.
- `AUTOINCREMENT` becomes a PostgreSQL identity, `PRAGMA table_info` becomes
  `information_schema`, `lastrowid` becomes `RETURNING id`, `Float` becomes
  `DOUBLE PRECISION`. `Money` remains `NUMERIC(10, 2)`: a binary float
  is not a money type.
- **Integrity errors are read structurally** (SQLSTATE `23505`/`23503`
  and constraint name) instead of the SQLite message, which does not exist on
  PostgreSQL. The three 409s remain distinct.
- CI launches a real PostgreSQL service; tests skip cleanly without
  `MONL_TEST_DATABASE_URL`.
- **Two defects found in review and fixed.** The integrity block no longer
  ended with a `raise`: a fourth kind of error exited it without raising
  anything and the route reached `return success` after a `rollback` (measured:
  500 `UnboundLocalError` on a duplicate `numbered` reference). And `manage.py`,
  importing `app` at the top of the file, no longer worked from another folder—
  whereas it is the only way to create an account with a privileged role.

### The generated backend is deployable (point 118)

- **CORS opt-in.** `MONL_CORS_ORIGINS` lists explicit origins; absent,
  no CORS header is emitted and behavior is unchanged. The `*` origin makes
  startup fail: combined with credentials, it would let any site read the
  authenticated responses of a logged-in user. The announced methods are
  calculated from the routes actually emitted.
- **Two healthchecks.** `/health` does not touch the database (liveness),
  `/health/ready` runs a `SELECT 1` and returns 503 if it does not respond
  (readiness). Both remain outside the frontend contract.
- **Structured logs.** `MONL_LOG_FORMAT=json` emits one JSON line per
  request. No body, incoming header, or query string is included—the body of
  `/register` contains the password in plaintext. A supplied `X-Request-ID` is
  reused only if it matches a narrow pattern; otherwise it is regenerated.
- **`MONL_ENV=production` requires `MONL_JWT_SECRET`.** The refusal applies even if
  a `.jwt_secret` is present: this fallback makes all issued tokens depend on a
  file that does not travel with the image, and is therefore lost on the first
  redeployment.
- **`Dockerfile` and `.dockerignore` are produced, never sealed.** Written
  if missing, preserved thereafter, and excluded from the fingerprints of
  protected artifacts: adapting the image is the normal case for a real
  deployment.
- Proven by `tests/test_deploiement.py` (9 tests) and an actual image build:
  container refusing to start without a secret, then serving registration,
  login, creation and reading, secret absent from the image.

## 0.9.0-beta.6 — Business capabilities and in-depth access control

This version completes the declarative core with the capabilities added since
beta 5: server-side calculations (`derivedFrom`, `sumOf`), transitive ownership,
stock counting, server-side timestamping and numbering, field constraints,
enumerated values, required profiles, locking after payment, and frontend
retouching tools. Typed SQL access control and its security invariants are also
consolidated.

The package version, tracking contract (`monl.json`), and documentation
are now aligned at `0.9.0-beta.6`.

## 0.9.0-beta.5 — Any API key, any agent

**The compiler remains unchanged.** No rule, generated route, or
contract differs from beta 4. This version opens the last link—the one
where an AI writes the frontend—to providers other than Anthropic. Full details and reasons
at point 69 of `docs/design_decisions.md`.

### API path: any key

- **OpenAI dialect providers.** `groq`, `openai`, `openrouter`,
  `deepseek`, `mistral`, `together`, `xai`, and `ollama` are preset, each
  reading **its own** environment variable (`GROQ_API_KEY`,
  `OPENAI_API_KEY`…)—a missing key names the expected variable rather than
  returning “missing key” without saying which one.
- **Complete escape hatch** for an endpoint absent from the table
  (custom server, vLLM, llama.cpp): `--provider openai-compatible` with
  `MONL_AI_BASE_URL` and `MONL_AI_API_KEY`.
- A single configurable provider instead of one per brand: writing code per
  actor would have produced duplication and a list that was always out of date.
  Two dialects—Anthropic Messages and OpenAI Chat Completions—cover the
  market.
- **`--model` is required outside the Anthropic path**, deliberately. Hard-coding
  `gpt-4o` or `llama-3.3-70b-versatile` would have turned a clear error into an obscure 404
  six months later, for a user who had changed nothing.
- The key is still read from the environment, never as a command-line
  argument: the rule set for the Anthropic path had no reason to be more lax
  elsewhere.

### Agent path: Codex, Gemini, and any other

- **`--provider codex` and `--provider gemini`** are added to
  `claude-code`.
- **`--agent-command "<cmd> {instruction}"`** wires up any command-line
  agent, and also makes it possible to correct a preset that has become wrong without
  waiting for a monl release. A template without `{instruction}` is
  refused rather than run silently.
- **No safeguard is relaxed for a third-party agent.** The fingerprint of
  protected artifacts, re-verification (consistency + smoke test), and the
  single correction are exactly those written for Claude Code: only the command
  line changes. Two tests establish this by having a fake “codex” agent attempt
  the intrusion into `app.py` that the fake Claude agent could not commit—it is
  blocked in the same way.
- **What is verified, plainly stated**: only `claude` is tested against the
  real binary. The `codex` and `gemini` presets follow the non-interactive invocation
  published by those tools, but neither was installed on the development
  machine. They are presets, not guarantees, and the table comment says so
  at that exact location.
- The original names (`run_claude_code`, `generate_with_claude_code`) are
  retained as special cases: the path from point 43 remains what it was.

### Verification

- **164 tests** (11 new): query actually formed for the API path
  (URL, `Bearer` header, body, response extraction), key variable named for each
  preset, command line for each agent, free-form template going through the
  complete loop, and the two intrusion tests.
- Coverage maintained at 85%, `ruff` reports no issues, architecture boundaries
  unchanged.

## 0.9.0-beta.4 — Public opening: license, documentation, demonstration

**The compiler is unchanged.** No rule, generated route, or
contract differs from beta 3: this version makes the repository readable to
someone discovering it, now that it is public. Updating therefore requires
nothing more than `pip install -e .`.

### License and governance

- **`LICENSE` added.** The repository became public *without* a license file.
  Legally, absence already means “all rights reserved”—but readers cannot tell
  a choice from an omission, and this ambiguity helps no one. The file puts in
  writing what `pyproject.toml` has always declared (`license = "Proprietary"`):
  public for reading and evaluation, not open source. A clarification that was
  not self-evident: applications *produced* by monl-compiler belong to their
  author—the license covers the compiler, not its output.
- **`CONTRIBUTING.md` added.** Documents the method rather than inviting
  contributions, which are not open: proof through actual execution,
  pre-PR checklist, executable boundaries, commit message format,
  “where to intervene” table. It addresses the maintainer, a future authorized
  collaborator, and any development AI working on the repository.
- **`demo/.jwt_secret` and `demo/app.db` removed from version control.** The root
  `.jwt_secret` had always been ignored; the exception had followed the demo
  folder. The real scope was small (nothing is deployed), but the symbolic
  scope was not: the project was publishing what it treats as sensitive. Both
  are regenerated on first startup. The history is **not** rewritten—the secret
  of a local demo does not justify breaking existing clones.

### Demonstration

- **`demo/` no longer versions its own output.** Nine generated files
  (`app.py`, `schema.sql`, `manage.py`, the contract, the brief, `serve.py`…)
  were committed alongside the spec from which they derive—a contradiction on
  the home page of a project whose thesis is that the spec is the sole source of
  truth. The damage was observed: the delivered contract predated
  points 51, 52, and 56 (absolute URL with hard-coded port, font to download,
  no derived tone). Only `spec.ml` and `frontend/` remain, the only two authored
  artifacts that recompilation cannot reproduce. Tests lose nothing: they
  already compiled in a temporary folder from these two inputs.
- **StudioNova replaces AtelierVélo**—a photographer's portfolio whose
  frontend was written by Claude Code against the contract.
- **`tests/test_design_contract.py` was repurposed rather than deleted.**
  The old demo pinned a theme and the test used it to check that a delivered
  frontend respected an imposed palette; StudioNova pins nothing, and its AI
  allowed itself a completely different palette. The test now proves, on an
  actual deliverable, that monl-compiler **stays silent** when the theme
  is only inferred—the less intuitive half of point 58. The constraint
  remains tested right alongside it, on a frontend built for the occasion.

### Documentation

- **README rewritten.** Quick start in three lines above the fold, requiring
  no pre-existing files and leading to an application of one's own—the actual
  product entry point is the guided dialogue, not compiling someone else's
  example. Badges, contents, tables for commands and access rules, “Quality and
  verification” section. Facts resynchronized: `src/` became the `src/monl/` package (point 65).
- **The architecture diagram becomes a real image**: two SVGs (light and
  dark) served by `<picture>` according to the reader's theme, generated from
  a single model so they cannot diverge. Geometry is checked—no overlapping
  boxes, no line crossing a box *or text*, no label wider than its box.
- **The “Why” section finally compares monl-compiler with something.** It criticized
  a framework and an AI generator without ever saying what monl-compiler does; it is
  now a three-column table where monl-compiler has its own column, row by row.
- **`exemples/` gets a README**: the folder does not contain five applications
  but the five `.ml` files that suffice to describe them. A reader who thinks
  they are opening applications misses the project's thesis.
- **Opening paragraphs state what they contain instead of denying it.** Several
  passages began with an absence (“this folder does not contain…”, “monl-compiler
  generates no interface”): readers had to remember what was missing
  before learning what they had in front of them.
- Unified naming: **monl-compiler** in titles and prose, `monl` for the
  command and package.

### Tests and continuous integration
- **The temporal channel test no longer depends on machine load.** It
  intermittently failed in CI (twice in a row on 3.12, then passed on the
  third attempt, on a branch that touched only documentation): it compared two
  HTTP measurements against half the cost of a PBKDF2, and a single runner
  preemption was enough to make the gap explode. Widening the threshold would
  have made the test blind to the leak it monitors; instead, five samples per
  group with the minimum retained (noise can only add time), the entire
  measurement replayed up to three times (a real leak is systematic, noise
  is not), quota emptied between groups.
- **A test server is no longer left orphaned if a failure occurs.** Its
  shutdown was written after the measurements: any failure abandoned a
  `uvicorn` and a temporary directory on a machine that would go on to run
  other tests. Moved under `try/finally`.
- **CI listens to all branches.** It was triggered only on `main` and pull
  requests: pushing a work branch started nothing, and the Actions page stayed
  empty, giving the impression of a repository without continuous integration.
- `dist/` and `build/` are ignored by git — the output of `python -m build` and
  the output directory suggested by the quick start never need to be
  versioned.

## 0.9.0-beta.3 — Audit fixes and generator split

### Security (second review, before external testing)

- **`ownedBy` protected writes only (data leak between accounts).**
  `rule X.Update ownedBy A` properly restricted changes, but `GET /x`
  returned records from *all* accounts to any authorized caller, and
  `GET /x/{id}` returned 200 for someone else's record. In the “personal
  expense tracking” model, whose catalog promises that each person sees only
  their own records, two accounts were enough to read each other's data.
  `ownedBy` now filters reads — for the designated owner actor only: an
  authorized third party role (shop manager viewing orders, manager viewing
  tasks) continues to see everything. Direct access returns 404 rather than
  403, so it does not confirm the existence of a record the caller is not
  allowed to read.
- **A rule with no effect is refused at compilation.** `rule X.Read ownedBy A`
  compiled without producing anything, and `rule X.Create ownedBy A` was
  accepted even though the generator does nothing with it: a silently ignored
  security rule is worse than no rule, because the author believes protection
  is in place.
- **Size limits on text fields**: a string several MB long was accepted and
  written to the database. The Pydantic limit now matches the SQL column
  (255 / 320 for Email / 20,000 for Text); refusal is returned as 422.
- **`/docs` and `/openapi.json` can be disabled** with `MONL_DOCS=off`.
- **Unified token lifetime**: 2 h in the code versus “1 h” stated in the
  frontend contract. A single value, configurable through
  `MONL_TOKEN_TTL_HOURS`, is published as is in the contract.
- **CI finally runs the frontend**: without Node.js on the runner, the jsdom
  smoke test degraded to a warning — the project's strongest guarantee was
  never executed in continuous integration. The package is also installed by
  `pip install -e .` and the `monl` command is exercised.

External audit of the beta 2 repository: one critical vulnerability, five
significant defects, and one determinism defect. All fixed, each with a
regression test (`tests/test_beta3_regressions.py`).

### Security

- **Privilege escalation through registration (critical).** `POST /register`
  accepted any declared role chosen by the client: on the example shop, two
  anonymous HTTP calls were enough to get a `ShopManager` account and write to
  the catalog. The role in the token did come from the actual account — but
  the account chose its own role. The DSL gains an explicit marker:
  `actor Customer selfRegister` enables open registration, while
  `actor ShopManager` (without the marker) does not. Refusal by default: a
  spec that omits the marker closes registration instead of opening it wide.
  The compiler displays the selected scope on every compilation, the frontend
  contract publishes it (`self_register_actors`), and the smoke test attempts
  registration for a provisioned role on every run.
- **Offline provisioning.** Each compilation now produces `manage.py`
  (`adduser`, `setactor`, `passwd`, `users`, `revoke-all`): privileged roles
  are created on the machine hosting the database, never over HTTP.
  `revoke-all` renews the secret and invalidates all sessions.
- **Account enumeration through a temporal channel.** `/login` returned 401
  without performing the 100,000 PBKDF2 iterations when the identifier did
  not exist; the response time gap (~100 ms) revealed which accounts exist.
  A dummy hash is now always computed.
- **Attempt quota could be bypassed (TOCTOU).** Counting and recording were
  done in two separate autocommit executions: N parallel requests read the
  same counter and all exceeded the quota. The whole operation now runs in a
  `BEGIN IMMEDIATE` transaction.
- **Signing secret readable by everyone.** `.jwt_secret` was created with
  default permissions (0644): any local account could read the key and forge
  tokens. It is created with mode 0600, and permissions on an existing
  project are tightened on recompilation.
- **Token blacklist with no cleanup.** `_monl_revoked_tokens` grew
  indefinitely and was checked on every authenticated request. Added an
  `expires_at` column (with migration of the system table) and cleanup of
  already expired tokens — their signatures are rejected anyway.

### Reliability

- **Referential integrity is actually enforced.** SQLite ignores foreign
  keys by default: those declared in `schema.sql` were never checked. All
  request connections go through `_connect()` (`PRAGMA foreign_keys`,
  `busy_timeout`, WAL). A violation becomes an explicit 409 instead of a 500.
- **Event loop was blocked.** Handlers were `async def` even though all SQLite
  calls are blocking: each request froze the loop. They are now synchronous,
  so they run in FastAPI's thread pool.
- **Determinism.** The actor list passed through a `set`: ordering depended on
  `PYTHONHASHSEED` and `VALID_ACTORS` could change from one compilation to the
  next — the guarantee “same spec, same backend byte for byte” was false.
  Declaration order is preserved, remaining sets are sorted, and a
  reproducibility test compares two processes with opposite seeds.
- Deprecated `@app.on_event('startup')` replaced with a `lifespan` handler;
  password limited to 256 characters at registration.

### Architecture

- `src/generator.py` (1,307 lines) split into package `src/generator/`:
  `core` (state and orchestration), `runtime` (auth, database, migrations),
  `routes` (CRUD and access control), `schemas`, `sql_schema`, `theme`,
  `sandbox`, `admin_cli`. Composition through mixins; the historical import
  `from generator import MonlSecureGenerator` remains valid. The split was
  verified by comparing generated output byte for byte across the six specs.

### Interface

- **Guided dialogue now has a presentation of its own** (`src/tui.py`):
  interview flow displayed before the first question and current step marked,
  menus in aligned columns with an explanation for each option, dedicated
  prompt, summary of what the spec will declare before compilation. No added
  dependencies (ANSI sequences), and graceful degradation: plain rendering
  outside an interactive terminal, no color with `NO_COLOR`, no drawing
  characters if the encoding does not support them. The engine knows only a
  presentation interface whose plain version reproduces the historical
  strings exactly — scripted dialogues are unaffected by the styling.
- **The dialogue asks about registration** (regression fixed): since the
  `selfRegister` marker, the emitter wrote `actor X` without a marker — every
  application created through the dialogue therefore refused *all*
  registration. The question is now explicit, and the answer order conveys
  the recommendation: first the roles that write only to their own records,
  never the manager of shared data.
- **Design direction becomes verifiable when declared in the spec.** The
  contract's `design` clause was the only one no check compared against the
  deliverable: a frontend could silently ignore it. Now a theme pinned by a
  `ui … theme:` block is binding — its exact palette is published (without
  the project's own hue variation) and the smoke test requires it to appear
  in the delivered styles. A theme merely inferred from entity vocabulary
  remains a proposal: deviations are reported, never blocking.
- Sixth theme, `atelier`: graph paper, fine lines, monospaced data, a single
  high-visibility accent, and no remote fonts — it covers the vocabulary of
  spare parts and repair, poorly served by `market`. This is now the theme
  pinned by the demo.

### Documentation

- The six shipped specs declare their self-registering actor.
- `docs/SECURITE.md`: registration scope, provisioning, settings.

## 0.9.0-beta.2 — Removal of local generative AI

The compiler becomes fully deterministic. The only AI in the lifecycle is now
the one that builds the frontend (Claude), against the contract.

### Removed
- Complete removal of Ollama and related modules (`nl_interpreter.py`,
  `ai_translator.py`, `ai_sandbox_filler.py`).
- Removed options: `--nl` (free-form dialogue answers), `--prompt` (spec from a
  description), `--fill-custom` (filling `custom` blocks).
- Guided dialogue is strict-input only; `custom` blocks are empty shells to
  complete by hand (no automated code generation).

### Fixed
- Removed dead compilation defect (reference to a nonexistent example).
- Documentation aligned (README, `docs/SECURITE.md`, `docs/BETA.md`): no more
  mention of Ollama or generative AI in the product core.

## 0.9.0-beta.1 — First beta

Fixed all blocking defects identified in the audit. Details in `docs/BETA.md`;
security model in `docs/SECURITE.md`.

> Note: some items described below (local AI `custom` block,
> generated-code safeguard) were removed in 0.9.0-beta.2. Entry retained
> for historical reference.

### Security
- `custom` block disabled by default; explicit activation with `--fill-custom`.
  Nominal compilation is now 100% deterministic and offline.
- Hardened static safeguard for `custom` code: blocks introspection escapes
  (`__class__`, `__subclasses__`, `__globals__`, `__code__`, `__mro__`…),
  expanded detection of loops with an always-true condition, expanded list of
  low-level imports (`inspect`, `threading`, `marshal`, `gc`…).
- Constant-time comparison (`hmac.compare_digest`) of password fingerprints
  on login.
- JWT secret injectable through environment variable `MONL_JWT_SECRET`
  (takes precedence over `.jwt_secret` file) — the secret need never touch
  disk in production.
- Proxy-aware rate limiting through `MONL_TRUST_PROXY`;
  `X-Forwarded-For` ignored by default to prevent IP spoofing.

### Reliability
- Transactional integrity: record creation and related effects
  (`increments`/`decrements`) run in one transaction with rollback.

### Packaging & documentation
- `pyproject.toml` (metadata, `monl` console entry point, pytest config).
- Dependencies pinned with upper bounds (`requirements.txt` + `pyproject.toml`).
- New documents: `docs/SECURITE.md`, `docs/BETA.md`.
- New test: `tests/test_sandbox_guardrail.py` (20 cases, including
  introspection escapes).
- Cleaned distribution archive (no secrets or generated artifacts).
