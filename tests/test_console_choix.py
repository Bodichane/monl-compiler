"""La console affiche-t-elle VRAIMENT des choix cliquables ? (point 171)

Chercher une chaîne dans du HTML ne distingue pas une page qui marche d'une
page morte — c'est le point 163, appris en trouvant deux pages qui n'avaient
jamais exécuté une ligne de JavaScript. Ce banc pilote donc la vraie page
avec jsdom, contre le vrai serveur, et compte les boutons réellement posés
dans le document.
"""

import json
import os
import shutil
import subprocess

import pytest

from monl.smoke_test.fondations import _ensure_jsdom, _jsdom_node_path
from tests.support.server import uvicorn_server

SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")

RUNNER = r"""
const { JSDOM } = require("jsdom");
const base = process.argv[2];

// Deux manques de jsdom, tous deux déjà payés (point 145) : sans `matchMedia`
// le script de la console meurt à sa PREMIÈRE ligne, et un `fetch` posé APRÈS
// construction n'est jamais vu par les scripts de la page — d'où `beforeParse`.
function equiper(w, jar) {
  w.matchMedia = w.matchMedia || (q => ({
    matches: false, media: q, onchange: null,
    addEventListener() {}, removeEventListener() {},
    addListener() {}, removeListener() {}, dispatchEvent() { return false; },
  }));
  w.fetch = (u, o) => {
    const options = Object.assign({}, o);
    options.headers = Object.assign({}, options.headers, { cookie: jar });
    return fetch(new URL(u, base), options);
  };
}

(async () => {
  const inscription = await fetch(base + "/api/auth/register", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ email: "choix@example.test", password: "MotDePasse-123" }),
  });
  if (inscription.status !== 201) throw new Error("inscription " + inscription.status);
  const jar = inscription.headers.getSetCookie()
    .map(c => c.split(";")[0]).join("; ");

  const html = await (await fetch(base + "/console", { headers: { cookie: jar } })).text();
  const dom = new JSDOM(html, {
    url: base + "/console", runScripts: "dangerously", pretendToBeVisual: true,
    beforeParse: w => equiper(w, jar),
  });
  const doc = dom.window.document;
  await new Promise(r => setTimeout(r, 600));

  const rapport = { erreurs: [] };
  dom.window.addEventListener("error", e => rapport.erreurs.push(String(e.message)));

  doc.querySelector("#dialogue-start button").click();
  await new Promise(r => setTimeout(r, 1500));

  const boutons = [...doc.querySelectorAll(".dialogue-choice")];
  rapport.nb_choix = boutons.length;
  rapport.intitule = (doc.querySelector("#dialogue-question").textContent || "").trim();
  rapport.premier = boutons.length ? {
    rang: boutons[0].querySelector(".dialogue-choice-num").textContent,
    libelle: boutons[0].querySelector(".dialogue-choice-label").textContent,
    aide: (boutons[0].querySelector(".dialogue-choice-hint") || {}).textContent || "",
  } : null;

  // Un clic doit RÉPONDRE : la question suivante remplace celle-ci.
  if (boutons.length > 2) {
    boutons[2].click();
    await new Promise(r => setTimeout(r, 1500));
    rapport.apres_clic = (doc.querySelector("#dialogue-question").textContent || "").trim();
    rapport.choix_apres_clic = doc.querySelectorAll(".dialogue-choice").length;
  }
  console.log(JSON.stringify(rapport));
})().catch(e => { console.log(JSON.stringify({ echec: String(e) })); });
"""


@pytest.fixture(scope="module")
def rapport_jsdom(tmp_path_factory):
    if shutil.which("node") is None:
        pytest.fail("node est requis : un saut ne dirait pas « rien à vérifier »")
    racine = tmp_path_factory.mktemp("console-choix")
    # jsdom vit dans le cache utilisateur (~/.monl/jsdom), comme pour le smoke
    # test. Son absence fait ÉCHOUER : un saut ne dit pas « rien à vérifier
    # ici », il dit « je n'ai pas vérifié » (point 140).
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
            ["node", str(racine / "runner.js"), base],
            capture_output=True, text=True, timeout=180, env=env,
        )
    assert sortie.returncode == 0, sortie.stderr[-3000:]
    ligne = [ligne for ligne in sortie.stdout.splitlines() if ligne.startswith("{")]
    assert ligne, sortie.stdout[-2000:] + sortie.stderr[-2000:]
    rapport = json.loads(ligne[-1])
    assert "echec" not in rapport, rapport["echec"]
    return rapport


def test_les_onze_modeles_sont_onze_boutons_et_pas_un_bloc_de_texte(rapport_jsdom):
    assert rapport_jsdom["nb_choix"] == 11, rapport_jsdom


def test_l_intitule_ne_repete_pas_le_menu_de_terminal(rapport_jsdom):
    intitule = rapport_jsdom["intitule"]
    assert intitule == "Quel type d'application construisez-vous ?", intitule
    assert "[1]" not in intitule


def test_chaque_bouton_porte_son_rang_son_nom_et_son_aide(rapport_jsdom):
    premier = rapport_jsdom["premier"]
    assert premier["rang"] == "1"
    assert premier["libelle"] == "Portfolio / site vitrine"
    # L'aide dit AUSSI si les visiteurs auront un compte — la question que la
    # console ne posait nulle part.
    assert "comptes créés par l" in premier["aide"], premier["aide"]


def test_un_clic_repond_et_fait_avancer_le_dialogue(rapport_jsdom):
    """Sans ça, on aurait onze beaux boutons qui ne font rien."""
    assert rapport_jsdom["apres_clic"] != rapport_jsdom["intitule"], rapport_jsdom
