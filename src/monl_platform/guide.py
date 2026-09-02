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
    """(ancre, titre court, compteur affiché, contenu HTML)."""
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
        ("frontiere", "Ce que Monl produit", "", """
<h2>Monl compile le backend. L’interface est une étape séparée.</h2>
<p class="lede">Vous écrivez les règles du métier. La compilation produit une API,
une base de données et des garanties serveur. Elle ne rend ni ne sert un site.</p>
<div class="boundary" aria-label="Ce que Monl compile et ce qu'il laisse à l'interface">
<article><span class="step-no">VOUS ÉCRIVEZ</span><h3>Une spec métier</h3>
<p>Entités, acteurs, relations, droits et invariants.</p></article>
<article><span class="step-no">MONL COMPILE</span><h3>Un backend vérifiable</h3>
<p>SQL, API, authentification et contrôle d’accès par enregistrement.</p></article>
<article><span class="step-no">ÉTAPE OPTIONNELLE</span><h3>Une interface est générée ou écrite</h3>
<p>Votre équipe ou <code>monl frontend</code> utilise le contrat et les briefs fournis.</p></article>
</div>
<h3>Contrat, brief et interface : trois choses différentes</h3>
<p>Le <code>frontend_contract.json</code> est une description lisible par une IA,
une équipe web ou une application mobile. Il ne contient ni HTML, ni React, ni
navigation. Il répond simplement à la question : <i>« quelles
opérations cette interface a-t-elle vraiment le droit d’appeler ? »</i></p>
<p><code>FRONTEND_PROMPT.md</code>, <code>DESIGN_SYSTEM.md</code>,
<code>DESIGN_SPEC.md</code> et <code>ASSET_MANIFEST.json</code> sont des
instructions et ressources pour cette étape UI. Un <code>DESIGN_SPEC.md</code>
écrit par l’auteur est prioritaire. Ils ne sont pas l’interface elle-même.</p>
<p>Si vous lancez <code>monl frontend</code>, un agent IA écrit l’interface dans
<code>frontend/</code>, puis Monl la contrôle contre le contrat. Vous pouvez tout
aussi bien faire écrire cette interface par votre équipe ou par une application
mobile : le backend, lui, reste le même.</p>
<div class="note"><p><b>Rien n'est deviné.</b> Le dialogue, la validation et la
génération sont entièrement déterministes : même spec, mêmes octets. Une règle
sans effet est refusée à la compilation plutôt qu'ignorée en silence, et une
règle qui désigne un champ inexistant aussi — une contrainte à laquelle rien ne
correspond laisse croire à une protection qui n'existe pas.</p></div>
<h3>Ce que vous récupérez</h3>
<ul>
<li><code>app.py</code> — l'API FastAPI complète, comptes et sessions compris.</li>
<li><code>schema.sql</code> — le schéma, avec ses index et ses clés étrangères.</li>
<li><code>frontend_contract.json</code> — les routes, champs et droits réellement disponibles.</li>
<li><code>FRONTEND_PROMPT.md</code> — un brief pour l’agent ou l’équipe qui construira l’interface.</li>
<li><code>manage.py</code> — la création des comptes privilégiés, hors ligne.</li>
<li><code>Dockerfile</code>, <code>serve.py</code> — de quoi le mettre en ligne.</li>
<li><code>DESIGN_SYSTEM.md</code>, <code>DESIGN_SPEC.md</code> — les contraintes de
composition et le cahier visuel utilisés lors d’une génération UI optionnelle.</li>
<li><code>ASSET_MANIFEST.json</code> — les visuels attendus et leur contrôle lors de cette même étape.</li>
</ul>"""),

        ("demarrer", "Premier backend", "3 étapes", f"""
<h2>Compilez d’abord un backend réel</h2>
<p class="lede">Partez de cette spec complète, validez-la dans la console, puis
récupérez une archive qui démarre localement. Chaque étape produit un résultat
que vous pouvez contrôler.</p>
<h3>1. Décrivez le métier</h3>
<pre class="codeblock"><code>{SPEC_EXEMPLE}</code></pre>
<p><a class="primary" href="/console">Ouvrir la console et compiler une spec</a></p>
<h3>2. Vérifiez puis compilez</h3>
<p>Le parseur et l’audit signalent les règles impossibles ou incomplètes. Si la
spec est valide, l’archive contient l’API, le schéma SQL et le contrat qui
décrit exactement ses capacités.</p>
<h3>3. Lancez l’archive</h3>
<pre class="codeblock"><code>unzip monl-backend-*.zip -d carnet &amp;&amp; cd carnet
pip install -r requirements.txt
python3 -m uvicorn app:app --port 8000
<span class="cm"># la documentation OpenAPI du backend : http://127.0.0.1:8000/docs</span></code></pre>
<h3>Facultatif : construire une interface ensuite</h3>
<p>Une fois le backend démarré, vous pouvez garder votre propre interface ou
demander à l’étape IA d’en construire une, séparément :</p>
<pre class="codeblock"><code>cd carnet
monl frontend . <span class="cm"># utilise FRONTEND_PROMPT.md et écrit frontend/</span></code></pre>
<p>Cette commande nécessite un fournisseur IA configuré. Elle ne modifie pas la
spec, le schéma, l’API ni le contrat.</p>"""),

        ("dsl", "Lire la référence", "", """
<h2>Quand utiliser la documentation du langage</h2>
<p class="lede">Le guide vous accompagne pour créer et lancer un premier backend.
La documentation est l’endroit où retrouver une syntaxe précise pendant que
vous écrivez votre spec.</p>
<div class="boundary" aria-label="Ce que contient la documentation du langage">
<article><span class="step-no">STRUCTURE</span><h3>Les blocs</h3>
<p><code>app</code>, <code>entity</code>, <code>actor</code>, <code>relation</code>,
<code>workflow</code> et <code>rule</code>.</p></article>
<article><span class="step-no">RÉFÉRENCE</span><h3>Les types et contraintes</h3>
<p>Types de champ, validations, calculs serveur, compteurs et encaissement.</p></article>
<article><span class="step-no">SÉCURITÉ</span><h3>Les droits réellement appliqués</h3>
<p>Lecture, propriété, rôles et autorisations sont décrits à côté de leur syntaxe.</p></article>
</div>
<p><a class="primary" href="/docs">Ouvrir la référence de la spec</a></p>
<p class="muted">Vous cherchez l’API de la plateforme ou le serveur MCP ? Les
sections suivantes les documentent séparément.</p>"""),

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
et la reconstruction d'interface par IA. Il n'est publié sur aucun index de
paquets : on l'installe depuis une copie du dépôt.</p>
<pre class="codeblock"><code>git clone https://github.com/Bodichane/monl-compiler
pip install ./monl-compiler
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
        description="Tutoriel pour compiler un premier backend Monl, utiliser la plateforme et le serveur MCP.",
        body=body,
        active="guide",
        scripts=SCRIPT,
        extra_css=EXTRA_CSS,
    )
