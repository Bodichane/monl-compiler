"""The public guide renderer for the platform.

Guide data, static fragments and HTML assembly have separate homes. The data
symbols are re-exported here for existing consumers and synchronization tests.
"""

from __future__ import annotations

from .guide_data import (
    CONTENU,
    LIMITES,
    OUTILS_MCP,
    REGLES_ACCES,
    REGLES_CHAMPS,
    REGLES_COMMERCE,
    REGLES_SERVEUR,
    ROUTES_API,
    TYPES,
)
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
    """(ancre, titre court, compteur affiché, contenu HTML)."""
    types = "".join(
        f"<tr><td><code>{nom}</code></td><td>{quoi}</td></tr>" for nom, quoi in TYPES
    )
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
        ("frontiere", "La frontière", "", """
<h2>Ce que monl compile, et ce qu'il ne fait pas</h2>
<p class="lede">Monl transforme une intention métier explicite en backend cohérent.
Il n'a aucun avis sur votre interface, et il n'en produit aucune.</p>
<p>Vous décrivez des <b>entités</b>, des <b>acteurs</b> et des <b>règles</b>. Le
compilateur en dérive le schéma SQL, les routes, l'authentification, le contrôle
d'accès au niveau de l'enregistrement — et un <b>contrat frontend</b> qui décrit
ce que le backend fait vraiment. Une IA, une équipe ou un client mobile
construisent l'interface contre ce contrat.</p>
<div class="note"><p><b>Rien n'est deviné.</b> Le dialogue, la validation et la
génération sont entièrement déterministes : même spec, mêmes octets. Une règle
sans effet est refusée à la compilation plutôt qu'ignorée en silence, et une
règle qui désigne un champ inexistant aussi — une contrainte à laquelle rien ne
correspond laisse croire à une protection qui n'existe pas.</p></div>
<h3>Ce que vous récupérez</h3>
<ul>
<li><code>app.py</code> — l'API FastAPI complète, comptes et sessions compris.</li>
<li><code>schema.sql</code> — le schéma, avec ses index et ses clés étrangères.</li>
<li><code>frontend_contract.json</code> et <code>FRONTEND_PROMPT.md</code> — le contrat, et le brief qui va avec.</li>
<li><code>manage.py</code> — la création des comptes privilégiés, hors ligne.</li>
<li><code>Dockerfile</code>, <code>serve.py</code> — de quoi le mettre en ligne.</li>
<li><code>DESIGN_SYSTEM.md</code>, <code>DESIGN_SPEC.md</code> — le système de design
et la direction retenue, pour que l'IA d'interface ne réinvente pas la palette.</li>
<li><code>ASSET_MANIFEST.json</code> — ce que le site doit fournir, et qui sert de preuve.</li>
</ul>"""),

        ("demarrer", "Démarrer", "3 étapes", f"""
<h2>Trois étapes</h2>
<p class="lede">Depuis cette page, sans rien installer — en répondant au
dialogue guidé ou en apportant votre spec.</p>
<div class="steps">
<article class="card step"><span class="step-no">01 / ÉCRIRE</span>
<h3>Répondez ou partez d'un exemple</h3><p>Le panneau Dialogue guidé pose les
mêmes questions que <code>monl</code>. Le studio propose aussi quatre specs
réelles, du plus simple au plus complet.</p></article>
<article class="card step"><span class="step-no">02 / VÉRIFIER</span>
<h3>Validez</h3><p>Le vrai parseur et le vrai audit répondent. Les erreurs nomment
la ligne et disent quoi corriger.</p></article>
<article class="card step"><span class="step-no">03 / COMPILER</span>
<h3>Récupérez l'archive</h3><p>Backend, schéma, contrat et instructions. Le secret
JWT n'y est pas : il naît au premier démarrage, chez vous.</p></article>
</div>
<h3>Une spécification complète</h3>
<pre class="codeblock"><code>{SPEC_EXEMPLE}</code></pre>
<h3>Puis, en local</h3>
<pre class="codeblock"><code>unzip monl-backend-*.zip -d carnet &amp;&amp; cd carnet
pip install -r requirements.txt
python3 -m uvicorn app:app --port 8000
<span class="cm"># la documentation OpenAPI du backend : http://127.0.0.1:8000/docs</span></code></pre>"""),

        ("dsl", "Référence DSL", f"{len(TYPES)} types", f"""
<h2>Écrire une spécification</h2>
<p class="lede">Cinq blocs suffisent : <code>app</code>, <code>entity</code>,
<code>actor</code>, <code>relation</code>, <code>workflow</code>. Les
<code>rule</code> ajoutent le comportement.</p>
<h3>Les types de champ</h3>
<div class="tablewrap"><table class="grid"><thead><tr><th>Type</th><th>Quand l'employer</th></tr></thead><tbody>{types}</tbody></table></div>
<h3>Contrôle d'accès</h3>
<p>Il s'exprime au niveau de l'enregistrement, <b>lecture comprise</b> — c'est
là que le contrôle d'accès écrit à la main se trompe le plus souvent.</p>
{_tableau(("Règle", "Effet"), REGLES_ACCES)}
<h3>Contraintes de champ</h3>
<p>Appliquées, pas seulement déclarées : elles répondent 422 ou 409 avant
d'écrire quoi que ce soit.</p>
{_tableau(("Règle", "Effet"), REGLES_CHAMPS)}
<h3>Champs peuplés par le serveur</h3>
<p>Tous disparaissent des corps de requête, création <b>et</b> modification.
Un champ que le client peut écrire est un champ qu'il peut négocier.</p>
{_tableau(("Règle", "Effet"), REGLES_SERVEUR)}
<h3>Compteurs, stock et encaissement</h3>
{_tableau(("Règle", "Effet"), REGLES_COMMERCE)}
<h3>Contenu, comptes et démonstration</h3>
{_tableau(("Bloc", "Rôle"), CONTENU)}"""),

        ("api", "API HTTP", f"{len(ROUTES_API)} routes", f"""
<h2>L'API de la plateforme</h2>
<p class="lede">Tout ce que fait la console passe par ces routes : rien n'est
réservé à l'interface.</p>
<div class="tablewrap"><table class="grid"><thead><tr><th>Route</th><th>Effet</th></tr></thead><tbody>{routes}</tbody></table></div>
<h3>Compiler en une commande</h3>
<pre class="codeblock"><code><span class="cm"># une fois : créer le compte et conserver la session</span>
curl -c monl.cookies -X POST http://127.0.0.1:8022/api/auth/register \\
  -H 'Content-Type: application/json' \\
  -d '{{"email":"vous@example.com","password":"une-phrase-secrete"}}'

curl -b monl.cookies -X POST http://127.0.0.1:8022/api/compile \\
  -H 'Content-Type: application/json' \\
  -d "$(jq -Rs '{{spec: .}}' ma-spec.ml)"</code></pre>
<div class="note"><p>Une spécification est bornée à <b>256 ko</b>. Aucun chemin de
sortie fourni par le client n'est accepté : chaque projet reçoit un identifiant
opaque, et une compilation qui échoue ne laisse aucun projet partiel visible.</p></div>
<p class="muted">La documentation développeur est servie sur <a href="/docs">/docs</a>,
l’explorateur interactif sur <a href="/api-docs">/api-docs</a>
et <a href="/openapi.json">/openapi.json</a>.</p>"""),

        ("mcp", "Serveur MCP", f"{len(OUTILS_MCP)} outils", f"""
<h2>Pour les agents</h2>
<p class="lede">Le même pipeline, exposé en MCP. Un agent valide et compile sans
installer le dépôt — et sans qu'un second générateur existe quelque part.</p>
<div class="tablewrap"><table class="grid"><thead><tr><th>Outil</th><th>Effet</th></tr></thead><tbody>{outils}</tbody></table></div>
<h3>En local, par stdio</h3>
<pre class="codeblock"><code>{{
  "mcpServers": {{
    "monl": {{
      "command": "monl-mcp"
    }}
  }}
}}</code></pre>
<h3>Ou en HTTP</h3>
<pre class="codeblock"><code>curl -s -X POST http://127.0.0.1:8022/mcp \\
  -H 'Content-Type: application/json' \\
  -H 'Authorization: Bearer monl_VOTRE_CLE' \\
  -d '{{"jsonrpc":"2.0","id":1,"method":"tools/list"}}'</code></pre>
<div class="note"><p><b>Clés par utilisateur :</b> créez la clé dans votre compte.
Elle n'est affichée qu'une fois ; Monl n'en conserve que l'empreinte et permet
sa révocation. Le client MCP la transmet avec
<code>Authorization: Bearer monl_…</code>.</p></div>"""),

        ("limites", "Limites", "", f"""
<h2>Ce que cette plateforme ne fait pas</h2>
<p class="lede">Énoncé plutôt que découvert en cours de route.</p>
<div class="tablewrap"><table class="grid"><thead><tr><th>Limite</th><th>Pourquoi, et le contournement</th></tr></thead><tbody>{limites}</tbody></table></div>
<h3>Pour aller plus loin</h3>
<p>Le compilateur en local ouvre le dialogue guidé, les assets, le contenu en CSV
et la reconstruction d'interface par IA :</p>
<pre class="codeblock"><code>pip install monl-compiler
monl                      <span class="cm"># dialogue guidé : spec + backend + contrat</span>
monl run MonProjet        <span class="cm"># cohérence, smoke test, puis lancement</span></code></pre>""")
    ]


def _compteur(valeur: str) -> str:
    """Le compteur du sommaire, hors f-string : une f-string ne peut pas
    contenir de barre oblique inverse avant Python 3.12, et la CI compile
    encore en 3.10."""
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
<nav class="toc" aria-label="Sommaire du guide">
<h2>Guide</h2>
<ol>{toc}</ol>
</nav>
<article>{corps}</article>
</div>"""
    return page(
        title="Guide — MONL",
        description="Écrire une spécification monl : types, règles d'accès, "
                    "contraintes, API HTTP et serveur MCP.",
        body=body,
        active="guide",
        scripts=SCRIPT,
        extra_css=EXTRA_CSS,
    )
