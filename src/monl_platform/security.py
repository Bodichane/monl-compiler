"""Public, evidence-oriented description of Monl's security boundary."""

from __future__ import annotations

from .theme import icon, page

EXTRA_CSS = """
.band{border-block:1px solid var(--line);background:var(--surface-2)}
.security-hero{padding:var(--space-8) 0 var(--space-7);max-width:850px}.security-hero h1{font-size:clamp(40px,7vw,70px);margin-bottom:var(--space-4)}
.security-hero .lede{font-size:20px;color:var(--muted);max-width:760px}.security-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:var(--space-3)}
.proof-card{min-height:260px}.proof-head{display:flex;align-items:center;gap:var(--space-3);margin-bottom:var(--space-4)}
.proof-head h2{font-size:20px}.proof-icon{width:42px;height:42px;display:grid;place-items:center;border-radius:12px;background:var(--soft);color:var(--brand)}
.proof-card p{color:var(--muted)}.proof-card ul{padding-left:1.1rem;margin:0}.proof-card li{margin:7px 0;font-size:14px}
.evidence{display:inline-flex;align-items:center;gap:7px;margin-top:var(--space-4);color:var(--brand);font:600 12px var(--mono)}
.boundary{display:grid;grid-template-columns:1fr 1fr;gap:var(--space-4)}.boundary>div{border-radius:var(--radius-lg);padding:var(--space-5)}
.guaranteed{background:var(--soft);border:1px solid var(--brand)}.responsibility{background:var(--danger-bg);border:1px solid var(--danger-line)}
.boundary h2{font-size:21px;margin-bottom:var(--space-3)}.boundary li{margin:8px 0}.attack-table td:first-child{font-family:var(--mono);font-size:13px}
@media(max-width:760px){.security-grid,.boundary{grid-template-columns:1fr}.security-hero{padding-top:var(--space-7)}}
"""

BODY = f"""
<section class="shell security-hero"><h1 data-reveal>The rules are enforced, not suggested.</h1>
<p class="lede" data-reveal>Monl compiles permissions and invariants into the backend. This page separates
what the compiler guarantees from what remains the deployment's responsibility.</p></section>

<section class="shell section"><div class="section-head" data-reveal><h2>Four layers from the same specification.</h2></div><div class="security-grid">
<article class="card proof-card" data-reveal><div class="proof-head"><span class="proof-icon">{icon('check')}</span><h2>Refused at compile time</h2></div>
<p>An impossible rule is never silently ignored.</p><ul><li>Reference to a missing field or actor</li><li>Ownership without a usable relation</li>
<li>Payment on an amount the client can change</li><li>Contradictory permission combinations</li></ul><span class="evidence">Parser + static audit</span></article>
<article class="card proof-card" data-reveal style="--reveal-delay:50ms"><div class="proof-head"><span class="proof-icon">{icon('shield')}</span><h2>Per-record control</h2></div>
<p>Permissions are evaluated in the API, lists included.</p><ul><li><code>ownedBy</code> limits to the owner</li><li><code>accessibleBy</code> limits to the parties</li>
<li><code>sharedBy</code> adds a supervisor role</li><li><code>publicWhen</code> filters list and detail</li></ul><span class="evidence">HTTP tests with distinct accounts</span></article>
<article class="card proof-card" data-reveal><div class="proof-head"><span class="proof-icon">{icon('package')}</span><h2>Database invariants</h2></div>
<p>Sensitive constraints do not depend on a frontend button.</p><ul><li>Uniqueness through SQL indexes</li><li>Stock decremented atomically</li>
<li>Amounts recalculated server-side</li><li>Paid orders frozen</li></ul><span class="evidence">Proven on SQLite and PostgreSQL</span></article>
<article class="card proof-card" data-reveal style="--reveal-delay:50ms"><div class="proof-head"><span class="proof-icon">{icon('code')}</span><h2>An unambiguous contract</h2></div>
<p>The frontend receives the same permissions the backend enforces.</p><ul><li>Public and authenticated routes</li><li>Fields written or calculated by the server</li>
<li>Actors allowed per action</li><li>Exact shape of authentication responses</li></ul><span class="evidence">Versioned frontend_contract.json</span></article>
</div></section>

<section class="band"><div class="shell section"><div class="section-head"><h2>What the suite actually tries to break.</h2></div><div class="tablewrap"><table class="grid attack-table"><thead><tr><th>Attempt</th><th>Expected defense</th></tr></thead><tbody>
<tr><td>JWT signed with the wrong key</td><td>401, identity refused</td></tr><tr><td>Authenticated but unauthorized actor</td><td>403, nothing written</td></tr>
<tr><td>Direct read of another account’s object</td><td>404, object not disclosed</td></tr><tr><td>Two simultaneous oncePer actions</td><td>A single insert, thanks to the index</td></tr>
<tr><td>Order larger than the stock</td><td>409, stock unchanged</td></tr><tr><td>Amount supplied by the payer</td><td>Body ignored, or rule refused at compile time</td></tr>
</tbody></table></div></div></section>

<section class="shell section"><div class="section-head"><h2>Guaranteed by Monl, or configured by you.</h2></div>
<div class="boundary"><div class="guaranteed"><h2>Monl guarantees</h2><ul><li>Consistency between spec, API, SQL and contract</li><li>Enforcement of the declared permissions</li>
<li>No JWT secret in the archive</li><li>MCP keys hashed, attributed and revocable</li><li>Persistent quotas and bounded compilation workers</li><li>Reproducible output for a given version</li></ul></div>
<div class="responsibility"><h2>The deployment must guarantee</h2><ul><li>HTTPS, backups and updates</li><li>Protection of environment variables</li>
<li>Monitoring and storage capacity</li><li>A reliable reverse proxy and a tested restore</li></ul></div></div>
<div style="margin-top:var(--space-5)"><a class="primary" href="/docs#acces">Read the security rules {icon('arrow')}</a></div></section>
"""

SECURITY_HTML = page(title="Security — MONL",
    description="Security guarantees, evidence and limits of the Monl compiler.",
    body=BODY, active="security", extra_css=EXTRA_CSS)
