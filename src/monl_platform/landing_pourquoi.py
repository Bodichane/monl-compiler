"""The three sections the home page did not carry.

The site explained WHAT monl does without ever answering the three
questions a visitor really asks: why this one rather than another, how it
differs from what they already know, and whether they must choose between
the two.

**No invented claim.** Each exploit cited below was measured on a real
server and carries its point in `docs/design_decisions.md`; the
combination with a managed PostgreSQL is proven by
`tests/test_postgresql.py` against a real server. A comparison page that
exaggerates is a page people stop believing at the first check — and the
comparison is written to be FAIR, not to win: Supabase and monl do not
answer the same question.

This module lives next to `landing.py` because the latter had already
reached its line ceiling; the split follows that of the rest of the
package."""

from __future__ import annotations

import html

from .theme import icon

# ---------------------------------------------------------------------------
# Contenu
# ---------------------------------------------------------------------------

# Three writes the client attempted, and what the compiler does with them. Each
# comes from a REAL defect, found on a running server — never by rereading
# code. The amounts are the ones that were measured.
REFUS = [
    {
        "titre": "A calculated value came from the client",
        "attaque": 'POST /order\n{ "total": 0.01 }',
        "avant": "The order was recorded at one cent, then charged for that "
                 "amount.",
        "regle": "rule Line.subtotal derivedFrom Product.price by quantity",
        "apres": "The field disappears from the request body. The server "
                 "calculates it from the linked row, on creation AND on update.",
        "point": "points 77 and 78",
    },
    {
        "titre": "An action exceeded a business limit",
        "attaque": 'POST /line\n{ "quantity": 50 }',
        "avant": "The payment went through. The stock did not move.",
        "regle": "rule Line.Create decrements Product.stock by quantity",
        "apres": "A single SQL statement carries the condition and the write: "
                 "two simultaneous orders cannot read the same stock. "
                 "409 if the floor is crossed.",
        "point": "point 86",
    },
    {
        "titre": "A final state stayed editable",
        "attaque": 'POST /line\n{ "order": 12, "product": 7 }',
        "avant": "Settled at €89, the order climbed to €238 — and the "
                 "back office showed “Paid” next to an amount nobody had "
                 "paid.",
        "regle": "rule Order.total payable",
        "apres": "Five doors close, not one: the total is not changed through "
                 "the order but through the LINE.",
        "point": "point 91",
    },
]

# The comparison. Each row is a FACT verifiable on both sides, never a
# judgment: "simpler", "more modern" and "safer" have no place here. The reader
# decides.
COMPARAISON = [
    ("What you receive",
     "A hosted service: database, API, authentication, storage.",
     "Source code — <code>app.py</code>, <code>schema.sql</code>, "
     "<code>manage.py</code> — that you run wherever you want."),
    ("Where permissions live",
     "<abbr title=\"Row Level Security\">RLS</abbr> policies written in SQL, "
     "table by table, and kept up to date by hand.",
     "Declared once in the spec. Compilation FAILS if two rules contradict "
     "each other."),
    ("Business invariants",
     "Stock, totals, states: to be written as triggers, functions, or in the "
     "calling application.",
     "Compiled into the routes themselves, inside the write's "
     "transaction."),
    ("What the frontend knows",
     "The database schema, through the generated client. Permissions are "
     "left to guess.",
     "An explicit contract: routes, fields, actions, allowed actors, "
     "read-only fields."),
    ("The day you leave",
     "The API and the policies belong to the service.",
     "The archive runs on its own. No monl component at runtime."),
    ("What it does not provide",
     "—",
     "No hosting, no real-time, no managed file storage, no hosted "
     "admin dashboard."),
]

# Three real setups. The first is PROVEN: `tests/test_postgresql.py` starts the
# generated artifacts against a real PostgreSQL and makes real calls. The other
# two are uses of the contract, not integrations — the nuance is written down,
# so as to promise nothing that is not verified.
MONTAGES = [
    {
        "titre": "Postgres is managed, the rules are compiled",
        "texte": "The generated backend reads <code>MONL_DATABASE_URL</code>. "
                 "Point it at your provider’s Postgres — Supabase, Neon, RDS — "
                 "and keep its backups, its replicas and its console.",
        "preuve": "Proven: the generated artifacts run against a real "
                  "PostgreSQL in the test suite.",
        "code": ("export MONL_DATABASE_URL=postgresql://…",
                 "python3 -m uvicorn app:app"),
        "etat": "verifie",
    },
    {
        "titre": "The contract feeds the interface generator",
        "texte": "<code>frontend_contract.json</code> lists the routes, the "
                 "accepted fields and the allowed actors. A UI generation "
                 "tool receives the list instead of inventing it.",
        "preuve": "The contract describes what the backend really does, not "
                  "what the spec declares: a server-calculated field is left "
                  "out.",
        "code": ("monl frontend --provider anthropic",
                 "monl import  # or copy/paste"),
        "etat": "verifie",
    },
    {
        "titre": "What monl leaves aside",
        "texte": "Large files, real-time, sending email: monl does none of "
                 "this and does not pretend otherwise. These pieces stay with "
                 "your provider.",
        "preuve": "A monl backend makes NO network calls, except for payment "
                  "when you declare it.",
        "code": (),
        "etat": "limite",
    },
]


# ---------------------------------------------------------------------------
# Presentation
# ---------------------------------------------------------------------------

# The patterns borrowed from reference libraries are TRANSPOSED, never copied:
# the platform serves HTML without a build, without React and without Motion.
# What crosses over is the mechanics — the comparison row with status dots, and
# opening through `grid-template-rows: 0fr -> 1fr`, which animates an unknown
# height without a line of JavaScript.
EXTRA_CSS = """
.refus { display:grid; gap:14px; margin-top:32px; }
.refus > details {
  border:1px solid var(--line); border-radius:var(--radius-lg);
  background:var(--surface); overflow:hidden;
  transition:border-color .18s ease, box-shadow .18s ease;
}
.refus > details[open] { border-color:var(--line-strong); box-shadow:var(--shadow); }
.refus summary {
  display:flex; align-items:center; gap:14px; cursor:pointer;
  padding:18px 20px; list-style:none; min-height:44px;
  font-weight:600; color:var(--ink);
}
.refus summary::-webkit-details-marker { display:none; }
.refus summary:hover { background:var(--surface-2); }
.refus summary:focus-visible { outline:2px solid var(--accent); outline-offset:-2px; }
.refus summary .chev {
  margin-left:auto; flex:none; width:18px; height:18px; color:var(--muted);
  transition:transform .22s cubic-bezier(.2,.8,.2,1);
}
.refus details[open] summary .chev { transform:rotate(90deg); }
.tag-refus {
  flex:none; font:600 11px/1 var(--mono); letter-spacing:.08em;
  text-transform:uppercase; padding:6px 9px; border-radius:999px;
  background:var(--danger-bg); color:var(--danger);
  border:1px solid var(--danger-line);
}
/* Une hauteur inconnue s'anime par la GRILLE : `height:auto` ne se transitionne
   pas, et figer une hauteur en pixels casse dès que le texte se replie. */
.refus .fold { display:grid; grid-template-rows:0fr; transition:grid-template-rows .26s cubic-bezier(.2,.8,.2,1); }
.refus details[open] .fold { grid-template-rows:1fr; }
.refus .fold > div { overflow:hidden; }
/* `minmax(0,1fr)` et non `1fr` : un `1fr` vaut `minmax(auto,1fr)`, et ce
   plancher `auto` est la largeur MIN-CONTENT de l'enfant — soit, ici, la ligne
   de spec non sécable du bloc de code. Mesuré à 375px avant correction : une
   colonne unique de 497px dans un conteneur de 333, coupée par
   l'`overflow:hidden` du dépliant, donc du texte perdu sans moyen de
   l'atteindre. Le `min-width:0` sur l'enfant fait la même chose pour la taille
   minimale automatique de l'élément de grille ; il faut les DEUX. Le
   défilement reste offert par le `overflow-x:auto` du bloc de code lui-même. */
.refus-body {
  display:grid; grid-template-columns:minmax(0,1fr) minmax(0,1fr); gap:1px;
  background:var(--line); border-top:1px solid var(--line);
}
.refus-body > div { background:var(--surface); padding:20px; min-width:0; }
.refus-body h4 {
  margin:0 0 10px; font:600 11px/1 var(--mono); letter-spacing:.09em;
  text-transform:uppercase; color:var(--muted);
}
.refus-body p { margin:10px 0 0; color:var(--muted); font-size:14.5px; }
.refus-body pre { margin:0; }
.refus-src { padding:12px 20px 16px; font-size:12.5px; color:var(--muted); }

.compare { margin-top:32px; border:1px solid var(--line); border-radius:var(--radius-lg); overflow:hidden; background:var(--surface); }
.compare-row { display:grid; grid-template-columns:minmax(150px,1fr) 1.4fr 1.4fr; gap:1px; background:var(--line); }
.compare-row + .compare-row { margin-top:1px; }
.compare-row > * { background:var(--surface); padding:16px 18px; font-size:14.5px; }
.compare-row.head > * { background:var(--surface-2); font-weight:600; }
.compare-row .who { display:flex; align-items:center; gap:9px; }
.compare-row .axis { font-weight:600; color:var(--ink); }
.compare-row .them, .compare-row .us { color:var(--muted); }
.compare-row .us { color:var(--ink); }
.compare code { font:500 13px/1.5 var(--mono); background:var(--soft); padding:1px 5px; border-radius:5px; }
.dot { width:9px; height:9px; border-radius:50%; flex:none; }
.dot.them { background:var(--line-strong); }
.dot.us { background:var(--accent); }

.montages { display:grid; grid-template-columns:repeat(3,1fr); gap:16px; margin-top:32px; }
.montage { display:flex; flex-direction:column; gap:12px; padding:22px; border:1px solid var(--line); border-radius:var(--radius-lg); background:var(--surface); }
.montage h3 { margin:0; font-size:17px; }
.montage p { margin:0; color:var(--muted); font-size:14.5px; }
.montage pre { margin:auto 0 0; background:var(--code-bg); color:var(--code-ink); border-radius:var(--radius); padding:12px 14px; white-space:pre-wrap; overflow-wrap:anywhere;
  font:500 12.5px/1.6 var(--mono); }
.etat { display:inline-flex; align-items:center; gap:7px; font:600 11px/1 var(--mono); letter-spacing:.07em; text-transform:uppercase; }
.etat.verifie { color:var(--accent); }
.etat.limite { color:var(--muted); }
.etat .icon { width:14px; height:14px; }
@media(max-width:900px){
  .montages{grid-template-columns:1fr}
  .compare-row{grid-template-columns:1fr}
  .refus-body{grid-template-columns:minmax(0,1fr)}
}
@media(prefers-reduced-motion:reduce){
  .refus .fold, .refus summary .chev { transition:none; }
}
"""


def _refus(item: dict, index: int) -> str:
    """An attempt, folded. Opened, the why and the how."""
    return f"""<details data-reveal style="--reveal-delay:{index * 60}ms">
<summary><span class="tag-refus">rule enforced</span>{item['titre']}
<span class="chev">{icon('arrow')}</span></summary>
<div class="fold"><div><div class="refus-body">
<div><h4>What the client sent</h4>
<pre class="codeblock"><code>{item['attaque']}</code></pre>
<p>{item['avant']}</p></div>
<div><h4>The rule that closes it</h4>
<pre class="codeblock"><code>{item['regle']}</code></pre>
<p>{item['apres']}</p></div>
</div><p class="refus-src">Measured on a real server — {item['point']} of
<code>docs/design_decisions.md</code>.</p></div></div>
</details>"""


def _ligne(axe: str, eux: str, nous: str) -> str:
    return (f'<div class="compare-row"><div class="axis">{axe}</div>'
            f'<div class="them">{eux}</div><div class="us">{nous}</div></div>')


def _montage(item: dict, index: int) -> str:
    libelle = ("verified by the tests" if item["etat"] == "verifie"
               else "stated limit")
    symbole = "check" if item["etat"] == "verifie" else "shield"
    # One LINE per command. Squeezed onto a single one, they overflowed the
    # frame and got cut: one read "postgresql://… python3 -m" without the end,
    # and two commands separated by a middle dot could not be copied. The first
    # card gains its `export` along the way: a `VAR=… command` prefix is ONE
    # invocation, so cutting it in two would have given a line that does
    # nothing.
    lignes = "\n".join(html.escape(ligne) for ligne in item["code"])
    code = f'<pre><code>{lignes}</code></pre>' if lignes else ""
    return f"""<article class="montage" data-reveal style="--reveal-delay:{index * 70}ms">
<span class="etat {item['etat']}">{icon(symbole)}{libelle}</span>
<h3>{item['titre']}</h3><p>{item['texte']}</p>
<p class="muted" style="font-size:13.5px">{item['preuve']}</p>{code}</article>"""


SECTIONS = f"""
<section class="shell section" aria-labelledby="pourquoi-title">
<div class="section-head" data-reveal><h2 id="pourquoi-title">The business rules keep applying.</h2>
<p>Calculated values, limits and final states live in the backend, not in an interface button. Open an example to see the rule and the check that enforces it.</p></div>
<div class="refus">{"".join(_refus(r, i) for i, r in enumerate(REFUS))}</div>
</section>

<section class="band"><div class="shell section" aria-labelledby="compare-title">
<div class="section-head" data-reveal><h2 id="compare-title">Monl complements your platform. It does not try to replace it.</h2>
<p>A managed platform provides the infrastructure. Monl provides a backend from business rules. The table shows exactly what belongs to each layer.</p></div>
<div class="compare" data-reveal>
<div class="compare-row head"><div>&nbsp;</div>
<div class="who"><span class="dot them"></span>A managed platform</div>
<div class="who"><span class="dot us"></span>MONL</div></div>
{"".join(_ligne(*ligne) for ligne in COMPARAISON)}
</div></div></section>

<section class="shell section" aria-labelledby="ensemble-title">
<div class="section-head" data-reveal><h2 id="ensemble-title">Use Monl with the tools you already have.</h2>
<p>The generated backend speaks PostgreSQL. You keep the provider, console, backups and replicas that suit your team.</p></div>
<div class="montages">{"".join(_montage(m, i) for i, m in enumerate(MONTAGES))}</div>
</section>
"""
