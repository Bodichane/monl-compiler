"""Terms of use and privacy policy.

Two rules guided the writing, and they show in the text.

**Nothing is invented.** The service's publisher — name, legal form,
address, contact — cannot be deduced from the code: these slots carry a
clearly visible `TO BE COMPLETED` marker rather than a plausible
identity. Making up a legal notice would be producing a false document.

**What is said is verifiable in the code.** The list of retained data is
compared to the real SQLite schema by `tests/test_platform_exploitation.py`: a
table that keeps personal data and that the page does not name makes the
suite fail. A privacy policy that drifts out of sync with the code is worse
than absent — it makes a claim."""

from __future__ import annotations

from .theme import page

MARQUEUR = "TO BE COMPLETED"

EDITEUR = "Itchane Bodi"
CONTACT = "contact@monl.dev"
# Unlike the two constants above, this one is a PUBLIC fact: OVH publishes its
# own legal identity so that its customers cite it. It is therefore filled in —
# taken from https://www.ovhcloud.com/fr/terms-and-conditions/ on 26/08/2026,
# not written from memory. The phone number appears on none of OVH's public
# pages; the LCEN requires it for the host, so it remains to be added if the
# service falls under French law.
#
# A useful clarification: naming the host is NOT a GDPR requirement, which
# concerns the identity of the data controller and people's rights. It is the
# French LCEN that imposes it, and it applies according to the publisher's
# establishment and the targeted public — not according to the server's
# country. The notice is kept because it costs nothing and covers that case.
HEBERGEUR = ("OVH SAS, SAS with a share capital of €50,000,000 — "
             "2 rue Kellermann, 59100 Roubaix, France — RCS 424 761 419")


def est_complete() -> bool:
    """True when the three slots carry a real identity."""
    return all(MARQUEUR not in valeur for valeur in (EDITEUR, CONTACT, HEBERGEUR))


def _lignes_manquantes() -> str:
    """Names what remains to be filled in, and nothing else.

    A fixed count ("these three slots") would send people to fix what is
    already correct as soon as a single value is missing — the same reproach
    as point 97 of the compiler: an assumption displayed as a diagnosis is
    worse than a vague message."""
    manquants = [nom for nom, valeur in (("the publisher", EDITEUR),
                                         ("the contact address", CONTACT),
                                         ("the host", HEBERGEUR))
                 if MARQUEUR in valeur]
    if not manquants:
        return ""
    quoi = manquants[0] if len(manquants) == 1 else (
        ", ".join(manquants[:-1]) + " and " + manquants[-1])
    return (f'<span class="trou">Still to be filled in before opening to the '
            f'public: {quoi}. These values cannot be inferred from the code, and '
            'inventing them would produce a forgery.</span>')


MENTIONS = f"""
<section class="shell legal">
<span class="maj">Legal notice</span>
<h1>Who publishes this service, who hosts it, and how to reach us.</h1>

{_lignes_manquantes()}

<h2>Publisher</h2>
<p>This service is published by <strong>{EDITEUR}</strong>, a natural person,
who is also the publication director.</p>

<h2>Host</h2>
<p>This service is hosted by <strong>{HEBERGEUR}</strong>.</p>

<h2>Contact</h2>
<p>For any question about the service, and to exercise your rights over your
data, write to <strong>{CONTACT}</strong>.</p>
<p>No other contact channel exists: the service sends no email and has no
telephone support.</p>

<h2>Ownership</h2>
<p>You remain the owner of the specifications you submit and of the backends
produced from them. The monl compiler and the code of this platform are covered
by their own license, published with their source code.</p>

<h2>The other documents</h2>
<ul>
<li><a href="/conditions">Terms of use</a> — what the service promises, and what
it does not guarantee.</li>
<li><a href="/confidentialite">Privacy policy</a> — the data kept, how long it
lives, and how to erase everything.</li>
</ul>
</section>
"""


CSS = """
.legal { max-width: 74ch; padding-block: var(--space-7) var(--space-8); }
.legal h1 { font-size: clamp(32px, 5vw, 48px); letter-spacing: -.03em; margin-bottom: var(--space-3); }
.legal .maj { color: var(--muted); font: 600 12px var(--mono); letter-spacing: .1em;
              text-transform: uppercase; margin-bottom: var(--space-6); display: block; }
.legal h2 { font-size: 22px; margin: var(--space-7) 0 var(--space-3); letter-spacing: -.02em; }
.legal h3 { font-size: 16px; margin: var(--space-5) 0 var(--space-2); }
.legal p, .legal li { color: var(--muted); }
.legal strong { color: var(--ink); font-weight: 600; }
.legal ul { padding-left: var(--space-5); display: grid; gap: 6px; margin: var(--space-3) 0; }
.legal table { width: 100%; border-collapse: collapse; margin: 0; font-size: 14px; }
/* The table lives in its OWN scrolling container. Measured at 375px before
   the fix: 17 elements off screen and outside any container, so clipped by
   the `body`'s `overflow-x:clip` — the third column ("How long") was lost,
   on the very page that STATES the retention periods. The first column
   carries `white-space:nowrap` (a table name is not broken), so the minimum
   width cannot go down: it needs scrolling, not a floored track. */
.legal .table-large { overflow-x: auto; margin: var(--space-4) 0; }
.legal th, .legal td { text-align: left; padding: 10px 12px; border-bottom: 1px solid var(--line);
                       vertical-align: top; }
.legal th { color: var(--ink); font-weight: 600; }
.legal td:first-child { font-family: var(--mono); font-size: 13px; color: var(--ink); white-space: nowrap; }
.legal .trou { display: block; border: 1px dashed var(--line-strong); border-radius: 10px;
               padding: var(--space-4); margin: var(--space-4) 0; background: var(--surface-2);
               color: var(--ink); font-size: 14px; }
.legal .trou b { font-family: var(--mono); font-size: 13px; }
.legal .identite { border-left: 3px solid var(--line-strong); padding-left: var(--space-4);
                   margin: var(--space-4) 0; color: var(--ink); }
.legal .identite b { font-weight: 600; }
@media (max-width: 620px) { .legal td:first-child { white-space: normal; } }
"""

# What each table retains. The test compares this list to the real schema:
# adding a table without listing it here makes the suite fail.
DONNEES = [
    ("users", "Email address, scrypt fingerprint of the password, creation date.",
     "As long as the account exists."),
    ("sessions", "SHA-256 fingerprint of the session token, expiry date.",
     "30 days, then automatic deletion."),
    ("projects", "Identifier and name of the compiled project, creation and expiry dates.",
     "30 days by default, then automatic deletion of the folder and the row."),
    ("api_keys", "Key name, its first thirteen characters, SHA-256 fingerprint, "
                 "date of last use.", "Until the key is revoked."),
    ("recovery_codes", "SHA-256 fingerprint of each unused recovery code.",
     "Until they are used or replaced."),
    ("rate_limits", "Fingerprint of the account or IP address, counter for the current window.",
     "For one rate-limit window, at most one hour."),
]

_LIGNES = "".join(
    f"<tr><td>{table}</td><td>{quoi}</td><td>{duree}</td></tr>"
    for table, quoi, duree in DONNEES
)

CONFIDENTIALITE = f"""
<section class="shell legal">
<span class="maj">Privacy policy</span>
<h1>What the service keeps, and for how long.</h1>

<p>This page describes the data the platform actually records. It is checked
against the database schema by the test suite: data that is kept but not
described here makes the build fail.</p>

<h2>The data kept</h2>
<div class="table-large"><table>
<thead><tr><th>Where</th><th>What</th><th>How long</th></tr></thead>
<tbody>{_LIGNES}</tbody>
</table></div>

<h3>What the service does not do</h3>
<ul>
<li><strong>No password is stored in plain text.</strong> Only a scrypt
fingerprint, with a salt unique to each account.</li>
<li><strong>No token is stored in plain text</strong> — neither session, API key
nor recovery code. A lost key cannot be recovered, only revoked and replaced; a
lost recovery code, only regenerated.</li>
<li><strong>No tracker, no audience measurement, no advertising cookie.</strong>
Only two cookies, both strictly necessary for signing in:
<code>monl_session</code>, which keeps you signed in, and <code>monl_oauth_flow</code>,
set for the duration of a Google or GitHub sign-in to check that the provider’s
return reaches the browser that started it — it is erased as soon as the round
trip is over.</li>
<li><strong>No email is sent.</strong> Your address serves as your sign-in
identifier, nothing else. It is neither verified nor used to write to you.</li>
<li><strong>No data is passed to any third party.</strong> The specs you compile
and the backends produced do not leave the service.</li>
</ul>

<h2>Your specs and your backends</h2>
<p>The text you compile is written to the server’s disk while the backend is
produced, then kept with the project. <strong>Everything is erased automatically
when the project expires</strong>, with no intervention. You can delete a project
at any time from the console.</p>

<h2>Your rights</h2>
<p><strong>Deletion is immediate and complete.</strong> From your account page,
deletion erases the account, its sessions, its API keys, its projects in the
database <em>and</em> the corresponding folders on disk, including the visitors’
databases. Hosted sites are stopped. An OAuth account requires a sign-in with its
provider less than ten minutes old; a local account requires its password.
Nothing is kept, and the operation is irreversible.</p>
<p>For access, rectification, objection or portability, write to
<strong>{CONTACT}</strong>. The data controller is named in the
<a href="/mentions-legales">legal notice</a>.</p>
<p>You may also <strong>lodge a complaint with the supervisory authority</strong>
of your country of residence if you believe the processing of your data does not
comply.</p>

<h2>Log retention</h2>
<p>The service logs operational events — sign-ins, compilations, key revocations —
so that an incident can be established. <strong>These logs contain no password,
no token and no key</strong>: the component that writes them masks these values
by construction, whether they are recognized by their name or by their shape.</p>
</section>
"""

CONDITIONS = """
<section class="shell legal">
<span class="maj">Terms of use</span>
<h1>What the service promises, and what it does not.</h1>

<h2>The service</h2>
<p>The platform compiles a Monl specification into a complete application
(FastAPI, SQLite, JWT). Compilation is <strong>deterministic</strong>: the same
spec produces the same backend, without artificial intelligence and without
network calls.</p>

<h2>The account</h2>
<ul>
<li>An account is created with an email address and a password of at least ten
characters. <strong>The address is not verified</strong>, and no email is
sent.</li>
<li><strong>Eight recovery codes are given to you at sign-up</strong>, only once.
Since no email is sent, they — and nothing else — let you regain control after a
lost password. Each one works only once. <strong>Without a password and without
a code, the account and its projects are permanently inaccessible.</strong> Keep
both in a password manager.</li>
<li>You can generate a new set from your account page: it replaces the old one,
which stops working immediately.</li>
<li>You are responsible for the API keys you create. A compromised key is revoked
from the dedicated page; it cannot be read again.</li>
</ul>

<h2>What you may compile</h2>
<p>You remain the owner of your specs and of the backends produced. It is up to
you to hold the rights to what you submit, and not to use it to produce an
unlawful service.</p>
<p>The service refuses a spec it considers dangerous or too costly to compile.
Compilations are bounded in time, memory and output size, and limited in number
per account and per hour.</p>

<h2>What is not guaranteed</h2>
<ul>
<li><strong>No availability is guaranteed.</strong> The service may be
interrupted at any time and without notice.</li>
<li><strong>Your projects are temporary.</strong> They are erased automatically
after their retention period. Download the archive of whatever you want to keep.</li>
<li>The produced backend is provided <strong>as is</strong>. Putting it into
production, operating it securely and backing up its data are your
responsibility.</li>
</ul>

<h2>Termination</h2>
<p>You can delete your account at any time from your account page. For an OAuth account, sign in again with your provider within the ten minutes before deletion; for a local account, confirm your password. Sites are stopped and their visitor databases erased:
the deletion is immediate, complete and irreversible. The publisher may suspend an
account that endangers the service or uses it unlawfully.</p>

<h2>Changes</h2>
<p>These terms may change. The version in force is the one published on this
page.</p>

<h2>Who publishes this service</h2>
<p>The publisher, the host and the contact address are named in the
<a href="/mentions-legales">legal notice</a>.</p>
</section>
"""

MENTIONS_HTML = page(
    title="Legal notice — MONL",
    description="Who publishes this service, who hosts it, and how to reach us.",
    body=MENTIONS, extra_css=CSS,
)

CONDITIONS_HTML = page(
    title="Terms of use — MONL",
    description="What the service promises, what it does not guarantee, and how "
                "to close an account.",
    body=CONDITIONS, extra_css=CSS,
)

CONFIDENTIALITE_HTML = page(
    title="Privacy — MONL",
    description="The data kept by the platform, how long it lives, and how to "
                "erase everything.",
    body=CONFIDENTIALITE, extra_css=CSS,
)
