"""A lost password is recovered FROM THE PAGE, not from the API alone.

The recovery code mechanism has been complete since point 142: the route
`/api/auth/recover` consumes a code in the password-change transaction,
closes the sessions, and refuses identically a wrong code, an unknown address
and a too-short password.

It lacked a CONSUMER. Measured against the real platform: the `/login` page
carried no link, no field, no mention — the only way to use one's codes was
to know the API and forge the request by hand. It is point 146 from the other
end: a brick nothing offers does not exist for the person who needs it.

This bench therefore drives the REAL page with jsdom, against the REAL
server. Looking for a string in HTML cannot tell a working page from a dead
one (point 163): we click, fill in, send, and look at what the server really
accepted afterwards.
"""

import json
import os
import shutil
import subprocess

import pytest

from monl.smoke_test.foundations import _ensure_jsdom, _jsdom_node_path
from tests.support.server import uvicorn_server

SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")

OLD = "MotDePasseInitial-2026"
NEW = "MotDePasseRepris-2026"

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
def walk(tmp_path_factory):
    if shutil.which("node") is None:
        pytest.fail("node is required: a skip would not say \"nothing to check\"")
    racine = tmp_path_factory.mktemp("mot-de-passe-oublie")
    assert _ensure_jsdom(str(racine), lambda *_: None), (
        "jsdom not found and not installable in ~/.monl/jsdom")
    (racine / "runner.js").write_text(RUNNER, encoding="utf-8")
    env = dict(os.environ)
    env["MONL_PLATFORM_WORKSPACE"] = str(racine / "projects")
    env["PYTHONPATH"] = SRC + os.pathsep + env.get("PYTHONPATH", "")
    env["NODE_PATH"] = _jsdom_node_path()
    with uvicorn_server(str(racine), env=env, module="monl_platform.app:app",
                        ready_path="/health") as base:
        output = subprocess.run(
            ["node", str(racine / "runner.js"), base, OLD, NEW],
            capture_output=True, text=True, timeout=180, env=env)
    assert output.returncode == 0, output.stderr[-3000:]
    lines = [line for line in output.stdout.splitlines()
              if line.startswith("{")]
    assert lines, output.stdout[-2000:] + output.stderr[-2000:]
    rapport = json.loads(lines[-1])
    assert "echec" not in rapport, rapport["echec"]
    return rapport


def test_the_login_page_offers_the_path(walk):
    """THE defect: the mechanism existed, the page said nothing about it."""
    assert walk["onglet_present"], (
        "no way to use one's codes from the page — one would have to "
        "know the API and forge the request by hand")
    assert walk["titre"] == "Recover your account", walk["titre"]
    assert walk["bouton"] == "Change the password", walk["bouton"]
    assert walk["label_motdepasse"] == "New password"


def test_the_code_field_follows_the_chosen_mode(walk):
    """`required` must follow what is DISPLAYED.

    A required but hidden field makes validation fail on a field nobody can
    see or fix: the button seems to do nothing, exactly the defect `novalidate`
    already served to fix on this page.
    """
    assert walk["code_masque_avant"], "the code is asked right at login"
    assert not walk["code_requis_avant"], (
        "a hidden field is required: ordinary login will no longer go out")
    assert walk["code_visible_apres"] and walk["code_requis_apres"]
    assert walk["aide_visible"], (
        "the page does not say what to do to whoever has no code left")


def test_a_wrong_code_shows_the_refusal_without_breaking_the_page(walk):
    assert walk["erreur_affichee"], walk
    assert walk["texte_erreur"], "mute refusal: the person will not know why"
    assert walk["erreurs"] == [], walk["erreurs"]


def test_a_valid_code_really_changes_the_password(walk):
    """The proof is what the SERVER accepts afterwards, not what the page says.

    The recovery's 204 has NO body: asking for its JSON would raise on the only
    case that succeeds, and the person would see an error after burning one of
    their eight codes.
    """
    assert walk["login_nouveau"] == 200, walk
    assert walk["login_ancien"] == 401, "l'ancien mot de passe fonctionne encore"


def test_the_page_returns_to_login_and_says_so(walk):
    """Without a message, a silent 204 looks like a form that did nothing."""
    assert walk["succes_affiche"], walk
    assert "Sign in with the new password" in walk["texte_succes"], walk["texte_succes"]
    assert walk["revenu_en_connexion"] == "Sign in"
    assert walk["code_vide_apres"], "the consumed code stays in the form"
    assert walk["email_conserve"] == "oubli@example.test", (
        "the address is lost: it must be retyped to log in")
