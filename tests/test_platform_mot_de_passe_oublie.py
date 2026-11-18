"""Un mot de passe perdu se reprend DEPUIS LA PAGE, pas depuis l'API seule.

Le mécanisme de codes de secours est complet depuis le point 142 : la route
`/api/auth/recover` consomme un code dans la transaction du changement de mot
de passe, ferme les sessions, et refuse à l'identique un code faux, une adresse
inconnue et un mot de passe trop court.

Il lui manquait un CONSOMMATEUR. Mesuré contre la vraie plateforme : la page
`/login` ne portait aucun lien, aucun champ, aucune mention — la seule façon
d'employer ses codes était de connaître l'API et de forger la requête à la
main. C'est le point 146 par l'autre bout : une brique que rien n'offre
n'existe pas pour la personne qui en a besoin.

Ce banc pilote donc la VRAIE page avec jsdom, contre le VRAI serveur. Chercher
une chaîne dans du HTML ne distingue pas une page qui marche d'une page morte
(point 163) : on clique, on remplit, on envoie, et on regarde ce que le
serveur a réellement accepté ensuite.
"""

import json
import os
import shutil
import subprocess

import pytest

from monl.smoke_test.fondations import _ensure_jsdom, _jsdom_node_path
from tests.support.server import uvicorn_server

SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")

ANCIEN = "MotDePasseInitial-2026"
NOUVEAU = "MotDePasseRepris-2026"

RUNNER = r"""
const { JSDOM } = require("jsdom");
const base = process.argv[2];
const ANCIEN = process.argv[3], NOUVEAU = process.argv[4];

// Sans `matchMedia`, le script de la page meurt à sa première ligne et on
// mesurerait le banc au lieu du produit (point 145). Le `fetch` doit être posé
// AVANT l'analyse du document, sinon les scripts de la page ne le voient pas.
function equiper(w) {
  w.matchMedia = w.matchMedia || (q => ({
    matches: false, media: q, onchange: null,
    addEventListener() {}, removeEventListener() {},
    addListener() {}, removeListener() {}, dispatchEvent() { return false; },
  }));
  w.fetch = (u, o) => fetch(new URL(u, base), o);
}

(async () => {
  const rapport = { erreurs: [] };

  const inscription = await fetch(base + "/api/auth/register", {
    method: "POST", headers: { "content-type": "application/json" },
    body: JSON.stringify({ email: "oubli@example.test", password: ANCIEN }),
  });
  if (inscription.status !== 201) throw new Error("inscription " + inscription.status);
  const codes = (await inscription.json()).recovery_codes;
  rapport.nb_codes = codes.length;

  const html = await (await fetch(base + "/login")).text();
  const dom = new JSDOM(html, {
    url: base + "/login", runScripts: "dangerously", pretendToBeVisual: true,
    beforeParse: equiper,
  });
  const doc = dom.window.document;
  dom.window.addEventListener("error", e => rapport.erreurs.push(String(e.message)));
  await new Promise(r => setTimeout(r, 400));

  // Le chemin doit exister comme un BOUTON, pas comme une phrase.
  const onglet = doc.querySelector('[data-mode="recover"]');
  rapport.onglet_present = Boolean(onglet);
  const champCode = doc.querySelector("#champ-code");
  rapport.code_masque_avant = champCode.classList.contains("masque");
  rapport.code_requis_avant = doc.querySelector("#code").required;

  onglet.click();
  await new Promise(r => setTimeout(r, 200));
  rapport.code_visible_apres = !champCode.classList.contains("masque");
  rapport.code_requis_apres = doc.querySelector("#code").required;
  rapport.titre = (doc.querySelector("#auth-title").textContent || "").trim();
  rapport.bouton = (doc.querySelector("#submit-label").textContent || "").trim();
  rapport.label_motdepasse = (doc.querySelector("#password-label").textContent || "").trim();
  rapport.aide_visible = !doc.querySelector("#auth-secours").hidden;

  // Un code FAUX doit afficher le refus, sans bloquer la page.
  doc.querySelector("#email").value = "oubli@example.test";
  doc.querySelector("#code").value = "code-qui-nexiste-pas";
  doc.querySelector("#password").value = NOUVEAU;
  doc.querySelector("#auth-form").dispatchEvent(new dom.window.Event("submit"));
  await new Promise(r => setTimeout(r, 900));
  rapport.erreur_affichee = doc.querySelector("#auth-error").className.includes("show");
  rapport.texte_erreur = (doc.querySelector("#auth-error").textContent || "").trim();

  // Le VRAI code : la page doit revenir en mode connexion et le dire.
  doc.querySelector("#code").value = codes[0];
  doc.querySelector("#password").value = NOUVEAU;
  doc.querySelector("#auth-form").dispatchEvent(new dom.window.Event("submit"));
  await new Promise(r => setTimeout(r, 900));
  rapport.succes_affiche = doc.querySelector("#auth-succes").className.includes("show");
  rapport.texte_succes = (doc.querySelector("#auth-succes").textContent || "").trim();
  rapport.revenu_en_connexion = (doc.querySelector("#auth-title").textContent || "").trim();
  rapport.code_vide_apres = doc.querySelector("#code").value === "";
  rapport.email_conserve = doc.querySelector("#email").value;

  // Ce que le SERVEUR a réellement accepté : la seule preuve qui compte.
  const avec_nouveau = await fetch(base + "/api/auth/login", {
    method: "POST", headers: { "content-type": "application/json" },
    body: JSON.stringify({ email: "oubli@example.test", password: NOUVEAU }),
  });
  rapport.login_nouveau = avec_nouveau.status;
  const avec_ancien = await fetch(base + "/api/auth/login", {
    method: "POST", headers: { "content-type": "application/json" },
    body: JSON.stringify({ email: "oubli@example.test", password: ANCIEN }),
  });
  rapport.login_ancien = avec_ancien.status;

  console.log(JSON.stringify(rapport));
})().catch(e => { console.log(JSON.stringify({ echec: String(e) })); });
"""


@pytest.fixture(scope="module")
def parcours(tmp_path_factory):
    if shutil.which("node") is None:
        pytest.fail("node est requis : un saut ne dirait pas « rien à vérifier »")
    racine = tmp_path_factory.mktemp("mot-de-passe-oublie")
    assert _ensure_jsdom(str(racine), lambda *_: None), (
        "jsdom introuvable et non installable dans ~/.monl/jsdom")
    (racine / "runner.js").write_text(RUNNER, encoding="utf-8")
    env = dict(os.environ)
    env["MONL_PLATFORM_WORKSPACE"] = str(racine / "projects")
    env["PYTHONPATH"] = SRC + os.pathsep + env.get("PYTHONPATH", "")
    env["NODE_PATH"] = _jsdom_node_path()
    with uvicorn_server(str(racine), env=env, module="monl_platform.app:app",
                        ready_path="/health") as base:
        sortie = subprocess.run(
            ["node", str(racine / "runner.js"), base, ANCIEN, NOUVEAU],
            capture_output=True, text=True, timeout=180, env=env)
    assert sortie.returncode == 0, sortie.stderr[-3000:]
    lignes = [ligne for ligne in sortie.stdout.splitlines()
              if ligne.startswith("{")]
    assert lignes, sortie.stdout[-2000:] + sortie.stderr[-2000:]
    rapport = json.loads(lignes[-1])
    assert "echec" not in rapport, rapport["echec"]
    return rapport


def test_la_page_de_connexion_offre_le_chemin(parcours):
    """LE défaut : le mécanisme existait, la page n'en disait rien."""
    assert parcours["onglet_present"], (
        "aucun moyen d'employer ses codes depuis la page — il faudrait "
        "connaître l'API et forger la requête à la main")
    assert parcours["titre"] == "Recover your account", parcours["titre"]
    assert parcours["bouton"] == "Change the password", parcours["bouton"]
    assert parcours["label_motdepasse"] == "New password"


def test_le_champ_de_code_suit_le_mode_choisi(parcours):
    """`required` doit suivre l'AFFICHAGE.

    Un champ obligatoire mais masqué fait échouer la validation sur un champ
    que personne ne peut ni voir ni corriger : le bouton semble ne rien faire,
    exactement le défaut que `novalidate` a déjà servi à réparer sur cette page.
    """
    assert parcours["code_masque_avant"], "le code est demandé dès la connexion"
    assert not parcours["code_requis_avant"], (
        "un champ masqué est obligatoire : la connexion ordinaire ne partira plus")
    assert parcours["code_visible_apres"] and parcours["code_requis_apres"]
    assert parcours["aide_visible"], (
        "la page ne dit pas quoi faire à qui n'a plus aucun code")


def test_un_code_faux_affiche_le_refus_sans_casser_la_page(parcours):
    assert parcours["erreur_affichee"], parcours
    assert parcours["texte_erreur"], "refus muet : la personne ne saura pas pourquoi"
    assert parcours["erreurs"] == [], parcours["erreurs"]


def test_un_code_valide_change_le_mot_de_passe_pour_de_vrai(parcours):
    """La preuve est ce que le SERVEUR accepte ensuite, pas ce que la page dit.

    Le 204 de la reprise n'a PAS de corps : en demander le JSON lèverait sur le
    seul cas qui réussit, et la personne verrait une erreur après avoir brûlé
    un de ses huit codes.
    """
    assert parcours["login_nouveau"] == 200, parcours
    assert parcours["login_ancien"] == 401, "l'ancien mot de passe fonctionne encore"


def test_la_page_ramene_a_la_connexion_et_le_dit(parcours):
    """Sans message, un 204 silencieux ressemble à un formulaire qui n'a rien fait."""
    assert parcours["succes_affiche"], parcours
    assert "Sign in with the new password" in parcours["texte_succes"], parcours["texte_succes"]
    assert parcours["revenu_en_connexion"] == "Sign in"
    assert parcours["code_vide_apres"], "le code consommé reste dans le formulaire"
    assert parcours["email_conserve"] == "oubli@example.test", (
        "l'adresse est perdue : il faut la retaper pour se connecter")
