"""Does the console REALLY show clickable choices? (point 171)

Looking for a string in HTML cannot tell a working page from a dead one —
that is point 163, learned by finding two pages that had never run a line of
JavaScript. This bench therefore drives the real page with jsdom, against
the real server, and counts the buttons really put in the document.
"""

import json
import os
import shutil
import subprocess

import pytest

from monl.smoke_test.foundations import _ensure_jsdom, _jsdom_node_path
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
def report_jsdom(tmp_path_factory):
    if shutil.which("node") is None:
        pytest.fail("node is required: a skip would not say \"nothing to check\"")
    racine = tmp_path_factory.mktemp("console-choix")
    # jsdom lives in the user cache (~/.monl/jsdom), as for the smoke test. Its
    # absence makes the test FAIL: a skip does not say "nothing to check here",
    # it says "I did not check" (point 140).
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
            ["node", str(racine / "runner.js"), base],
            capture_output=True, text=True, timeout=180, env=env,
        )
    assert output.returncode == 0, output.stderr[-3000:]
    line = [line for line in output.stdout.splitlines() if line.startswith("{")]
    assert line, output.stdout[-2000:] + output.stderr[-2000:]
    rapport = json.loads(line[-1])
    assert "echec" not in rapport, rapport["echec"]
    return rapport


def test_the_eleven_templates_are_eleven_buttons_not_a_text_block(report_jsdom):
    assert report_jsdom["nb_choix"] == 11, report_jsdom


def test_the_title_does_not_repeat_the_terminal_menu(report_jsdom):
    label = report_jsdom["intitule"]
    assert label == "What type of application are you building?", label
    assert "[1]" not in label


def test_each_button_carries_its_rank_name_and_help(report_jsdom):
    first = report_jsdom["premier"]
    assert first["rang"] == "1"
    assert first["libelle"] == "Portfolio / showcase site"
    # The help ALSO says whether visitors will have an account — the question
    # the console asked nowhere.
    assert "accounts created by the" in first["aide"], first["aide"]


def test_a_click_answers_and_advances_the_dialogue(report_jsdom):
    """Without this, we would have eleven fine buttons that do nothing."""
    assert report_jsdom["apres_clic"] != report_jsdom["intitule"], report_jsdom
