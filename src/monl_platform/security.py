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
<section class="shell security-hero"><span class="eyebrow" data-reveal>Sécurité vérifiable</span>
<h1 data-reveal>Les règles sont exécutées, pas suggérées.</h1>
<p class="lede" data-reveal>Monl compile les autorisations et invariants dans le backend. Cette page distingue
ce que le compilateur garantit de ce qui reste sous la responsabilité du déploiement.</p></section>

<section class="shell section"><div class="section-head" data-reveal><span class="eyebrow">Défense en profondeur</span>
<h2>Quatre niveaux issus de la même spécification.</h2></div><div class="security-grid">
<article class="card proof-card" data-reveal><div class="proof-head"><span class="proof-icon">{icon('check')}</span><h2>Refus à la compilation</h2></div>
<p>Une règle impossible n’est jamais ignorée silencieusement.</p><ul><li>Référence à un champ ou acteur absent</li><li>Propriété sans relation exploitable</li>
<li>Paiement sur un montant modifiable par le client</li><li>Combinaisons de permissions contradictoires</li></ul><span class="evidence">Parseur + audit statique</span></article>
<article class="card proof-card" data-reveal style="--reveal-delay:50ms"><div class="proof-head"><span class="proof-icon">{icon('shield')}</span><h2>Contrôle par enregistrement</h2></div>
<p>Les droits sont évalués dans l’API, y compris sur les listes.</p><ul><li><code>ownedBy</code> limite au propriétaire</li><li><code>accessibleBy</code> limite aux parties</li>
<li><code>sharedBy</code> ajoute un rôle superviseur</li><li><code>publicWhen</code> filtre liste et détail</li></ul><span class="evidence">Tests HTTP avec comptes distincts</span></article>
<article class="card proof-card" data-reveal><div class="proof-head"><span class="proof-icon">{icon('package')}</span><h2>Invariants en base</h2></div>
<p>Les contraintes sensibles ne dépendent pas d’un bouton frontend.</p><ul><li>Unicité par index SQL</li><li>Stock décrémenté atomiquement</li>
<li>Montants recalculés côté serveur</li><li>Commandes payées figées</li></ul><span class="evidence">SQLite et PostgreSQL éprouvés</span></article>
<article class="card proof-card" data-reveal style="--reveal-delay:50ms"><div class="proof-head"><span class="proof-icon">{icon('code')}</span><h2>Contrat sans ambiguïté</h2></div>
<p>Le frontend reçoit les mêmes droits que le backend applique.</p><ul><li>Routes publiques et authentifiées</li><li>Champs écrits ou calculés par le serveur</li>
<li>Acteurs autorisés par action</li><li>Forme exacte des réponses d’authentification</li></ul><span class="evidence">frontend_contract.json versionné</span></article>
</div></section>

<section class="band"><div class="shell section"><div class="section-head"><span class="eyebrow">Attaques couvertes</span>
<h2>Ce que la suite essaie réellement de casser.</h2></div><div class="tablewrap"><table class="grid attack-table"><thead><tr><th>Tentative</th><th>Défense attendue</th></tr></thead><tbody>
<tr><td>JWT signé avec une mauvaise clé</td><td>401, identité refusée</td></tr><tr><td>Acteur authentifié mais non autorisé</td><td>403, aucune écriture</td></tr>
<tr><td>Lecture directe d’un objet d’un autre compte</td><td>404, objet non divulgué</td></tr><tr><td>Deux actions simultanées oncePer</td><td>Une seule insertion grâce à l’index</td></tr>
<tr><td>Commande supérieure au stock</td><td>409, stock inchangé</td></tr><tr><td>Montant fourni par le payeur</td><td>Corps ignoré ou règle refusée à la compilation</td></tr>
</tbody></table></div></div></section>

<section class="shell section"><div class="section-head"><span class="eyebrow">Frontière honnête</span><h2>Garanti par Monl ou à configurer par vous.</h2></div>
<div class="boundary"><div class="guaranteed"><h2>Le compilateur garantit</h2><ul><li>Cohérence entre spec, API, SQL et contrat</li><li>Application des permissions déclarées</li>
<li>Secret JWT absent de l’archive</li><li>Sortie reproductible pour une même version</li></ul></div>
<div class="responsibility"><h2>Le déploiement doit garantir</h2><ul><li>HTTPS, sauvegardes et mises à jour</li><li>Protection des variables d’environnement</li>
<li>Clés API MCP, quotas et révocation</li><li>Isolation des workers en multi-utilisateur</li></ul></div></div>
<div style="margin-top:var(--space-5)"><a class="primary" href="/docs#acces">Lire les règles de sécurité {icon('arrow')}</a></div></section>
"""

SECURITY_HTML = page(title="Sécurité — monl compiler",
    description="Garanties, preuves et limites de sécurité du compilateur Monl.",
    body=BODY, active="security", extra_css=EXTRA_CSS)
