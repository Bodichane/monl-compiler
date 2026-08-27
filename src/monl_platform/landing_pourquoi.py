"""Les trois sections que la page d'accueil ne portait pas.

Le site expliquait CE QUE monl fait sans jamais répondre aux trois questions
qu'un visiteur pose vraiment : pourquoi celui-ci plutôt qu'un autre, en quoi
il diffère de ce qu'il connaît déjà, et faut-il choisir entre les deux.

**Aucune affirmation inventée.** Chaque exploit cité ci-dessous a été mesuré
sur un vrai serveur et porte son point de `docs/design_decisions.md` ; la
combinaison avec un PostgreSQL managé est éprouvée par
`tests/test_postgresql.py` contre un vrai serveur. Une page de comparaison qui
force le trait est une page qu'on cesse de croire à la première vérification —
et la comparaison est écrite pour être JUSTE, pas pour gagner : Supabase et
monl ne répondent pas à la même question.

Ce module vit à côté de `landing.py` parce que ce dernier atteignait déjà son
plafond de lignes ; la découpe suit celle du reste du paquet.
"""

from __future__ import annotations

from .theme import icon

# ---------------------------------------------------------------------------
# Contenu
# ---------------------------------------------------------------------------

# Trois écritures que le client tentait, et ce que le compilateur en fait.
# Chacune vient d'un défaut RÉEL, trouvé sur un serveur en marche — jamais en
# relisant du code. Les montants sont ceux qui ont été mesurés.
REFUS = [
    {
        "titre": "Le prix venait du navigateur",
        "attaque": 'POST /commande\n{ "total": 0.01 }',
        "avant": "La commande était enregistrée à un centime, puis encaissée "
                 "pour ce montant.",
        "regle": "rule Ligne.sousTotal derivedFrom Produit.prix by quantite",
        "apres": "Le champ disparaît du corps de requête. Le serveur le calcule "
                 "depuis la ligne liée, à la création ET à la modification.",
        "point": "points 77 et 78",
    },
    {
        "titre": "On commandait cinquante paires sur douze",
        "attaque": 'POST /ligne\n{ "quantite": 50 }',
        "avant": "Le paiement passait. Le stock ne bougeait pas.",
        "regle": "rule Ligne.Create decrements Produit.stock by quantite",
        "apres": "Une seule instruction SQL porte la condition et l'écriture : "
                 "deux commandes simultanées ne peuvent pas lire le même stock. "
                 "409 si le plancher est franchi.",
        "point": "point 86",
    },
    {
        "titre": "Une commande payée acceptait encore des articles",
        "attaque": 'POST /ligne\n{ "commande": 12, "produit": 7 }',
        "avant": "Réglée 89 €, la commande remontait à 238 € — et le "
                 "back-office affichait « Payée » en face d'un montant que "
                 "personne n'avait versé.",
        "regle": "rule Commande.total payable",
        "apres": "Cinq portes se ferment, pas une : le total ne se modifie pas "
                 "par la commande mais par la LIGNE.",
        "point": "point 91",
    },
]

# La comparaison. Chaque ligne est un FAIT vérifiable des deux côtés, jamais un
# jugement : « plus simple », « plus moderne » et « plus sûr » n'ont pas leur
# place ici. Le lecteur tranche.
COMPARAISON = [
    ("Ce que vous recevez",
     "Un service hébergé : base, API, authentification, stockage.",
     "Du code source — <code>app.py</code>, <code>schema.sql</code>, "
     "<code>manage.py</code> — que vous exécutez où vous voulez."),
    ("Où vivent les droits",
     "Des politiques <abbr title=\"Row Level Security\">RLS</abbr> écrites en "
     "SQL, table par table, et tenues à jour à la main.",
     "Déclarés une fois dans la spec. La compilation ÉCHOUE si deux règles se "
     "contredisent."),
    ("Les invariants métier",
     "Stock, totaux, états : à écrire en triggers, en fonctions, ou dans "
     "l'application appelante.",
     "Compilés dans les routes elles-mêmes, dans la transaction de "
     "l'écriture."),
    ("Ce que le frontend sait",
     "Le schéma de la base, via le client généré. Les droits restent à "
     "deviner.",
     "Un contrat explicite : routes, champs, actions, acteurs autorisés, "
     "champs en lecture seule."),
    ("Le jour où vous partez",
     "L'API et les politiques sont celles du service.",
     "L'archive tourne seule. Aucun composant monl à l'exécution."),
    ("Ce qu'il n'apporte pas",
     "—",
     "Ni hébergement, ni temps réel, ni stockage de fichiers managé, ni "
     "tableau de bord d'administration hébergé."),
]

# Trois montages réels. Le premier est ÉPROUVÉ : `tests/test_postgresql.py`
# démarre les artefacts générés contre un vrai PostgreSQL et fait de vrais
# appels. Les deux autres sont des usages du contrat, pas des intégrations —
# la nuance est écrite, pour ne rien promettre qui ne soit vérifié.
MONTAGES = [
    {
        "titre": "Le Postgres est managé, les règles sont compilées",
        "texte": "Le backend généré lit <code>MONL_DATABASE_URL</code>. "
                 "Pointez-le vers le Postgres de votre fournisseur — Supabase, "
                 "Neon, RDS — et gardez ses sauvegardes, ses répliques et sa "
                 "console.",
        "preuve": "Éprouvé : les artefacts générés tournent contre un vrai "
                  "PostgreSQL dans la suite de tests.",
        "code": "MONL_DATABASE_URL=postgresql://…  python3 -m uvicorn app:app",
        "etat": "verifie",
    },
    {
        "titre": "Le contrat nourrit le générateur d'interface",
        "texte": "<code>frontend_contract.json</code> énumère les routes, les "
                 "champs acceptés et les acteurs autorisés. Un outil de "
                 "génération d'UI reçoit la liste au lieu de l'inventer.",
        "preuve": "Le contrat décrit ce que le backend fait vraiment, pas ce "
                  "que la spec déclare : un champ calculé par le serveur en "
                  "sort.",
        "code": "monl frontend --provider …   ·   monl import",
        "etat": "verifie",
    },
    {
        "titre": "Ce que monl laisse à côté",
        "texte": "Fichiers volumineux, temps réel, envoi de courriel : monl "
                 "n'en fait rien et ne prétend pas le contraire. Ces briques "
                 "restent chez votre fournisseur.",
        "preuve": "Un backend monl ne fait AUCUN appel réseau, hormis "
                  "l'encaissement quand vous le déclarez.",
        "code": None,
        "etat": "limite",
    },
]


# ---------------------------------------------------------------------------
# Présentation
# ---------------------------------------------------------------------------

# Les motifs empruntés aux bibliothèques de référence sont TRANSPOSÉS, jamais
# copiés : la plateforme sert du HTML sans build, sans React et sans Motion.
# Ce qui traverse, c'est la mécanique — la ligne de comparaison à pastilles
# d'état, et l'ouverture par `grid-template-rows: 0fr -> 1fr`, qui anime une
# hauteur inconnue sans une ligne de JavaScript.
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
.refus-body {
  display:grid; grid-template-columns:1fr 1fr; gap:1px;
  background:var(--line); border-top:1px solid var(--line);
}
.refus-body > div { background:var(--surface); padding:20px; }
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
.montage pre { margin:auto 0 0; background:var(--code-bg); color:var(--code-ink); border-radius:var(--radius); padding:12px 14px; overflow-x:auto; font:500 12.5px/1.6 var(--mono); }
.etat { display:inline-flex; align-items:center; gap:7px; font:600 11px/1 var(--mono); letter-spacing:.07em; text-transform:uppercase; }
.etat.verifie { color:var(--accent); }
.etat.limite { color:var(--muted); }
.etat .icon { width:14px; height:14px; }
@media(max-width:900px){
  .montages{grid-template-columns:1fr}
  .compare-row{grid-template-columns:1fr}
  .refus-body{grid-template-columns:1fr}
}
@media(prefers-reduced-motion:reduce){
  .refus .fold, .refus summary .chev { transition:none; }
}
"""


def _refus(item: dict, index: int) -> str:
    """Une tentative, repliée. Ouverte, le pourquoi et le comment."""
    return f"""<details data-reveal style="--reveal-delay:{index * 60}ms">
<summary><span class="tag-refus">refusé</span>{item['titre']}
<span class="chev">{icon('arrow')}</span></summary>
<div class="fold"><div><div class="refus-body">
<div><h4>Ce que le client envoyait</h4>
<pre class="codeblock"><code>{item['attaque']}</code></pre>
<p>{item['avant']}</p></div>
<div><h4>La règle qui ferme</h4>
<pre class="codeblock"><code>{item['regle']}</code></pre>
<p>{item['apres']}</p></div>
</div><p class="refus-src">Mesuré sur un serveur réel — {item['point']} de
<code>docs/design_decisions.md</code>.</p></div></div>
</details>"""


def _ligne(axe: str, eux: str, nous: str) -> str:
    return (f'<div class="compare-row"><div class="axis">{axe}</div>'
            f'<div class="them">{eux}</div><div class="us">{nous}</div></div>')


def _montage(item: dict, index: int) -> str:
    libelle = ("vérifié par les tests" if item["etat"] == "verifie"
               else "limite énoncée")
    symbole = "check" if item["etat"] == "verifie" else "shield"
    code = (f'<pre><code>{item["code"]}</code></pre>' if item["code"] else "")
    return f"""<article class="montage" data-reveal style="--reveal-delay:{index * 70}ms">
<span class="etat {item['etat']}">{icon(symbole)}{libelle}</span>
<h3>{item['titre']}</h3><p>{item['texte']}</p>
<p class="muted" style="font-size:13.5px">{item['preuve']}</p>{code}</article>"""


SECTIONS = f"""
<section class="shell section" aria-labelledby="pourquoi-title">
<div class="section-head" data-reveal><span class="eyebrow">Pourquoi monl</span>
<h2 id="pourquoi-title">Trois écritures que le client tentait. Trois refus compilés.</h2>
<p>Aucune n'a été trouvée en relisant du code : chacune vient d'un serveur en
marche, et chacune a coûté quelque chose de réel — un article vendu à un
centime, un stock qui ne bougeait pas, une commande qui grossissait après
paiement.</p></div>
<div class="refus">{"".join(_refus(r, i) for i, r in enumerate(REFUS))}</div>
</section>

<section class="band"><div class="shell section" aria-labelledby="compare-title">
<div class="section-head" data-reveal><span class="eyebrow">monl et les plateformes</span>
<h2 id="compare-title">Supabase héberge et exécute. Monl compile et refuse.</h2>
<p>Les deux ne répondent pas à la même question, et le tableau est écrit pour
être juste plutôt que pour gagner : la dernière ligne dit ce que monl
n'apporte pas.</p></div>
<div class="compare" data-reveal>
<div class="compare-row head"><div>&nbsp;</div>
<div class="who"><span class="dot them"></span>Une plateforme managée</div>
<div class="who"><span class="dot us"></span>monl compiler</div></div>
{"".join(_ligne(*ligne) for ligne in COMPARAISON)}
</div></div></section>

<section class="shell section" aria-labelledby="ensemble-title">
<div class="section-head" data-reveal><span class="eyebrow">Les deux ensemble</span>
<h2 id="ensemble-title">Le choix n'est pas « l'un ou l'autre ».</h2>
<p>Monl produit un backend qui parle PostgreSQL. Le vôtre peut être celui d'un
service managé — vous gardez sa console, ses sauvegardes et ses répliques.</p></div>
<div class="montages">{"".join(_montage(m, i) for i, m in enumerate(MONTAGES))}</div>
</section>
"""
