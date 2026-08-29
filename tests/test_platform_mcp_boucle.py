"""La boucle MCP se ferme SANS navigateur — preuve HTTP contre un vrai serveur.

POINT 162. Un agent pouvait valider et compiler par MCP, puis butait sur trois
murs : l'archive n'était ouverte que par le cookie `monl_session`, il n'existait
aucun moyen de retrouver ses projets, et aucun équivalent de `monl update` ni de
`monl diff` — or c'est TOUT le geste après la première compilation.

Ce fichier fait le parcours entier avec UNE clé MCP et rien d'autre : compiler,
lister, télécharger les octets de l'archive, mesurer ce qu'une spec nouvelle
changerait, puis recompiler en place. Le compte n'ouvre jamais de session.
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

from monl_platform.app import create_app

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

SPEC_EVOLUEE = SPEC.replace(
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
def plateforme(tmp_path):
    app = create_app(workspace=tmp_path / "projects", domain="localhost")
    port = _free_port()
    serveur = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    )
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
            pytest.fail("le serveur de plateforme n'a pas démarré")
        yield base
    finally:
        serveur.should_exit = True
        fil.join(timeout=10)
        assert not fil.is_alive()


def _cle(base, identifiant="agent@example.test"):
    """Crée un compte, en tire une clé MCP, PUIS oublie la session."""
    inscription = requests.post(
        f"{base}/api/auth/register",
        json={"email": identifiant, "password": "MotDePasse-123"},
        timeout=10,
    )
    assert inscription.status_code == 201, inscription.text
    creation = requests.post(
        f"{base}/api/keys", json={"name": "agent"},
        cookies=inscription.cookies, timeout=10,
    )
    assert creation.status_code == 201, creation.text
    return creation.json()["key"]


def _appel(base, cle, outil, arguments=None, identifiant=1):
    reponse = requests.post(
        f"{base}/mcp",
        headers={"authorization": f"Bearer {cle}"},
        json={
            "jsonrpc": "2.0", "id": identifiant, "method": "tools/call",
            "params": {"name": outil, "arguments": arguments or {}},
        },
        timeout=120,
    )
    assert reponse.status_code == 200, reponse.text
    corps = reponse.json()
    assert "error" not in corps, corps
    resultat = corps["result"]
    assert not resultat.get("isError"), resultat
    return json.loads(resultat["content"][0]["text"])


def test_un_agent_compile_liste_et_telecharge_sans_jamais_ouvrir_de_session(plateforme):
    base = plateforme
    cle = _cle(base)

    compile = _appel(base, cle, "monl_compile_backend", {"spec": SPEC})
    project_id = compile["project_id"]
    assert compile["download_url"].endswith(f"/api/projects/{project_id}/download")
    assert "Bearer" in compile["download_auth"]

    projets = _appel(base, cle, "monl_list_projects")["projects"]
    assert [p["project_id"] for p in projets] == [project_id]

    # LE MUR D'AVANT : sans cookie, cette requête répondait 401.
    archive = requests.get(
        f"{base}{compile['download_path']}",
        headers={"authorization": f"Bearer {cle}"},
        timeout=30,
    )
    assert archive.status_code == 200, archive.text
    with zipfile.ZipFile(io.BytesIO(archive.content)) as paquet:
        noms = set(paquet.namelist())
    assert {"app.py", "schema.sql", "frontend_contract.json",
            "FRONTEND_PROMPT.md"} <= noms
    assert ".jwt_secret" not in noms


def test_sans_cle_ni_session_l_archive_reste_fermee(plateforme):
    """La contre-épreuve : ouvrir la porte à la clé ne l'ouvre pas à tous."""
    base = plateforme
    cle = _cle(base, "proprietaire@example.test")
    project_id = _appel(base, cle, "monl_compile_backend", {"spec": SPEC})["project_id"]
    chemin = f"{base}/api/projects/{project_id}/download"

    assert requests.get(chemin, timeout=10).status_code == 401
    assert requests.get(
        chemin, headers={"authorization": "Bearer monl_inexistante"}, timeout=10
    ).status_code == 401
    # Une clé VALIDE d'un autre compte ne vaut pas mieux : 404, jamais 403 —
    # l'identifiant opaque ne devient pas un oracle d'existence.
    autre = _cle(base, "intrus@example.test")
    assert requests.get(
        chemin, headers={"authorization": f"Bearer {autre}"}, timeout=10
    ).status_code == 404


def test_le_diff_annonce_le_delta_sans_rien_ecrire(plateforme):
    base = plateforme
    cle = _cle(base, "diff@example.test")
    project_id = _appel(base, cle, "monl_compile_backend", {"spec": SPEC})["project_id"]

    avant = _appel(base, cle, "monl_inspect_contract", {"project_id": project_id})

    identique = _appel(base, cle, "monl_diff_spec",
                       {"project_id": project_id, "spec": SPEC})
    assert identique["delta"]["interface_inchangee"] is True

    evolue = _appel(base, cle, "monl_diff_spec",
                    {"project_id": project_id, "spec": SPEC_EVOLUEE})
    assert evolue["ecrit"] is False
    assert evolue["delta"]["interface_inchangee"] is False
    assert "Note.etiquette" in evolue["delta"]["champs"]["ajoutes"]
    # Le choix parmi une liste vit dans « contenus » (point 96) : sans lui,
    # l'IA dessinerait un champ texte au lieu d'un menu déroulant.
    assert any("Note.etiquette" in cle_contenu
               for cle_contenu in evolue["delta"]["contenus"]["ajoutes"])

    # RIEN n'a été écrit : le contrat du projet n'a pas bougé.
    apres = _appel(base, cle, "monl_inspect_contract", {"project_id": project_id})
    assert apres["contract"] == avant["contract"]


def test_la_mise_a_jour_recompile_en_place_et_garde_l_adresse(plateforme):
    base = plateforme
    cle = _cle(base, "update@example.test")
    project_id = _appel(base, cle, "monl_compile_backend", {"spec": SPEC})["project_id"]

    rapport = _appel(base, cle, "monl_update_backend",
                     {"project_id": project_id, "spec": SPEC_EVOLUEE})

    assert rapport["project_id"] == project_id, "l'identifiant doit SURVIVRE"
    assert rapport["ecrit"] is True
    assert "Note.etiquette" in rapport["delta"]["champs"]["ajoutes"]

    # Les artefacts ont vraiment changé, et l'adresse n'a pas bougé.
    contrat = _appel(base, cle, "monl_inspect_contract",
                     {"project_id": project_id})["contract"]
    champs = {champ["name"] for champ in contrat["entities"]["Note"]["fields"]}
    assert "etiquette" in champs

    archive = requests.get(
        f"{base}/api/projects/{project_id}/download",
        headers={"authorization": f"Bearer {cle}"}, timeout=30,
    )
    assert archive.status_code == 200
    with zipfile.ZipFile(io.BytesIO(archive.content)) as paquet:
        spec_livree = paquet.read("spec.ml").decode("utf-8")
    assert "etiquette" in spec_livree

    # Le résumé suit le nouveau contrat : le garder ferait mentir la fiche.
    resume = _appel(base, cle, "monl_inspect_contract",
                    {"project_id": project_id})["project"]["summary"]
    assert resume["contract_version"]


def test_une_spec_refusee_laisse_le_projet_intact(plateforme):
    """Une compilation qui échoue ne doit rien détruire."""
    base = plateforme
    cle = _cle(base, "refus@example.test")
    project_id = _appel(base, cle, "monl_compile_backend", {"spec": SPEC})["project_id"]
    avant = _appel(base, cle, "monl_inspect_contract", {"project_id": project_id})

    reponse = requests.post(
        f"{base}/mcp",
        headers={"authorization": f"Bearer {cle}"},
        json={"jsonrpc": "2.0", "id": 9, "method": "tools/call", "params": {
            "name": "monl_update_backend",
            "arguments": {"project_id": project_id, "spec": "app Cassee\n\nentity\n"},
        }},
        timeout=60,
    )
    assert reponse.status_code == 200
    assert reponse.json()["result"]["isError"] is True

    apres = _appel(base, cle, "monl_inspect_contract", {"project_id": project_id})
    assert apres["contract"] == avant["contract"]
