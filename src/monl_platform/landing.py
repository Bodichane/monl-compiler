"""Page de présentation de monl, servie à la racine de la plateforme.

La console est un OUTIL : elle suppose qu'on sait déjà ce que monl fait. Cette
page-ci s'adresse à quelqu'un qui l'ignore, propose une version à installer,
puis conduit à la console.

Registre assumé : un terminal, en thème sombre unique. Le produit est une
ligne de commande, la page ne prétend donc pas être autre chose — et un thème
à moitié tenu serait pire qu'un thème assumé.

Comme la console, la page est ENTIÈREMENT autonome : aucune police web, aucune
image distante, aucun script tiers, et pas même un lien sortant. C'est ce que
vérifie ``tests/test_platform_landing.py``.
"""

from fastapi.responses import HTMLResponse

LANDING_HTML = r'''<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<title>monl — compilateur</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="description" content="monl compile une spécification déclarative en un backend FastAPI complet et scellé. Dialogue guidé, aucune IA, aucun appel réseau.">
<style>
/* ══════════════════════════════════════════════════════════════════════════
   monl — page de présentation.

   Ce qui est emprunté aux bonnes pages produit techniques n'est pas une
   apparence, c'est une MÉTHODE : on montre le produit qui tourne, avec de
   vraies entrées à gauche et de vraies sorties à droite, avant de demander
   quoi que ce soit. Le contenu de la démonstration est produit par le VRAI
   compilateur (voir batir_landing.py) — une démonstration inventée serait
   exactement ce que monl interdit aux sites qu'il produit.

   Deux argiles, et la distinction n'est pas cosmétique :
     --clay      #d97757  →  3,12:1 sur blanc. GROS TEXTE et DÉCOR seulement
                             (AA grand texte demande 3:1, c'est tenu).
     --clay-ink  #b8542f  →  4,83:1 sur blanc. Petit texte, liens, et fond
                             de bouton sous du blanc.
   Confondre les deux rend un bouton illisible : c'est le défaut déjà corrigé
   deux fois sur la version sombre de cette page.
   ══════════════════════════════════════════════════════════════════════════ */

:root {
  --paper:   #ffffff;
  --paper-2: #faf9f7;
  --paper-3: #f2efec;
  --ink:     #1c1917;  /* 17,49:1 */
  --ink-2:   #57534e;  /*  7,63:1 */
  --ink-3:   #78716c;  /*  4,80:1 — le plus clair encore lisible */
  --rule:    #e7e3df;
  --rule-2:  #d6d0ca;
  --clay:     #d97757;
  --clay-ink: #b8542f;
  --wash:     #fdf5f1;

  --sans: ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto,
          Helvetica, Arial, "Liberation Sans", sans-serif;
  --mono: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas,
          "Liberation Mono", monospace;

  --page: 1120px;
  --s1: .25rem; --s2: .5rem;  --s3: .75rem; --s4: 1rem;
  --s5: 1.5rem; --s6: 2.5rem; --s7: 4rem;  --s8: 6rem;
  --r1: 6px; --r2: 10px; --r3: 14px;
}

* { box-sizing: border-box; }
html { -webkit-text-size-adjust: 100%; }
body {
  margin: 0; background: var(--paper); color: var(--ink);
  font-family: var(--sans); font-size: 16px; line-height: 1.6;
  -webkit-font-smoothing: antialiased;
}
a { color: inherit; text-decoration: none; }
h1, h2, h3 { margin: 0; font-weight: 600; letter-spacing: -.022em; }
p, ul { margin: 0; }
:focus-visible { outline: 2px solid var(--clay-ink); outline-offset: 3px; border-radius: 3px; }

.wrap { width: min(var(--page), 100% - 3rem); margin-inline: auto; }
.tag {
  font-family: var(--mono); font-size: .68rem; letter-spacing: .07em;
  text-transform: uppercase; color: var(--ink-3);
}
.tag b { color: var(--clay-ink); font-weight: 600; }
.tag.file { text-transform: none; letter-spacing: .02em; }

/* ────────────────────────────────────────────────────────── navigation ── */
.topline {
  background: var(--ink); color: #f5f5f4; text-align: center;
  font-size: .82rem; padding: var(--s2) var(--s4);
}
.topline a { color: var(--clay); text-decoration: underline; text-underline-offset: 2px; }
nav { border-bottom: 1px solid var(--rule); background: var(--paper);
      position: sticky; top: 0; z-index: 20; }
.nav-in { display: flex; align-items: center; justify-content: space-between;
          gap: var(--s4); min-height: 3.5rem; }
.logo { display: inline-flex; align-items: center; gap: var(--s2); font-weight: 600; }
.logo-mark {
  display: grid; place-items: center; width: 1.5rem; height: 1.5rem;
  border-radius: var(--r1); background: var(--clay-ink); color: #fff;
  font-family: var(--mono); font-size: .78rem; font-weight: 700;
}
/* `.logo span` sans exception repeindrait la pastille : c'est la règle LARGE
   qu'on restreint, jamais la règle précise qu'on renforce. */
.logo span:not(.logo-mark) { color: var(--ink-3); font-weight: 400; }
.nav-links { display: flex; align-items: center; gap: var(--s5); }
.nav-links a { color: var(--ink-2); font-size: .88rem; }
.nav-links a:hover { color: var(--ink); }

.btn {
  display: inline-flex; align-items: center; gap: var(--s2);
  padding: .5rem .95rem; border-radius: var(--r1);
  background: var(--clay-ink); color: #fff; border: 1px solid var(--clay-ink);
  font: inherit; font-size: .87rem; font-weight: 500; cursor: pointer;
}
.btn:hover { background: #9c4526; border-color: #9c4526; }
.nav-links a.btn, .nav-links a.btn:hover { color: #fff; }
.btn.ghost { background: var(--paper); color: var(--ink); border-color: var(--rule-2); }
.btn.ghost:hover { background: var(--paper-2); color: var(--ink); }
.btn.lg { padding: .7rem 1.25rem; font-size: .95rem; }

/* ─────────────────────────────────────────────────────────────── héros ── */
header { padding: var(--s7) 0 var(--s6); text-align: center; }
.pill {
  display: inline-flex; align-items: center; gap: var(--s2);
  padding: .3rem .85rem; border: 1px solid var(--rule-2); border-radius: 999px;
  font-size: .8rem; color: var(--ink-2); background: var(--paper);
}
.pill em { font-style: normal; color: var(--clay-ink); font-weight: 600; }
h1 {
  margin: var(--s5) auto var(--s4); max-width: 17ch;
  font-size: clamp(2.3rem, 6vw, 3.9rem); line-height: 1.06;
  letter-spacing: -.035em; font-weight: 600;
}
/* L'argile vive est admissible ici : à cette taille et à ce gras, AA demande
   3:1 et elle donne 3,12. Elle ne l'est nulle part ailleurs. */
h1 em { font-style: normal; color: var(--clay); }
.lede { max-width: 56ch; margin: 0 auto var(--s5); color: var(--ink-2); font-size: 1.05rem; }
.lede b { color: var(--ink); font-weight: 600; }
.cta { display: flex; gap: var(--s3); justify-content: center; flex-wrap: wrap; }
.meta { margin-top: var(--s4); font-family: var(--mono); font-size: .74rem; color: var(--ink-3); }

/* ═══════════════════════════════════════════════════ la démonstration ══ */
/* Le cœur de la page : ce que vous écrivez à gauche, ce que le compilateur
   en fait à droite. Les deux colonnes viennent d'une vraie compilation. */
.demo { border: 1px solid var(--rule); border-radius: var(--r3); overflow: hidden;
        background: var(--paper); box-shadow: 0 1px 2px rgba(28,25,23,.04),
        0 16px 40px rgba(28,25,23,.06); text-align: left; }
.demo-head {
  display: flex; align-items: center; gap: var(--s3); flex-wrap: wrap;
  padding: var(--s3) var(--s4); border-bottom: 1px solid var(--rule);
  background: var(--paper-2);
}
.tabs { display: flex; gap: var(--s1); flex-wrap: wrap; }
.tab {
  padding: .35rem .8rem; border-radius: var(--r1); border: 1px solid transparent;
  background: transparent; color: var(--ink-2); font: inherit; font-size: .84rem;
  cursor: pointer;
}
.tab:hover { color: var(--ink); }
.tab[aria-selected="true"] {
  background: var(--paper); border-color: var(--rule-2); color: var(--ink); font-weight: 500;
}
.demo-head .tag { margin-left: auto; }

.demo-body { display: grid; grid-template-columns: 1fr 1fr; }
.panel { min-width: 0; }
.panel + .panel { border-left: 1px solid var(--rule); }
.panel-head {
  display: flex; align-items: center; gap: var(--s3);
  padding: .55rem var(--s4); border-bottom: 1px solid var(--rule);
  background: var(--paper);
}
.panel-head .tabs { margin-left: auto; }
.panel-head .tab { padding: .2rem .55rem; font-size: .75rem; }
pre, .out {
  margin: 0; padding: var(--s4); font-family: var(--mono); font-size: .78rem;
  line-height: 1.8; color: var(--ink-2); overflow: auto; height: 23rem;
}
.k { color: var(--clay-ink); font-weight: 500; }
.t { color: #1d4ed8; }
.c { color: var(--ink-3); }
.out ul { list-style: none; padding: 0; }
.out li { white-space: pre; }
.out .m { color: var(--clay-ink); font-weight: 600; }
.out .sys { color: var(--ink-3); }
.demo-foot {
  display: flex; align-items: center; gap: var(--s4); flex-wrap: wrap;
  padding: var(--s3) var(--s4); border-top: 1px solid var(--rule);
  background: var(--paper-2); font-size: .84rem; color: var(--ink-2);
}
.demo-foot b { color: var(--ink); font-family: var(--mono); }
.demo-foot .btn { margin-left: auto; }

/* ────────────────────────────────────────────── rythme des sections ── */
/* Deux sections empilées ADDITIONNENT leurs marges : à 6rem de chaque côté,
   la jointure faisait 192 px de blanc — mesuré, contre 138 px au plus sur la
   page qui a servi de référence. 4rem donne 128. */
section { padding: var(--s7) 0; border-top: 1px solid var(--rule); }
section.alt { background: var(--paper-2); }
.chapter { display: flex; align-items: center; gap: var(--s3); margin-bottom: var(--s4); }
.chapter i { width: 3px; height: 1rem; background: var(--clay); border-radius: 2px; }
h2 { font-size: clamp(1.7rem, 3.3vw, 2.4rem); line-height: 1.14; }
h2 em { font-style: normal; color: var(--clay); }
.intro { color: var(--ink-2); }
/* Le titre à gauche, le chapeau à droite. Alignés en pied, ils remplissent la
   largeur : l'en-tête ne laissait sinon que du blanc sur toute la moitié
   droite, sur un cinquième de la page. */
.sec-head {
  display: grid; grid-template-columns: minmax(0, 1.05fr) minmax(0, 1fr);
  gap: var(--s4) var(--s7); align-items: end; margin-bottom: var(--s6);
}
.sec-head > div:first-child { grid-row: span 2; }
@media (max-width: 900px) {
  .sec-head { grid-template-columns: 1fr; gap: var(--s3); }
  .sec-head > div:first-child { grid-row: auto; }
}

/* verbes de la ligne de commande */
.verbs { border: 1px solid var(--rule); border-radius: var(--r2); overflow: hidden;
         background: var(--paper); }
.verb { display: grid; grid-template-columns: 12rem 1fr; gap: var(--s4);
        padding: var(--s4) var(--s5); border-bottom: 1px solid var(--rule); }
.verb:last-child { border-bottom: 0; }
.verb code { font-family: var(--mono); font-size: .85rem; color: var(--clay-ink);
             background: none; border: 0; padding: 0; font-weight: 500; }
.verb p { color: var(--ink-2); font-size: .93rem; }
.verb p b { color: var(--ink); font-weight: 600; }

code {
  font-family: var(--mono); font-size: .86em; background: var(--paper-3);
  border: 1px solid var(--rule); padding: .08em .34em; border-radius: 4px; color: var(--ink);
}

/* refus */
.refus { list-style: none; display: grid; gap: var(--s3); }
.refus li { border: 1px solid var(--rule); border-left: 3px solid var(--clay);
            border-radius: var(--r2); background: var(--paper); overflow: hidden; }
.refus .quoi { padding: var(--s4) var(--s5); color: var(--ink-2); font-size: .93rem; }
.refus b { color: var(--ink); display: block; margin-bottom: 2px; }
.refus .dit { padding: var(--s3) var(--s5); background: var(--ink); color: #d6d3d1;
              font-family: var(--mono); font-size: .76rem; overflow-x: auto;
              white-space: pre-wrap; }
.refus .dit span { color: #fca5a5; }

/* chiffres */
.stats { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr));
         border: 1px solid var(--rule); border-radius: var(--r2); overflow: hidden;
         background: var(--paper); }
.stat { padding: var(--s4) var(--s5); border-right: 1px solid var(--rule); }
.stat:last-child { border-right: 0; }
.stat b { display: block; font-size: 2rem; letter-spacing: -.03em; font-weight: 600; }
.stat span { display: block; margin-top: var(--s1); color: var(--ink-3); font-size: .85rem; }

/* téléchargement */
.install { display: flex; align-items: center; gap: var(--s3);
           padding: var(--s3) var(--s4); background: var(--ink); border-radius: var(--r2); }
.install code { background: none; border: 0; color: #f5f5f4; padding: 0;
                font-size: .84rem; overflow-x: auto; white-space: nowrap; }
.copy { margin-left: auto; padding: .3rem .6rem; border-radius: var(--r1);
        border: 1px solid #44403c; background: transparent; color: #e7e5e4;
        font-family: var(--mono); font-size: .72rem; cursor: pointer; }
.copy:hover { background: #292524; }
.dl { display: grid; gap: var(--s3); margin-top: var(--s4); }
.dl-item { display: flex; align-items: center; gap: var(--s4); flex-wrap: wrap;
           padding: var(--s4) var(--s5); background: var(--paper);
           border: 1px solid var(--rule); border-radius: var(--r2); }
.dl-item .who { min-width: 0; flex: 1 1 20rem; }
.dl-item .who b { font-family: var(--mono); font-size: .86rem; word-break: break-all; }
.dl-item .who span { display: block; margin-top: 2px; color: var(--ink-3); font-size: .78rem; }
.sha { font-family: var(--mono); font-size: .68rem; color: var(--ink-3); word-break: break-all; }
.hint { margin-top: var(--s4); color: var(--ink-3); font-size: .85rem; }

.close { text-align: center; padding: var(--s6) var(--s5); border: 1px solid var(--rule);
         border-radius: var(--r3); background: var(--paper); }
.close h2 { margin-inline: auto; text-align: center; }
.close p { max-width: 48ch; margin: var(--s3) auto var(--s5); color: var(--ink-2); }

footer { border-top: 1px solid var(--rule); padding: var(--s6) 0 var(--s7); }
.foot { display: flex; flex-wrap: wrap; gap: var(--s4); justify-content: space-between;
        color: var(--ink-3); font-size: .82rem; }

/* L'état caché d'une apparition vit dans une RÈGLE, jamais dans un style en
   ligne : `element.style.opacity = "0"` l'emporte sur n'importe quel
   sélecteur de classe, donc `.rise.seen` ne pouvait pas le défaire et les
   sections restaient blanches POUR TOUJOURS. Mesuré : 43,3 % de la page vide,
   dont une bande de 993 px. La classe `.rise` est posée par le JAVASCRIPT, de
   sorte qu'une page sans JS montre tout. */
.rise { opacity: 0; transform: translateY(12px); }
.rise.seen { opacity: 1; transform: none;
             transition: opacity .5s ease, transform .5s cubic-bezier(.16,1,.3,1); }

@media (max-width: 980px) {
  .demo-body { grid-template-columns: 1fr; }
  .panel + .panel { border-left: 0; border-top: 1px solid var(--rule); }
  pre, .out { height: 17rem; }
  .stats { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .stat:nth-child(2) { border-right: 0; }
  .nav-links a:not(.btn) { display: none; }
  .verb { grid-template-columns: 1fr; gap: var(--s1); }
}
@media (max-width: 620px) {
  :root { --s8: 3.5rem; }
  .wrap { width: calc(100% - 1.6rem); }
  /* « / compiler » cassait la marque sur deux lignes et poussait le bouton
     hors de la barre. */
  .logo span:not(.logo-mark) { display: none; }
  .stats { grid-template-columns: 1fr; }
  .stat { border-right: 0; border-bottom: 1px solid var(--rule); }
  .stat:last-child { border-bottom: 0; }
  .demo-foot .btn { margin-left: 0; width: 100%; justify-content: center; }
}
@media (prefers-reduced-motion: reduce) {
  * { animation: none !important; transition: none !important; }
  .rise { opacity: 1 !important; transform: none !important; }
}
</style>
</head>
<body>

<div class="topline">
  Bêta publique 0.9.0-beta.7 — <a href="#telecharger">installer le compilateur</a>
</div>

<nav>
  <div class="wrap nav-in">
    <a class="logo" href="#top"><span class="logo-mark">m</span><b>monl</b><span>/ compiler</span></a>
    <div class="nav-links">
      <a href="#demonstration">Démonstration</a>
      <a href="#commandes">Commandes</a>
      <a href="#refus">Ce qu'il refuse</a>
      <a href="#telecharger">Télécharger</a>
      <a class="btn" href="/console">Ouvrir la console</a>
    </div>
  </div>
</nav>

<header id="top">
  <div class="wrap">
    <span class="pill">Déterministe de bout en bout <em>→</em></span>
    <h1>Décrivez votre site. <em>Le compilateur écrit le serveur.</em></h1>
    <p class="lede">Un dialogue guidé, <b>sans aucune IA et sans le moindre
      appel réseau</b>, produit une spécification. monl la compile en un
      backend FastAPI complet — base SQLite, authentification, contrôle
      d'accès, paiement — puis le <b>scelle</b>.</p>
    <div class="cta">
      <a class="btn lg" href="#telecharger">Télécharger monl</a>
      <a class="btn lg ghost" href="/console">Essayer dans le navigateur →</a>
    </div>
    <p class="meta">Python 3.10+ · licence FSL-1.1-ALv2 · aucune télémétrie</p>
  </div>
</header>

<section id="demonstration" style="border-top:0; padding-top:0">
  <div class="wrap">
    <div class="demo">
      <div class="demo-head">
        <div class="tabs" role="tablist" aria-label="Modèle d'application" id="modeles"></div>
        <span class="tag">sorties réelles du compilateur</span>
      </div>
      <div class="demo-body">
        <div class="panel">
          <div class="panel-head">
            <span class="tag">ce que vous écrivez</span>
            <span class="tag file">[ <b>.ml</b> ]</span>
          </div>
          <pre id="spec"></pre>
        </div>
        <div class="panel">
          <div class="panel-head">
            <span class="tag">ce que monl produit</span>
            <div class="tabs" role="tablist" aria-label="Sortie" id="sorties">
              <button class="tab" type="button" role="tab" data-vue="routes">routes</button>
              <button class="tab" type="button" role="tab" data-vue="tables">tables</button>
              <button class="tab" type="button" role="tab" data-vue="scelle">scellé</button>
            </div>
          </div>
          <div class="out" id="sortie"></div>
        </div>
      </div>
      <div class="demo-foot" id="resume"></div>
    </div>
    <p class="hint">Aucune de ces lignes n'est écrite à la main : elles sortent
      d'une compilation réelle des modèles livrés avec monl.</p>
  </div>
</section>

<section id="commandes" class="alt">
  <div class="wrap">
    <div class="sec-head">
      <div><p class="chapter"><i></i><span class="tag">[ <b>01</b> / 04 ] · les commandes</span></p>
    <h2>Cinq verbes, et <em>un seul</em> appelle une IA.</h2></div>
      <p class="intro">monl est une ligne de commande. Chaque verbe fait une
      chose, et la prouve avant de rendre la main.</p>
    </div>
    <div class="verbs">
      <div class="verb"><code>monl init</code><p>Le dialogue guidé. Dix modèles
        d'applications comme point de départ, questions fermées, saisie
        stricte. <b>Aucune IA, aucun appel réseau</b> — et la spécification
        produite est relue par le vrai analyseur avant d'être écrite.</p></div>
      <div class="verb"><code>monl compile</code><p>Grammaire, validation,
        audit de sécurité, génération. Sortent <code>app.py</code>,
        <code>schema.sql</code>, un <code>manage.py</code> d'administration, un
        <code>Dockerfile</code> — et un <b>contrat d'interface</b> qui décrit ce
        que le serveur fait vraiment.</p></div>
      <div class="verb"><code>monl frontend</code><p>La seule étape non
        déterministe. Une IA écrit le HTML, la CSS et le JavaScript en
        obéissant au contrat, par clé d'API ou par un agent en ligne de
        commande. <b>Les artefacts scellés sont vérifiés intacts</b> après
        coup.</p></div>
      <div class="verb"><code>monl run</code><p>Vérifie la cohérence, démarre un
        serveur éphémère, appelle de vraies routes, charge la page dans un vrai
        moteur JavaScript — puis sert le site. <b>Un échec est un échec</b>, pas
        un avertissement.</p></div>
      <div class="verb"><code>monl update</code><p>Recompile après un changement
        de spec et rapporte le delta : route ajoutée, champ devenu en lecture
        seule, accès ouvert, verrou posé, section à dessiner. <b>Ce qu'il reste
        à réécrire</b>, écran par écran.</p></div>
    </div>
  </div>
</section>

<section id="refus">
  <div class="wrap">
    <div class="sec-head">
      <div><p class="chapter"><i></i><span class="tag">[ <b>02</b> / 04 ] · ce qu'il refuse</span></p>
    <h2>Un compilateur utile est <em>un compilateur qui dit non</em>.</h2></div>
      <p class="intro">Chacun de ces refus vient d'une faille réellement
      exploitée sur un projet, puis fermée à la racine. Ils font échouer la
      compilation, en nommant la ligne fautive — voici ce que monl affiche.</p>
    </div>
    <ul class="refus">
      <li><div class="quoi"><b>Un montant que le client peut écrire.</b>
        Une commande était postée à 0,01 € et le serveur l'encaissait.</div>
        <div class="dit"><span>✕ ERREUR</span>  rule Order.total payable — le champ 'total' est
   saisissable par le client. Un montant encaissable doit être
   calculé par le serveur : ajoutez 'derivedFrom' ou 'sumOf'.</div></li>
      <li><div class="quoi"><b>Une propriété qui ne remonte à aucun compte.</b>
        La règle compilait en silence et rattachait les enregistrements au
        mauvais propriétaire.</div>
        <div class="dit"><span>✕ ERREUR</span>  rule Line.Read ownedBy Cart — la chaîne de propriété
   n'aboutit à aucun acteur. 'Cart' n'appartient lui-même à personne.</div></li>
      <li><div class="quoi"><b>Une règle qui ne produit rien.</b>
        Quatre règles de contrainte n'avaient aucun effet sur la sortie ; un
        prix négatif partait en base.</div>
        <div class="dit"><span>✕ ERREUR</span>  rule Colis.champFantome required — le champ
   'champFantome' n'existe pas sur l'entité 'Colis'.</div></li>
      <li><div class="quoi"><b>Un fichier déclaré mais absent.</b>
        Trois chemins d'image fautifs compilaient sans un mot. Une image
        cassée ne se voit qu'à l'œil, une fois en ligne.</div>
        <div class="dit"><span>✕ ERREUR</span>  assets: photo "produits/halo-rs.jpg" — fichier
   introuvable. Cherché dans : ./produits/halo-rs.jpg</div></li>
      <li><div class="quoi"><b>Une section vide sur le site livré.</b>
        Une balise portant le bon nom mais rien dedans passait pour une page
        complète.</div>
        <div class="dit"><span>✕ ERREUR</span>  section vide ou incomplète — « trust » : il manque
   un titre (&lt;h1&gt; à &lt;h4&gt;), du texte lisible (0 caractères sur 120
   attendus).</div></li>
    </ul>
  </div>
</section>

<section class="alt">
  <div class="wrap">
    <div class="sec-head">
      <div><p class="chapter"><i></i><span class="tag">[ <b>03</b> / 04 ] · l'état du projet</span></p>
    <h2>Des chiffres, <em>pas des logos</em>.</h2></div>
      <p class="intro">monl n'affiche ni clients, ni avis, ni récompenses : il ne
      pourrait pas les vérifier, et c'est exactement ce qu'il interdit aux
      sites qu'il produit. Voici ce qui est mesurable.</p>
    </div>
    <div class="stats">
      <div class="stat"><b>1 112</b><span>tests, rejoués à chaque changement</span></div>
      <div class="stat"><b>28</b><span>briques du langage, chacune éprouvée contre un vrai serveur</span></div>
      <div class="stat"><b>10</b><span>modèles d'applications prêts au dialogue</span></div>
      <div class="stat"><b>140</b><span>décisions de conception écrites, avec leur pourquoi</span></div>
    </div>
  </div>
</section>

<section id="telecharger">
  <div class="wrap">
    <div class="sec-head">
      <div><p class="chapter"><i></i><span class="tag">[ <b>04</b> / 04 ] · télécharger</span></p>
    <h2>Installez le compilateur, <em>gardez vos projets</em>.</h2></div>
      <p class="intro">monl s'exécute chez vous. Les projets qu'il compile sont
      des dossiers ordinaires : du Python, du SQL, un Dockerfile. Rien ne
      dépend d'un service en ligne pour continuer à tourner.</p>
    </div>
    <div class="install">
      <code id="cmd">pip install monl_compiler-0.9.0b7-py3-none-any.whl</code>
      <button class="copy" type="button" data-copy="cmd">copier</button>
    </div>
    <div class="dl" id="artifacts">
      <div class="dl-item"><div class="who"><b>Chargement des versions…</b></div></div>
    </div>
    <p class="hint">Chaque fichier est publié avec son empreinte SHA-256 :
      comparez-la après téléchargement.</p>
  </div>
</section>

<section class="alt">
  <div class="wrap">
    <div class="close">
      <h2>Prêt à décrire <em>votre site</em> ?</h2>
      <p>La console mène le même dialogue que la ligne de commande, une
        question à la fois, puis construit et sert le site sous sa propre
        adresse.</p>
      <a class="btn lg" href="/console">Ouvrir la console →</a>
    </div>
  </div>
</section>

<footer>
  <div class="wrap foot">
    <span>monl — compilateur d'applications déclaratives · 0.9.0-beta.7</span>
    <span>licence FSL-1.1-ALv2 · aucune télémétrie · aucun cookie</span>
  </div>
</footer>

<script>
/* Sorties RÉELLES du compilateur, injectées à la construction de cette page.
   Voir batir_landing.py : chaque modèle a été réellement compilé. */
var DEMO = {
 "Boutique en ligne": {
  "spec": "entity Product\n    name: String\n    price: Money\n    description: Text\n    imageUrl: String\n    stock: Integer\n    category: String\nactor Admin\nactor Customer selfRegister\nrule Product.name required\nrule Customer.displayName required\nrule LigneOrder.quantite required\nrule Product.Read public\nrule Order.Read ownedBy Customer\nrule Order.Update ownedBy Customer\nrule Order.Delete ownedBy Customer\nrule LigneOrder.Read ownedBy Order\nrule LigneOrder.Update ownedBy Order",
  "routes": [
   "GET    /customer",
   "POST   /customer",
   "DELETE /customer/{id}",
   "GET    /customer/{id}",
   "PUT    /customer/{id}",
   "GET    /ligneorder",
   "POST   /ligneorder",
   "DELETE /ligneorder/{id}",
   "GET    /ligneorder/{id}",
   "PUT    /ligneorder/{id}",
   "GET    /order",
   "POST   /order",
   "DELETE /order/{id}",
   "GET    /order/{id}",
   "PUT    /order/{id}",
   "POST   /order/{id}/paiement",
   "POST   /paiement/webhook",
   "GET    /product",
   "POST   /product",
   "DELETE /product/{id}",
   "GET    /product/{id}",
   "PUT    /product/{id}"
  ],
  "tables": [
   "product",
   "order",
   "customer",
   "ligneorder"
  ],
  "systeme": [
   "_monl_users",
   "_monl_revoked_tokens",
   "_monl_rate_limit",
   "_monl_sequences",
   "_monl_migrations"
  ],
  "entites": [
   "Customer",
   "LigneOrder",
   "Order",
   "Product"
  ],
  "octets": 81621,
  "lignes": 125,
  "regles": 16
 },
 "Blog": {
  "spec": "entity Article\n    title: String\n    content: Text\n    imageUrl: String\n    author: String\n    publishedOn: String\n    status: String\nactor Author\nactor Reader selfRegister\nactor Moderator\nrule Article.title required\nrule Report.reason required\nrule Comment.content required\nrule Reader.displayName required\nrule Comment.Read public\nrule Comment.Update ownedBy Reader\nrule Comment.Delete ownedBy Reader\nrule Article.status oneOf \"published\", \"hidden\"",
  "routes": [
   "GET    /article",
   "POST   /article",
   "DELETE /article/{id}",
   "GET    /article/{id}",
   "PUT    /article/{id}",
   "GET    /comment",
   "POST   /comment",
   "DELETE /comment/{id}",
   "GET    /comment/{id}",
   "PUT    /comment/{id}",
   "GET    /reader",
   "POST   /reader",
   "DELETE /reader/{id}",
   "GET    /reader/{id}",
   "PUT    /reader/{id}",
   "GET    /report",
   "POST   /report",
   "DELETE /report/{id}",
   "GET    /report/{id}",
   "PUT    /report/{id}"
  ],
  "tables": [
   "article",
   "report",
   "comment",
   "reader"
  ],
  "systeme": [
   "_monl_users",
   "_monl_revoked_tokens",
   "_monl_rate_limit",
   "_monl_sequences",
   "_monl_migrations"
  ],
  "entites": [
   "Article",
   "Comment",
   "Reader",
   "Report"
  ],
  "octets": 66961,
  "lignes": 96,
  "regles": 13
 },
 "Réservation de rendez-vous": {
  "spec": "entity Service\n    name: String\n    duration: Integer\n    price: Money\n    description: Text\nactor Admin\nactor Client selfRegister\nrule Service.name required\nrule Booking.date required\nrule Client.displayName required\nrule Service.Read public\nrule Booking.Read ownedBy Client\nrule Booking.Update ownedBy Client\nrule Booking.Delete ownedBy Client",
  "routes": [
   "GET    /booking",
   "POST   /booking",
   "DELETE /booking/{id}",
   "GET    /booking/{id}",
   "PUT    /booking/{id}",
   "GET    /client",
   "POST   /client",
   "DELETE /client/{id}",
   "GET    /client/{id}",
   "PUT    /client/{id}",
   "GET    /service",
   "POST   /service",
   "DELETE /service/{id}",
   "GET    /service/{id}",
   "PUT    /service/{id}"
  ],
  "tables": [
   "service",
   "booking",
   "client"
  ],
  "systeme": [
   "_monl_users",
   "_monl_revoked_tokens",
   "_monl_rate_limit",
   "_monl_sequences",
   "_monl_migrations"
  ],
  "entites": [
   "Booking",
   "Client",
   "Service"
  ],
  "octets": 61427,
  "lignes": 66,
  "regles": 7
 }
};

(function () {
  "use strict";
  var reduit = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var noms = Object.keys(DEMO);
  var etat = { modele: noms[0], vue: "routes" };

  function milliers(n) {
    return String(n).replace(/\B(?=(\d{3})+(?!\d))/g, " ");
  }
  function ech(s) {
    return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }
  /* Coloration minimale de la spec : mots-clés du langage et types. Pas un
     analyseur — juste de quoi rendre la structure lisible. */
  function colorer(spec) {
    return ech(spec)
      .replace(/^(\s*)(entity|actor|rule|relation|workflow|landing|seed|assets)\b/gm,
               '$1<span class="k">$2</span>')
      .replace(/: (String|Text|Integer|Float|Money|Boolean|DateTime|Date|Image|UUID)\b/g,
               ': <span class="t">$1</span>')
      .replace(/^(\s*)(#.*)$/gm, '$1<span class="c">$2</span>');
  }

  function onglets(cible, items, actif, clic) {
    cible.innerHTML = "";
    items.forEach(function (item) {
      var b = document.createElement("button");
      b.type = "button";
      b.className = "tab";
      b.setAttribute("role", "tab");
      b.setAttribute("aria-selected", String(item === actif));
      b.textContent = item;
      b.addEventListener("click", function () { clic(item); });
      cible.appendChild(b);
    });
  }

  function rendre() {
    var d = DEMO[etat.modele];
    document.getElementById("spec").innerHTML = colorer(d.spec);

    var out = document.getElementById("sortie");
    var lignes;
    if (etat.vue === "routes") {
      lignes = d.routes.map(function (r) {
        var m = r.slice(0, 6).trim();
        return '<li><span class="m">' + m + '</span>' + ech(r.slice(m.length)) + "</li>";
      });
    } else if (etat.vue === "tables") {
      lignes = d.tables.map(function (t) { return '<li><span class="m">•</span> ' + ech(t) + "</li>"; })
        .concat(d.systeme.map(function (t) {
          return '<li class="sys">  ' + ech(t) + "  (interne)</li>";
        }));
    } else {
      lignes = [
        '<li><span class="m">app.py</span>          ' + milliers(d.octets) + " octets</li>",
        '<li><span class="m">schema.sql</span>      ' + (d.tables.length + d.systeme.length) + " tables</li>",
        "<li>&nbsp;</li>",
        '<li class="sys">Ces fichiers portent une empreinte. Aucune IA,</li>',
        '<li class="sys">aucun agent, aucune commande ne les réécrit :</li>',
        '<li class="sys">la vérification refuse et nomme le fichier.</li>'
      ];
    }
    out.innerHTML = "<ul>" + lignes.join("") + "</ul>";

    document.getElementById("resume").innerHTML =
      "<span><b>" + d.lignes + "</b> lignes de spécification · <b>" + d.regles +
      "</b> règles</span><span>→</span><span><b>" + d.routes.length +
      "</b> routes · <b>" + (d.tables.length + d.systeme.length) +
      "</b> tables · <b>" + milliers(d.octets) +
      "</b> octets de serveur scellé</span>" +
      '<a class="btn" href="/console">Construire celui-ci →</a>';

    onglets(document.getElementById("modeles"), noms, etat.modele, function (n) {
      etat.modele = n; rendre();
    });
    Array.prototype.forEach.call(
      document.getElementById("sorties").querySelectorAll(".tab"), function (b) {
        b.setAttribute("aria-selected", String(b.getAttribute("data-vue") === etat.vue));
      });
  }

  Array.prototype.forEach.call(
    document.getElementById("sorties").querySelectorAll(".tab"), function (b) {
      b.addEventListener("click", function () {
        etat.vue = b.getAttribute("data-vue"); rendre();
      });
    });
  rendre();

  /* ── Les téléchargements réellement disponibles ─────────────────────── */
  var zone = document.getElementById("artifacts");
  function octets(n) {
    if (n < 1024) { return n + " o"; }
    if (n < 1048576) { return (n / 1024).toFixed(0) + " Ko"; }
    return (n / 1048576).toFixed(1) + " Mo";
  }
  fetch("/telechargements").then(function (r) { return r.json(); }).then(function (data) {
    var liste = (data && data.artifacts) || [];
    zone.innerHTML = "";
    if (!liste.length) {
      var vide = document.createElement("div");
      vide.className = "dl-item";
      vide.innerHTML = '<div class="who"><b>Aucune version publiée sur cette ' +
        'instance.</b><span>Construisez la distribution, ou récupérez le dépôt.</span></div>';
      zone.appendChild(vide);
      return;
    }
    liste.forEach(function (a) {
      var el = document.createElement("div");
      el.className = "dl-item";
      el.innerHTML = '<div class="who"><b></b><span></span><span class="sha"></span></div>';
      el.querySelector("b").textContent = a.name;
      el.querySelectorAll("span")[0].textContent =
        (a.kind === "wheel" ? "roue Python — à installer" : "archive des sources")
        + " · " + octets(a.bytes);
      el.querySelector(".sha").textContent = "sha256 " + a.sha256;
      var lien = document.createElement("a");
      lien.className = "btn" + (a.kind === "wheel" ? "" : " ghost");
      lien.href = "/telechargements/" + encodeURIComponent(a.name);
      lien.textContent = "Télécharger";
      el.appendChild(lien);
      zone.appendChild(el);
      if (a.kind === "wheel") {
        document.getElementById("cmd").textContent = "pip install " + a.name;
      }
    });
  }).catch(function () {
    zone.innerHTML = '<div class="dl-item"><div class="who"><b>Liste ' +
      'indisponible.</b><span>Le service de téléchargement n\'a pas répondu.</span></div></div>';
  });

  /* ── Apparition à l'entrée dans le cadre ────────────────────────────── */
  var cibles = document.querySelectorAll(".verb, .stat, .refus li, .dl-item, .close");
  function tout_montrer() {
    Array.prototype.forEach.call(cibles, function (el) { el.classList.add("seen"); });
  }
  if (!reduit && "IntersectionObserver" in window) {
    try {
      Array.prototype.forEach.call(cibles, function (el, n) {
        el.classList.add("rise");
        el.style.transitionDelay = (n % 5) * 40 + "ms";
      });
      var oeil = new IntersectionObserver(function (entrees) {
        entrees.forEach(function (e) {
          if (e.isIntersecting) { e.target.classList.add("seen"); oeil.unobserve(e.target); }
        });
      }, { rootMargin: "0px 0px -8% 0px", threshold: 0.05 });
      Array.prototype.forEach.call(cibles, function (el) { oeil.observe(el); });
      /* Filet : si l'observateur ne se déclenche jamais — écran très haut,
         navigateur exotique, erreur en amont — la page ne doit pas rester
         blanche. Un contenu invisible est pire qu'un contenu non animé. */
      window.setTimeout(tout_montrer, 2500);
    } catch (e) {
      tout_montrer();
    }
  }

  /* ── Copier la commande d'installation ──────────────────────────────── */
  document.addEventListener("click", function (e) {
    var bouton = e.target.closest ? e.target.closest(".copy") : null;
    if (!bouton) { return; }
    var source = document.getElementById(bouton.getAttribute("data-copy"));
    if (!source) { return; }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(source.textContent).then(function () {
        bouton.textContent = "copié";
        window.setTimeout(function () { bouton.textContent = "copier"; }, 1600);
      }, function () {});
    }
  });
})();
</script>
</body>
</html>
'''


def landing_response():
    """Rend la page de présentation."""
    return HTMLResponse(content=LANDING_HTML)
