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

function equiper(w, base) {
  w.matchMedia = w.matchMedia || (q => ({
    matches: false, media: q, onchange: null,
    addEventListener() {}, removeEventListener() {},
    addListener() {}, removeListener() {}, dispatchEvent() { return false; },
  }));
  w.fetch = (u, o) => fetch(new URL(u, base), o);
  w.addEventListener("error", e => erreurs.push(String(e.message)));
}

async function charger(base, chemin) {
  const html = await (await fetch(base + chemin)).text();
  const virtuelle = new VirtualConsole();
  virtuelle.on("jsdomError", e => erreurs.push(String(e.message)));
  virtuelle.on("error", (...m) => erreurs.push(m.map(String).join(" ")));
  const dom = new JSDOM(html, {
    url: base + chemin, runScripts: "dangerously", pretendToBeVisual: true,
    virtualConsole: virtuelle, beforeParse: w => equiper(w, base),
  });
  await new Promise(r => setTimeout(r, 600));
  return dom;
}

(async () => {
  const github = await charger(avecGithub, "/login");
  const lien = github.window.document.querySelector("#oauth-zone a");

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
