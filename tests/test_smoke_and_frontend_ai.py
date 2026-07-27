# Tests du smoke test comportemental (point 1) et de la boucle IA frontend
# (point 4). Fidèles à la méthode du projet : serveurs réels éphémères,
# jamais de simple relecture — seul le FOURNISSEUR d'IA est factice
# (l'orchestration, elle, s'exécute pour de vrai de bout en bout).
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from cli import compile_project
from frontend_ai import (
    FrontendAIError,
    generate_and_verify,
    parse_files_payload,
)
from smoke_test import run_smoke_test

SPEC = """app SmokeApp

entity Item
    label: String
    price: Money

actor Admin selfRegister

rule Item.label required
rule Item.Read public

workflow ManageItem for Admin
    Create Item
    Read Item
    Update Item
    Delete Item

seed Item
    label: "Alpha", price: 9.5
    label: "Beta", price: 19.5
"""

GOOD_FRONT = """<!doctype html><html><body><div id="l"></div>
<script>
fetch('/item?limit=5').then(r => r.json()).then(d => {
  document.getElementById('l').textContent = d.data.map(i => i.label).join(', ');
});
</script></body></html>"""

BAD_FRONT = ("<!doctype html><html><body><script>"
             "fetch('/fantome/1'); casse();</script></body></html>")

ABSOLUTE_FRONT = ("<!doctype html><html><body><script>"
                  "fetch('http://127.0.0.1:8000/item?limit=5');"
                  "</script></body></html>")


@pytest.fixture()
def project(tmp_path):
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "spec.ml").write_text(SPEC, encoding="utf-8")
    compile_project(str(proj / "spec.ml"), str(proj))
    return proj


def _quiet(*_a, **_k):
    pass


def test_smoke_passe_sans_frontend_et_ne_touche_pas_la_base(project):
    # Sentinelle : une base réelle avec un contenu marqueur.
    sentinel = project / "app.db"
    sentinel.write_bytes(b"donnees-reelles-intouchables")
    ok, errors, _w = run_smoke_test(str(project), say=_quiet)
    assert ok, errors
    assert sentinel.read_bytes() == b"donnees-reelles-intouchables", (
        "le smoke test a modifié la base réelle du projet")


def test_smoke_valide_un_frontend_correct(project):
    front = project / "frontend"
    front.mkdir()
    (front / "index.html").write_text(GOOD_FRONT, encoding="utf-8")
    ok, errors, warnings = run_smoke_test(str(project), say=_quiet)
    assert ok, errors
    # le fetch initial a bien été observé (pas un faux positif silencieux)
    assert not any("aucun appel API" in w for w in warnings)


def test_smoke_bloque_un_frontend_casse(project):
    front = project / "frontend"
    front.mkdir()
    (front / "index.html").write_text(BAD_FRONT, encoding="utf-8")
    ok, errors, _w = run_smoke_test(str(project), say=_quiet)
    assert not ok
    assert any("casse" in e for e in errors), errors          # exception JS
    assert any("/fantome" in e for e in errors), errors        # hors contrat


def test_smoke_nomme_lurl_absolue_au_lieu_de_fetch_failed(project):
    """Régression (point 51) : le serveur éphémère écoutant sur un port
    libre, un frontend qui vise 8000 en dur échouait en 'TypeError: fetch
    failed' — message muet sur la cause, sur lequel la correction
    automatique tournait en rond deux fois avant d'abandonner. L'échec doit
    rester un échec (ce port casserait aussi 'monl run --port'), mais nommé."""
    front = project / "frontend"
    front.mkdir()
    (front / "index.html").write_text(ABSOLUTE_FRONT, encoding="utf-8")
    ok, errors, warnings = run_smoke_test(str(project), say=_quiet)
    assert not ok
    assert any("URL absolue" in e for e in errors), errors
    # La tentative compte comme un appel : sans cela le rapport conclurait
    # « aucun appel API au chargement », ce qui est faux et brouille la piste.
    assert not any("aucun appel API" in w for w in warnings), warnings


def test_parse_files_payload_gardes_fous():
    with pytest.raises(FrontendAIError):   # traversée de chemin
        parse_files_payload(json.dumps({"files": {"../evil.html": "x", "index.html": "x"}}))
    with pytest.raises(FrontendAIError):   # extension interdite
        parse_files_payload(json.dumps({"files": {"index.html": "x", "run.py": "x"}}))
    with pytest.raises(FrontendAIError):   # index.html manquant
        parse_files_payload(json.dumps({"files": {"app.js": "x"}}))
    # clôtures Markdown tolérées malgré la consigne
    fenced = "```json\n" + json.dumps({"files": {"index.html": "ok"}}) + "\n```"
    assert parse_files_payload(fenced) == {"index.html": "ok"}


def test_boucle_ia_corrige_puis_reussit(project):
    calls = []

    def provider(prompt):
        calls.append(prompt)
        payload = BAD_FRONT if len(calls) == 1 else GOOD_FRONT
        return json.dumps({"files": {"index.html": payload}})

    ok, errors = generate_and_verify(str(project), provider, say=_quiet)
    assert ok, errors
    assert len(calls) == 2
    # la 2e tentative embarque les erreurs réellement constatées
    assert "ÉCHEC DE LA VÉRIFICATION" in calls[1]
    assert "casse" in calls[1] or "/fantome" in calls[1]


def test_boucle_ia_echoue_apres_une_seule_correction(project):
    calls = []

    def provider(prompt):
        calls.append(prompt)
        return json.dumps({"files": {"index.html": BAD_FRONT}})

    ok, errors = generate_and_verify(str(project), provider, say=_quiet)
    assert not ok and errors
    assert len(calls) == 2, "jamais plus d'UNE correction automatique"
    # les fichiers restent inspectables, mais run refusera (smoke bloquant)
    assert (project / "frontend" / "index.html").exists()


# ---- 'monl import' : la voie SANS clé API (abonnement claude.ai) ----
import zipfile  # noqa: E402

from frontend_ai import import_and_verify, load_frontend_source  # noqa: E402

GOOD_SPLIT_HTML = ('<!doctype html><html><body><div id="l"></div>'
                   '<script src="app.js"></script></body></html>')
GOOD_SPLIT_JS = ("fetch('/item?limit=5').then(r => r.json()).then(d => {"
                 "document.getElementById('l').textContent = d.total;});")


def test_import_zip_realiste_sous_dossier_et_parasite(project, tmp_path):
    """Un zip 'comme Claude le rend' : sous-dossier, JS séparé, fichier hors
    liste blanche — installé, filtré, et le fetch de app.js est bien ÉPROUVÉ
    (les scripts locaux sont inlinés avant jsdom, sinon faux positif)."""
    zpath = tmp_path / "telechargement.zip"
    with zipfile.ZipFile(zpath, "w") as z:
        z.writestr("mon-app/index.html", GOOD_SPLIT_HTML)
        z.writestr("mon-app/app.js", GOOD_SPLIT_JS)
        z.writestr("mon-app/notes.py", "parasite")
    ok, errors = import_and_verify(str(project), str(zpath), say=_quiet)
    assert ok, errors
    assert (project / "frontend" / "app.js").exists()
    assert not (project / "frontend" / "notes.py").exists()


def test_import_refuse_zip_slip_et_cdn(project, tmp_path):
    evil = tmp_path / "evil.zip"
    with zipfile.ZipFile(evil, "w") as z:
        z.writestr("../evasion.html", "x")
        z.writestr("index.html", "x")
    with pytest.raises(FrontendAIError):
        load_frontend_source(str(evil))

    cdn = tmp_path / "cdn.zip"
    with zipfile.ZipFile(cdn, "w") as z:
        z.writestr("index.html", '<html><body>'
                   '<script src="https://cdn.exemple.com/lib.js"></script>'
                   '</body></html>')
    ok, errors = import_and_verify(str(project), str(cdn), say=_quiet)
    assert not ok
    assert any("CDN" in e for e in errors), errors


def test_import_html_seul_et_sauvegarde_du_precedent(project, tmp_path):
    single = tmp_path / "telechargement.html"
    single.write_text(GOOD_FRONT, encoding="utf-8")
    ok, _e = import_and_verify(str(project), str(single), say=_quiet)
    assert ok
    # Réimporter par-dessus : l'ancien frontend est conservé, jamais perdu.
    ok, _e = import_and_verify(str(project), str(single), say=_quiet)
    assert ok
    assert (project / "frontend.precedent" / "index.html").exists()


# ---- Claude Code : le travail directement dans le dossier cible ----
import stat  # noqa: E402

from frontend_ai import generate_with_claude_code  # noqa: E402
from frontend_contract import PROJECT_CLAUDE_MD_MARKER  # noqa: E402


def _fake_agent(tmp_path, body):
    """Un exécutable 'claude' factice — l'orchestration s'exécute pour de
    vrai, seul l'agent est simulé (même approche que le fournisseur API)."""
    script = tmp_path / "fake_claude"
    script.write_text("#!/usr/bin/env python3\nimport os, sys\n" + body,
                      encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return str(script)


GOOD_AGENT = """os.makedirs("frontend", exist_ok=True)
open("frontend/index.html", "w").write('''<html><body><div id="l"></div>
<script>fetch('/item?limit=5').then(r=>r.json()).then(d=>{
document.getElementById('l').textContent=d.total;});</script></body></html>''')
"""

FIXER_AGENT = """os.makedirs("frontend", exist_ok=True)
if not os.path.exists(".attempt"):
    open(".attempt", "w").write("x")
    open("frontend/index.html", "w").write(
        "<html><body><script>fetch('/fantome/1'); boom();</script></body></html>")
else:
    assert "fantome" in sys.argv[2] or "boom" in sys.argv[2]
    open("frontend/index.html", "w").write('''<html><body><div id="l"></div>
<script>fetch('/item?limit=5').then(r=>r.json()).then(d=>{
document.getElementById('l').textContent=d.total;});</script></body></html>''')
"""

EVIL_AGENT = """os.makedirs("frontend", exist_ok=True)
open("frontend/index.html", "w").write("<html><body>ok</body></html>")
open("app.py", "a").write("\\n# intrusion\\n")
"""


def test_claude_md_de_projet_genere_et_jamais_ecrase(project):
    claude_md = project / "CLAUDE.md"
    assert claude_md.exists()
    assert PROJECT_CLAUDE_MD_MARKER in claude_md.read_text(encoding="utf-8")
    # Repris en main par l'utilisateur (marqueur retiré) -> intouchable.
    claude_md.write_text("# mes propres consignes", encoding="utf-8")
    compile_project(str(project / "spec.ml"), str(project))
    assert claude_md.read_text(encoding="utf-8") == "# mes propres consignes"


def test_claude_code_reussit_et_verifie(project, tmp_path):
    agent = _fake_agent(tmp_path, GOOD_AGENT)
    ok, errors = generate_with_claude_code(str(project), command=agent, say=_quiet)
    assert ok, errors


def test_claude_code_recoit_les_erreurs_et_se_corrige(project, tmp_path):
    agent = _fake_agent(tmp_path, FIXER_AGENT)
    msgs = []
    ok, errors = generate_with_claude_code(str(project), command=agent, say=msgs.append)
    assert ok, errors
    assert any("Correction automatique" in m for m in msgs)


MAXTURNS_AGENT = """os.makedirs("frontend", exist_ok=True)
open("frontend/index.html", "w").write('''<html><body><div id="l"></div>
<script>fetch('/item?limit=5').then(r=>r.json()).then(d=>{
document.getElementById('l').textContent=d.total;});</script></body></html>''')
sys.stderr.write("Error: Reached max turns (40)\\n")
sys.exit(1)
"""

MAXTURNS_VIDE_AGENT = """sys.stderr.write("Error: Reached max turns (40)\\n")
sys.exit(1)
"""

CRASH_AGENT = """sys.stderr.write("Error: authentication failed\\n")
sys.exit(1)
"""


def test_budget_de_tours_epuise_mais_frontend_valide(project, tmp_path):
    """POINT 62 : l'agent peut finir son travail au dernier tour et dépasser
    d'un cheveu. Le frontend produit doit être vérifié sur pièces, pas jeté
    parce que le processus a rendu un code de sortie non nul."""
    agent = _fake_agent(tmp_path, MAXTURNS_AGENT)
    ok, errors = generate_with_claude_code(str(project), command=agent, say=_quiet)
    assert ok, errors


def test_budget_epuise_sans_rien_produire_passe_par_la_correction(project, tmp_path):
    """Le même dépassement, mais sans frontend : c'est un échec — qui doit
    emprunter la boucle de correction, pas interrompre la commande."""
    agent = _fake_agent(tmp_path, MAXTURNS_VIDE_AGENT)
    msgs = []
    ok, errors = generate_with_claude_code(str(project), command=agent, say=msgs.append)
    assert not ok
    assert any("index.html absent" in e for e in errors), errors
    assert any("Correction automatique" in m for m in msgs)


def test_une_vraie_erreur_dagent_reste_une_erreur(project, tmp_path):
    """Le relâchement ne vaut QUE pour le budget de tours : une panne
    d'authentification doit continuer d'arrêter net."""
    from frontend_ai import FrontendAIError
    agent = _fake_agent(tmp_path, CRASH_AGENT)
    with pytest.raises(FrontendAIError):
        generate_with_claude_code(str(project), command=agent, say=_quiet)


def test_claude_code_ne_peut_pas_toucher_le_backend(project, tmp_path):
    agent = _fake_agent(tmp_path, EVIL_AGENT)
    ok, errors = generate_with_claude_code(str(project), command=agent, say=_quiet)
    assert not ok
    assert any("app.py" in e for e in errors), errors
