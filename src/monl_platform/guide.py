"""Le guide servi sur `/guide` : ce que la plateforme doit expliquer.

Une plateforme qui accepte une spécification doit dire comment on l'écrit,
sinon elle ne s'adresse qu'à ceux qui connaissent déjà le dépôt.

Le contenu est structuré en DONNÉES (`TYPES`, `REGLES_*`, `ROUTES_API`,
`OUTILS_MCP`) plutôt qu'en HTML figé, pour une raison précise : une
documentation ne peut pas se contenter d'être écrite, il faut qu'elle
puisse être CONFRONTÉE. `tests/test_platform_guide.py` compare les types à
la grammaire Lark, les routes à celles que FastAPI a réellement montées et
les outils à ceux que le serveur MCP déclare. Une doc qui ment est pire
qu'une doc absente : elle envoie écrire une spec que le compilateur
refusera.
"""

from __future__ import annotations

from .theme import page

# Les douze types de la grammaire (`TYPE` dans src/monl/parser.py). Un test
# refuse toute divergence, dans les deux sens.
TYPES: list[tuple[str, str]] = [
    ("String", "Texte court sur une ligne : un nom, une référence, une catégorie."),
    ("Text", "Texte long, multi-lignes : une description, un message."),
    ("Integer", "Nombre entier : un stock, une quantité, un compteur."),
    ("Float", "Nombre à virgule, pour ce qui n'est pas un montant."),
    ("Boolean", "Vrai ou faux."),
    ("Date", "Un jour, sans heure."),
    ("DateTime", "Un instant. Le type qu'exige <code>timestamp</code>."),
    ("Email", "Adresse électronique."),
    ("UUID", "Identifiant technique. Pour un numéro qu'un humain lit et dicte, "
             "préférez <code>numbered</code>."),
    ("Money", "Un montant. Distinct de <code>Float</code> : c'est lui que "
              "<code>payable</code> et <code>sumOf</code> attendent."),
    ("Image", "Un fichier LOCAL, déclaré dans le bloc <code>assets</code> et "
              "vérifié présent à la compilation. Indisponible sur cette "
              "plateforme, qui n'accepte aucun téléversement."),
    ("Upload", "Un fichier déposé par le client à l'exécution."),
]

REGLES_ACCES: list[tuple[str, str]] = [
    ("rule Entite.Action ownedBy Acteur",
     "Seul le propriétaire agit. Le filtrage couvre <b>aussi la lecture</b> — "
     "liste et accès direct. La colonne de propriété est peuplée depuis le "
     "jeton à la création, jamais fournie par le client."),
    ("rule Ligne.Action ownedBy Commande",
     "Propriété <b>transitive</b> : cette ligne appartient à qui possède sa "
     "commande. La chaîne doit remonter jusqu'à un compte."),
    ("rule Entite.Action public",
     "Retire l'authentification d'une action précise. Une galerie se lit sans "
     "compte ; l'écriture reste fermée."),
    ("rule Article.Read publicWhen statut \"publie\"",
     "Lecture publique <b>sous condition</b> : liste filtrée, détail en 404. "
     "Appliqué côté API — un contenu masqué ne reste pas lisible par son URL."),
    ("rule Message.Read accessibleBy expediteur_id, destinataire_id",
     "Réservé aux parties que l'enregistrement désigne : c'est la messagerie "
     "privée. Au moins deux colonnes, sinon <code>ownedBy</code> suffit."),
    ("rule Entite.Action sharedBy Role, Autre",
     "Ouvre la même route à plusieurs rôles. Posé sur une action déjà régie "
     "par <code>ownedBy</code> ou <code>accessibleBy</code>, il nomme le "
     "<b>superviseur</b> : il voit et modifie tout, les autres restent chez eux."),
    ("rule Vote.Create oncePer Participant, Entree",
     "Un compte n'agit qu'une fois par cible. L'unicité tient à un index "
     "composite en base, jamais à une vérification applicative — c'est lui qui "
     "protège aussi deux requêtes simultanées."),
    ("rule Commande.Create requiresOwn Fiche",
     "L'appelant doit déjà posséder une fiche pour créer ceci. Répond 409 en "
     "disant quoi créer d'abord : une commande qu'on ne peut attribuer à "
     "personne est inexpédiable."),
]

REGLES_CHAMPS: list[tuple[str, str]] = [
    ("rule Produit.prix min 0",
     "Borne d'entrée, <b>422 avant tout INSERT</b>. Valeur sur les nombres, "
     "longueur sur les textes."),
    ("rule Produit.nom max 120", "La borne haute, même mécanique."),
    ("rule Membre.pseudo unique",
     "Index unique en base : un doublon répond 409, à la création comme à la "
     "modification."),
    ("rule Produit.nom required",
     "Assertion vérifiée : le champ doit exister. Une règle qui désigne un "
     "champ inexistant fait échouer la compilation."),
    ("rule Commande.statut oneOf \"panier\", \"expediee\"",
     "Une valeur parmi une liste, sur un champ texte. Le message d'erreur "
     "énumère les valeurs permises, et le contrat demande un menu déroulant."),
]

REGLES_SERVEUR: list[tuple[str, str]] = [
    ("rule Message.auteur generated",
     "Le serveur écrit un pseudonyme stable par compte. Le champ disparaît du "
     "corps de requête : un champ libre ne garantit aucune identité."),
    ("rule Commande.passeeLe timestamp",
     "Instant de création, ISO 8601 UTC, écrit une fois. Absent des corps de "
     "requête — création <b>et</b> modification : une date qu'on se donne "
     "à soi-même n'atteste de rien."),
    ("rule Commande.reference numbered \"CMD-{YYYY}-{NNNN}\"",
     "Le numéro qu'un humain lit et dicte. Le compteur vit dans une table "
     "système : un numéro n'est jamais réattribué, même après suppression."),
    ("rule Ligne.sousTotal derivedFrom Produit.prix by quantite",
     "Calculé depuis une ligne liée, et <b>recalculé</b> à la modification. "
     "Sans lui, le client écrit le montant qu'on va lui facturer."),
    ("rule Commande.total sumOf Ligne.sousTotal",
     "Somme des lignes enfants, recalculée à chaque écriture — création, "
     "modification <b>et suppression</b>. Jamais ajustée par addition : une "
     "somme qu'on ajuste se désynchronise."),
    ("rule Membre.email hidden",
     "Retiré de toutes les réponses de lecture, pour tout le monde. Reste en "
     "base et reste modifiable."),
    ("rule Message.jaimes categorized: \"discret\" below 10, \"viral\" otherwise",
     "Remplace un nombre par un libellé à la lecture. Le dernier palier est "
     "toujours <code>otherwise</code> : la couverture est totale."),
]

REGLES_COMMERCE: list[tuple[str, str]] = [
    ("rule Ligne.Create decrements Produit.stock by quantite",
     "Décompte <b>la quantité demandée</b>. Un <code>min 0</code> déclaré sur "
     "le stock arme la vérification de disponibilité : sans lui, un compteur "
     "garde le droit de passer sous zéro. Rendu à la suppression."),
    ("rule Jaime.Create increments Message.jaimes by 1",
     "Le symétrique, pour les compteurs."),
    ("rule Commande.total payable",
     "Ouvre <code>POST /commande/{id}/paiement</code> et "
     "<code>POST /paiement/webhook</code>. Le montant est relu <b>en base</b> "
     "à chaque appel — la route n'accepte aucun corps de requête. Exige un "
     "montant calculé par le serveur : un total que le payeur peut écrire "
     "fait échouer la compilation."),
    ("rule Commande.statut \"annulee\" releases Ligne",
     "Atteindre cette valeur rend le stock, une seule fois, et l'état devient "
     "terminal."),
    ("rule Commande.statut writableAfterPayment Vendeur",
     "Un enregistrement réglé se fige. Cette règle rouvre <b>un</b> champ, par "
     "une route dédiée réservée au rôle nommé — jamais au propriétaire."),
]

CONTENU: list[tuple[str, str]] = [
    ("seed Entite", "Jeu de démonstration, écrit une seule fois et seulement "
     "dans une table vide. Une vitrine vide ne se juge pas."),
    ("seed Enfant for Parent.champ \"valeur\"",
     "Rattache l'enfant en désignant son parent par une <b>valeur</b>, jamais "
     "par un rang : un numéro ne se lit pas et se décale à la première insertion."),
    ("landing / brief", "Ce que fait l'application, en une phrase. C'est le "
     "point de départ du brief d'interface."),
    ("section \"Titre\": \"Texte\"",
     "Une rubrique éditoriale. Le séparateur <code>¶</code> y découpe des "
     "paragraphes, la grammaire interdisant le saut de ligne dans une chaîne."),
    ("question \"Q\": \"R\"", "Un couple de FAQ. L'ordre déclaré est conservé."),
    ("capability auth / identifier: email, phone",
     "Contraint la <b>forme</b> de l'identifiant de compte, et surtout le "
     "normalise : sans forme canonique, une majuscule suffit à créer un "
     "second compte. <code>phone_prefix: \"+229\"</code> rend « 97… » et "
     "« +22997… » équivalents."),
    ("actor Client selfRegister",
     "Seuls les rôles ainsi marqués peuvent s'inscrire par "
     "<code>POST /register</code>. Les autres se provisionnent hors ligne avec "
     "le <code>manage.py</code> généré — laisser choisir son rôle à "
     "l'inscription serait une élévation de privilège en un appel HTTP."),
]

ROUTES_API: list[tuple[str, str, str]] = [
    ("GET", "/health", "État du service."),
    ("GET", "/ready", "Disponibilité du stockage persistant."),
    ("GET", "/api/version", "Version du compilateur et du contrat frontend."),
    ("GET", "/api/templates", "Les dix modèles métier du dialogue guidé."),
    ("GET", "/api/examples", "Le catalogue des spécifications d'exemple."),
    ("GET", "/api/examples/{example_id}", "La spécification d'un exemple, en texte."),
    ("POST", "/api/auth/register", "Crée un compte et ouvre une session."),
    ("POST", "/api/auth/login", "Ouvre une session avec email et mot de passe."),
    ("POST", "/api/auth/logout", "Révoque la session du navigateur."),
    ("DELETE", "/api/auth/account", "Supprime le compte, ses clés et ses projets. Exige le mot de passe dans le corps, et l'effacement est irréversible."),
    ("GET", "/api/auth/me", "Compte de la session active."),
    ("GET", "/api/projects", "Projets du compte connecté."),
    ("DELETE", "/api/projects/{project_id}", "Supprime un projet et son archive."),
    ("GET", "/api/keys", "Clés MCP du compte, sans leur secret."),
    ("POST", "/api/keys", "Crée une clé MCP affichée une seule fois."),
    ("DELETE", "/api/keys/{key_id}", "Révoque définitivement une clé MCP."),
    ("POST", "/api/validate", "Parseur et audit réels, sans rien écrire."),
    ("POST", "/api/compile", "Compile et rend un manifeste (201)."),
    ("GET", "/api/projects/{project_id}", "Manifeste et résumé d'une compilation."),
    ("GET", "/api/projects/{project_id}/contract", "Le contrat frontend complet."),
    ("GET", "/api/projects/{project_id}/download", "Archive ZIP, sans le secret JWT."),
    ("GET", "/mcp", "Configuration MCP et gestion des clés d’accès."),
    ("POST", "/mcp", "Transport MCP HTTP, authentifié par clé Bearer."),
]

OUTILS_MCP: list[tuple[str, str]] = [
    ("monl_list_templates", "Découvrir les modèles métier."),
    ("monl_validate_spec", "Les erreurs du vrai parseur et de l'audit."),
    ("monl_compile_backend", "Compiler, et recevoir l'identifiant du projet."),
    ("monl_inspect_contract", "Lire le manifeste et le contrat complet."),
]

LIMITES: list[tuple[str, str]] = [
    ("Aucun téléversement",
     "Une spec déclarant un bloc <code>assets</code> ou un champ "
     "<code>Image</code> est refusée : le compilateur vérifie que le fichier "
     "existe, et rien ici ne permet de le déposer. Utilisez "
     "<code>String</code> pour une adresse distante, ou le compilateur en "
     "local avec <code>monl assets add</code>."),
    ("Pas de dialogue guidé",
     "Le dialogue qui produit une spec par questions est une commande locale "
     "(<code>monl</code>). La plateforme part d'une spécification déjà écrite."),
    ("Rétention bornée",
     "Les projets vivent dans le stockage persistant puis expirent après "
     "30 jours par défaut. Téléchargez l'archive avant cette échéance."),
    ("Compilations isolées et bornées",
     "Chaque compilation tourne dans un sous-processus limité en durée, CPU, "
     "mémoire et fichiers. Les quotas sont persistés et partagés entre workers."),
    ("Le secret ne voyage pas",
     "L'archive ne contient jamais <code>.jwt_secret</code> : le backend en "
     "génère un au premier démarrage, sur la machine qui l'héberge."),
]

EXTRA_CSS = """
.doc { display: grid; grid-template-columns: 248px minmax(0, 1fr); gap: var(--space-7);
       align-items: start; padding-block: var(--space-7); }
.toc { position: sticky; top: 88px; font-size: 15px; }
.toc h2 { font: 600 12px var(--mono); letter-spacing: .1em; text-transform: uppercase;
          color: var(--muted); margin-bottom: var(--space-3); }
.toc ol { list-style: none; margin: 0; padding: 0; }
.toc a { display: flex; justify-content: space-between; gap: var(--space-3);
         text-decoration: none; color: var(--muted); padding: 7px 10px;
         border-radius: 9px; min-height: 44px; align-items: center;
         transition: background .18s ease, color .18s ease; }
.toc a:hover { background: var(--surface-2); color: var(--ink); }
.toc a.active { background: var(--soft); color: var(--ink); font-weight: 600; }
.toc .count { font: 12px var(--mono); opacity: .7; }
.doc article > section { padding-bottom: var(--space-7); scroll-margin-top: 88px; }
.doc h2 { font-size: clamp(24px, 3vw, 32px); margin-bottom: var(--space-3); }
.doc h3 { font-size: 19px; margin: var(--space-6) 0 var(--space-3); }
.doc p, .doc li { color: var(--ink); }
.doc .lede { color: var(--muted); font-size: 17px; }
.doc ul { padding-left: 1.15rem; margin: 0 0 var(--space-4); }
.doc li { margin-bottom: var(--space-2); }
.steps { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
         gap: var(--space-3); margin-bottom: var(--space-5); }
.step-no { font: 600 12px var(--mono); color: var(--brand); }
.step h3 { margin: var(--space-3) 0 var(--space-2); font-size: 17px; }
.step p { margin: 0; color: var(--muted); font-size: 15px; }
.note { border-left: 3px solid var(--brand); background: var(--soft);
        padding: var(--space-4) var(--space-5); border-radius: 0 var(--radius) var(--radius) 0;
        margin-bottom: var(--space-5); }
.note p:last-child { margin-bottom: 0; }
.method { font: 600 12px var(--mono); color: var(--brand); }
@media (max-width: 900px) {
  .doc { grid-template-columns: 1fr; gap: var(--space-5); }
  .toc { position: static; border-bottom: 1px solid var(--line); padding-bottom: var(--space-4); }
  .toc ol { display: flex; flex-wrap: wrap; gap: var(--space-1); }
}
"""

SCRIPT = """
<script>
(function () {
  var liens = [].slice.call(document.querySelectorAll('.toc a'));
  var cibles = liens.map(function (a) { return document.querySelector(a.getAttribute('href')); });
  function marquer(id) {
    liens.forEach(function (a) { a.classList.toggle('active', a.getAttribute('href') === '#' + id); });
  }
  if ('IntersectionObserver' in window) {
    var observateur = new IntersectionObserver(function (entrees) {
      entrees.forEach(function (e) { if (e.isIntersecting) marquer(e.target.id); });
    }, { rootMargin: '-88px 0px -70% 0px' });
    cibles.forEach(function (c) { if (c) observateur.observe(c); });
  }
  document.querySelectorAll('.codeblock').forEach(function (bloc) {
    var bouton = document.createElement('button');
    bouton.type = 'button';
    bouton.className = 'copy';
    bouton.textContent = 'Copier';
    bouton.addEventListener('click', function () {
      var texte = bloc.querySelector('code') ? bloc.querySelector('code').innerText : bloc.innerText;
      navigator.clipboard.writeText(texte).then(function () {
        bouton.textContent = 'Copié';
        setTimeout(function () { bouton.textContent = 'Copier'; }, 1800);
      }, function () { bouton.textContent = 'Échec'; });
    });
    bloc.appendChild(bouton);
  });
})();
</script>
"""

SPEC_EXEMPLE = """<span class="cm"># Une spécification complète tient en une page.</span>
<span class="kw">app</span> CarnetAtelier

<span class="kw">entity</span> Fiche
    titre: String
    contenu: Text
    statut: String

<span class="kw">actor</span> Auteur selfRegister
<span class="kw">actor</span> Relecteur

<span class="kw">relation</span> Auteur hasMany Fiche

<span class="kw">rule</span> Fiche.titre required
<span class="kw">rule</span> Fiche.statut oneOf "brouillon", "publiee"
<span class="kw">rule</span> Fiche.Read publicWhen statut "publiee"
<span class="kw">rule</span> Fiche.Update ownedBy Auteur
<span class="kw">rule</span> Fiche.Update sharedBy Relecteur

<span class="kw">workflow</span> Ecrire <span class="kw">for</span> Auteur
    Create Fiche
    Read Fiche
    Update Fiche

<span class="kw">workflow</span> Relire <span class="kw">for</span> Relecteur
    Read Fiche
    Update Fiche"""


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
<p class="lede">Depuis cette page, sans rien installer.</p>
<div class="steps">
<article class="card step"><span class="step-no">01 / ÉCRIRE</span>
<h3>Partez d'un exemple</h3><p>Le studio en propose quatre, du plus simple au plus
complet. Chacun compile : ce sont des specs réelles, pas des extraits.</p></article>
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
        title="Guide — monl compiler",
        description="Écrire une spécification monl : types, règles d'accès, "
                    "contraintes, API HTTP et serveur MCP.",
        body=body,
        active="guide",
        scripts=SCRIPT,
        extra_css=EXTRA_CSS,
    )
