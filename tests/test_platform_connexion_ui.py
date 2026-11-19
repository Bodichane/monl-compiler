"""The front door works in a real DOM against a real server."""

import json
import os
import shutil
import subprocess

import pytest

from monl.smoke_test.foundations import _ensure_jsdom, _jsdom_node_path
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
        pytest.fail("node is required: a skip would not say \"nothing to check\"")
    assert _ensure_jsdom(str(tmp_path), lambda *_: None), (
        "jsdom not found and not installable in ~/.monl/jsdom")
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


def test_the_real_login_page_works_in_jsdom(rapport_connexion_jsdom):
    assert rapport_connexion_jsdom["github"] == {
        "texte": "Continue with GitHub", "chemin": "/auth/github"}
    assert rapport_connexion_jsdom["oauth_vide"]
    assert rapport_connexion_jsdom["configuration_absente"]
    assert "Sign-in cancelled" in rapport_connexion_jsdom["refus"]
    assert rapport_connexion_jsdom["apres_affichage"] == ["text", "Hide", "true"]
    assert rapport_connexion_jsdom["apres_masquage"] == ["password", "Show", "false"]
    assert rapport_connexion_jsdom["onglet"] == ["Create an account", "true"]
    assert rapport_connexion_jsdom["code_visible"]
    assert rapport_connexion_jsdom["erreurs"] == []


LOGIN = {"titre": "Sign in", "code_masque": True, "lien": "Forgot your password?"}


def test_recovery_hides_providers_then_returns_to_login(
        rapport_connexion_jsdom):
    """Issue #75, M5 and M6 — on the page that HAS a provider.

    Without a provider the area is empty anyway: one could not see whether it is
    hidden. And the SECOND click is the only visible way out of recovery mode
    outside the tabs: clicking only once leaves the way back untested.
    """
    assert rapport_connexion_jsdom["reprise_avant"] == {**LOGIN, "oauth_masque": False}
    assert rapport_connexion_jsdom["reprise_ouverte"] == {
        "titre": "Recover your account", "code_masque": False,
        "lien": "← Back to sign in", "oauth_masque": True}
    assert rapport_connexion_jsdom["reprise_fermee"] == {**LOGIN, "oauth_masque": False}


def test_a_provider_can_neither_hijack_the_address_nor_inject_markup(
        rapport_connexion_jsdom):
    """Issue #75, M2: the name is ENCODED in the address, the label stays text."""
    assert rapport_connexion_jsdom["piege"] == {
        "chemin": "/auth/x%2Fy%3F%23",
        "texte": 'Continue with <img src="x" id="injecte">Piège',
        "injecte": False,
    }


def test_the_card_tilt_obeys_reduced_motion(
        rapport_connexion_jsdom):
    """Issue #75, M10: the JavaScript half of "reduced motion".

    The CSS is guarded by string searches; the script was guarded by nothing.
    BOTH directions are required: without the second, a script that never
    tilted anything would pass for respectful.
    """
    assert rapport_connexion_jsdom["mouvement_reduit"] == {"present": True, "tilt": ["", ""]}
    # Pointer at (150, 25) on a 200×100 area: x = +0.25, y = -0.25, hence 0.75°
    # on each axis. An EXACT value: "ends with deg" accepted "NaNdeg" and
    # "-Infinitydeg", which the browser rejects (issue #80).
    assert rapport_connexion_jsdom["mouvement_libre"] == {
        "present": True, "tilt": ["0.75deg", "0.75deg"]}


def test_the_form_stays_structured_and_named():
    assert '<label for="email">' in AUTH_HTML
    assert '<label for="password"' in AUTH_HTML
    assert 'autocomplete="current-password"' in AUTH_HTML
    assert 'aria-controls="password"' in AUTH_HTML
    assert 'role="tablist"' in AUTH_HTML
    assert 'id="auth-recovery"' in AUTH_HTML


def test_decorations_are_ignored_by_assistive_technologies():
    assert 'class="auth-backdrop" aria-hidden="true"' in AUTH_HTML
    assert 'class="console-ambient" aria-hidden="true"' in CONSOLE_HTML


def test_animations_respect_reduced_motion():
    assert "@media(prefers-reduced-motion:reduce)" in AUTH_HTML
    assert "@media(prefers-reduced-motion:reduce)" in CONSOLE_HTML
    assert ".auth-backdrop::before,.auth-backdrop::after{animation:none}" in AUTH_HTML
    assert ".console-node{animation:none}" in CONSOLE_HTML


def test_the_home_page_has_a_discreet_accessible_visual_ambiance():
    assert 'class="landing-network" aria-hidden="true"' in LANDING_HTML
    assert "@keyframes landing-node" in LANDING_HTML
    assert ".landing-node,.float-card{animation:none}" in LANDING_HTML
    assert "landing-node-f" in LANDING_HTML
    assert "console-node-f" in CONSOLE_HTML


def test_the_home_page_points_to_the_official_github_repository():
    assert GITHUB_URL == "https://github.com/Bodichane/monl-compiler"
    assert f'href="{GITHUB_URL}" target="_blank" rel="noopener"' in LANDING_HTML
    assert "View the project on GitHub" in LANDING_HTML


def test_every_page_gets_the_shared_ambiance():
    html = page(title="Test", description="Test", body="<h1>Test</h1>")
    assert AMBIANCE_CSS in html
    assert 'class="site-ambient" aria-hidden="true"' in html
    assert "ambient-orbit-a" in html and "ambient-orbit-b" in html
    assert "@keyframes ambient-turn" in html
    assert ".ambient-orbit { animation:none !important; }" in html
