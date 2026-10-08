# External security audit — scope and brief

Status: **prepared, not commissioned.** Hiring an independent party is the
maintainer's decision and budget (issue #124, second half). This document is
what that party receives, so the engagement can start without a week of
scoping. It states no price, no vendor and no date: none has been chosen.

The [threat model](THREAT_MODEL.md) is the starting point. It names the trust
boundaries (TB1 to TB6) and lists the gaps below as "known gaps". Giving them
to the auditor up front is deliberate: an audit that rediscovers what is
already written down is money spent on the wrong things.

## 1. What is audited

A **frozen version**, never `main`. Cut it as a tag on the release candidate
or the final 1.0.0, record the commit hash in the engagement letter, and give
the auditor that exact archive. A finding is reproducible only against a fixed
target.

| In scope | Where | Why it matters |
| --- | --- | --- |
| Generated backend (FastAPI, SQLite, JWT) | any project compiled from `exemples/*.ml` and `demo/spec.ml` | Every deployment is a generated backend; this is the product. |
| Access-control model | owner, transitive owner, `accessibleBy`, supervisor, `publicWhen`, `writableAfterPayment` | A wrong decision here exposes other people's records. |
| Authentication | register, login, lockout, password reset, refresh tokens, TOTP, `selfRegister` role boundary | The only place an anonymous caller gains an identity. |
| Payment webhook | signature check, replay window, amount source | The only route where an unauthenticated third party writes to the database. |
| Uploads and assets | byte-signature check, size limit, path handling | File handling is the classic bypass surface. |
| Compiler as a service | `src/monl_platform` compile and recompile routes, isolated worker | Runs a third party's specification. |
| Hosting | `serve.py` wrapper, hosted site processes, admission limits | Runs one account's backend next to another's. |
| Operations CLI | `manage.py`, `monl-platform admin` | Privileged by design; check it grants nothing over the network. |
| Platform sessions, API keys, MCP, OAuth sign-in | `src/monl_platform` | Account takeover across the platform. |
| Deployment files | `Dockerfile.platform`, `compose.platform.yaml`, `deploy/` | What a production operator actually runs. |

**Out of scope** (say so in the letter, so nobody tests it by accident):
the operator's host and reverse proxy beyond the files above; Stripe, FedaPay
and SMTP providers themselves; denial of service by raw bandwidth; social
engineering; any production system other than a deployment built for the test.

## 2. Gaps the auditor is told about

Taken from the threat model's "Known gaps". Ask the auditor to confirm or
refute each one with a proof of concept, not to rediscover it.

1. **`custom` code is not isolated** (#123). It runs in the backend process
   and can read the signing secret and the database. Decision taken: the
   platform accepts no Python from users, so this stays the project author's
   responsibility. *Ask*: can any platform route make a user-supplied string
   end up as executable code in `sandbox_ai.py`?
2. **Hosted processes and compilation workers share the platform's OS
   identity** and environment. *Ask*: from a hosted backend, can anything
   reach the platform's secrets or another tenant's files?
3. **Email ownership is not verified** at sign-up (#122).
4. **Resource limits** are proved by a simulated timeout, not by exhausting
   each limit. *Ask*: can one account starve the others?
5. **Payments**: live providers are never contacted by the tests, only fake
   ones. Settlement reconciliation is not proved.
6. **Browser policy**: the CSP still allows inline scripts and styles on
   hosted sites.

## 3. Rules of engagement

- Test only a deployment built for the audit, with its own secrets and its
  own database. Never the maintainer's machines, and never real customer data.
- The maintainer supplies: the frozen archive, a deployed instance reachable
  by the auditor, two test accounts per role, and a fake payment provider
  (`tests/test_paiement.py` embeds one). The auditor does not need real Stripe
  or FedaPay keys.
- Credentials and tokens used during the test are revoked at the end.
- Findings go to the maintainer privately first. **No vulnerability detail is
  published in a public issue** until a fix is released; this repository
  already follows that rule.

## 4. What the auditor delivers

1. A report listing each finding with: affected component, reproduction steps
   against the frozen version, impact, and a severity with its scoring method.
2. An explicit statement of what was **not** tested. A clean report without
   that statement says nothing.
3. A retest of each fixed finding on the fixed version.

## 5. What the maintainer publishes afterwards

Following the same discipline as the rest of the project (claims are made
only where something proves them):

- the **scope** (section 1 as engaged), the **version and commit** audited,
  the auditor's name and the dates;
- the **severity counts** and what was fixed, with the fix commits;
- the findings left open, with the reason;
- the sentence "no vulnerability found" **only if** the report says so and
  lists what it covered.

[Security model](SECURITE.md) and the threat model are updated in the same
pull request, so the written guarantees match the audited ones.

## 6. Choosing the auditor

No vendor is named here. Criteria worth writing into the request:

- has audited a code generator or an API framework, not only websites;
- accepts the frozen-archive and private-disclosure rules above;
- will state its non-coverage in writing;
- can retest after fixes within the engagement.

## 7. Decisions that stay with the maintainer

Budget, timing (a release candidate is the natural moment, not the final
release, so fixes can still land before 1.0.0), and the choice of auditor.
Until they are made, issue #124 stays open for this half only.
