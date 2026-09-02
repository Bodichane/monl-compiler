"""Static CSS, script and example markup for the platform guide."""

from __future__ import annotations

from .coloration import coloriser

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
.boundary { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:var(--space-3);
            margin:var(--space-5) 0 var(--space-6); }
.boundary article { border:1px solid var(--line); border-radius:var(--radius); padding:var(--space-4);
                   background:var(--surface-2); }
.boundary h3 { margin:var(--space-3) 0 var(--space-2); font-size:17px; }
.boundary p { color:var(--muted); margin:0; font-size:15px; }
.step-no { font: 600 12px var(--mono); color: var(--brand); }
.step h3 { margin: var(--space-3) 0 var(--space-2); font-size: 17px; }
.step p { margin: 0; color: var(--muted); font-size: 15px; }
.note { border-left: 3px solid var(--brand); background: var(--soft);
        padding: var(--space-4) var(--space-5); border-radius: 0 var(--radius) var(--radius) 0;
        margin-bottom: var(--space-5); }
.note p:last-child { margin-bottom: 0; }
.method { font: 600 12px var(--mono); color: var(--brand); }
@media (max-width: 900px) {
  /* `minmax(0,…)` et non `1fr` : le plancher `auto` d'un `1fr` est la largeur
     MIN-CONTENT de l'enfant, ici les lignes de spec non sécables des blocs de
     code. Mesuré à 375px avant correction : une piste de 550px dans un écran
     de 375, donc 351 éléments coupés par l'`overflow-x:clip` du `body` — le
     guide entier illisible sur téléphone. Le défilement reste offert par le
     `overflow-x:auto` du bloc de code lui-même : plancherer la piste sans
     cela ne ferait que DÉPLACER la coupure. */
  .doc { grid-template-columns: minmax(0, 1fr); gap: var(--space-5); }
  .toc { position: static; border-bottom: 1px solid var(--line); padding-bottom: var(--space-4); }
  .toc ol { display: flex; flex-wrap: wrap; gap: var(--space-1); }
  .boundary { grid-template-columns:1fr; }
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

SPEC_EXEMPLE = coloriser("""# Une spécification complète tient en une page.
app CarnetAtelier

entity Fiche
    titre: String
    contenu: Text
    statut: String

actor Auteur selfRegister
actor Relecteur

relation Auteur hasMany Fiche

rule Fiche.titre required
rule Fiche.statut oneOf "brouillon", "publiee"
rule Fiche.Read publicWhen statut "publiee"
rule Fiche.Update ownedBy Auteur
rule Fiche.Update sharedBy Relecteur

workflow Ecrire for Auteur
    Create Fiche
    Read Fiche
    Update Fiche

workflow Relire for Relecteur
    Read Fiche
    Update Fiche""")
