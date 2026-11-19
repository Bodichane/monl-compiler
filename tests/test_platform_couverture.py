"""Coverage complements on the application's boundaries.

The HTTP dialogue tests deliberately start uvicorn in another process. These
ASGI tests keep the same response assertions, but also run the route
functions in the measured process: otherwise coverage would confuse "tested"
with "visible to coverage.py".
"""

import ast
import asyncio
import io
import json
import json as json_module
import urllib.error
from http.cookies import SimpleCookie
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from fastapi import HTTPException, Request

from monl_platform.app import create_app
from tests.test_platform_service import SPEC

MOT_DE_PASSE = "MotDePasse-Couverture-2026"


class _Response:
    def __init__(self, status_code, headers, body):
        self.status_code = status_code
        self.headers = headers
        self.content = body

    @property
    def text(self):
        return self.content.decode("utf-8")

    def json(self):
        return json.loads(self.content)


class _ASGIClient:
    """Minimal ASGI client, without any dependency foreign to the project."""

    def __init__(self, application):
        self.application = application
        self.cookies = {}

    async def request(self, method, url, *, json=None, content=None, headers=None):
        if url.startswith("/"):
            url = "http://testserver" + url
        parsed = urlsplit(url)
        body = content if content is not None else (
            json_module.dumps(json).encode() if json is not None else b""
        )
        request_headers = {key.lower(): value for key, value in (headers or {}).items()}
        request_headers.setdefault("host", parsed.netloc or "testserver")
        request_headers.setdefault("content-length", str(len(body)))
        if json is not None:
            request_headers.setdefault("content-type", "application/json")
        if self.cookies:
            request_headers["cookie"] = "; ".join(
                f"{key}={value}" for key, value in self.cookies.items()
            )
        messages = [{"type": "http.request", "body": body, "more_body": False}]
        started = {}
        chunks = []

        async def receive():
            # Like a real ASGI server: once the body is delivered, the next
            # read BLOCKS until the end of the response (recent Starlette
            # awaits it in parallel to detect a disconnection). Neither an
            # empty list raising IndexError, nor an immediate disconnection
            # cutting a file.
            if messages:
                return messages.pop(0)
            await asyncio.Event().wait()

        async def send(message):
            if message["type"] == "http.response.start":
                started["status"] = message["status"]
                started["headers"] = message["headers"]
            elif message["type"] == "http.response.body":
                chunks.append(message.get("body", b""))

        scope = {
            "type": "http", "http_version": "1.1", "method": method,
            "scheme": parsed.scheme or "http", "path": parsed.path or "/",
            "raw_path": (parsed.path or "/").encode("latin-1"),
            "query_string": parsed.query.encode("ascii"), "headers": [
                (key.encode("latin-1"), value.encode("latin-1"))
                for key, value in request_headers.items()
            ], "client": ("127.0.0.1", 1234), "server": ("testserver", 80),
        }
        await self.application(scope, receive, send)
        response_headers = {
            key.decode("latin-1").lower(): value.decode("latin-1")
            for key, value in started["headers"]
        }
        for key, value in started["headers"]:
            if key.lower() == b"set-cookie":
                morsel = SimpleCookie(value.decode("latin-1"))
                for name, item in morsel.items():
                    self.cookies[name] = item.value
        return _Response(started["status"], response_headers, b"".join(chunks))

    async def get(self, url, **kwargs):
        return await type(self).request(self, "GET", url, **kwargs)

    async def post(self, url, **kwargs):
        return await type(self).request(self, "POST", url, **kwargs)

    async def delete(self, url, **kwargs):
        return await type(self).request(self, "DELETE", url, **kwargs)


async def _dialogue(app):
    client = _ASGIClient(app)
    base_url = "http://testserver"
    async def get(path, **kwargs):
        return await _ASGIClient.get(client, base_url + path, **kwargs)

    async def post(path, **kwargs):
        return await _ASGIClient.post(client, base_url + path, **kwargs)

    async def delete(path, **kwargs):
        return await _ASGIClient.delete(client, base_url + path, **kwargs)

    async def request(method, path, **kwargs):
        return await _ASGIClient.request(client, method, base_url + path, **kwargs)

    # Keep the route dialogue compact while retaining explicit assertions on
    # every response that drives the next action.
    client.get = get
    client.post = post
    client.delete = delete
    client.request = request
    try:
        assert (await client.get("/health")).json()["status"] == "ok"
        assert (await client.get("/ready")).json()["status"] == "ready"
        assert (await client.get("/console")).status_code == 303
        assert (await client.get("/login")).status_code == 200
        assert (await client.get("/account")).status_code == 303
        assert (await client.get("/mcp")).status_code == 303
        for path in ("/guide", "/docs", "/mentions-legales", "/conditions",
                     "/confidentialite", "/security"):
            assert (await client.get(path)).status_code == 200
        assert (await client.get("/favicon.svg")).headers["content-type"].startswith(
            "image/svg+xml")
        assert (await client.get("/logo.svg")).status_code == 200
        assert (await client.get("/brand/monl-wordmark.png")).status_code == 200
        assert (await client.get("/api/version")).json()["contract"]
        assert len((await client.get("/api/templates")).json()["templates"]) == 10
        assert (await client.get("/api/examples")).json()["examples"]
        assert (await client.get("/api/examples/inconnu")).status_code == 404
        assert (await client.get("/api/telechargements")).status_code == 200
        assert (await client.get("/api/models")).json()["models"]

        assert (await client.post("/api/validate", json={})).status_code == 422
        assert (await client.post("/api/validate", content=b"[]",
                                  headers={"content-type": "application/json"})).status_code == 400
        assert (await client.post("/api/validate", json={"spec": SPEC})).json()["valid"]

        invalid = await client.post("/api/auth/register", json={})
        assert invalid.status_code == 422
        registered = await client.post("/api/auth/register", json={
            "email": "couverture@exemple.test", "password": MOT_DE_PASSE})
        assert registered.status_code == 201
        recovery_codes = registered.json()["recovery_codes"]
        assert len(recovery_codes) == 8
        user_id = registered.json()["user"]["id"]
        assert (await client.get("/api/auth/me")).json()["id"] == user_id
        assert (await client.get("/api/auth/recovery-codes")).json()["remaining"] == 8
        assert (await client.get("/api/projects")).json()["projects"] == []
        assert (await client.get("/api/keys")).json()["keys"] == []

        duplicate = await client.post("/api/auth/register", json={
            "email": "COUVERTURE@EXEMPLE.TEST", "password": MOT_DE_PASSE})
        assert duplicate.status_code == 422
        bad_login = await client.post("/api/auth/login", json={
            "email": "couverture@exemple.test", "password": "mauvaise-cle"})
        assert bad_login.status_code == 401
        logged = await client.post("/api/auth/login", json={
            "email": "couverture@exemple.test", "password": MOT_DE_PASSE})
        assert logged.status_code == 200

        bad_compile = await client.post("/api/compile", json={"spec": ""})
        assert bad_compile.status_code == 422
        compiled = await client.post("/api/compile", json={"spec": SPEC})
        assert compiled.status_code == 201, compiled.text
        project_id = compiled.json()["id"]
        assert (await client.get(f"/api/projects/{project_id}")).status_code == 200
        assert (await client.get(f"/api/projects/{project_id}/contract")).status_code == 200
        archive = await client.get(f"/api/projects/{project_id}/download")
        assert archive.status_code == 200 and archive.content.startswith(b"PK")

        # POINT 162: the build queue gave way to ONE deterministic compilation,
        # then to starting the resulting API.
        compilation = await client.post(f"/api/projects/{project_id}/compiler")
        assert compilation.status_code == 201, compilation.json()
        assert compilation.json()["routes"] > 0
        assert "app.py" in compilation.json()["files"]
        assert (await client.post(f"/api/projects/{project_id}/stop")).json()["stopped"] is False

        invalid_key = await client.post("/api/keys", json={"name": ""})
        assert invalid_key.status_code == 422
        key_response = await client.post("/api/keys", json={"name": "couverture"})
        assert key_response.status_code == 201
        raw_key = key_response.json()["key"]
        key_id = key_response.json()["id"]
        assert (await client.get("/api/keys")).json()["keys"][0]["id"] == key_id
        mcp_headers = {"authorization": f"Bearer {raw_key}"}
        tools = await client.post("/mcp", headers=mcp_headers, json={
            "jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        assert tools.status_code == 200 and tools.json()["result"]["tools"]
        unknown = await client.post("/mcp", headers=mcp_headers, json={
            "jsonrpc": "2.0", "id": 2, "method": "unknown"})
        assert unknown.status_code == 200 and unknown.json()["error"]
        assert (await client.delete(f"/api/keys/{key_id}")).status_code == 204
        assert (await client.post("/mcp", headers=mcp_headers, json={
            "jsonrpc": "2.0", "id": 3, "method": "tools/list"})).status_code == 401

        assert (await client.post("/api/auth/recover", json={
            "email": "couverture@exemple.test", "code": "faux",
            "password": MOT_DE_PASSE})).status_code == 401
        recovered = await client.post("/api/auth/recover", json={
            "email": "couverture@exemple.test", "code": recovery_codes[0],
            "password": "MotDePasse-Repris-2026"})
        assert recovered.status_code == 204
        assert (await client.post("/api/auth/login", json={
            "email": "couverture@exemple.test",
            "password": "MotDePasse-Repris-2026"})).status_code == 200

        wrong_delete = await client.request("DELETE", "/api/auth/account",
                                            json={"password": "mauvais"})
        assert wrong_delete.status_code == 403
        deleted = await client.request("DELETE", "/api/auth/account",
                                       json={"password": "MotDePasse-Repris-2026"})
        assert deleted.status_code == 204
        assert (await client.get("/api/auth/me")).status_code == 401
    finally:
        client.get = _ASGIClient.get.__get__(client)
        client.post = _ASGIClient.post.__get__(client)
        client.delete = _ASGIClient.delete.__get__(client)
        client.request = _ASGIClient.request.__get__(client)


def test_asgi_routes_cover_responses_and_effects(tmp_path):
    app = create_app(workspace=tmp_path)
    asyncio.run(_dialogue(app))


def _request(path="/", *, headers=(), body=b"", client=("127.0.0.1", 1234)):
    """Minimal Request to exercise the safeguards without bypassing ASGI."""
    messages = [{"type": "http.request", "body": body, "more_body": False}]

    async def receive():
        return messages.pop(0)

    scope = {
        "type": "http", "method": "POST", "path": path,
        "raw_path": path.encode(), "query_string": b"", "headers": [
            (key.lower().encode(), value.encode()) for key, value in headers
        ], "client": client, "server": ("testserver", 80), "scheme": "http",
    }
    return Request(scope, receive)


def test_http_safeguards_normalize_and_refuse_invalid_inputs(
    tmp_path, monkeypatch
):
    from monl_platform import app_http

    assert app_http._liens_de_pied([
        {"label": " Documentation ", "url": "https://example.test/docs"},
        {"label": "documentation", "url": "/autre"},
        {"label": 'dangereux"', "url": "/x"},
        {"label": "externe", "url": "https://example.test"},
        "pas-un-objet",
    ]) == [
        {"label": "Documentation", "url": "https://example.test/docs"},
        {"label": "externe", "url": "https://example.test"},
    ]
    assert app_http._is_compile_message({
        "method": "tools/call", "params": {"name": "monl_compile_backend"}
    })
    assert not app_http._is_compile_message({"method": "ping"})

    from monl_platform.identity import IdentityStore

    identities = IdentityStore(tmp_path)
    user = identities.register("helper@exemple.test", MOT_DE_PASSE)
    token = identities.create_session(user["id"])
    authenticated = _request(headers=(("cookie", f"monl_session={token}"),))
    assert app_http._require_user(authenticated, identities)["id"] == user["id"]
    with pytest.raises(HTTPException, match="Sign in to continue"):
        app_http._require_user(_request(), identities)
    with pytest.raises(HTTPException, match="Project not found"):
        app_http._require_project(identities, user["id"], "absent")

    assert app_http._client_ip(_request()) == "127.0.0.1"
    monkeypatch.setenv("MONL_TRUST_PROXY", "yes")
    assert app_http._client_ip(_request(
        headers=(("x-forwarded-for", "203.0.113.8, 10.0.0.1"),)
    )) == "203.0.113.8"
    monkeypatch.delenv("MONL_TRUST_PROXY")
    assert app_http._client_ip(_request(client=None)) == "unknown"

    app_http._rate_limit(_request(), identities, "test", "sujet", 1, 60)
    with pytest.raises(HTTPException) as limite:
        app_http._rate_limit(_request(), identities, "test", "sujet", 1, 60)
    assert limite.value.status_code == 429
    assert app_http._veut_du_json(_request("/api/test", headers=(("accept", "text/html"),)))
    assert not app_http._veut_du_json(_request("/page", headers=(("accept", "text/html"),)))
    assert app_http._veut_du_json(_request("/page", headers=(("accept", "application/json"),)))
    assert "This page does not exist" in app_http._page_404("absente")

    response = app_http._session_response(identities, user, extra={"ok": True})
    assert response.status_code == 200 and b'"ok":true' in response.body
    assert b"monl_session=" in b"".join(
        value for key, value in response.raw_headers if key == b"set-cookie"
    )

    assert asyncio.run(app_http._json_body(_request(
        body=b'{"spec":"ok"}', headers=(("content-type", "application/json"),)
    ))) == {"spec": "ok"}
    with pytest.raises(HTTPException, match="too large"):
        asyncio.run(app_http._json_body(_request(
            headers=(("content-length", "300001"),), body=b"{}"
        )))
    with pytest.raises(HTTPException, match="Invalid Content-Length"):
        asyncio.run(app_http._json_body(_request(
            headers=(("content-length", "non"),), body=b"{}"
        )))
    with pytest.raises(HTTPException, match="Invalid JSON body"):
        asyncio.run(app_http._json_body(_request(body=b"pas-json")))
    with pytest.raises(HTTPException, match="JSON object"):
        asyncio.run(app_http._json_body(_request(body=b"[]")))


def test_setting_the_cookie_is_unique_and_follows_configuration(tmp_path, monkeypatch):
    """Each cookie family has a single setter and shares the Secure rule."""
    racine = Path(__file__).resolve().parent.parent / "src" / "monl_platform"
    poses = []
    for chemin in racine.glob("*.py"):
        arbre = ast.parse(chemin.read_text(encoding="utf-8"))
        poses.extend(
            (chemin.name, noeud.lineno)
            for noeud in ast.walk(arbre)
            if isinstance(noeud, ast.Call)
            and isinstance(noeud.func, ast.Attribute)
            and noeud.func.attr == "set_cookie"
        )
    assert [nom for nom, _ligne in poses].count("session.py") == 1
    assert [nom for nom, _ligne in poses].count("builder_auth_routes.py") == 1
    assert len(poses) == 2

    from fastapi.responses import Response

    from monl_platform import app_http
    from monl_platform.builder_runtime import _set_session_cookie
    from monl_platform.identity import IdentityStore

    identities = IdentityStore(tmp_path)
    user = identities.register("cookie@exemple.test", MOT_DE_PASSE)
    monkeypatch.setenv("MONL_COOKIE_SECURE", "yes")
    secure = app_http._session_response(identities, user)
    oauth_secure = Response()
    _set_session_cookie(oauth_secure, "jeton-de-test")
    for response in (secure, oauth_secure):
        assert b"Secure" in b"".join(
            value for key, value in response.raw_headers if key == b"set-cookie"
        )

    monkeypatch.setenv("MONL_COOKIE_SECURE", "0")
    insecure = app_http._session_response(identities, user)
    assert b"Secure" not in b"".join(
        value for key, value in insecure.raw_headers if key == b"set-cookie"
    )


def test_the_lifecycle_starts_stops_and_keeps_the_purge(monkeypatch):
    from monl_platform import app_lifecycle

    class RapideEvent:
        def __init__(self):
            self.waits = 0

        def wait(self, _interval):
            self.waits += 1
            return self.waits > 1

        def set(self):
            return None

    class Runtime:
        def __init__(self):
            self.started = False
            self.stopped = False

        def start(self):
            self.started = True

        def stop(self):
            self.stopped = True

    class Identities:
        def __init__(self, error=False):
            self.error = error
            self.calls = 0

        def expired_projects(self):
            self.calls += 1
            if self.error:
                raise RuntimeError("base indisponible")
            return ["périmé"]

    class Service:
        pass

    purges = []
    monkeypatch.setattr(app_lifecycle, "_purger", lambda service, identities, runtime=None:
                        purges.append(identities.expired_projects()) or 1)
    assert app_lifecycle._purger(Service(), Identities()) == 1

    import threading

    class ThreadingProxy:
        Event = RapideEvent
        Thread = threading.Thread

    monkeypatch.setattr(app_lifecycle, "threading", ThreadingProxy)

    async def run_lifespan(identities, runtime):
        lifespan = app_lifecycle.create_lifespan(Service(), identities, runtime)
        async with lifespan(None):
            await asyncio.sleep(0.01)

    ok = Identities()
    runtime = Runtime()
    asyncio.run(run_lifespan(ok, runtime))
    assert ok.calls == 1 and runtime.started and runtime.stopped

    broken = Identities(error=True)
    runtime = Runtime()
    asyncio.run(run_lifespan(broken, runtime))
    assert broken.calls == 1 and runtime.started and runtime.stopped


def test_the_mcp_dispatcher_answers_protocols_and_tools(tmp_path, monkeypatch, capsys):
    from monl_platform.identity import IdentityStore
    from monl_platform.mcp_server import MCPDispatcher, run_stdio
    from monl_platform.service import CompilationService

    service = CompilationService(tmp_path)
    identities = IdentityStore(tmp_path)
    user = identities.register("mcp-direct@exemple.test", MOT_DE_PASSE)
    dispatcher = MCPDispatcher(service, identities)
    assert dispatcher.dispatch({"method": "ping"}) is None
    assert dispatcher.dispatch({"id": 1, "method": "initialize"})["result"]["serverInfo"]
    assert dispatcher.dispatch({"id": 2, "method": "ping"})["result"] == {}
    assert dispatcher.dispatch({"id": 3, "method": "tools/list"})["result"]["tools"]
    assert dispatcher.dispatch({"id": 4, "method": "unknown"})["error"]["code"] == -32601

    templates = dispatcher.dispatch({"id": 5, "method": "tools/call", "params": {
        "name": "monl_list_templates"}})
    assert "templates" in templates["result"]["content"][0]["text"]
    invalid = dispatcher.dispatch({"id": 6, "method": "tools/call", "params": {
        "name": "monl_validate_spec", "arguments": {}}})
    assert invalid["result"]["isError"] is True
    unknown_tool = dispatcher.dispatch({"id": 7, "method": "tools/call", "params": {
        "name": "inconnu"}})
    assert unknown_tool["result"]["isError"] is True

    compiled = dispatcher.dispatch({"id": 8, "method": "tools/call", "params": {
        "name": "monl_compile_backend", "arguments": {"spec": SPEC}}}, user["id"])
    payload = json.loads(compiled["result"]["content"][0]["text"])
    project_id = payload["project_id"]
    assert identities.owns_project(user["id"], project_id)
    inspected = dispatcher.dispatch({"id": 9, "method": "tools/call", "params": {
        "name": "monl_inspect_contract", "arguments": {"project_id": project_id}}},
        user["id"])
    assert "contract" in inspected["result"]["content"][0]["text"]
    forbidden = dispatcher.dispatch({"id": 10, "method": "tools/call", "params": {
        "name": "monl_inspect_contract", "arguments": {"project_id": "autre"}}},
        user["id"])
    assert forbidden["result"]["isError"] is True

    class Broken:
        def list_templates(self):
            raise RuntimeError("panne de test")

    assert MCPDispatcher(Broken()).dispatch({
        "id": 11, "method": "tools/call", "params": {"name": "monl_list_templates"}
    })["error"]["code"] == -32603
    monkeypatch.setattr("sys.stdin", io.StringIO('\nnot-json\n{"id":12,"method":"ping"}\n'))
    run_stdio(service)
    sortie = capsys.readouterr().out
    assert "-32700" in sortie and '"id":12' in sortie


def test_the_store_validates_its_metadata_and_transitions(tmp_path):
    from monl_platform.identity import IdentityStore
    from monl_platform.store import PlatformStore, normalize_slug

    identities = IdentityStore(tmp_path)
    user = identities.register("store-direct@exemple.test", MOT_DE_PASSE)
    store = PlatformStore(tmp_path)
    assert normalize_slug("  Boutique-Maj  ") == "boutique-maj"
    assert PlatformStore._normalize_model_routes(None) == {}
    assert PlatformStore._normalize_model_routes({"Product": "fast"}) == {"Product": "fast"}
    assert PlatformStore._normalize_model_routes([" Product = quality "]) == {
        "Product": "quality"
    }
    with pytest.raises(ValueError, match="strings"):
        PlatformStore._normalize_model_routes([1])
    with pytest.raises(ValueError, match="expected form"):
        PlatformStore._normalize_model_routes(["Product"])
    with pytest.raises(ValueError, match="repeated"):
        PlatformStore._normalize_model_routes(["Product=a", "Product=b"])
    with pytest.raises(ValueError, match="object"):
        PlatformStore._normalize_model_routes("Product=fast")
    assert PlatformStore._project_values(None) is None
    assert PlatformStore._project_values({"model_routes": "pas-json"})["model_routes"] == {}

    project_id = "store-project"
    identities.add_project(user["id"], project_id, "Store project")
    assert store.create_project(user["id"], project_id, " Boutique ",
                                model_routes=["Product=quality"], generate_images=True)
    project = store.get_project_for_user(user["id"], project_id)
    assert project["slug"] == "boutique"
    assert project["model_routes"] == {"Product": "quality"}
    assert project["generate_images"] is True
    assert store.list_projects(user["id"])[0]["project_id"] == project_id
    assert store.list_all_projects()[0]["project_id"] == project_id
    assert store.list_projects_by_slug("BOUTIQUE")[0]["project_id"] == project_id
    assert store.discard_project(user["id"], "absent") is False

    assert store.discard_project(user["id"], project_id) is True


def test_the_oauth_adapter_covers_configuration_and_provider_responses(monkeypatch):
    from monl_platform import oauth

    environnement = {
        "MONL_OAUTH_GITHUB_CLIENT_ID": "client",
        "MONL_OAUTH_GITHUB_SECRET": "secret",
        "MONL_OAUTH_GITHUB_BASE_URL": "https://faux.example/api/",
        "MONL_PLATFORM_PUBLIC_URL": "https://monl.example/",
    }
    assert oauth._base_url("github", "api", environnement) == "https://faux.example/api"
    assert oauth.redirect_uri("github", environnement) == (
        "https://monl.example/auth/github/retour"
    )
    assert oauth.authorize_url(
        "github", "etat", environnement
    ).startswith("https://faux.example/api/login/oauth/authorize?")
    with pytest.raises(oauth.OAuthError, match="inconnu"):
        oauth._spec("inconnu")
    with pytest.raises(oauth.OAuthNotConfigured) as missing:
        oauth._credentials("github", {"MONL_OAUTH_GITHUB_CLIENT_ID": "client"})
    assert missing.value.variable == "MONL_OAUTH_GITHUB_SECRET"

    state = oauth.make_state(
        "github", "secret", "secret-navigateur", maintenant=1_700_000_000
    )
    assert oauth.check_state(
        state, "github", "secret", "secret-navigateur", maintenant=1_700_000_000
    )
    bad_timestamp_charge = "github.pas-un-entier.alea.empreinte"
    bad_timestamp = f"{bad_timestamp_charge}.{oauth._signer('secret', bad_timestamp_charge)}"
    for malformed, provider, now, message in (
        ("", "github", 0, "unreadable"),
        (state, "google", 1_700_000_000, "another provider"),
        (state.rsplit(".", 1)[0] + ".faux", "github", 1_700_000_000, "not signed"),
        (bad_timestamp,
         "github", 1_700_000_000, "unreadable"),
        (state, "github", 1_700_001_000, "expired"),
    ):
        with pytest.raises(oauth.OAuthError, match=message):
            oauth.check_state(
                malformed, provider, "secret", "secret-navigateur", maintenant=now
            )

    class Reply:
        def __init__(self, value):
            self.value = value

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps(self.value).encode()

    monkeypatch.setattr(oauth.urllib.request, "urlopen",
                        lambda *_args, **_kwargs: Reply({"ok": True}))
    assert oauth._post_json("https://faux.test", {"x": "y"}, {"X-Test": "oui"}) == {
        "ok": True
    }
    assert oauth._get_json("https://faux.test", "jeton") == {"ok": True}

    def http_failure(*_args, **_kwargs):
        raise urllib.error.HTTPError("https://faux.test", 502, "refus", {}, None)

    monkeypatch.setattr(oauth.urllib.request, "urlopen", http_failure)
    with pytest.raises(oauth.OAuthError, match="refused"):
        oauth._post_json("https://faux.test", {})
    with pytest.raises(oauth.OAuthError, match="refused"):
        oauth._get_json("https://faux.test", "jeton")

    def network_failure(*_args, **_kwargs):
        raise urllib.error.URLError("hors ligne")

    monkeypatch.setattr(oauth.urllib.request, "urlopen", network_failure)
    with pytest.raises(oauth.OAuthError, match="unreachable"):
        oauth._post_json("https://faux.test", {})
    with pytest.raises(oauth.OAuthError, match="unreachable"):
        oauth._get_json("https://faux.test", "jeton")

    monkeypatch.setattr(oauth, "_post_json", lambda *_args, **_kwargs: {"access_token": "ok"})
    assert oauth.exchange_code("github", "code", environnement) == "ok"
    monkeypatch.setattr(oauth, "_post_json", lambda *_args, **_kwargs: {})
    with pytest.raises(oauth.OAuthError, match="access token"):
        oauth.exchange_code("github", "code", environnement)

    def github_identity(url, _token):
        if url.endswith("/user"):
            return {"id": 42}
        return [{"email": "alice@example.test", "primary": True, "verified": True}]

    monkeypatch.setattr(oauth, "_get_json", github_identity)
    assert oauth.fetch_identity("github", "jeton", environnement) == (
        "github:42", "alice@example.test"
    )
    monkeypatch.setattr(oauth, "_get_json", lambda *_args: {"id": 0})
    with pytest.raises(oauth.OAuthError, match="did not identify"):
        oauth.fetch_identity("github", "jeton", environnement)
    monkeypatch.setattr(oauth, "_get_json", lambda url, _token: (
        {"id": 42} if url.endswith("/user") else []
    ))
    with pytest.raises(oauth.OAuthError, match="verified primary"):
        oauth.fetch_identity("github", "jeton", environnement)

    def google_identity(_url, _token):
        return {"sub": "1078", "email": "google@example.test", "email_verified": True}

    monkeypatch.setattr(oauth, "_get_json", google_identity)
    assert oauth.fetch_identity("google", "jeton", environnement) == (
        "google:1078", "google@example.test"
    )
    monkeypatch.setattr(oauth, "_get_json", lambda *_args: {"sub": "1078"})
    with pytest.raises(oauth.OAuthError, match="verified"):
        oauth.fetch_identity("google", "jeton", environnement)
