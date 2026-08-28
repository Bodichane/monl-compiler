"""Practical reference for writing a Monl specification."""

from __future__ import annotations

from .coloration import coloriser
from .guide import REGLES_ACCES, REGLES_CHAMPS, REGLES_COMMERCE, REGLES_SERVEUR, TYPES
from .theme import icon, page

EXTRA_CSS = """
.docs-layout{display:grid;grid-template-columns:220px minmax(0,1fr);gap:var(--space-7);padding-block:var(--space-7);align-items:start}
.docs-nav{position:sticky;top:88px}.docs-nav p{font:600 11px var(--mono);letter-spacing:.1em;text-transform:uppercase;color:var(--muted)}
.docs-nav a{display:flex;align-items:center;min-height:44px;padding:7px 10px;border-radius:9px;text-decoration:none;color:var(--muted)}
.docs-nav a:hover{background:var(--surface-2);color:var(--ink)}
.docs-main>section{padding-bottom:var(--space-8);scroll-margin-top:90px}.docs-main h1{font-size:clamp(38px,6vw,62px);margin-bottom:var(--space-4)}
.docs-main h2{font-size:clamp(27px,4vw,38px);margin-bottom:var(--space-3)}.docs-main .lede{color:var(--muted);font-size:18px;max-width:760px}
.quick{display:grid;grid-template-columns:1.1fr .9fr;gap:var(--space-4);margin-top:var(--space-6)}
.anatomy{display:grid;gap:var(--space-3)}.anatomy h3{margin:var(--space-3) 0 var(--space-2);font-size:17px}.anatomy p{color:var(--muted);margin:0;font-size:14px}
.feature-icon{width:40px;height:40px;display:grid;place-items:center;border-radius:11px;background:var(--soft);color:var(--brand)}
.keyword-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:var(--space-3)}.keyword{border:1px solid var(--line);border-radius:var(--radius);padding:var(--space-4);background:var(--surface)}
.keyword code{display:block;color:var(--brand);margin-bottom:7px;overflow-wrap:anywhere}.keyword p{color:var(--muted);margin:0;font-size:14px}
.type-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:var(--space-2)}.type{border:1px solid var(--line);border-radius:10px;padding:var(--space-3);background:var(--surface)}
.type code{color:var(--brand);font-weight:700}.type p{color:var(--muted);font-size:13px;margin:5px 0 0}
.tip{display:grid;grid-template-columns:auto 1fr;gap:var(--space-3);background:var(--soft);border:1px solid var(--line);border-radius:var(--radius);padding:var(--space-4)}.tip p{margin:0}
.docs-actions{display:flex;flex-wrap:wrap;gap:var(--space-3)}
@media(max-width:820px){.docs-layout{grid-template-columns:1fr}.docs-nav{display:none}.quick{grid-template-columns:1fr}}
@media(max-width:620px){.keyword-grid,.type-grid{grid-template-columns:1fr}}
"""

# Écrit en TEXTE NU : la coloration est faite par le coloriseur, dont les
# mots-clés viennent de la grammaire. Marqués à la main, ils dataient du jour
# où on les avait écrits.
EXAMPLE = coloriser("""app BoutiqueLocale

entity Produit
    nom: String
    prix: Money
    stock: Integer

actor Client selfRegister
actor Vendeur

rule Produit.nom required
rule Produit.prix min 0
rule Produit.Read public

workflow GererCatalogue for Vendeur
    Create Produit
    Read Produit
    Update Produit
    Delete Produit""")


def _types() -> str:
    return "".join(f'<div class="type"><code>{name}</code><p>{text}</p></div>' for name, text in TYPES)


def _rules(rows: list[tuple[str, str]]) -> str:
    return "".join(f'<article class="keyword"><code>{syntax}</code><p>{text}</p></article>' for syntax, text in rows)


BODY = f"""
<div class="shell docs-layout"><aside class="docs-nav" aria-label="Sommaire"><p>Écrire une spec</p>
<a href="#structure">Structure</a><a href="#mots-cles">Mots-clés</a><a href="#types">Types</a>
<a href="#acces">Accès et sécurité</a><a href="#validation">Validation</a><a href="/guide#dsl">Référence avancée</a></aside>
<article class="docs-main">
<section id="structure"><h1>Écrire une spécification Monl.</h1>
<p class="lede">Une spec décrit le métier dans cet ordre : application, données, acteurs, relations, règles, puis actions autorisées.</p>
<div class="quick"><pre class="codeblock"><code>{EXAMPLE}</code></pre><div class="anatomy">
<article class="card"><span class="feature-icon">{icon('code')}</span><h3>Les données</h3><p><code>entity</code> déclare une table et ses champs typés.</p></article>
<article class="card"><span class="feature-icon">{icon('shield')}</span><h3>Les droits</h3><p><code>actor</code> et <code>rule</code> déterminent qui agit sur quoi.</p></article>
<article class="card"><span class="feature-icon">{icon('terminal')}</span><h3>Les actions</h3><p><code>workflow</code> ouvre les opérations de chaque acteur.</p></article></div></div></section>

<section id="mots-cles"><h2>Les mots-clés essentiels.</h2><div class="keyword-grid">
<article class="keyword"><code>app Nom</code><p>Nomme l’application, une fois, au début.</p></article>
<article class="keyword"><code>entity Nom</code><p>Déclare une donnée ; les lignes indentées sont ses champs.</p></article>
<article class="keyword"><code>actor Nom [selfRegister]</code><p>Déclare un rôle et, éventuellement, son inscription publique.</p></article>
<article class="keyword"><code>relation A hasMany B</code><p>Relie les objets et donne le chemin de propriété.</p></article>
<article class="keyword"><code>rule Cible contrainte</code><p>Ajoute validation, calcul serveur ou règle d’accès.</p></article>
<article class="keyword"><code>workflow Nom for Acteur</code><p>Liste Create, Read, Update et Delete autorisés.</p></article>
<article class="keyword"><code>capability auth</code><p>Configure l’identification et les sessions.</p></article>
<article class="keyword"><code>seed Entite</code><p>Ajoute les données initiales dans une table vide.</p></article>
</div></section>

<section id="types"><h2>Les types acceptés.</h2>
<p class="lede">Le type détermine validation, stockage SQL et contrat frontend.</p><div class="type-grid">{_types()}</div></section>

<section id="acces"><h2>Accès et sécurité.</h2>
<p class="lede">Ces règles s’appliquent côté API : masquer un bouton ne constitue jamais une autorisation.</p>
<div class="keyword-grid">{_rules(REGLES_ACCES)}</div><h2 style="margin-top:var(--space-7)">Validation et calcul serveur.</h2>
<div class="keyword-grid">{_rules(REGLES_CHAMPS + REGLES_SERVEUR + REGLES_COMMERCE)}</div></section>

<section id="validation"><h2>Valider la spec.</h2>
<div class="tip"><span class="feature-icon">{icon('check')}</span><p>Collez le fichier dans la <a href="/console">console</a> puis choisissez <b>Vérifier la spec</b>.
En local : <code>monl compile ma-spec.ml</code>. Les capacités avancées sont détaillées dans le <a href="/guide#dsl">guide complet</a>.</p></div>
<div class="docs-actions" style="margin-top:var(--space-5)"><a class="primary" href="/console">Tester une spécification {icon('arrow')}</a>
<a class="secondary" href="/api-docs">Documentation de l’API</a></div></section>
</article></div>
"""

DOCS_HTML = page(title="Écrire une spécification — documentation Monl",
    description="Mots-clés, types et règles pour écrire une spécification Monl valide.",
    body=BODY, active="docs", extra_css=EXTRA_CSS)
