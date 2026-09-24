"""La porte d'entrée fonctionne dans un vrai DOM contre un vrai serveur."""

import json
import os
import shutil
import subprocess

import pytest

from monl.smoke_test.fondations import _ensure_jsdom, _jsdom_node_path
from monl_platform.account import AUTH_HTML
from monl_platform.console import CONSOLE_HTML
from monl_platform.landing import GITHUB_URL, LANDING_HTML
from monl_platform.theme import page
from monl_platform.theme_ambiance import CSS as AMBIANCE_CSS
from tests import test_oauth
from tests.support.server import uvicorn_server

SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
plateforme = test_oauth.plateforme
faux_github = test_oauth.faux_github


RUNNER = r"""
const { JSDOM, VirtualConsole } = require("jsdom");
const avecGithub = process.argv[2];
const sansFournisseur = process.argv[3];
const erreurs = [];

/* Un nom qui porte les trois caractères qui changent le sens d'une adresse, et
   un libellé qui serait du balisage s'il passait par innerHTML (issue #75, M2).
   Seul le pilote les sert : la table du serveur n'en contient aucun. */
const PIEGE = { name: "x/y?#", label: '<img src="x" id="injecte">Piège' };

function reponseLente(texte, delai) {
  const corps = new ReadableStream({
    start(flux) {
      setTimeout(() => { flux.enqueue(new TextEncoder().encode(texte)); flux.close(); }, delai);
    },
  });
  return new Response(corps, { headers: { "content-type": "application/json" } });
}

function equiper(w, base, options) {
  const reduit = Boolean(options.reduit);
  w.matchMedia = q => ({
    matches: reduit && q.includes("prefers-reduced-motion"), media: q, onchange: null,
    addEventListener() {}, removeEventListener() {},
    addListener() {}, removeListener() {}, dispatchEvent() { return false; },
  });
  /* `fetch` se résout à l'arrivée des EN-TÊTES : la lecture du corps et le
     `.then` qui remplit la page viennent après (issue #80). Chaque lecture de
     corps est donc comptée elle aussi — la page ne se relâche qu'une fois ses
     réponses LUES. Les microtâches qui suivent une lecture s'enchaînent avant
     la prochaine tâche : le compteur ne retombe à zéro qu'après elles. */
  w.__enCours = 0;
  const suivre = promesse => {
    w.__enCours += 1;
    return promesse.finally(() => { w.__enCours -= 1; });
  };
  w.fetch = (u, o) => {
    const cible = new URL(u, base);
    const reponse = options.fournisseurs && cible.pathname === "/auth/fournisseurs"
      ? Promise.resolve(reponseLente(JSON.stringify({ providers: options.fournisseurs }),
          options.corpsLent || 0))
      : fetch(cible, o);
    return suivre(reponse.then(r => {
      for (const lecture of ["json", "text"]) {
        const lire = r[lecture].bind(r);
        r[lecture] = () => suivre(lire());
      }
      return r;
    }));
  };
  w.addEventListener("error", e => erreurs.push(String(e.message)));
}

/* On attend que les requêtes de la page soient RÉELLEMENT revenues, jamais
   une durée fixe : sur une machine lente, « la zone est vide » serait vrai
   aussi avant la réponse, et le test passerait sans avoir rien mesuré. */
async function charger(base, chemin, options = {}) {
  const html = await (await fetch(base + chemin)).text();
  const virtuelle = new VirtualConsole();
  virtuelle.on("jsdomError", e => erreurs.push(String(e.message)));
  virtuelle.on("error", (...m) => erreurs.push(m.map(String).join(" ")));
  const dom = new JSDOM(html, {
    url: base + chemin, runScripts: "dangerously", pretendToBeVisual: true,
    virtualConsole: virtuelle, beforeParse: w => equiper(w, base, options),
  });
  const limite = Date.now() + 15000;
  while (dom.window.__enCours > 0) {
    if (Date.now() > limite) throw new Error("requêtes toujours en cours : " + chemin);
    await new Promise(r => setTimeout(r, 20));
  }
  await new Promise(r => setTimeout(r, 0));
  return dom;
}

function etatReprise(doc) {
  return {
    oauth_masque: doc.querySelector("#oauth-zone").hidden,
    titre: doc.querySelector("#auth-title").textContent.trim(),
    code_masque: doc.querySelector("#champ-code").classList.contains("masque"),
    lien: doc.querySelector("#auth-recovery").textContent.trim(),
  };
}

async function inclinaison(base, reduit) {
  const dom = await charger(base, "/", { reduit });
  const w = dom.window;
  const visuel = w.document.querySelector(".hero-visual");
  const carte = w.document.querySelector(".start-card");
  const present = Boolean(visuel && carte);
  if (present) {
    /* jsdom ne calcule aucune mise en page : sans taille, la carte mesure 0×0,
       le calcul divise par zéro et rend « -Infinitydeg » — une valeur qu'un
       navigateur refuse, donc une carte qui ne s'incline jamais (issue #80). */
    visuel.getBoundingClientRect = () => ({ left: 0, top: 0, width: 200, height: 100 });
    visuel.dispatchEvent(new w.MouseEvent("pointermove", { clientX: 150, clientY: 25, bubbles: true }));
    await new Promise(r => setTimeout(r, 100));
  }
  const tilt = present ? [carte.style.getPropertyValue("--tilt-x"),
                          carte.style.getPropertyValue("--tilt-y")] : null;
  w.close();
  return { present, tilt };
}

(async () => {
  const github = await charger(avecGithub, "/login");
  const lien = github.window.document.querySelector("#oauth-zone a");
  const gdoc = github.window.document;
  const repriseAvant = etatReprise(gdoc);
  gdoc.querySelector("#auth-recovery").click();
  const repriseOuverte = etatReprise(gdoc);
  gdoc.querySelector("#auth-recovery").click();
  const repriseFermee = etatReprise(gdoc);

  const piege = await charger(sansFournisseur, "/login", {
    fournisseurs: [PIEGE], corpsLent: 1500,
  });
  const lienPiege = piege.window.document.querySelector("#oauth-zone a");
  const rapportPiege = {
    chemin: lienPiege && lienPiege.getAttribute("href"),
    texte: lienPiege && lienPiege.textContent.trim(),
    injecte: Boolean(piege.window.document.querySelector("#injecte")),
  };
  piege.window.close();

  const mouvementReduit = await inclinaison(sansFournisseur, true);
  const mouvementLibre = await inclinaison(sansFournisseur, false);

  const vide = await charger(sansFournisseur, "/login");
  const doc = vide.window.document;
  const zone = doc.querySelector("#oauth-zone");
  const password = doc.querySelector("#password");
  const toggle = doc.querySelector("#password-toggle");
  toggle.click();
  const apresAffichage = [password.type, toggle.textContent, toggle.getAttribute("aria-pressed")];
  toggle.click();
  const apresMasquage = [password.type, toggle.textContent, toggle.getAttribute("aria-pressed")];

  const connexion = doc.querySelector('.auth-tabs [data-mode="login"]');
  connexion.focus();
  connexion.dispatchEvent(new vide.window.KeyboardEvent("keydown", {
    key: "ArrowRight", bubbles: true,
  }));
  const creation = doc.querySelector('.auth-tabs [data-mode="register"]');
  const onglet = [creation.textContent.trim(), creation.getAttribute("aria-selected")];
  doc.querySelector("#auth-recovery").click();
  const codeVisible = !doc.querySelector("#champ-code").classList.contains("masque");

  const refus = await charger(sansFournisseur, "/login?erreur=refus");
  const rapport = {
    github: lien && { texte: lien.textContent.trim(), chemin: lien.getAttribute("href") },
    oauth_vide: zone.innerHTML.trim() === "",
    configuration_absente: !vide.serialize().toLowerCase().includes("configuration"),
    refus: refus.window.document.querySelector("#auth-error").textContent.trim(),
    apres_affichage: apresAffichage,
    apres_masquage: apresMasquage,
    onglet: onglet,
    code_visible: codeVisible,
    reprise_avant: repriseAvant,
    reprise_ouverte: repriseOuverte,
    reprise_fermee: repriseFermee,
    piege: rapportPiege,
    mouvement_reduit: mouvementReduit,
    mouvement_libre: mouvementLibre,
    erreurs: erreurs,
  };
  github.window.close(); vide.window.close(); refus.window.close();
  console.log(JSON.stringify(rapport));
})().catch(e => { console.log(JSON.stringify({ echec: String(e), erreurs })); });
"""


@pytest.fixture()
def rapport_connexion_jsdom(tmp_path, plateforme):
    if shutil.which("node") is None:
        pytest.fail("node est requis : un saut ne dirait pas « rien à vérifier »")
    assert _ensure_jsdom(str(tmp_path), lambda *_: None), (
        "jsdom introuvable et non installable dans ~/.monl/jsdom")
    runner = tmp_path / "runner.js"
    runner.write_text(RUNNER, encoding="utf-8")
    env = dict(os.environ)
    for cle in list(env):
        if cle.startswith("MONL_OAUTH_") or cle == "MONL_PLATFORM_PUBLIC_URL":
            del env[cle]
    env["MONL_PLATFORM_WORKSPACE"] = str(tmp_path / "projects-sans-oauth")
    env["PYTHONPATH"] = SRC + os.pathsep + env.get("PYTHONPATH", "")
    env["NODE_PATH"] = _jsdom_node_path()
    with uvicorn_server(str(tmp_path), env=env, module="monl_platform.app:app",
                        ready_path="/health") as sans_fournisseur:
        sortie = subprocess.run(
            ["node", str(runner), plateforme, sans_fournisseur],
            capture_output=True, text=True, timeout=180, env=env,
        )
    assert sortie.returncode == 0, sortie.stderr[-3000:]
    lignes = [ligne for ligne in sortie.stdout.splitlines() if ligne.startswith("{")]
    assert lignes, sortie.stdout[-2000:] + sortie.stderr[-2000:]
    rapport = json.loads(lignes[-1])
    assert "echec" not in rapport, rapport
    return rapport


def test_la_vraie_page_de_connexion_fonctionne_dans_jsdom(rapport_connexion_jsdom):
    assert rapport_connexion_jsdom["github"] == {
        "texte": "Continuer avec GitHub", "chemin": "/auth/github"}
    assert rapport_connexion_jsdom["oauth_vide"]
    assert rapport_connexion_jsdom["configuration_absente"]
    assert "Connexion annulée" in rapport_connexion_jsdom["refus"]
    assert rapport_connexion_jsdom["apres_affichage"] == ["text", "Masquer", "true"]
    assert rapport_connexion_jsdom["apres_masquage"] == ["password", "Afficher", "false"]
    assert rapport_connexion_jsdom["onglet"] == ["Créer un compte", "true"]
    assert rapport_connexion_jsdom["code_visible"]
    assert rapport_connexion_jsdom["erreurs"] == []


LOGIN = {"titre": "Se connecter", "code_masque": True, "lien": "Mot de passe oublié ?"}


def test_la_reprise_masque_les_fournisseurs_puis_ramene_a_la_connexion(
        rapport_connexion_jsdom):
    """Issue #75, M5 et M6 — sur la page qui A un fournisseur.

    Sans fournisseur la zone est vide de toute façon : on ne pourrait pas voir
    si elle est masquée. Et le SECOND clic est la seule sortie visible du mode
    reprise hors des onglets : ne cliquer qu'une fois laisse le retour non
    éprouvé.
    """
    assert rapport_connexion_jsdom["reprise_avant"] == {**LOGIN, "oauth_masque": False}
    assert rapport_connexion_jsdom["reprise_ouverte"] == {
        "titre": "Retrouver votre compte", "code_masque": False,
        "lien": "← Retour à la connexion", "oauth_masque": True}
    assert rapport_connexion_jsdom["reprise_fermee"] == {**LOGIN, "oauth_masque": False}


def test_un_fournisseur_ne_peut_ni_detourner_l_adresse_ni_injecter_du_balisage(
        rapport_connexion_jsdom):
    """Issue #75, M2 : le nom est ENCODÉ dans l'adresse, le libellé reste du texte."""
    assert rapport_connexion_jsdom["piege"] == {
        "chemin": "/auth/x%2Fy%3F%23",
        "texte": 'Continuer avec <img src="x" id="injecte">Piège',
        "injecte": False,
    }


def test_l_inclinaison_de_la_carte_obeit_a_la_reduction_de_mouvement(
        rapport_connexion_jsdom):
    """Issue #75, M10 : la moitié JavaScript de « réduction de mouvement ».

    Le CSS est gardé par des recherches de chaînes ; le script, lui, ne l'était
    par rien. Les DEUX sens sont exigés : sans le second, un script qui
    n'inclinerait jamais rien passerait pour respectueux.
    """
    assert rapport_connexion_jsdom["mouvement_reduit"] == {"present": True, "tilt": ["", ""]}
    # Pointeur à (150, 25) sur une zone de 200×100 : x = +0,25, y = -0,25, donc
    # 0,75° sur chaque axe. Une valeur EXACTE : « finit par deg » acceptait
    # « NaNdeg » et « -Infinitydeg », que le navigateur rejette (issue #80).
    assert rapport_connexion_jsdom["mouvement_libre"] == {
        "present": True, "tilt": ["0.75deg", "0.75deg"]}


def test_le_formulaire_reste_structure_et_nomme():
    assert '<label for="email">' in AUTH_HTML
    assert '<label for="password"' in AUTH_HTML
    assert 'autocomplete="current-password"' in AUTH_HTML
    assert 'aria-controls="password"' in AUTH_HTML
    assert 'role="tablist"' in AUTH_HTML
    assert 'id="auth-recovery"' in AUTH_HTML


def test_les_decors_sont_ignores_par_les_technologies_d_assistance():
    assert 'class="auth-backdrop" aria-hidden="true"' in AUTH_HTML
    assert 'class="console-ambient" aria-hidden="true"' in CONSOLE_HTML


def test_les_animations_respectent_la_reduction_de_mouvement():
    assert "@media(prefers-reduced-motion:reduce)" in AUTH_HTML
    assert "@media(prefers-reduced-motion:reduce)" in CONSOLE_HTML
    assert ".auth-backdrop::before,.auth-backdrop::after{animation:none}" in AUTH_HTML
    assert ".console-node{animation:none}" in CONSOLE_HTML


def test_l_accueil_a_un_ambient_visuel_discret_et_accessible():
    assert 'class="landing-network" aria-hidden="true"' in LANDING_HTML
    assert "@keyframes landing-node" in LANDING_HTML
    assert ".landing-node,.float-card{animation:none}" in LANDING_HTML
    assert "landing-node-f" in LANDING_HTML
    assert "console-node-f" in CONSOLE_HTML


def test_l_accueil_pointe_vers_le_depot_github_officiel():
    assert GITHUB_URL == "https://github.com/Bodichane/monl-compiler"
    assert f'href="{GITHUB_URL}" target="_blank" rel="noopener"' in LANDING_HTML
    assert "Voir le projet sur GitHub" in LANDING_HTML


def test_toutes_les_pages_recoivent_l_ambiance_partagee():
    html = page(title="Test", description="Test", body="<h1>Test</h1>")
    assert AMBIANCE_CSS in html
    assert 'class="site-ambient" aria-hidden="true"' in html
    assert "ambient-orbit-a" in html and "ambient-orbit-b" in html
    assert "@keyframes ambient-turn" in html
    assert ".ambient-orbit { animation:none !important; }" in html
