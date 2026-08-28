"""L'explorateur de cas métier de la page d'accueil.

Extrait de `landing.py` quand celle-ci a franchi le plafond de 400 lignes du
point 155 — un fichier de plus, pas une exception de plus : ce module est du
CODE, pas un littéral de données comme les deux seules exceptions écrites.

L'ensemble se tient : la feuille, les données des quatre cas, le balisage et
le script du repère qui glisse. Les séparer aurait mis la classe `glisse` dans
un fichier et la règle qui la lit dans un autre.
"""

from __future__ import annotations

from . import examples
from .coloration import coloriser
from .theme import icon, page  # noqa: F401  (page reste importable d'ici)

EXTRA_CSS = """
.case-explorer { display:grid; grid-template-columns:minmax(230px,.7fr) minmax(0,1.55fr); border:1px solid var(--line);
  border-radius:var(--radius-lg); overflow:hidden; min-height:560px; }
.case-tabs { position:relative; background:var(--surface-2); border-right:1px solid var(--line); padding:12px; }
.case-tab { position:relative; z-index:1; width:100%; border:0; border-radius:10px; padding:16px; background:transparent; color:var(--muted); text-align:left;
  cursor:pointer; display:block; transition:background .18s,color .18s; }
.case-tab:hover { color:var(--ink); }.case-tab[aria-selected="true"] { background:var(--surface); color:var(--ink); }
/* Le fond de l'onglet actif devient un repère unique qui GLISSE d'un onglet à
   l'autre. Il n'est cédé que si le script a réellement posé le repère
   (classe `glisse`) : sans JavaScript, la règle `[aria-selected]` reste seule
   et l'onglet garde son fond. Sa spécificité est plus forte (0,3,1 contre 0,2,1),
   donc l'ordre des règles n'a pas à être défendu. */
.case-tabs.glisse .case-tab[aria-selected="true"] { background:transparent; }
/* Et le fond de l'onglet cesse d'être animé dès que le repère prend le relais :
   sans ça, l'onglet quitté s'éteint en .18s pendant que le repère met .34s à
   arriver, et les deux mouvements se contredisent. */
.case-tabs.glisse .case-tab { transition:color .18s; }
.case-repere {
  position:absolute; top:0; left:0; z-index:0; pointer-events:none;
  width:var(--repere-w,0); height:var(--repere-h,0);
  transform:translate(var(--repere-x,0), var(--repere-y,0));
  background:var(--surface); border-radius:10px;
  transition:transform .34s cubic-bezier(.4,0,.2,1), width .34s cubic-bezier(.4,0,.2,1),
             height .34s cubic-bezier(.4,0,.2,1);
}
.case-tab b { display:block; margin-bottom:4px; font-size:15px; }.case-tab span { font-size:12px; line-height:1.4; display:block; }
.case-panels { min-width:0; background:var(--surface); }
.case-panel { display:none; min-height:100%; padding:clamp(28px,5vw,58px); }
.case-panel.active { display:grid; grid-template-columns:1fr 1fr; gap:clamp(24px,5vw,56px); animation:case-in .25s ease-out; }
.case-panel h3 { font-size:clamp(27px,4vw,42px); margin:8px 0 16px; }.case-panel p { color:var(--muted); }
.case-spec { min-width:0; display:flex; flex-direction:column; }
.case-spec .codeblock { flex:1; min-height:0; white-space:pre-wrap; overflow:visible; overflow-wrap:anywhere; }
.case-rules { display:flex; flex-wrap:wrap; gap:6px; }
.case-rules span { border:1px solid var(--line); border-radius:999px; padding:3px 8px; color:var(--muted); font:10px var(--mono); }
.case-result { display:grid; grid-template-columns:repeat(3,1fr); gap:10px; }
.case-result b { display:block; color:var(--ink); font:700 18px var(--mono); }
.case-result span { color:var(--muted); font-size:10px; }
.case-open { display:inline-flex; align-items:center; gap:6px; margin-top:24px; color:var(--ink); font-size:13px; font-weight:650; }
@keyframes case-in { from { opacity:0; transform:translateY(5px); } to { opacity:1; transform:none; } }
@media(max-width:760px){
  .case-tabs { border-right:0; border-bottom:1px solid var(--line); display:flex; overflow-x:auto; }
  .case-tab { width:190px; flex:none; }.case-tab span { display:none; }
  .case-panel.active { grid-template-columns:1fr; }.case-explorer { min-height:0; }
}
"""


CASE_OUTCOMES = {
    "vitrine": "Lecture publique, administration privée et catalogue initialisé dès le premier démarrage.",
    "rendez-vous": "Chaque client reste isolé ; le praticien retrouve toutes les demandes et maîtrise leurs statuts.",
    "boutique": "Prix calculés côté serveur, stock jamais négatif, commande numérotée et paiement verrouillé.",
    "communaute": "Pseudonymes générés, une réaction par compte, signalement et modération sans contournement.",
}

CASE_SNIPPETS = {
    "vitrine": """rule Realisation.Read public

workflow Gerer for Admin
    Create Realisation
    Update Realisation
    Delete Realisation""",
    "rendez-vous": """rule Demande.Read ownedBy Visiteur
rule Demande.Read sharedBy Praticien
rule Demande.Create requiresOwn Client
rule Demande.statut oneOf
    \"deposee\", \"confirmee\", \"honoree\"""",
    "boutique": """rule Ligne.sousTotal derivedFrom Produit.prix by quantite
rule Commande.total sumOf Ligne.sousTotal
rule Ligne.Create decrements Produit.stock by quantite
rule Commande.total payable""",
    "communaute": """rule Membre.pseudo generated \"MBR-{NNNN}\"
rule Jaime.Create oncePer Membre, Message
rule Jaime.Create increments Message.jaimes by 1
rule Message.Read publicWhen statut \"publie\"""",
}


def case_tab(item: dict, index: int) -> str:
    selected = ' aria-selected="true"' if index == 0 else ' aria-selected="false"'
    return (f'<button class="case-tab" id="tab-{item["id"]}" role="tab" '
            f'aria-controls="case-{item["id"]}"{selected} data-case="{item["id"]}">'
            f'<b>{item["name"]}</b><span>{item["summary"]}</span></button>')


def case_panel(item: dict, index: int) -> str:
    result = item["result"]
    rules = "".join(f"<span>{rule}</span>" for rule in item["teaches"])
    active = " active" if index == 0 else ""
    hidden = "" if index == 0 else " hidden"
    # Colorié ICI et non dans la table : la table reste du texte nu,
    # relisible et comparable à une vraie spec.
    snippet = coloriser(CASE_SNIPPETS[item["id"]])
    return f"""<section class="case-panel{active}" id="case-{item['id']}" role="tabpanel"
aria-labelledby="tab-{item['id']}"{hidden}><div><h3>{item['name']}</h3><p>{CASE_OUTCOMES[item['id']]}</p>
<div class="case-rules" aria-label="Règles démontrées">{rules}</div>
<div class="case-result" style="margin-top:28px"><span><b>{result['entities']}</b>entités</span>
<span><b>{result['routes']}</b>routes</span><span><b>{result['files']}</b>fichiers</span></div>
<a class="case-open" href="/console?example={item['id']}">Ouvrir dans la console {icon('arrow')}</a></div>
<div class="case-spec"><pre class="codeblock"><code>{snippet}</code></pre></div></section>"""

CATALOGUE = examples.catalogue()
CASE_TABS = "".join(case_tab(item, index) for index, item in enumerate(CATALOGUE))
CASE_PANELS = "".join(case_panel(item, index) for index, item in enumerate(CATALOGUE))


EXPLORATEUR = f"""<div class="case-explorer" data-reveal>\
<div class="case-tabs" role="tablist" aria-label="Cas métier">{CASE_TABS}</div>
<div class="case-panels">{CASE_PANELS}</div></div>"""


CASE_SCRIPT = """<script>
(function () {
  var tabs = Array.from(document.querySelectorAll('.case-tab'));
  var panels = Array.from(document.querySelectorAll('.case-panel'));
  var liste = document.querySelector('.case-tabs');
  var repere = null;
  if (liste && tabs.length) {
    repere = document.createElement('span');
    repere.className = 'case-repere';
    repere.setAttribute('aria-hidden', 'true');
    liste.insertBefore(repere, liste.firstChild);
    liste.classList.add('glisse');
  }
  /* offsetTop/offsetLeft se mesurent depuis le bord de PADDING du parent
     positionné, exactement là où `top:0; left:0` pose un absolu. L'onglet est
     posé dans la boite de CONTENU, donc offsetLeft vaut le padding (12px
     mesurés) et le translate reconduit le repère pile sur l'onglet : écart
     mesuré 0,0 au navigateur. Une seule mesure couvre la colonne verticale du
     bureau et la rangée horizontale du mobile. */
  function placer(tab, anime) {
    if (!repere) return;
    if (!anime) repere.style.transition = 'none';
    repere.style.setProperty('--repere-x', tab.offsetLeft + 'px');
    repere.style.setProperty('--repere-y', tab.offsetTop + 'px');
    repere.style.setProperty('--repere-w', tab.offsetWidth + 'px');
    repere.style.setProperty('--repere-h', tab.offsetHeight + 'px');
    if (!anime) { void repere.offsetWidth; repere.style.transition = ''; }
  }
  function select(tab, focus) {
    tabs.forEach(function (item) {
      var active = item === tab;
      item.setAttribute('aria-selected', active ? 'true' : 'false');
      item.tabIndex = active ? 0 : -1;
    });
    panels.forEach(function (panel) {
      var active = panel.id === 'case-' + tab.dataset.case;
      panel.classList.toggle('active', active);
      panel.hidden = !active;
    });
    placer(tab, true);
    if (focus) tab.focus();
  }
  tabs.forEach(function (tab, index) {
    tab.tabIndex = index === 0 ? 0 : -1;
    tab.addEventListener('click', function () { select(tab, false); });
    tab.addEventListener('keydown', function (event) {
      if (event.key !== 'ArrowRight' && event.key !== 'ArrowLeft' &&
          event.key !== 'ArrowDown' && event.key !== 'ArrowUp') return;
      event.preventDefault();
      var direction = event.key === 'ArrowRight' || event.key === 'ArrowDown' ? 1 : -1;
      select(tabs[(index + direction + tabs.length) % tabs.length], true);
    });
  });
  /* Premier placement SANS animation : sinon le repère traverse la liste
     depuis l'angle au chargement. Et replacement au redimensionnement, la
     grille passant de la colonne à la rangée sous 900px. */
  var actif = tabs.filter(function (t) { return t.getAttribute('aria-selected') === 'true'; })[0] || tabs[0];
  if (actif) placer(actif, false);
  window.addEventListener('resize', function () {
    var courant = tabs.filter(function (t) { return t.getAttribute('aria-selected') === 'true'; })[0];
    if (courant) placer(courant, false);
  });
})();
</script>"""
