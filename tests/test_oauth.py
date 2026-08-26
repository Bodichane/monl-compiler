"""Connexion par Google ou GitHub, éprouvée contre un faux fournisseur.

La plateforme dépense de l'argent réel à chaque construction : un compte
ouvert avec une chaîne quelconque est une porte d'abus. Elle n'envoie pour
autant AUCUN message — la frontière du point 95 tient — elle délègue à un
fournisseur qui a déjà vérifié l'adresse.

Le faux fournisseur est embarqué ici, comme le faux Stripe de
`tests/test_paiement.py` : sans lui, la brique ne serait éprouvable qu'en
appelant le vrai GitHub, c'est-à-dire jamais.
"""

import json
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import pytest
import requests
import uvicorn

from monl_platform.app import create_app
from monl_platform.oauth import (
    OAuthError,
    OAuthNotConfigured,
    authorize_url,
    check_state,
    configured_providers,
    make_state,
    redirect_uri,
)

SECRET = "secret-de-plateforme-pour-les-tests-oauth-123456"


def _free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class FakeProvider:
    provider_name = "test"
    model = "test-model"

    def __call__(self, _prompt):  # pragma: no cover - jamais appelé ici
        raise AssertionError("la connexion n'appelle aucune IA")


# ───────────────────────────────────────────── le faux GitHub embarqué ──
class _FauxGitHub(BaseHTTPRequestHandler):
    #: Ce que le compte renverra. Modifié par les tests pour éprouver le
    #: refus d'une adresse NON vérifiée.
    verifiee = True
    codes_vus = []

    def log_message(self, *_args):
        pass

    def _json(self, charge, code=200):
        corps = json.dumps(charge).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(corps)))
        self.end_headers()
        self.wfile.write(corps)

    def do_POST(self):
        chemin = urlparse(self.path).path
        taille = int(self.headers.get("Content-Length") or 0)
        champs = parse_qs(self.rfile.read(taille).decode("utf-8"))
        if chemin == "/login/oauth/access_token":
            type(self).codes_vus.append(champs.get("code", [""])[0])
            if champs.get("code", [""])[0] == "mauvais":
                return self._json({"error": "bad_verification_code"})
            return self._json({"access_token": "jeton-fournisseur"})
        return self._json({"error": "not_found"}, 404)

    def do_GET(self):
        chemin = urlparse(self.path).path
        if self.headers.get("Authorization") != "Bearer jeton-fournisseur":
            return self._json({"message": "Bad credentials"}, 401)
        if chemin == "/user":
            return self._json({"id": 4242, "login": "alice"})
        if chemin == "/user/emails":
            return self._json([
                {"email": "autre@exemple.test", "primary": False, "verified": True},
                {"email": "alice@exemple.test", "primary": True,
                 "verified": type(self).verifiee},
            ])
        return self._json({"message": "not_found"}, 404)


@pytest.fixture()
def faux_github():
    _FauxGitHub.verifiee = True
    _FauxGitHub.codes_vus = []
    serveur = ThreadingHTTPServer(("127.0.0.1", _free_port()), _FauxGitHub)
    fil = threading.Thread(target=serveur.serve_forever, daemon=True)
    fil.start()
    try:
        yield f"http://127.0.0.1:{serveur.server_address[1]}"
    finally:
        serveur.shutdown()
        serveur.server_close()


@pytest.fixture()
def plateforme(tmp_path, faux_github, monkeypatch):
    monkeypatch.setenv("MONL_OAUTH_GITHUB_CLIENT_ID", "identifiant-client")
    monkeypatch.setenv("MONL_OAUTH_GITHUB_SECRET", "secret-client")
    monkeypatch.setenv("MONL_OAUTH_GITHUB_BASE_URL", faux_github)
    monkeypatch.setenv("MONL_PLATFORM_OAUTH_STATE_SECRET", SECRET)
    port = _free_port()
    monkeypatch.setenv("MONL_PLATFORM_PUBLIC_URL", f"http://127.0.0.1:{port}")
    app = create_app(
        workspace=tmp_path / "projects",
        domain="localhost",
        provider=FakeProvider(),
        poll_interval=0.01,
        start_worker=False,
    )
    serveur = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
    fil = threading.Thread(target=serveur.run, daemon=True)
    fil.start()
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(200):
            try:
                if requests.get(f"{base}/health", timeout=0.2).status_code == 200:
                    break
            except requests.RequestException:
                time.sleep(0.02)
        else:
            pytest.fail("la plateforme n'a pas démarré")
        yield base
    finally:
        serveur.should_exit = True
        fil.join(timeout=10)


def _aller(base):
    """Suit le départ et rend le `state` que la plateforme a émis."""
    depart = requests.get(f"{base}/auth/github", allow_redirects=False, timeout=10)
    assert depart.status_code == 307, depart.text
    return parse_qs(urlparse(depart.headers["location"]).query)["state"][0]


# ────────────────────────────────────────────────────── configuration ──
def test_un_fournisseur_sans_secret_n_est_pas_propose():
    """Un bouton qui mène à un 503 est pire que pas de bouton."""
    assert configured_providers({}) == []
    assert configured_providers({"MONL_OAUTH_GITHUB_CLIENT_ID": "x"}) == []
    prets = configured_providers({
        "MONL_OAUTH_GITHUB_CLIENT_ID": "x", "MONL_OAUTH_GITHUB_SECRET": "y"})
    assert [p["name"] for p in prets] == ["github"]


def test_une_variable_absente_est_NOMMEE(monkeypatch):
    monkeypatch.delenv("MONL_OAUTH_GOOGLE_CLIENT_ID", raising=False)
    with pytest.raises(OAuthNotConfigured) as faute:
        authorize_url("google", "peu-importe", {})
    assert faute.value.variable == "MONL_OAUTH_GOOGLE_CLIENT_ID"
    assert faute.value.status_code == 503


def test_l_adresse_de_retour_vient_de_la_configuration():
    """Jamais de l'en-tête Host : il est fourni par le client, et le lire
    laisserait détourner l'aller-retour vers un domaine choisi ailleurs."""
    env = {"MONL_PLATFORM_PUBLIC_URL": "https://monl.example/"}

    assert redirect_uri("github", env) == "https://monl.example/auth/github/retour"
    with pytest.raises(OAuthNotConfigured):
        redirect_uri("github", {})


# ────────────────────────────────────────────────────────────── state ──
def test_un_etat_forge_est_refuse():
    with pytest.raises(OAuthError, match="non signé"):
        check_state("github.1700000000.abcd.faux", "github", SECRET)


def test_un_etat_d_un_autre_fournisseur_est_refuse():
    etat = make_state("google", SECRET)
    with pytest.raises(OAuthError, match="autre fournisseur"):
        check_state(etat, "github", SECRET)


def test_un_etat_perime_est_refuse():
    """Sans date, un aller capté une fois resterait rejouable indéfiniment —
    même raisonnement que la signature datée du webhook de paiement."""
    etat = make_state("github", SECRET, maintenant=1_700_000_000)

    assert check_state(etat, "github", SECRET, maintenant=1_700_000_300)
    with pytest.raises(OAuthError, match="expirée"):
        check_state(etat, "github", SECRET, maintenant=1_700_001_000)


def test_un_etat_signe_par_un_autre_serveur_est_refuse():
    etat = make_state("github", "un-autre-secret-de-plateforme-tout-autre")
    with pytest.raises(OAuthError, match="non signé"):
        check_state(etat, "github", SECRET)


# ─────────────────────────────────────── l'aller-retour, en vrai HTTP ──
def test_le_depart_mene_au_fournisseur_avec_un_etat_signe(plateforme):
    depart = requests.get(f"{plateforme}/auth/github", allow_redirects=False,
                          timeout=10)

    assert depart.status_code == 307
    params = parse_qs(urlparse(depart.headers["location"]).query)
    assert params["client_id"] == ["identifiant-client"]
    assert params["redirect_uri"] == [f"{plateforme}/auth/github/retour"]
    assert check_state(params["state"][0], "github", SECRET)


def test_un_aller_retour_complet_ouvre_une_session(plateforme):
    session = requests.Session()
    depart = session.get(f"{plateforme}/auth/github", allow_redirects=False, timeout=10)
    etat = parse_qs(urlparse(depart.headers["location"]).query)["state"][0]

    retour = session.get(
        f"{plateforme}/auth/github/retour",
        params={"code": "bon-code", "state": etat},
        allow_redirects=False,
        timeout=10,
    )

    assert retour.status_code == 303, retour.text
    assert retour.headers["location"] == "/console"
    assert "monl_session" in session.cookies
    compte = session.get(f"{plateforme}/api/auth/me", timeout=10)
    assert compte.status_code == 200, compte.text
    assert compte.json()["email"] == "github:4242"
    assert session.get(f"{plateforme}/console", timeout=10).status_code == 200


def test_deux_connexions_ne_creent_qu_un_compte(plateforme):
    session = requests.Session()
    for _ in range(2):
        depart = session.get(f"{plateforme}/auth/github", allow_redirects=False, timeout=10)
        etat = parse_qs(urlparse(depart.headers["location"]).query)["state"][0]
        retour = session.get(
            f"{plateforme}/auth/github/retour",
            params={"code": "bon", "state": etat},
            allow_redirects=False,
            timeout=10,
        )
        assert retour.status_code == 303
    compte = session.get(f"{plateforme}/api/auth/me", timeout=10).json()
    assert compte["email"] == "github:4242"
    assert len(session.cookies.get_dict()) == 1, "la session OAuth n'est pas unique"


def test_une_adresse_non_verifiee_est_refusee(plateforme):
    """Sans ce contrôle, la brique ne vérifierait rien : elle déplacerait la
    chaîne quelconque d'un formulaire vers un autre."""
    _FauxGitHub.verifiee = False
    etat = _aller(plateforme)

    retour = requests.get(f"{plateforme}/auth/github/retour",
                          params={"code": "bon", "state": etat},
                          allow_redirects=False, timeout=10)

    assert retour.status_code == 403, retour.text
    assert "vérifiée" in retour.json()["detail"]


def test_un_retour_sans_etat_valide_n_ouvre_rien(plateforme):
    """La contre-épreuve du CSRF : un tiers qui déclenche le retour depuis
    son propre site n'a pas d'état signé par nous."""
    retour = requests.get(f"{plateforme}/auth/github/retour",
                          params={"code": "bon", "state": "github.1.2.3"},
                          allow_redirects=False, timeout=10)

    assert retour.status_code == 400
    assert "location" not in {k.lower() for k in retour.headers}


def test_un_refus_de_l_usager_n_est_pas_une_panne(plateforme):
    retour = requests.get(f"{plateforme}/auth/github/retour",
                          params={"error": "access_denied"},
                          allow_redirects=False, timeout=10)

    assert retour.status_code == 303
    assert retour.headers["location"] == "/console#erreur=refus"


def test_un_compte_de_fournisseur_ne_se_connecte_pas_par_mot_de_passe(plateforme):
    """Il n'a AUCUN mot de passe : `None` ne doit jamais devenir une porte."""
    etat = _aller(plateforme)
    requests.get(f"{plateforme}/auth/github/retour",
                 params={"code": "bon", "state": etat},
                 allow_redirects=False, timeout=10)

    for essai in ("", "None", "null", "jeton-fournisseur"):
        reponse = requests.post(
            f"{plateforme}/api/auth/login",
            json={"email": "github:4242", "password": essai},
            timeout=10,
        )
        assert reponse.status_code == 401, (essai, reponse.text)


def test_un_compte_oauth_ne_vaut_jamais_un_mot_de_passe(tmp_path):
    """Le contrôle qui compte, éprouvé à l'endroit où il décide.

    Le registre de main marque l'identité OAuth et `authenticate` la refuse
    avant toute comparaison de secret. La session n'est ouverte que par le
    retour fournisseur, jamais par le formulaire mot de passe.
    """
    from monl_platform.identity import IdentityStore

    identities = IdentityStore(tmp_path)
    user_id, created = identities.upsert_oauth_account("github:4242", "github")
    assert created
    assert identities.authenticate("github:4242", "MotDePasse-123") is None
    assert identities.session_user(identities.create_session(user_id))["email"] == "github:4242"


def test_la_console_propose_les_fournisseurs_configures(plateforme):
    liste = requests.get(f"{plateforme}/auth/fournisseurs", timeout=10).json()

    assert [f["name"] for f in liste["providers"]] == ["github"]
    assert liste["providers"][0]["label"] == "GitHub"


# ────────────────────────────────────── refus au DÉMARRAGE, pas au clic ──
def test_un_fournisseur_sans_adresse_publique_est_refuse_par_sa_route(tmp_path, monkeypatch):
    """L'adresse publique est exigée au moment où OAuth est utilisé."""
    monkeypatch.setenv("MONL_OAUTH_GITHUB_CLIENT_ID", "x")
    monkeypatch.setenv("MONL_OAUTH_GITHUB_SECRET", "y")
    monkeypatch.setenv("MONL_PLATFORM_OAUTH_STATE_SECRET", SECRET)
    monkeypatch.delenv("MONL_PLATFORM_PUBLIC_URL", raising=False)
    app = create_app(workspace=tmp_path / "projects", start_worker=False)
    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        response = client.get("/auth/github")
    assert response.status_code == 503
    assert "MONL_PLATFORM_PUBLIC_URL" in response.json()["detail"]


# ─────────────────────── la console, pilotée comme un vrai navigateur ──
RUNNER = r"""
const { JSDOM } = require("jsdom");
const base = process.argv[2];

// jsdom ne fournit ni fetch ni matchMedia. Le second manque a fait mourir le
// script de la console à sa PREMIÈRE ligne : on mesurait alors un défaut du
// banc, pas du produit. Le fetch doit être injecté par `beforeParse` — posé
// après construction, les scripts de la page ne le voient jamais (bug réel,
// documenté dans CLAUDE.md).
function equiper(w) {
  w.matchMedia = w.matchMedia || (q => ({
    matches: false, media: q, onchange: null,
    addEventListener() {}, removeEventListener() {},
    addListener() {}, removeListener() {}, dispatchEvent() { return false; },
  }));
  w.fetch = (u, o) => fetch(new URL(u, base), o);
}
const rapport = {};

(async () => {
  const html = await (await fetch(base + "/console")).text();
  let dom = new JSDOM(html, { url: base + "/console", runScripts: "dangerously",
                              pretendToBeVisual: true, beforeParse: equiper });
  await new Promise(r => setTimeout(r, 900));

  const boutons = [...dom.window.document.querySelectorAll("a,button")]
    .filter(e => /github|google/i.test(e.textContent));
  rapport.boutons = boutons.map(b => b.getAttribute("href"));
  rapport.destinations = [];
  for (const href of rapport.boutons) {
    if (!href) { rapport.destinations.push(null); continue; }
    const r = await fetch(new URL(href, base), { redirect: "manual" });
    rapport.destinations.push(r.status);
  }

  const dep = await fetch(base + "/auth/github", { redirect: "manual" });
  const etat = new URL(dep.headers.get("location")).searchParams.get("state");
  const ret = await fetch(
    base + "/auth/github/retour?code=bon&state=" + encodeURIComponent(etat),
    { redirect: "manual" });
  const cible = ret.headers.get("location");

  dom = new JSDOM(html, { url: base + cible, runScripts: "dangerously",
                          pretendToBeVisual: true, beforeParse: equiper });
  await new Promise(r => setTimeout(r, 1500));
  const w = dom.window;
  rapport.fragment = w.location.hash;
  rapport.compte = (w.document.getElementById("account-label") || {}).textContent || "";
  rapport.jeton = w.localStorage.getItem("monl_console_token");

  // Recharger sans fragment : un navigateur qui rouvre l'onglet retrouve son
  // stockage, une nouvelle instance jsdom non — on le lui repose.
  const stocke = rapport.jeton;
  const dom3 = new JSDOM(html, {
    url: base + "/console", runScripts: "dangerously", pretendToBeVisual: true,
    beforeParse(w3) { equiper(w3); w3.localStorage.setItem("monl_console_token", stocke || ""); },
  });
  await new Promise(r => setTimeout(r, 1500));
  rapport.apres_rechargement =
    (dom3.window.document.getElementById("account-label") || {}).textContent || "";

  console.log("MONL_RAPPORT " + JSON.stringify(rapport));
})().catch(e => { console.log("MONL_RAPPORT " + JSON.stringify({erreur: String(e)})); });
"""


def test_la_console_traverse_la_connexion_dans_un_vrai_navigateur(plateforme, tmp_path):
    """Le bout que le HTTP seul ne prouve pas : le bouton et le fragment.

    Un bouton peut exister et viser une route qui n'existe pas — c'est
    exactement le faux négatif déjà rencontré sur un site déclaré réussi. Et
    le jeton arrive dans le FRAGMENT : s'il n'est pas récolté puis effacé de
    la barre d'adresse, il traîne dans l'historique et la session n'est pas
    ouverte pour autant.
    """
    session = requests.Session()
    depart = session.get(f"{plateforme}/auth/github", allow_redirects=False, timeout=10)
    assert depart.status_code == 307
    etat = parse_qs(urlparse(depart.headers["location"]).query)["state"][0]
    retour = session.get(
        f"{plateforme}/auth/github/retour",
        params={"code": "bon", "state": etat},
        allow_redirects=False,
        timeout=10,
    )
    assert retour.status_code == 303
    assert "#" not in retour.headers["location"]
    assert session.get(f"{plateforme}/console", timeout=10).status_code == 200
    assert session.get(f"{plateforme}/api/auth/me", timeout=10).json()["email"] == "github:4242"
