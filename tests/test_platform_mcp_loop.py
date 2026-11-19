"""The MCP loop closes WITHOUT a browser — HTTP proof against a real server.

POINT 162. An agent could validate and compile over MCP, then hit three
walls: the archive was only opened by the `monl_session` cookie, there was no
way to find one's projects again, and no equivalent of `monl update` nor
`monl diff` — yet that is THE WHOLE gesture after the first compilation.

This file walks the whole journey with ONE MCP key and nothing else: compile,
list, download the archive bytes, measure what a new spec would change, then
recompile in place. The account never opens a session.
"""

import io
import json
import socket
import threading
import time
import zipfile

import pytest
import requests
import uvicorn

from monl_platform.administration import main as administer
from monl_platform.app import create_app
from monl_platform.identity import IdentityStore

SPEC = """app BoucleMCP

entity Note
    titre: String
    contenu: Text

actor Membre selfRegister

rule Note.titre required
rule Note.Read public

workflow GererNotes for Membre
    Create Note
    Read Note
    Update Note
    Delete Note

landing
    brief: "Un carnet de notes minimal, banc d'essai de la boucle MCP."
    link "Contact": "mailto:contact@monl.test"
"""

SPEC_EVOLVED = SPEC.replace(
    "    contenu: Text\n",
    "    contenu: Text\n    etiquette: String\n",
).replace(
    'rule Note.Read public\n',
    'rule Note.Read public\nrule Note.etiquette oneOf "perso", "travail"\n',
)


def _free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture()
def platform(tmp_path):
    app = create_app(workspace=tmp_path / "projects", domain="localhost")
    port = _free_port()
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    )
    fil = threading.Thread(target=server.run, daemon=True)
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
            pytest.fail("the platform server did not start")
        yield base
    finally:
        server.should_exit = True
        fil.join(timeout=10)
        assert not fil.is_alive()


def _key(base, identifier="agent@example.test"):
    """Creates an account, draws an MCP key from it, THEN forgets the session."""
    inscription = requests.post(
        f"{base}/api/auth/register",
        json={"email": identifier, "password": "MotDePasse-123"},
        timeout=10,
    )
    assert inscription.status_code == 201, inscription.text
    creation = requests.post(
        f"{base}/api/keys", json={"name": "agent"},
        cookies=inscription.cookies, timeout=10,
    )
    assert creation.status_code == 201, creation.text
    return creation.json()["key"]


def _call(base, key, tool, arguments=None, identifier=1):
    response = requests.post(
        f"{base}/mcp",
        headers={"authorization": f"Bearer {key}"},
        json={
            "jsonrpc": "2.0", "id": identifier, "method": "tools/call",
            "params": {"name": tool, "arguments": arguments or {}},
        },
        timeout=120,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert "error" not in body, body
    result = body["result"]
    assert not result.get("isError"), result
    return json.loads(result["content"][0]["text"])


@pytest.mark.parametrize("action", ["regenerer", "recuperer", "administrer", "expirer"])
def test_security_change_on_all_accesses(platform, tmp_path, capsys, action):
    base = platform
    session = requests.Session()
    account = session.post(f"{base}/api/auth/register", json={
        "email": "preuve@exemple.test", "password": "MotDePasse-123"}, timeout=10).json()
    other = requests.Session()
    other.post(f"{base}/api/auth/login", json={
        "email": "preuve@exemple.test", "password": "MotDePasse-123"}, timeout=10)
    key = session.post(f"{base}/api/keys", json={"name": "preuve"}, timeout=10).json()["key"]
    headers = {"Authorization": f"Bearer {key}"}
    project = _call(base, key, "monl_compile_backend", {"spec": SPEC})["project_id"]
    archive = f"{base}/api/projects/{project}/download"
    assert requests.get(archive, headers=headers, timeout=10).status_code == 200
    store = IdentityStore(tmp_path / "projects")
    if action == "regenerer":
        refusal = session.post(f"{base}/api/auth/recovery-codes", json={}, timeout=10)
        assert refusal.status_code == 403, "Regeneration without password accepted"
        assert store.count_recovery_codes(account["user"]["id"]) == 8
        codes = session.post(f"{base}/api/auth/recovery-codes", json={
            "password": "MotDePasse-123"}, timeout=10).json()["recovery_codes"]
        assert session.get(f"{base}/api/auth/me", timeout=10).status_code == 200
        assert other.get(f"{base}/api/auth/me", timeout=10).status_code == 401, "Other session kept after regeneration"
        assert requests.get(archive, headers=headers, timeout=10).status_code == 200
        assert requests.post(f"{base}/api/auth/recover", json={
            "email": "preuve@exemple.test", "code": codes[0],
            "password": "NouveauMotDePasse-123"}, timeout=10).status_code == 204
        return
    if action == "expirer":
        assert session.post(f"{base}/api/projects/{project}/compiler", timeout=60).status_code == 201
        site = session.post(f"{base}/api/projects/{project}/start", timeout=30).json()
        assert requests.get(f"{base}/openapi.json", headers={"Host": site["host"]}, timeout=30).status_code == 200
        store.move_deadline(project, -1)
        assert requests.get(archive, headers=headers, timeout=10).status_code == 404, "Expired archive still accessible before purge"
        assert session.get(archive, timeout=10).status_code == 404
        assert session.get(f"{base}/api/projects/{project}", timeout=10).status_code == 404
        assert session.post(f"{base}/api/projects/{project}/compiler", timeout=10).status_code == 404
        assert session.post(f"{base}/api/projects/{project}/start", timeout=10).status_code == 404
        assert requests.get(f"{base}/openapi.json", headers={"Host": site["host"]}, timeout=10).status_code == 404, "Expired site still relayed"
        response = requests.post(f"{base}/mcp", headers=headers, json={
            "jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
                "name": "monl_inspect_contract", "arguments": {"project_id": project}}}, timeout=10)
        assert response.json()["result"]["isError"], "Expired project still accessible through MCP"
        return
    if action == "administrer":
        assert administer(["codes", "preuve@exemple.test", "--workspace", str(tmp_path / "projects")]) == 0
        output = capsys.readouterr().out
        assert "revoked" in output
        code_operator = next(line.strip() for line in output.splitlines()
                              if line.startswith("  "))
    else:
        assert requests.post(f"{base}/api/auth/recover", json={
            "email": "preuve@exemple.test", "code": account["recovery_codes"][0],
            "password": "NouveauMotDePasse-123"}, timeout=10).status_code == 204
    assert session.get(f"{base}/api/auth/me", timeout=10).status_code == 401, "Session kept after account takeover recovery"
    assert other.get(f"{base}/api/auth/me", timeout=10).status_code == 401
    assert requests.post(f"{base}/mcp", headers=headers, json={}, timeout=10).status_code == 401, "MCP key kept after account takeover recovery"
    assert requests.get(archive, headers=headers, timeout=10).status_code == 401
    if action == "administrer":
        assert requests.post(f"{base}/api/auth/recover", json={
            "email": "preuve@exemple.test", "code": code_operator,
            "password": "NouveauMotDePasse-123"}, timeout=10).status_code == 204
    word = "NouveauMotDePasse-123"
    assert session.post(f"{base}/api/auth/login", json={
        "email": "preuve@exemple.test", "password": word}, timeout=10).status_code == 200
    new = session.post(f"{base}/api/keys", json={"name": "neuve"}, timeout=10).json()["key"]
    assert requests.get(archive, headers={"Authorization": f"Bearer {new}"}, timeout=10).status_code == 200
    assert _call(base, new, "monl_list_projects")["projects"]


def test_oauth_without_recovery_codes(platform, tmp_path):
    store = IdentityStore(tmp_path / "projects")
    account, _ = store.upsert_oauth_account("github:4242", "github")
    assert store.count_recovery_codes(account) == 0
    session = requests.Session()
    session.cookies.set("monl_session", store.create_session(account))
    refusal = session.post(f"{platform}/api/auth/recovery-codes", json={
        "password": "MotDePasse-123"}, timeout=10)
    assert refusal.status_code == 403, "OAuth regeneration accepted"
    assert "OAuth" in refusal.json()["detail"]
    assert store.count_recovery_codes(account) == 0


def test_refused_regeneration_keeps_the_victims_code(platform):
    session = requests.Session()
    account = session.post(f"{platform}/api/auth/register", json={
        "email": "victime@exemple.test", "password": "MotDePasse-123"}, timeout=10).json()
    for content in ({}, {"password": "MotDePasse-Incorrect"}):
        assert session.post(f"{platform}/api/auth/recovery-codes", json=content,
                            timeout=10).status_code == 403, "Regeneration without valid secret accepted"
    assert requests.post(f"{platform}/api/auth/recover", json={
        "email": "victime@exemple.test", "code": account["recovery_codes"][0],
        "password": "NouveauMotDePasse-123"}, timeout=10).status_code == 204, "Victim's code destroyed by a refused regeneration"


def test_recovery_refuses_an_already_started_key_creation(platform, monkeypatch):
    session = requests.Session()
    account = session.post(f"{platform}/api/auth/register", json={
        "email": "differee@exemple.test", "password": "MotDePasse-123"}, timeout=10).json()
    entry, finish = threading.Event(), threading.Event()
    create = IdentityStore.create_api_key
    responses = []

    def creation_deferred(store, *arguments, **options):
        entry.set()
        assert finish.wait(10), "Recovery did not release the deferred creation"
        return create(store, *arguments, **options)

    monkeypatch.setattr(IdentityStore, "create_api_key", creation_deferred)
    fil = threading.Thread(target=lambda: responses.append(session.post(
        f"{platform}/api/keys", json={"name": "différée"}, timeout=15)))
    fil.start()
    try:
        assert entry.wait(10), "Key creation did not reach the registry"
        assert requests.post(f"{platform}/api/auth/recover", json={
            "email": "differee@exemple.test", "code": account["recovery_codes"][0],
            "password": "NouveauMotDePasse-123"}, timeout=10).status_code == 204
    finally:
        finish.set()
        fil.join(20)
    assert not fil.is_alive()
    assert responses[0].status_code == 401, "A revoked session created a new MCP key"


def test_an_agent_compiles_lists_and_downloads_without_ever_opening_a_session(platform):
    base = platform
    key = _key(base)

    compile = _call(base, key, "monl_compile_backend", {"spec": SPEC})
    project_id = compile["project_id"]
    assert compile["download_url"].endswith(f"/api/projects/{project_id}/download")
    assert "Bearer" in compile["download_auth"]

    projects = _call(base, key, "monl_list_projects")["projects"]
    assert [p["project_id"] for p in projects] == [project_id]

    # THE WALL OF BEFORE: without a cookie, this request answered 401.
    archive = requests.get(
        f"{base}{compile['download_path']}",
        headers={"authorization": f"Bearer {key}"},
        timeout=30,
    )
    assert archive.status_code == 200, archive.text
    with zipfile.ZipFile(io.BytesIO(archive.content)) as package:
        names = set(package.namelist())
    assert {"app.py", "schema.sql", "frontend_contract.json",
            "docs/FRONTEND_PROMPT.md"} <= names
    assert ".jwt_secret" not in names


def test_without_key_or_session_the_archive_stays_closed(platform):
    """The counter-proof: opening the door to the key does not open it to all."""
    base = platform
    key = _key(base, "proprietaire@example.test")
    project_id = _call(base, key, "monl_compile_backend", {"spec": SPEC})["project_id"]
    path = f"{base}/api/projects/{project_id}/download"

    assert requests.get(path, timeout=10).status_code == 401
    assert requests.get(
        path, headers={"authorization": "Bearer monl_inexistante"}, timeout=10
    ).status_code == 401
    # A VALID key of another account is no better: 404, never 403 — the opaque
    # identifier does not become an existence oracle.
    other = _key(base, "intrus@example.test")
    assert requests.get(
        path, headers={"authorization": f"Bearer {other}"}, timeout=10
    ).status_code == 404


def test_the_diff_announces_the_delta_without_writing_anything(platform):
    base = platform
    key = _key(base, "diff@example.test")
    project_id = _call(base, key, "monl_compile_backend", {"spec": SPEC})["project_id"]

    before = _call(base, key, "monl_inspect_contract", {"project_id": project_id})

    identical = _call(base, key, "monl_diff_spec",
                       {"project_id": project_id, "spec": SPEC})
    assert identical["delta"]["interface_inchangee"] is True

    evolved = _call(base, key, "monl_diff_spec",
                    {"project_id": project_id, "spec": SPEC_EVOLVED})
    assert evolved["ecrit"] is False
    assert evolved["delta"]["interface_inchangee"] is False
    assert "Note.etiquette" in evolved["delta"]["champs"]["ajoutes"]
    # Choosing from a list lives in "contents" (point 96): without it, the AI
    # would draw a text field instead of a dropdown menu.
    assert any("Note.etiquette" in key_content
               for key_content in evolved["delta"]["contenus"]["ajoutes"])

    # NOTHING was written: the project's contract did not move.
    apres = _call(base, key, "monl_inspect_contract", {"project_id": project_id})
    assert apres["contract"] == before["contract"]


def test_the_update_recompiles_in_place_and_keeps_the_address(platform):
    base = platform
    key = _key(base, "update@example.test")
    project_id = _call(base, key, "monl_compile_backend", {"spec": SPEC})["project_id"]

    rapport = _call(base, key, "monl_update_backend",
                     {"project_id": project_id, "spec": SPEC_EVOLVED})

    assert rapport["project_id"] == project_id, "the identifier must SURVIVE"
    assert rapport["ecrit"] is True
    assert "Note.etiquette" in rapport["delta"]["champs"]["ajoutes"]

    # The artifacts really changed, and the address did not move.
    contract = _call(base, key, "monl_inspect_contract",
                     {"project_id": project_id})["contract"]
    fields = {field["name"] for field in contract["entities"]["Note"]["fields"]}
    assert "etiquette" in fields

    archive = requests.get(
        f"{base}/api/projects/{project_id}/download",
        headers={"authorization": f"Bearer {key}"}, timeout=30,
    )
    assert archive.status_code == 200
    with zipfile.ZipFile(io.BytesIO(archive.content)) as package:
        spec_delivered = package.read("spec.ml").decode("utf-8")
    assert "etiquette" in spec_delivered

    # The summary follows the new contract: keeping it would make the card lie.
    resume = _call(base, key, "monl_inspect_contract",
                    {"project_id": project_id})["project"]["summary"]
    assert resume["contract_version"]


def test_a_refused_spec_leaves_the_project_intact(platform):
    """A failing compilation must destroy nothing."""
    base = platform
    key = _key(base, "refus@example.test")
    project_id = _call(base, key, "monl_compile_backend", {"spec": SPEC})["project_id"]
    before = _call(base, key, "monl_inspect_contract", {"project_id": project_id})

    response = requests.post(
        f"{base}/mcp",
        headers={"authorization": f"Bearer {key}"},
        json={"jsonrpc": "2.0", "id": 9, "method": "tools/call", "params": {
            "name": "monl_update_backend",
            "arguments": {"project_id": project_id, "spec": "app Cassee\n\nentity\n"},
        }},
        timeout=60,
    )
    assert response.status_code == 200
    assert response.json()["result"]["isError"] is True

    apres = _call(base, key, "monl_inspect_contract", {"project_id": project_id})
    assert apres["contract"] == before["contract"]
