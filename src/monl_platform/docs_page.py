"""Practical reference for writing a Monl specification."""

from __future__ import annotations

from .coloration import coloriser

# Read from `guide_data`, the SOURCE, and not through `guide`: that detour made
# `guide` a mere pipe, and ruff reported its imports as dead while they carried
# this very page.
from .guide_data import (
    REGLES_ACCES,
    REGLES_CHAMPS,
    REGLES_COMMERCE,
    REGLES_SERVEUR,
    TYPES,
)
from .theme import icon, page

EXTRA_CSS = """
.docs-layout{display:grid;grid-template-columns:minmax(0,1fr) 212px;gap:var(--space-7);padding-block:var(--space-7);align-items:start}
.docs-main{min-width:0}.docs-main>section{padding-bottom:var(--space-8);scroll-margin-top:96px}.docs-main h1{font-size:clamp(38px,6vw,62px);margin:0 0 var(--space-4)}
.docs-main h2{font-size:clamp(27px,4vw,38px);margin-bottom:var(--space-3)}.docs-main .lede{color:var(--muted);font-size:18px;max-width:700px}
.docs-eyebrow{font:600 12px var(--mono);letter-spacing:.1em;text-transform:uppercase;color:var(--brand);margin:0 0 var(--space-3)}
.docs-nav{position:sticky;top:88px;border-left:1px solid var(--line);padding-left:var(--space-3)}.docs-nav p{font:600 11px var(--mono);letter-spacing:.1em;text-transform:uppercase;color:var(--muted);margin:0 0 var(--space-2)}
.docs-nav a{display:flex;align-items:center;min-height:44px;padding:6px 9px;border-radius:8px;text-decoration:none;color:var(--muted)}
.docs-nav a:hover,.docs-nav a:focus-visible{background:var(--surface-2);color:var(--ink)}
.docs-start{border-top:1px solid var(--line);border-bottom:1px solid var(--line);margin:var(--space-6) 0;padding:var(--space-4) 0}.docs-start h2{font-size:20px;margin:0 0 var(--space-3)}
.docs-paths{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:var(--space-2)}.docs-path{display:block;min-height:126px;padding:var(--space-3);border-radius:var(--radius);text-decoration:none;border:1px solid transparent;color:var(--ink);transition:background-color .16s ease,border-color .16s ease,transform .16s ease}
.docs-path:hover,.docs-path:focus-visible{border-color:var(--line);background:var(--surface-2);transform:translateY(-1px)}.docs-path b{display:block;font-size:16px;margin-bottom:5px}.docs-path span{display:block;color:var(--muted);font-size:14px;line-height:1.5}
.quick{display:grid;grid-template-columns:1.1fr .9fr;gap:var(--space-4);margin-top:var(--space-5)}
.anatomy{display:grid;gap:var(--space-2)}.anatomy h3{margin:var(--space-2) 0 5px;font-size:16px}.anatomy p{color:var(--muted);margin:0;font-size:14px}
.feature-icon{width:40px;height:40px;display:grid;place-items:center;border-radius:11px;background:var(--soft);color:var(--brand)}
.keyword-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:var(--space-3)}.keyword{border:1px solid var(--line);border-radius:var(--radius);padding:var(--space-4);background:var(--surface)}
.keyword code{display:block;color:var(--brand);margin-bottom:7px;overflow-wrap:anywhere}.keyword p{color:var(--muted);margin:0;font-size:14px}
.type-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:var(--space-2)}.type{border:1px solid var(--line);border-radius:10px;padding:var(--space-3);background:var(--surface)}
.type code{color:var(--brand);font-weight:700}.type p{color:var(--muted);font-size:13px;margin:5px 0 0}
.tip{display:grid;grid-template-columns:auto 1fr;gap:var(--space-3);background:var(--soft);border:1px solid var(--line);border-radius:var(--radius);padding:var(--space-4)}.tip p{margin:0}
.docs-actions{display:flex;flex-wrap:wrap;gap:var(--space-3)}
@media(max-width:900px){.docs-layout{grid-template-columns:1fr}.docs-nav{position:static;order:-1;border-left:0;border-bottom:1px solid var(--line);padding:0 0 var(--space-3);display:flex;align-items:center;gap:var(--space-1);overflow:auto}.docs-nav p{margin:0}.docs-nav a{white-space:nowrap}.docs-nav a:last-child{margin-right:var(--space-3)}.docs-paths{grid-template-columns:repeat(3,minmax(180px,1fr));overflow-x:auto;padding-bottom:var(--space-2)}}
@media(max-width:620px){.quick,.keyword-grid,.type-grid{grid-template-columns:1fr}.docs-paths{grid-template-columns:1fr;overflow:visible}.docs-path{min-height:0}}
@media(prefers-reduced-motion:reduce){.docs-path{transition:none}.docs-path:hover,.docs-path:focus-visible{transform:none}}
"""

# Written as PLAIN TEXT: highlighting is done by the highlighter, whose
# keywords come from the grammar. Marked by hand, they dated from the day they
# were written.
EXAMPLE = coloriser("""app LocalShop

entity Product
    name: String
    price: Money
    stock: Integer

actor Customer selfRegister
actor Seller

rule Product.name required
rule Product.price min 0
rule Product.Read public

workflow ManageCatalog for Seller
    Create Product
    Read Product
    Update Product
    Delete Product""")


def _types() -> str:
    return "".join(f'<div class="type"><code>{name}</code><p>{text}</p></div>' for name, text in TYPES)


def _rules(rows: list[tuple[str, str]]) -> str:
    return "".join(f'<article class="keyword"><code>{syntax}</code><p>{text}</p></article>' for syntax, text in rows)


BODY = f"""
<div class="shell docs-layout"><article class="docs-main">
<section id="structure"><p class="docs-eyebrow">Language documentation</p><h1>Write a Monl specification.</h1>
<p class="lede">Describe the data, the people who act on it, and the rules that must never be bypassed. Monl then compiles the backend and its exact contract.</p>
<div class="docs-start"><h2>Choose your starting point</h2><nav class="docs-paths" aria-label="Documentation starting points">
<a class="docs-path" href="#premiere-spec"><b>First spec</b><span>Understand the order of the blocks with a complete example.</span></a>
<a class="docs-path" href="#mots-cles"><b>Language reference</b><span>Find a keyword, a type or a rule.</span></a>
<a class="docs-path" href="#acces"><b>Security and permissions</b><span>Define what each actor can actually do.</span></a>
</nav></div>
<div id="premiere-spec" class="quick"><pre class="codeblock"><code>{EXAMPLE}</code></pre><div class="anatomy">
<article class="card"><span class="feature-icon">{icon('code')}</span><h3>The data</h3><p><code>entity</code> declares a table and its typed fields.</p></article>
<article class="card"><span class="feature-icon">{icon('shield')}</span><h3>The permissions</h3><p><code>actor</code> and <code>rule</code> decide who acts on what.</p></article>
<article class="card"><span class="feature-icon">{icon('terminal')}</span><h3>The actions</h3><p><code>workflow</code> opens each actor’s operations.</p></article></div></div></section>

<section id="mots-cles"><h2>The essential keywords.</h2><div class="keyword-grid">
<article class="keyword"><code>app Name</code><p>Names the application, once, at the top.</p></article>
<article class="keyword"><code>entity Name</code><p>Declares a piece of data; the indented lines are its fields.</p></article>
<article class="keyword"><code>actor Name [selfRegister]</code><p>Declares a role and, optionally, its public sign-up.</p></article>
<article class="keyword"><code>relation A hasMany B</code><p>Links objects and gives the ownership path.</p></article>
<article class="keyword"><code>rule Target constraint</code><p>Adds validation, a server calculation or an access rule.</p></article>
<article class="keyword"><code>workflow Name for Actor</code><p>Lists the allowed Create, Read, Update and Delete.</p></article>
<article class="keyword"><code>capability auth</code><p>Configures identification and sessions.</p></article>
<article class="keyword"><code>seed Entity</code><p>Adds initial data to an empty table.</p></article>
</div></section>

<section id="types"><h2>Accepted types.</h2>
<p class="lede">The type determines validation, SQL storage and the frontend contract.</p><div class="type-grid">{_types()}</div></section>

<section id="acces"><h2>Access and security.</h2>
<p class="lede">These rules apply in the API: hiding a button is never an authorization.</p>
<div class="keyword-grid">{_rules(REGLES_ACCES)}</div><h2 style="margin-top:var(--space-7)">Validation and server calculation.</h2>
<div class="keyword-grid">{_rules(REGLES_CHAMPS + REGLES_SERVEUR + REGLES_COMMERCE)}</div></section>

<section id="validation"><h2>Validate the spec.</h2>
<div class="tip"><span class="feature-icon">{icon('check')}</span><p>Paste the file into the <a href="/console">console</a>, then choose <b>Check the spec</b>.
Locally: <code>monl compile my-spec.ml</code>. For the full path, the archive and how to start it, follow the <a href="/guide#demarrer">getting-started guide</a>.</p></div>
<div class="docs-actions" style="margin-top:var(--space-5)"><a class="primary" href="/console">Try a specification {icon('arrow')}</a>
<a class="secondary" href="/api-docs">API documentation</a></div></section>
</article><aside class="docs-nav" aria-label="Contents"><p>On this page</p>
<a href="#structure">Overview</a><a href="#premiere-spec">First spec</a><a href="#mots-cles">Keywords</a><a href="#types">Types</a>
<a href="#acces">Access and security</a><a href="#validation">Compile and validate</a><a href="/guide#demarrer">Getting started</a></aside></div>
"""

DOCS_HTML = page(title="Write a specification — Monl documentation",
    description="Keywords, types and rules for writing a valid Monl specification.",
    body=BODY, active="docs", extra_css=EXTRA_CSS)
