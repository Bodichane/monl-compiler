# Defensive threat model — monl

## Scope and version

This model covers **1.0.0-rc.1**, as declared in `pyproject.toml`, and the
current worktree, including the security headers added after that release tag.
It completes the written-model half of issue #124; an independent external
audit/penetration test remains open. It is a defensive architecture review,
not a certification or a claim that every attack has been tested.

monl parses a third-party DSL specification, validates its declared policies,
and emits a FastAPI backend, SQLite schema, operator CLI and frontend contract.
The default compiler is deterministic and offline. PostgreSQL is optional;
this model concentrates on the default SQLite path. The hosting platform in
`src/monl_platform/` additionally manages accounts, sessions, API/MCP keys,
private projects, compilation workers and hosted sites.

Primary sources: [security guarantees](SECURITE.md), [GA criteria](BETA.md),
[dated codebase audit](../CODEBASE_AUDIT.md), `src/monl/generator/`,
`src/monl_platform/service.py`, `src/monl_platform/hosting.py` and
`src/monl_platform/administration.py`. The dated audit is context, not evidence
of the current version's independent security review.

## Assets and security objectives

| Asset | Required property |
| --- | --- |
| JWT signing secret, access/refresh tokens and revocation state | Confidential signing authority; only valid, unrevoked identities authorize requests. |
| Accounts, password hashes, TOTP/recovery material, platform sessions and API/MCP keys | No public assignment of privileged roles; credential confidentiality and revocation. |
| Business records and their ownership relations | Declared role/record permissions; private reads; atomic effects and referential integrity. |
| Monetary amounts, payment references and paid state | Server-held amount and payment state; only authenticated provider events confirm payment. |
| Deposited/uploaded files and project archives | Authorized access, bounded input, safe paths; no accidental secret export. |
| Stripe, FedaPay and SMTP secrets | Operator-controlled configuration, never client-supplied credentials; restricted host access. |
| Multi-account platform, tenant projects, hosted sites and visitor databases | Account separation at application level, bounded shared resources, deletion/expiry enforcement. |

## Actors and starting capabilities

- **Anonymous visitor:** controls HTTP requests, headers and public form data;
  can use explicitly public routes and self-registration, but has no account
  authority or valid provider signature.
- **Registered account:** holds its own credentials/tokens; may invoke its
  declared workflows, upload permitted files and access its own platform projects.
- **Privileged role (supervisor):** provisioned by a trusted operator; may
  deliberately see/moderate records outside party ownership where the spec
  declares supervisor access. That access is authorized, not tenant isolation.
- **Shell operator:** can run `manage.py` and `monl-platform admin`, read local
  secrets/databases and replace generated code. This is trusted host authority.
- **Payment provider:** can send signed webhooks; it has no general account
  token. A compromised provider/signing secret exceeds the signature guarantee.
- **Platform spec author:** supplies DSL text through the web/API/MCP; does not
  thereby acquire operator authority or permission to execute arbitrary Python.
- **Other platform tenant:** owns a different account/project; can compete for
  shared resources but must not obtain another account's private artifacts.

## Named trust boundaries and STRIDE scenarios

STRIDE labels: **S** spoofing, **T** tampering, **R** repudiation,
**I** information disclosure, **D** denial of service, **E** elevation of privilege.
Scenarios below describe threats, not newly validated vulnerabilities. Test
references name existing witnesses and their limited scope; the documentation
check validates their existence, not their semantic completeness.

### TB1 — Client ↔ generated backend

Requests cross from an untrusted browser/API client into generated route,
authentication and database code. The invariant is the spec's declared policy,
including intentionally public actions, rather than universal authentication.

| Threat (STRIDE) | Existing mitigation | Test evidence |
| --- | --- | --- |
| Forged/unsigned JWT or self-assigned privileged role (S, E) | Explicit HS256 verification; registration limited to `selfRegister` actors. | tests/test_temoins_securite.py::test_le_serveur_refuse_les_jetons_non_signes_ou_signes_autrement; tests/test_beta3_regressions.py::test_role_provisionne_refuse_a_inscription |
| Cross-record private messaging access (I, T, E) | Party filtering and route authorization; supervisor access is separately declared. | tests/test_access_parties.py::test_private_messaging_end_to_end; tests/test_access_parties.py::test_supervisor_moderates_private_messages_end_to_end |
| Injection of SQL values (T, I, E) | Parameterized values; grammar-constrained identifiers. This witness checks emitted SQL, not arbitrary handwritten code. | tests/test_invariants_securite.py::test_aucun_exemple_ne_colle_de_valeur_dans_le_sql |
| Account enumeration/brute force (I, D) | Dummy password hash for unknown identifiers; atomic database-backed authentication quota. | tests/test_beta3_regressions.py::test_login_ne_revele_pas_l_existence_du_compte; tests/test_beta3_regressions.py::test_quota_non_contournable_en_parallele |
| Stolen logged-out token remains usable (S) | JWT `jti` blacklist and logout revocation. | tests/test_beta3_regressions.py::test_logout_revoque_le_jeton |
| Local disclosure of fallback JWT key (I) | Secret file created owner-only (0600); production environment injection is documented separately. | tests/test_beta3_regressions.py::test_secret_jwt_lisible_par_le_seul_proprietaire |
| Malicious file/path, oversized upload, unauthorized file access (T, I, D) | Upload ACL, byte/type limits, generated names, storage outside served frontend. | tests/test_uploads.py::test_upload_reel_acl_octets_limite_type_nom_et_suppression |
| Clickjacking/content sniffing and browser transport exposure (S, I) | Global headers and CSP; HSTS only on HTTPS/forwarded HTTPS. CSP still permits inline site scripts. | tests/test_security_headers.py::test_api_site_erreurs_et_hsts |
| Denial of a business write by its author (R) | Authentication attributes requests to accounts, but no tamper-resistant business audit trail is established. | No dedicated proof: see Known gaps. |

### TB2 — Payment webhook ↔ backend

The payment route rereads the amount from the database and sends it with the
server's provider key. The public webhook is the exceptional unauthenticated
write path: the provider signature, not a browser JWT, authorizes it.
`src/monl/generator/routes_paiement.py` verifies the raw body signature and
bounded timestamp age before processing the event; references qualify entity IDs.

| Threat (STRIDE) | Existing mitigation | Test evidence |
| --- | --- | --- |
| Client changes payable amount or pays another account's record (T, E) | Database amount and owner check, not a request-body price. | tests/test_paiement.py::test_le_montant_encaisse_vient_de_la_base_jamais_du_client; tests/test_paiement.py::test_payer_l_enregistrement_d_un_autre_compte_est_refuse |
| Forged/rebound Stripe event (S, T) | HMAC verification binds signature to raw body and configured secret. | tests/test_paiement.py::test_un_webhook_mal_signe_ne_paie_rien; tests/test_paiement.py::test_une_signature_valide_pour_un_autre_corps_est_refusee |
| Forged FedaPay event or future timestamp (S, T) | Provider signature and timestamp tolerance. | tests/test_fedapay.py::test_un_webhook_mal_signe_ne_paie_rien; tests/test_fedapay.py::test_une_signature_datee_du_futur_est_refusee |
| Browser declares its own paid state (T, E) | Payment tracking columns excluded from client input. | tests/test_paiement.py::test_le_client_ne_peut_pas_se_declarer_paye_a_la_creation |
| Oversized webhook exhausts resources (D) | Bounded raw body even without Content-Length. | tests/test_paiement.py::test_un_webhook_trop_volumineux_est_refuse_avec_ou_sans_content_length |
| Provider denies settlement or signed event is duplicated (R, T) | Signed events authenticate origin, not financial settlement or durable nonrepudiation. | No end-to-end reconciliation/nonrepudiation proof: see Known gaps. |

### TB3 — Platform ↔ hosted sites (`serve.py` processes)

The platform routes project hosts to local uvicorn processes running
`serve:app` in each compiled project directory (`src/monl_platform/hosting.py`).
Loopback binding, separate working directories and processes are routing/process
separation; they do **not** establish an OS tenant sandbox. `Popen` supplies no
restricted user or scrubbed environment, so children inherit host authority and
environment. Browser account isolation and process isolation are distinct.

| Threat (STRIDE) | Existing mitigation | Test evidence |
| --- | --- | --- |
| Another tenant obtains private project records (S, I, E) | Identity store checks project ownership. Witness covers store authorization, not hostile process reads. | tests/test_platform_identity.py::test_projets_appartiennent_a_un_seul_compte |
| One tenant exhausts site slots / oversized relay body (D) | Global/per-account admission and relay byte limit. | tests/test_platform_hebergement.py::test_plafond_par_compte_nempeche_pas_un_autre_compte; tests/test_platform_hebergement.py::test_relais_borne_le_corps_et_transmet_un_corps_legitime_intact |
| Deleted tenant leaves a live site or private database (I, T) | Shared deletion path stops sites and removes owned directories and rows. | tests/test_platform_exploitation.py::test_supprimer_son_compte_efface_tout_y_compris_sur_le_disque |
| Hosted code reads platform/provider secrets or modifies another tenant (I, T, E) | No dedicated OS/environment sandbox in the inspected launcher. | No containment test: see Known gaps. |
| Tenant disputes hosted activity (R) | Operational logs exist; no tamper-resistant site activity ledger established. | No nonrepudiation test: see Known gaps. |

### TB4 — Operations CLI (`manage.py`, `monl-platform admin`)

Shell authority crosses into account provisioning, role changes, revocation,
backup and deletion. Public clients cannot invoke these commands through an
admin web endpoint. The shell operator is intentionally trusted.

| Threat (STRIDE) | Existing mitigation | Test evidence |
| --- | --- | --- |
| Visitor obtains provisioned role or web administration (S, E) | Offline provisioning; platform admin creates no HTTP administration routes. | tests/test_beta3_regressions.py::test_role_provisionne_par_manage_py; tests/test_administration.py::test_ladministration_nouvre_aucune_route |
| Accidental destructive administration (T, D) | Platform deletion requires its explicit CLI confirmation flag. | tests/test_administration.py::test_supprimer_sans_confirmer_ne_touche_a_rien |
| Operator denies changes / logs disclose identities (R, I) | Platform mutations are journaled, identifiers are redacted. This is traceability, not protection against a malicious shell operator. | tests/test_administration.py::test_tout_geste_qui_ecrit_laisse_une_trace; tests/test_administration.py::test_le_journal_de_ladministration_ne_livre_aucun_identifiant_nu |

### TB5 — Compiler ↔ third-party specification (compilation isolation)

DSL text enters parser/validation/generation; it is not an authorization to run
Python. `compiler_dans` in `src/monl_platform/service.py` defaults to a separate
worker (`MONL_ISOLATE_COMPILES=1`), with a wall timeout and POSIX CPU, address-space,
file-size and descriptor limits. Disabling that option compiles in-process.
These resource limits do not revoke filesystem/network access or inherited secrets.

| Threat (STRIDE) | Existing mitigation | Test evidence |
| --- | --- | --- |
| Oversized spec or path traversal through project ID (T, I, D) | Spec input bound and opaque validated IDs. | tests/test_platform_service.py::test_entrees_bornees_et_identifiants_opaques |
| Stuck worker publishes incomplete output (T, D) | Timeout failure cleans unpublished project. Witness simulates timeout; it does not measure OS resource limits. | tests/test_platform_service.py::test_worker_interrompu_ne_publie_aucun_projet |
| Recompilation bypasses admission quotas (D) | Compile/recompile share quota and semaphore. | tests/test_admission_compilation.py::test_compilation_et_recompilation_partagent_le_quota; tests/test_admission_compilation.py::test_compilation_et_recompilation_partagent_le_semaphore |
| Export leaks runtime JWT secret (I) | Compiled archives exclude the secret. | tests/test_platform_service.py::test_validation_compile_inspection_et_archive_partagent_le_pipeline |
| Compiler compromise escalates to host authority (E, I, T); author disputes submissions (R) | Parser/validator and worker separation reduce exposure; no lower-privilege sandbox or tamper-resistant submission ledger is established. | No containment/nonrepudiation test: see Known gaps. |

### TB6 — `custom` code (`sandbox_ai.py`, NOT isolated; issue #123)

The generator emits empty Python shells (`src/monl/generator/sandbox.py`).
Handwritten implementations are imported by the generated backend and called
in-process (`src/monl/generator/routes_suppression.py`). The filename is not a
security boundary. An implementation receives backend process authority.

| Threat (STRIDE) | Existing mitigation | Test evidence |
| --- | --- | --- |
| Custom implementation forges identities, changes payments/data, reads secrets, suppresses traces or exhausts resources (S, T, R, I, D, E) | Deterministic empty shells avoid automatically generating business code, but provide no containment of handwritten code. Operator review is an assumption, not a runtime control. | No execution-isolation test or dedicated sandbox: issue #123, see Known gaps. |

## Deployment assumptions and effective resources

| Workflow/resource | Configuration and effective location | Trust assumption |
| --- | --- | --- |
| Generated JWT key | `MONL_JWT_SECRET` overrides local `.jwt_secret`; `MONL_ENV=production` requires environment key. | Unique strong key per app, protected environment/files and backups. |
| SQLite data | Local generated application database; platform account/project storage resolved through `src/monl_platform/paths.py`. | Host permissions and backups prevent direct tenant access. SQL ACLs cannot protect against shell access. |
| Uploads | `MONL_UPLOADS_DIR`, default `.monl_uploads`, outside `frontend/`. | Proxy/static server does not independently publish private upload/database directories. |
| Provider/SMTP secrets | Stripe/FedaPay/SMTP environment variables listed in SECURITE.md; provider base URL overrides left unset in production. | Trusted operator supplies endpoints/keys; providers and mail transport are trusted to the extent required by each integration. |
| Compilation worker | Separate process by default; POSIX limits in `_worker_limits`; inherited host identity/environment. | Keep isolation enabled; use host/container resource controls. Windows does not receive the POSIX limits. |
| Hosted backend | Project working directory, loopback uvicorn `serve:app`; inherited environment and OS identity. | Do not interpret project directories as protection against malicious executable code. |

- TLS terminates at a trusted reverse proxy. It overwrites forwarded headers;
  direct access is blocked when `MONL_TRUST_PROXY=1`. Never trust arbitrary
  client X-Forwarded-For or X-Forwarded-Proto.
- CORS origins are explicit, security headers remain enabled, and separate site
  hostnames/proxy routing preserve browser origin separation.
- Operators, generated-code maintainers and dependency/release installation are
  trusted. Host compromise and malicious shell operators are outside API ACL guarantees.
- Specs deliberately define public actions and supervisor rights; an incorrectly
  permissive business policy is not corrected by token verification.
- Deployment-specific hardening and real-provider behavior require external
  review. This model was reviewed sequentially, without an independent reviewer.

## Known gaps

- **#123: custom execution isolation.** No dedicated sandbox or containment
  witness; handwritten code can access process secrets, database and host resources.
- **#122: email verification.** Identifier syntax/normalization does not prove
  inbox ownership; no email-verification control or proof is claimed.
- **Tenant process containment.** Hosted processes and compilation workers are
  not separated by restricted users, scrubbed environments or filesystem/network
  sandboxing in the inspected launchers. No hostile-child containment witness
  proves isolation of platform secrets or other tenants' files.
- **Resource-limit coverage.** The timeout witness is simulated; no cited test
  proves actual exhaustion of every POSIX worker limit, non-POSIX equivalents,
  or comprehensive hosted-process CPU/memory/disk limits.
- **Repudiation and payments.** Operational journals are not tamper-resistant
  against shell authority. No cited witness proves a complete business audit
  ledger, real-provider settlement reconciliation or exactly-once processing of
  all webhook side effects. Fake-provider tests do not certify live providers.
- **Browser policy limits.** Headers exist and are tested; they can be disabled.
  Inline site scripts/styles remain allowed by CSP. TLS/proxy correctness and
  cross-site browser isolation are deployment assumptions, not proved by the
  header witness. No separate blanket platform-header guarantee is asserted.
- **Limits recorded in SECURITE.md.** SMTP sends have no delivery guarantee or
  retry; SQLite can bottleneck under heavy multi-worker writes; `drop` migrations
  need backups for recovery. None has a universal prevention/recovery proof here.
- **External audit remains open (#124, second half).** Existing internal tests,
  this model and CODEBASE_AUDIT.md do not replace it. Future changes must refresh
  the boundaries, version and evidence; passing reference checks only prevents
  dangling test names.
