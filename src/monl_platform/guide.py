"""The public guide renderer for the platform.

Guide data, static fragments and HTML assembly have separate homes. The data
symbols are re-exported here for existing consumers and synchronization tests.
"""

from __future__ import annotations

from .guide_data import LIMITES, OUTILS_MCP, ROUTES_API
from .guide_template import EXTRA_CSS, SCRIPT, SPEC_EXEMPLE
from .theme import page


def _tableau(entetes: tuple[str, str], lignes: list[tuple[str, str]]) -> str:
    corps = "".join(
        f"<tr><td><code>{regle}</code></td><td>{effet}</td></tr>"
        for regle, effet in lignes
    )
    return (f'<div class="tablewrap"><table class="grid"><thead><tr>'
            f"<th>{entetes[0]}</th><th>{entetes[1]}</th></tr></thead>"
            f"<tbody>{corps}</tbody></table></div>")



def _sections() -> list[tuple[str, str, str, str]]:
    """(anchor, short title, displayed counter, HTML content)."""
    routes = "".join(
        f'<tr><td><span class="method">{verbe}</span> <code>{chemin}</code></td>'
        f"<td>{quoi}</td></tr>"
        for verbe, chemin, quoi in ROUTES_API
    )
    outils = "".join(
        f"<tr><td><code>{nom}</code></td><td>{quoi}</td></tr>" for nom, quoi in OUTILS_MCP
    )
    limites = "".join(
        f"<tr><td><b>{titre}</b></td><td>{texte}</td></tr>" for titre, texte in LIMITES
    )
    return [
        ("frontiere", "What Monl produces", "", """
<h2>Monl compiles the backend. The interface is a separate step.</h2>
<p class="lede">You write the business rules. Compilation produces an API,
a database and server-side guarantees. It neither renders nor serves a site.</p>
<div class="boundary" aria-label="What Monl compiles and what it leaves to the interface">
<article><span class="step-no">YOU WRITE</span><h3>A business spec</h3>
<p>Entities, actors, relations, permissions and invariants.</p></article>
<article><span class="step-no">MONL COMPILES</span><h3>A verifiable backend</h3>
<p>SQL, API, authentication and per-record access control.</p></article>
<article><span class="step-no">OPTIONAL STEP</span><h3>An interface is generated or written</h3>
<p>Your team or <code>monl frontend</code> uses the contract and the briefs provided.</p></article>
</div>
<h3>Contract, brief and interface: three different things</h3>
<p>The <code>frontend_contract.json</code> is a description readable by an AI,
a web team or a mobile app. It contains no HTML, no React, no navigation. It
simply answers the question: <i>“which operations is this interface really
allowed to call?”</i></p>
<p><code>FRONTEND_PROMPT.md</code>, <code>DESIGN_SYSTEM.md</code>,
<code>DESIGN_SPEC.md</code> and <code>ASSET_MANIFEST.json</code> are
instructions and resources for that UI step. A <code>DESIGN_SPEC.md</code>
written by the author takes priority. They are not the interface itself.</p>
<p>If you run <code>monl frontend</code>, an AI agent writes the interface in
<code>frontend/</code>, then Monl checks it against the contract. You can just as
well have the interface written by your team or by a mobile app: the backend
stays the same.</p>
<div class="note"><p><b>Nothing is guessed.</b> The dialogue, validation and
generation are fully deterministic: same spec, same bytes. A rule with no effect
is refused at compile time rather than silently ignored, and so is a rule that
names a missing field — a constraint that matches nothing suggests a protection
that does not exist.</p></div>
<h3>What you get</h3>
<ul>
<li><code>app.py</code> — the complete FastAPI API, accounts and sessions included.</li>
<li><code>schema.sql</code> — the schema, with its indexes and foreign keys.</li>
<li><code>frontend_contract.json</code> — the routes, fields and permissions actually available.</li>
<li><code>FRONTEND_PROMPT.md</code> — a brief for the agent or team that will build the interface.</li>
<li><code>manage.py</code> — creation of privileged accounts, offline.</li>
<li><code>Dockerfile</code>, <code>serve.py</code> — what you need to put it online.</li>
<li><code>DESIGN_SYSTEM.md</code>, <code>DESIGN_SPEC.md</code> — the composition
constraints and visual brief used by an optional UI generation.</li>
<li><code>ASSET_MANIFEST.json</code> — the expected visuals and how that same step checks them.</li>
</ul>"""),

        ("demarrer", "First backend", "3 steps", f"""
<h2>Compile a real backend first</h2>
<p class="lede">Start from this complete spec, validate it in the console, then
download an archive that starts locally. Each step produces a result you can
check.</p>
<h3>1. Describe the business</h3>
<pre class="codeblock"><code>{SPEC_EXEMPLE}</code></pre>
<p><a class="primary" href="/console">Open the console and compile a spec</a></p>
<h3>2. Check, then compile</h3>
<p>The parser and the audit report impossible or incomplete rules. If the spec
is valid, the archive contains the API, the SQL schema and the contract that
describes exactly what it can do.</p>
<h3>3. Start the archive</h3>
<pre class="codeblock"><code>unzip monl-backend-*.zip -d notebook &amp;&amp; cd notebook
pip install -r requirements.txt
python3 -m uvicorn app:app --port 8000
<span class="cm"># the backend's OpenAPI documentation: http://127.0.0.1:8000/docs</span></code></pre>
<h3>Optional: build an interface afterwards</h3>
<p>Once the backend is running, you can keep your own interface or ask the AI
step to build one, separately:</p>
<pre class="codeblock"><code>cd notebook
monl frontend . <span class="cm"># uses FRONTEND_PROMPT.md and writes frontend/</span></code></pre>
<p>This command requires a configured AI provider. It does not change the spec,
the schema, the API or the contract.</p>"""),

        ("dsl", "Read the reference", "", """
<h2>When to use the language documentation</h2>
<p class="lede">The guide walks you through creating and starting a first
backend. The documentation is where you look up a precise syntax while you write
your spec.</p>
<div class="boundary" aria-label="What the language documentation contains">
<article><span class="step-no">STRUCTURE</span><h3>The blocks</h3>
<p><code>app</code>, <code>entity</code>, <code>actor</code>, <code>relation</code>,
<code>workflow</code> and <code>rule</code>.</p></article>
<article><span class="step-no">REFERENCE</span><h3>Types and constraints</h3>
<p>Field types, validations, server calculations, counters and payment.</p></article>
<article><span class="step-no">SECURITY</span><h3>The permissions actually enforced</h3>
<p>Reads, ownership, roles and authorizations are described next to their syntax.</p></article>
</div>
<p><a class="primary" href="/docs">Open the spec reference</a></p>
<p class="muted">Looking for the platform API or the MCP server? The next
sections document them separately.</p>"""),

        ("api", "HTTP API", f"{len(ROUTES_API)} routes", f"""
<h2>The platform API</h2>
<p class="lede">Everything the console does goes through these routes: nothing
is reserved to the interface.</p>
<div class="tablewrap"><table class="grid"><thead><tr><th>Route</th><th>Effect</th></tr></thead><tbody>{routes}</tbody></table></div>
<h3>Compile in one command</h3>
<pre class="codeblock"><code><span class="cm"># once: create the account and keep the session</span>
curl -c monl.cookies -X POST http://127.0.0.1:8022/api/auth/register \\
  -H 'Content-Type: application/json' \\
  -d '{{"email":"you@example.com","password":"a-secret-passphrase"}}'

curl -b monl.cookies -X POST http://127.0.0.1:8022/api/compile \\
  -H 'Content-Type: application/json' \\
  -d "$(jq -Rs '{{spec: .}}' my-spec.ml)"</code></pre>
<div class="note"><p>A specification is limited to <b>256 KB</b>. No output path
supplied by the client is accepted: each project receives an opaque identifier,
and a failed compilation leaves no visible partial project.</p></div>
<p class="muted">The developer documentation is served at <a href="/docs">/docs</a>,
the interactive explorer at <a href="/api-docs">/api-docs</a>
and <a href="/openapi.json">/openapi.json</a>.</p>"""),

        ("mcp", "MCP server", f"{len(OUTILS_MCP)} tools", f"""
<h2>For agents</h2>
<p class="lede">The same pipeline, exposed over MCP. An agent validates and
compiles without installing the repository — and without a second generator
existing anywhere.</p>
<div class="tablewrap"><table class="grid"><thead><tr><th>Tool</th><th>Effect</th></tr></thead><tbody>{outils}</tbody></table></div>
<h3>Locally, over stdio</h3>
<pre class="codeblock"><code>{{
  "mcpServers": {{
    "monl": {{
      "command": "monl-mcp"
    }}
  }}
}}</code></pre>
<h3>Or over HTTP</h3>
<pre class="codeblock"><code>curl -s -X POST http://127.0.0.1:8022/mcp \\
  -H 'Content-Type: application/json' \\
  -H 'Authorization: Bearer monl_YOUR_KEY' \\
  -d '{{"jsonrpc":"2.0","id":1,"method":"tools/list"}}'</code></pre>
<div class="note"><p><b>Per-user keys:</b> create the key in your account. It
is shown only once; Monl keeps only its fingerprint and lets you revoke it. The
MCP client sends it with <code>Authorization: Bearer monl_…</code>.</p></div>"""),

        ("limites", "Limits", "", f"""
<h2>What this platform does not do</h2>
<p class="lede">Stated up front rather than discovered along the way.</p>
<div class="tablewrap"><table class="grid"><thead><tr><th>Limit</th><th>Why, and the workaround</th></tr></thead><tbody>{limites}</tbody></table></div>
<h3>Going further</h3>
<p>The local compiler opens the guided dialogue, assets, CSV content and
AI-driven interface rebuilds. It is published on PyPI as
<code>monl-compiler</code>.</p>
<pre class="codeblock"><code>pip install monl-compiler
monl                      <span class="cm"># guided dialogue: spec + backend + contract</span>
monl run MyProject        <span class="cm"># consistency, smoke test, then launch</span></code></pre>""")
    ]


def _compteur(valeur: str) -> str:
    """The table of contents counter, outside an f-string: an f-string cannot
    contain a backslash before Python 3.12, and CI still compiles on 3.10."""
    return f'<span class="count">{valeur}</span>' if valeur else ""


def guide_html() -> str:
    sections = _sections()
    toc = "".join(
        f'<li><a href="#{ancre}">{titre}{_compteur(compte)}</a></li>'
        for ancre, titre, compte, _ in sections
    )
    corps = "".join(
        f'<section id="{ancre}">{contenu}</section>' for ancre, _, _, contenu in sections
    )
    body = f"""
<div class="shell doc">
<nav class="toc" aria-label="Guide contents">
<h2>Guide</h2>
<ol>{toc}</ol>
</nav>
<article>{corps}</article>
</div>"""
    return page(
        title="Guide — MONL",
        description="Tutorial for compiling a first Monl backend and using the platform and the MCP server.",
        body=body,
        active="guide",
        scripts=SCRIPT,
        extra_css=EXTRA_CSS,
    )
