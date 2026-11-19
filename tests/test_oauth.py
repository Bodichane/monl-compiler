"""Google or GitHub sign-in, tested against a fake provider.

The platform spends real money on every build: an account opened with any
string is an abuse door. Yet it sends NO message — point 95's boundary holds —
it delegates to a provider that has already verified the address.

The fake provider is embedded here, like `tests/test_paiement.py`'s fake
Stripe: without it, the brick could only be tested by calling the real
GitHub, that is never.
"""

import json
import os
import socket
import threading
import time
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import pytest
import requests
import uvicorn

from monl_platform.app import create_app
from monl_platform.oauth import (
    STATE_TTL,
    OAuthError,
    OAuthNotConfigured,
    authorize_url,
    check_state,
    configured_providers,
    make_state,
    redirect_uri,
)
from tests.support.server import uvicorn_server
from tests.support.sqlite import base_sqlite

SECRET = "secret-de-plateforme-pour-les-tests-oauth-123456"
OAUTH_FLOW_COOKIE = "monl_oauth_flow"
OAUTH_FLOW_PATH = "/auth/"
SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src")


def _free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class FakeProvider:
    provider_name = "test"
    model = "test-model"

    def __call__(self, _prompt):  # pragma: no cover - never called here
        raise AssertionError("la connexion n'appelle aucune IA")


# ───────────────────────────────────────────────── the embedded fake GitHub ──
class _FauxGitHub(BaseHTTPRequestHandler):
    #: What the account will return. Changed by the tests to test refusing an
    #: UNverified address.
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


def _aller(base, session):
    """Follows the start and returns the `state` the platform issued."""
    depart = session.get(f"{base}/auth/github", allow_redirects=False, timeout=10)
    assert depart.status_code == 307, depart.text
    return parse_qs(urlparse(depart.headers["location"]).query)["state"][0]


def _nombre(base_path, table):
    with base_sqlite(base_path / "projects" / "platform.sqlite3") as db:
        return db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


# ────────────────────────────────────────────────────── configuration ──
def test_a_provider_without_secret_is_not_offered():
    """A button leading to a 503 is worse than no button."""
    assert configured_providers({}) == []
    assert configured_providers({"MONL_OAUTH_GITHUB_CLIENT_ID": "x"}) == []
    prets = configured_providers({
        "MONL_OAUTH_GITHUB_CLIENT_ID": "x", "MONL_OAUTH_GITHUB_SECRET": "y"})
    assert [p["name"] for p in prets] == ["github"]


def test_a_missing_variable_is_NAMED(monkeypatch):
    monkeypatch.delenv("MONL_OAUTH_GOOGLE_CLIENT_ID", raising=False)
    with pytest.raises(OAuthNotConfigured) as faute:
        authorize_url("google", "peu-importe", {})
    assert faute.value.variable == "MONL_OAUTH_GOOGLE_CLIENT_ID"
    assert faute.value.status_code == 503


def test_the_return_address_comes_from_configuration():
    """Never from the Host header: it is provided by the client, and reading it
    would let the round trip be diverted to a domain chosen elsewhere."""
    env = {"MONL_PLATFORM_PUBLIC_URL": "https://monl.example/"}

    assert redirect_uri("github", env) == "https://monl.example/auth/github/retour"
    with pytest.raises(OAuthNotConfigured):
        redirect_uri("github", {})


# ────────────────────────────────────────────────────────────── state ──
def test_a_forged_state_is_refused():
    with pytest.raises(OAuthError, match="not signed"):
        check_state("github.1700000000.abcd.empreinte.faux", "github", SECRET, "secret")


def test_another_providers_state_is_refused():
    etat = make_state("google", SECRET, "secret-navigateur")
    with pytest.raises(OAuthError, match="another provider"):
        check_state(etat, "github", SECRET, "secret-navigateur")


def test_an_expired_state_is_refused():
    """Without a date, a start captured once would stay replayable forever —
    same reasoning as the payment webhook's dated signature."""
    etat = make_state("github", SECRET, "secret-navigateur", maintenant=1_700_000_000)

    assert check_state(
        etat, "github", SECRET, "secret-navigateur", maintenant=1_700_000_300
    )
    with pytest.raises(OAuthError, match="expired"):
        check_state(
            etat, "github", SECRET, "secret-navigateur", maintenant=1_700_001_000
        )


def test_a_state_signed_by_another_server_is_refused():
    etat = make_state(
        "github", "un-autre-secret-de-plateforme-tout-autre", "secret-navigateur"
    )
    with pytest.raises(OAuthError, match="not signed"):
        check_state(etat, "github", SECRET, "secret-navigateur")


# ─────────────────────────────────────── l'aller-retour, en vrai HTTP ──
def test_the_start_leads_to_the_provider_with_a_signed_state(plateforme):
    session = requests.Session()
    depart = session.get(f"{plateforme}/auth/github", allow_redirects=False, timeout=10)

    assert depart.status_code == 307
    params = parse_qs(urlparse(depart.headers["location"]).query)
    assert params["client_id"] == ["identifiant-client"]
    assert params["redirect_uri"] == [f"{plateforme}/auth/github/retour"]
    assert check_state(
        params["state"][0], "github", SECRET, session.cookies[OAUTH_FLOW_COOKIE]
    )


def test_a_full_round_trip_opens_a_session(plateforme):
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
    assert OAUTH_FLOW_COOKIE not in session.cookies
    compte = session.get(f"{plateforme}/api/auth/me", timeout=10)
    assert compte.status_code == 200, compte.text
    assert compte.json()["email"] == "github:4242"
    assert session.get(f"{plateforme}/console", timeout=10).status_code == 200


def test_two_logins_create_only_one_account(plateforme):
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


def test_an_unverified_address_is_refused(plateforme):
    """Without this check, the brick would verify nothing: it would move the
    arbitrary string from one form to another."""
    _FauxGitHub.verifiee = False
    session = requests.Session()
    etat = _aller(plateforme, session)

    retour = session.get(
        f"{plateforme}/auth/github/retour",
        params={"code": "bon", "state": etat},
        allow_redirects=False,
        timeout=10,
    )

    assert retour.status_code == 403, retour.text
    assert "verified" in retour.json()["detail"]


def test_a_return_without_valid_state_opens_nothing(plateforme):
    """The CSRF counter-proof: a third party triggering the return from their own
    site has no state signed by us."""
    retour = requests.get(f"{plateforme}/auth/github/retour",
                          params={"code": "bon", "state": "github.1.2.3"},
                          allow_redirects=False, timeout=10)

    assert retour.status_code == 400
    assert "location" not in {k.lower() for k in retour.headers}


def test_the_login_attack_with_valid_state_without_cookie_is_refused(
    plateforme, tmp_path
):
    """The attacker starts the flow, but the victim does not own their secret."""
    attaquant = requests.Session()
    victime = requests.Session()
    etat = _aller(plateforme, attaquant)

    retour = victime.get(
        f"{plateforme}/auth/github/retour",
        params={"code": "code-attaquant", "state": etat},
        allow_redirects=False,
        timeout=10,
    )

    assert retour.status_code == 400
    assert "browser" in retour.json()["detail"]
    assert _FauxGitHub.codes_vus == []
    assert "monl_session" not in victime.cookies
    assert _nombre(tmp_path, "sessions") == 0
    assert _nombre(tmp_path, "users") == 0


def test_another_flows_cookie_does_not_validate_the_state(plateforme):
    premier = requests.Session()
    autre = requests.Session()
    etat_premier = _aller(plateforme, premier)
    _aller(plateforme, autre)

    retour = autre.get(
        f"{plateforme}/auth/github/retour",
        params={"code": "bon", "state": etat_premier},
        allow_redirects=False,
        timeout=10,
    )

    assert retour.status_code == 400
    assert _FauxGitHub.codes_vus == []
    assert "monl_session" not in autre.cookies


def test_a_callback_replayed_after_success_is_refused(plateforme):
    session = requests.Session()
    etat = _aller(plateforme, session)
    params = {"code": "bon", "state": etat}

    succes = session.get(
        f"{plateforme}/auth/github/retour",
        params=params,
        allow_redirects=False,
        timeout=10,
    )
    rejeu = session.get(
        f"{plateforme}/auth/github/retour",
        params=params,
        allow_redirects=False,
        timeout=10,
    )

    assert succes.status_code == 303
    assert rejeu.status_code == 400
    assert _FauxGitHub.codes_vus == ["bon"]


def test_the_oauth_cookie_is_transient_and_limited_to_oauth_routes(
    plateforme, monkeypatch
):
    monkeypatch.setenv("MONL_COOKIE_SECURE", "1")

    depart = requests.get(
        f"{plateforme}/auth/github", allow_redirects=False, timeout=10
    )
    cookie = SimpleCookie()
    cookie.load(depart.headers["Set-Cookie"])
    morsel = cookie[OAUTH_FLOW_COOKIE]

    assert morsel["httponly"]
    assert morsel["samesite"].lower() == "lax"
    assert morsel["path"] == OAUTH_FLOW_PATH
    assert morsel["max-age"] == str(STATE_TTL)
    assert morsel["secure"]
    etat = parse_qs(urlparse(depart.headers["location"]).query)["state"][0]
    assert morsel.value not in etat


def test_a_user_refusal_is_not_a_failure(plateforme):
    retour = requests.get(f"{plateforme}/auth/github/retour",
                          params={"error": "access_denied"},
                          allow_redirects=False, timeout=10)

    assert retour.status_code == 303
    assert retour.headers["location"] == "/login?erreur=refus"


def test_a_provider_account_does_not_log_in_by_password(plateforme):
    """It has NO password: `None` must never become a door."""
    session = requests.Session()
    etat = _aller(plateforme, session)
    session.get(
        f"{plateforme}/auth/github/retour",
        params={"code": "bon", "state": etat},
        allow_redirects=False,
        timeout=10,
    )

    for essai in ("", "None", "null", "jeton-fournisseur"):
        reponse = requests.post(
            f"{plateforme}/api/auth/login",
            json={"email": "github:4242", "password": essai},
            timeout=10,
        )
        assert reponse.status_code == 401, (essai, reponse.text)


def test_an_oauth_account_is_never_worth_a_password(tmp_path):
    """The check that counts, tested where it decides.

    The main registry marks the OAuth identity and `authenticate` refuses it
    before any secret comparison. The session is only opened by the provider
    return, never by the password form.
    """
    from monl_platform.identity import IdentityStore

    identities = IdentityStore(tmp_path)
    user_id, created = identities.upsert_oauth_account("github:4242", "github")
    assert created
    assert identities.authenticate("github:4242", "MotDePasse-123") is None
    assert identities.session_user(identities.create_session(user_id))["email"] == "github:4242"


def test_the_console_offers_the_configured_providers(plateforme):
    liste = requests.get(f"{plateforme}/auth/fournisseurs", timeout=10).json()

    assert [f["name"] for f in liste["providers"]] == ["github"]
    assert liste["providers"][0]["label"] == "GitHub"


# ───────────────────────────────────────── refusal at STARTUP, not on click ──
def test_a_provider_without_public_address_is_refused_by_its_route(tmp_path, monkeypatch):
    """The public address is required when OAuth is used."""
    monkeypatch.setenv("MONL_OAUTH_GITHUB_CLIENT_ID", "x")
    monkeypatch.setenv("MONL_OAUTH_GITHUB_SECRET", "y")
    monkeypatch.setenv("MONL_PLATFORM_OAUTH_STATE_SECRET", SECRET)
    monkeypatch.delenv("MONL_PLATFORM_PUBLIC_URL", raising=False)

    env = os.environ.copy()
    env["MONL_PLATFORM_WORKSPACE"] = str(tmp_path / "projects")
    env["PYTHONPATH"] = SRC + os.pathsep + env.get("PYTHONPATH", "")
    with uvicorn_server(str(tmp_path), env=env,
                        module="monl_platform.app:app", ready_path="/health") as base:
        response = requests.get(base + "/auth/github", allow_redirects=False, timeout=10)

    assert response.status_code == 503
    assert "MONL_PLATFORM_PUBLIC_URL" in response.json()["detail"]


# ────────────────────────────────── the console, driven like a real browser ──
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


def test_the_console_goes_through_login_in_a_real_browser(plateforme, tmp_path):
    """The part HTTP alone does not prove: the button and the fragment.

    A button can exist and target a route that does not exist — exactly the
    false negative already met on a site declared successful. And the token
    arrives in the FRAGMENT: if it is not collected then cleared from the address
    bar, it lingers in the history and the session is not opened anyway.
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


@pytest.mark.parametrize("ancienne", [False, True])
def test_oauth_deletion_requires_a_recent_login(plateforme, tmp_path, ancienne):
    session = requests.Session()
    etat = _aller(plateforme, session)
    retour = session.get(plateforme + "/auth/github/retour",
                         params={"code": "bon-code", "state": etat},
                         allow_redirects=False, timeout=10)
    assert retour.status_code == 303, retour.text
    cle = session.post(plateforme + "/api/keys", json={"name": "preuve"}, timeout=10)
    assert cle.status_code == 201, cle.text
    assert requests.post(plateforme + "/mcp",
                         headers={"Authorization": "Bearer " + cle.json()["key"]},
                         json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                         timeout=10).status_code == 200
    if ancienne:
        with base_sqlite(tmp_path / "projects" / "platform.sqlite3") as db:
            db.execute("UPDATE sessions SET created_at = created_at - 601")
    reponse = session.delete(plateforme + "/api/auth/account", json={}, timeout=10)
    if ancienne:
        assert reponse.status_code == 403, "Une session OAuth ancienne autorise la suppression"
        assert "Sign in again with your OAuth provider" in reponse.text
        assert session.get(plateforme + "/api/auth/me", timeout=10).status_code == 200
    else:
        assert reponse.status_code == 204, "Une connexion OAuth récente ne permet pas la suppression"
        assert session.get(plateforme + "/api/auth/me", timeout=10).status_code == 401
        assert requests.post(plateforme + "/mcp",
                             headers={"Authorization": "Bearer " + cle.json()["key"]},
                             json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                             timeout=10).status_code == 401
