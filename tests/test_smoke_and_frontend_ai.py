# Tests du smoke test comportemental (point 1) et de la boucle IA frontend
# (point 4). Fidèles à la méthode du projet : serveurs réels éphémères,
# jamais de simple relecture — seul le FOURNISSEUR d'IA est factice
# (l'orchestration, elle, s'exécute pour de vrai de bout en bout).
import json

import pytest

from monl.cli import compile_project
from monl.frontend_ai import (
    RETOUCHE_PROMPT_FILENAME,
    FrontendAIError,
    generate_and_verify,
    parse_files_payload,
)
from monl.smoke_test import run_smoke_test

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
import zipfile

from monl.frontend_ai import import_and_verify, load_frontend_source

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
import stat

from monl.frontend_ai import generate_with_claude_code
from monl.frontend_contract import PROJECT_CLAUDE_MD_MARKER


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
    from monl.frontend_ai import FrontendAIError
    agent = _fake_agent(tmp_path, CRASH_AGENT)
    with pytest.raises(FrontendAIError):
        generate_with_claude_code(str(project), command=agent, say=_quiet)


def test_claude_code_ne_peut_pas_toucher_le_backend(project, tmp_path):
    agent = _fake_agent(tmp_path, EVIL_AGENT)
    ok, errors = generate_with_claude_code(str(project), command=agent, say=_quiet)
    assert not ok
    assert any("app.py" in e for e in errors), errors


# POINT 134 : l'agent SOURNOIS ne touche PAS à frontend/. C'est tout l'écart
# avec EVIL_AGENT — et c'est le chemin qui échappait au garde-fou.
SNEAKY_AGENT = """open("manage.py", "a").write("\\n# porte derobee\\n")
"""


def test_un_agent_ne_peut_pas_reecrire_manage_py(project, tmp_path):
    """manage.py CRÉE les comptes administrateurs — c'est la frontière que
    `selfRegister` tient côté API. Il était scellé dans monl.json mais absent
    des artefacts dont l'empreinte est comparée avant/après le passage de
    l'agent.

    Le pire cas est reproduit ici : un frontend VALIDE existe déjà et l'agent
    n'y touche pas. `generate_with_cli_agent` retourne alors un SUCCÈS avant
    même d'appeler `check_coherence` — donc sans le correctif, monl répondait
    « rien n'est cassé » sur un manage.py piégé. Le code injecté s'exécutait à
    la première création de compte privilégié.
    """
    frontend = project / "frontend"
    frontend.mkdir(exist_ok=True)
    (frontend / "index.html").write_text(
        "<html><body>déjà là</body></html>", encoding="utf-8")
    avant = (project / "manage.py").read_text(encoding="utf-8")

    agent = _fake_agent(tmp_path, SNEAKY_AGENT)
    ok, errors = generate_with_claude_code(str(project), command=agent, say=_quiet)

    assert not ok, "un manage.py réécrit doit faire ÉCHOUER la construction"
    assert any("manage.py" in e for e in errors), errors
    # Le fichier reste sur disque — monl dit de le restaurer, il ne le fait
    # pas à votre place (point 73). Le test le CONSTATE plutôt que de laisser
    # croire à une remise en état.
    assert (project / "manage.py").read_text(encoding="utf-8") != avant


# L'agent fait un VRAI travail de frontend — et en profite au passage. C'est
# le cas qui passait tous les contrôles : empreintes protégées OK, cohérence
# OK, smoke test OK (il ne lit pas le Dockerfile), succès annoncé.
SABOTEUR_DOCKER = """os.makedirs("frontend", exist_ok=True)
open("frontend/index.html", "w").write("<html><body>ok</body></html>")
open("Dockerfile", "w").write(
    open("Dockerfile").read().replace('"serve:app"', '"app:app"'))
"""

SABOTEUR_SECRET = """os.makedirs("frontend", exist_ok=True)
open("frontend/index.html", "w").write("<html><body>ok</body></html>")
open(".dockerignore", "w").write("*.db\\n__pycache__\\n")
"""


def test_un_agent_ne_peut_pas_remettre_le_conteneur_en_404(project, tmp_path):
    """Annuler le point 133 dans le Dockerfile ne casse RIEN de vérifiable :
    la cohérence passe, le smoke test ne lit pas le Dockerfile, et l'image
    suivante répond à nouveau 404 sur /site. Seule l'empreinte protégée
    pouvait le voir — et elle ne regardait pas ce fichier."""
    agent = _fake_agent(tmp_path, SABOTEUR_DOCKER)
    ok, errors = generate_with_claude_code(str(project), command=agent, say=_quiet)
    assert not ok
    assert any("Dockerfile" in e for e in errors), errors


def test_un_agent_ne_peut_pas_faire_embarquer_le_secret_jwt(project, tmp_path):
    """Le pire des deux : `.dockerignore` exclut `.jwt_secret` du `COPY . .`
    du gabarit. L'en retirer fait entrer le secret de signature des jetons
    dans l'image — donc dans tout registre où elle est poussée. Aucun autre
    contrôle de monl ne regarde ce fichier."""
    agent = _fake_agent(tmp_path, SABOTEUR_SECRET)
    ok, errors = generate_with_claude_code(str(project), command=agent, say=_quiet)
    assert not ok
    assert any(".dockerignore" in e for e in errors), errors


def test_tout_ce_qui_sexecute_hors_frontend_est_protege():
    """L'empreinte protégée est un invariant PENDANT le passage de l'agent,
    pas une déclaration de propriété : l'auteur adapte son Dockerfile entre
    deux exécutions sans que ça gêne. C'est cette confusion qui avait laissé
    dehors des fichiers exécutables au prétexte qu'ils sont éditables."""
    from monl.frontend_ai import PROTECTED_ARTEFACTS
    for nom in ("manage.py", "serve.py", "Dockerfile", ".dockerignore"):
        assert nom in PROTECTED_ARTEFACTS, nom


# ─────────────────────────────────────────────────────────────────────
# POINT 69 : n'importe quelle clé API, n'importe quel agent
#
# Deux voies ouvertes, deux façons de les éprouver sans réseau ni binaire
# tiers : la requête HTTP est interceptée (on vérifie ce que monl ENVOIE),
# et l'agent est un exécutable factice qui enregistre son argv (on vérifie
# ce que monl LANCE). L'orchestration, elle, s'exécute pour de vrai.
# ─────────────────────────────────────────────────────────────────────
from monl.frontend_ai import (
    CLI_AGENTS,
    OPENAI_COMPATIBLE,
    PROVIDERS,
    build_agent_argv,
    generate_with_cli_agent,
)


def test_fournisseur_openai_compatible_forme_la_requete(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "cle-de-test")
    vu = {}

    class Reponse:
        status_code = 200
        text = ""

        def json(self):
            return {"choices": [{"message": {"content": '{"files": {}}'}}]}

    def faux_post(url, headers=None, json=None, timeout=None):
        vu.update(url=url, headers=headers, body=json)
        return Reponse()

    import requests
    monkeypatch.setattr(requests, "post", faux_post)

    call = PROVIDERS["groq"](model="un-modele")
    assert call("le brief") == '{"files": {}}'
    assert vu["url"] == "https://api.groq.com/openai/v1/chat/completions"
    assert vu["headers"]["Authorization"] == "Bearer cle-de-test"
    assert vu["body"]["model"] == "un-modele"
    assert vu["body"]["messages"][0]["content"] == "le brief"


def test_chaque_prereglage_nomme_sa_propre_variable_de_cle(monkeypatch):
    """Une clé absente doit nommer LA variable attendue : « clé manquante »
    sans dire laquelle envoie l'utilisateur lire le code."""
    from monl.frontend_ai import FrontendAIError
    for nom, (_url, variable) in OPENAI_COMPATIBLE.items():
        if nom == "ollama":
            continue                      # serveur local : pas de clé exigée
        monkeypatch.delenv(variable, raising=False)
        with pytest.raises(FrontendAIError) as e:
            PROVIDERS[nom](model="un-modele")
        assert variable in str(e.value), nom


def test_aucun_modele_par_defaut_hors_voie_anthropic(monkeypatch):
    """Le message doit demander --model, pas laisser partir une requête
    vers un identifiant deviné."""
    from monl.frontend_ai import FrontendAIError
    monkeypatch.setenv("GROQ_API_KEY", "cle-de-test")
    with pytest.raises(FrontendAIError) as e:
        PROVIDERS["groq"](model=None)
    assert "--model" in str(e.value)


def test_point_de_terminaison_libre_par_lenvironnement(monkeypatch):
    monkeypatch.setenv("MONL_AI_BASE_URL", "https://exemple.interne/v1")
    monkeypatch.setenv("MONL_AI_API_KEY", "cle-maison")
    vu = {}

    class Reponse:
        status_code = 200
        text = ""

        def json(self):
            return {"choices": [{"message": {"content": "ok"}}]}

    import requests
    monkeypatch.setattr(requests, "post",
                        lambda url, **kw: (vu.update(url=url), Reponse())[1])
    call = PROVIDERS["openai-compatible"](model="modele-maison")
    assert call("brief") == "ok"
    assert vu["url"] == "https://exemple.interne/v1/chat/completions"


def test_chaque_agent_a_sa_propre_ligne_de_commande():
    """Le point de la généralisation : l'instruction voyage jusqu'à l'agent,
    quelle que soit la forme de son argv."""
    for nom in CLI_AGENTS:
        binaire, args = build_agent_argv(nom, "CONSIGNE", 120)
        assert binaire == CLI_AGENTS[nom]["binary"]
        assert "CONSIGNE" in args, nom
    assert build_agent_argv("codex", "CONSIGNE", 120)[1][0] == "exec"


def test_gabarit_libre_pour_un_agent_hors_liste():
    binaire, args = build_agent_argv(None, "CONSIGNE", 120,
                                     agent_command="mon-agent --auto {instruction}")
    assert (binaire, args) == ("mon-agent", ["--auto", "CONSIGNE"])


def test_gabarit_sans_instruction_est_refuse():
    from monl.frontend_ai import FrontendAIError
    with pytest.raises(FrontendAIError) as e:
        build_agent_argv(None, "CONSIGNE", 120, agent_command="mon-agent --auto")
    assert "{instruction}" in str(e.value)


def test_agent_inconnu_est_refuse_en_nommant_les_connus():
    from monl.frontend_ai import FrontendAIError
    with pytest.raises(FrontendAIError) as e:
        build_agent_argv("inexistant", "CONSIGNE", 120)
    assert "claude-code" in str(e.value) and "--agent-command" in str(e.value)


def test_un_agent_tiers_construit_et_verifie_pour_de_vrai(project, tmp_path):
    """La boucle complète (exécution → empreintes → cohérence → smoke test)
    par la voie 'codex', avec un binaire factice."""
    agent = _fake_agent(tmp_path, GOOD_AGENT)
    ok, errors = generate_with_cli_agent(str(project), command=agent,
                                         agent="codex", say=_quiet)
    assert ok, errors


def test_un_agent_tiers_ne_peut_pas_davantage_toucher_le_backend(project, tmp_path):
    """Le garde-fou ne dépend PAS de qui écrit : c'est tout l'enjeu de la
    généralisation du point 69."""
    agent = _fake_agent(tmp_path, EVIL_AGENT)
    ok, errors = generate_with_cli_agent(str(project), command=agent,
                                         agent="codex", say=_quiet)
    assert not ok
    assert any("app.py" in e for e in errors), errors


def test_le_gabarit_libre_traverse_toute_la_boucle(project, tmp_path):
    agent = _fake_agent(tmp_path, GOOD_AGENT)
    ok, errors = generate_with_cli_agent(
        str(project), agent_command=f"{agent} {{instruction}}", say=_quiet)
    assert ok, errors


# --------------------------------------------------------------------------
# POINT 93 : la retouche — corriger sans reconstruire
# --------------------------------------------------------------------------

DEMANDE = "les images de la section Tendances sont mal cadrées"

NOOP_AGENT = "pass  # l'agent ne touche à rien\n"

RETOUCHE_AGENT = """open("frontend/index.html", "a").write(
    "<!-- object-position ajusté -->")
"""


def _projet_avec_frontend(project):
    front = project / "frontend"
    front.mkdir(exist_ok=True)
    (front / "index.html").write_text(GOOD_FRONT, encoding="utf-8")
    return front


def test_la_retouche_ecrit_sa_consigne_et_sauvegarde_lexistant(project):
    """La sauvegarde n'est pas du zèle : aucune vérification automatique ne peut
    trancher une question de goût, donc la seule garantie qu'on puisse offrir
    est de pouvoir revenir en arrière. C'est une COPIE — l'IA doit trouver
    l'existant en place pour le faire évoluer."""
    from monl.cli import cmd_retouche

    front = _projet_avec_frontend(project)
    cmd_retouche(str(project), DEMANDE, say=_quiet)

    consigne = (project / RETOUCHE_PROMPT_FILENAME).read_text(encoding="utf-8")
    assert DEMANDE in consigne
    assert (project / "frontend.precedent" / "index.html").read_text(
        encoding="utf-8") == GOOD_FRONT
    assert front.joinpath("index.html").exists(), "l'existant doit rester en place"


def test_la_retouche_refuse_un_projet_sans_frontend(project):
    """Retoucher ce qui n'existe pas n'a pas de sens — et le message doit
    envoyer vers la commande qui construit, pas laisser deviner."""
    from monl.cli import cmd_retouche

    with pytest.raises(SystemExit):
        cmd_retouche(str(project), DEMANDE, say=_quiet)


def test_la_retouche_refuse_une_demande_vide(project):
    from monl.cli import cmd_retouche

    _projet_avec_frontend(project)
    with pytest.raises(SystemExit):
        cmd_retouche(str(project), "   ", say=_quiet)


def test_le_prompt_de_retouche_porte_la_demande_les_fichiers_et_le_contrat(project):
    """Les trois morceaux sont indispensables ensemble : la demande dit QUOI,
    les fichiers actuels disent qu'il s'agit d'une évolution et non d'une page
    neuve, le contrat rappelle ce qui reste non négociable."""
    from monl.cli import cmd_retouche
    from monl.frontend_ai import build_generation_prompt

    _projet_avec_frontend(project)
    cmd_retouche(str(project), DEMANDE, say=_quiet)

    prompt = build_generation_prompt(str(project), False, retouche_mode=True)
    assert DEMANDE in prompt
    assert "Fichiers actuels du frontend" in prompt
    assert "fetch('/item?limit=5')" in prompt, "l'existant doit être joint"
    assert "Rappel du contrat d'origine" in prompt


def test_la_retouche_demande_linterpretation_la_plus_etroite(project):
    """Sans cette consigne, « les images sont mal cadrées » invite à refaire
    toute la mise en page — et une retouche trop large ne se distingue plus
    d'une reconstruction, c'est-à-dire de ce que la commande évite."""
    from monl.cli import cmd_retouche

    _projet_avec_frontend(project)
    chemin = cmd_retouche(str(project), DEMANDE, say=_quiet)
    consigne = open(chemin, encoding="utf-8").read()
    assert "ÉTROITE" in consigne
    assert "ne pas refaire la mise en page générale" in consigne.lower()
    # Et le garde-fou de contenu : ce qui vient de la spec ne se rattrape pas
    # par une astuce d'affichage (c'est le cas de la FAQ, point 94).
    assert "structure devinée" in consigne


def test_lagent_recoit_une_instruction_de_retouche_et_non_de_construction(project, tmp_path):
    """La voie agent doit changer de gabarit : « construis le frontend demandé »
    invitait à repartir de zéro."""
    from monl.cli import cmd_retouche
    from monl.frontend_ai import generate_with_cli_agent

    _projet_avec_frontend(project)
    cmd_retouche(str(project), DEMANDE, say=_quiet)
    mouchard = tmp_path / "argv.json"
    agent = _fake_agent(tmp_path, RETOUCHE_AGENT + f"""
import json
json.dump(sys.argv, open({str(mouchard)!r}, "w"))
""")
    generate_with_cli_agent(str(project), command=agent, say=_quiet,
                            retouche_mode=True)

    argv = json.loads(mouchard.read_text(encoding="utf-8"))
    instruction = " ".join(argv)
    assert RETOUCHE_PROMPT_FILENAME in instruction
    assert "défaut CONSTATÉ" in instruction
    assert "construis le frontend demandé" not in instruction


def test_une_retouche_qui_ne_change_rien_est_un_echec(project, tmp_path):
    """POINT 73 poussé d'un cran. Sur une CONSTRUCTION, « l'agent n'a rien
    écrit » est un avertissement : un frontend valide existait déjà. Sur une
    RETOUCHE, c'est la demande non traitée — l'humain a signalé un défaut qu'il
    VOIT, et répondre « tout va bien » serait le contraire d'un rapport
    honnête."""
    from monl.cli import cmd_retouche
    from monl.frontend_ai import generate_with_cli_agent

    _projet_avec_frontend(project)
    cmd_retouche(str(project), DEMANDE, say=_quiet)
    agent = _fake_agent(tmp_path, NOOP_AGENT)

    ok, errors = generate_with_cli_agent(str(project), command=agent, say=_quiet,
                                         retouche_mode=True)

    assert not ok
    assert any("retouche non appliquée" in e for e in errors), errors


def test_la_retouche_ne_peut_pas_davantage_toucher_le_backend(project, tmp_path):
    """Le garde-fou ne dépend pas de la commande qui l'emprunte — c'est tout
    l'enjeu d'avoir UNE voie vers l'IA et non deux."""
    from monl.cli import cmd_retouche
    from monl.frontend_ai import generate_with_cli_agent

    _projet_avec_frontend(project)
    cmd_retouche(str(project), DEMANDE, say=_quiet)
    agent = _fake_agent(tmp_path, EVIL_AGENT)

    ok, errors = generate_with_cli_agent(str(project), command=agent, say=_quiet,
                                         retouche_mode=True)

    assert not ok
    assert any("app.py" in e for e in errors), errors


def test_une_retouche_reussie_evolue_lexistant_et_reverifie(project, tmp_path):
    """Le bout en bout : l'agent modifie, monl re-vérifie (cohérence + smoke
    test), et ce que l'agent a écrit est TOUJOURS là après la vérification."""
    from monl.cli import cmd_retouche
    from monl.frontend_ai import generate_with_cli_agent

    _projet_avec_frontend(project)
    cmd_retouche(str(project), DEMANDE, say=_quiet)
    agent = _fake_agent(tmp_path, RETOUCHE_AGENT)

    ok, errors = generate_with_cli_agent(str(project), command=agent, say=_quiet,
                                         retouche_mode=True)

    assert ok, errors
    rendu = (project / "frontend" / "index.html").read_text(encoding="utf-8")
    assert "object-position ajusté" in rendu
    assert "fetch('/item?limit=5')" in rendu, "l'existant ne doit pas être réécrit"


DECLINING_AGENT = """print("Je ne peux pas retirer cette rubrique depuis frontend/ :")
print("elle vient du bloc 'landing' de la spec, et FRONTEND_PROMPT.md exige")
print("qu'elle soit lisible au fil de l'accueil. Cela se règle dans la spec.")
"""


def test_quand_lagent_decline_sa_raison_est_affichee(project, tmp_path):
    """POINT 97 : le message d'échec était une HYPOTHÈSE, et elle était fausse.
    « Reformuler en nommant l'écran et l'élément » s'affichait sur une demande
    qui les nommait — parce que la vraie raison (« cette rubrique vient de la
    spec, pas du frontend ») avait été jetée avec la sortie de l'agent.

    La consigne de retouche demande explicitement à l'IA de SIGNALER ce cas
    plutôt que de le contourner ; l'entendre et ne pas le répéter était le
    défaut le plus coûteux possible — il envoyait l'utilisateur reformuler une
    demande déjà claire."""
    from monl.cli import cmd_retouche
    from monl.frontend_ai import generate_with_cli_agent

    _projet_avec_frontend(project)
    cmd_retouche(str(project), "retire la rubrique À propos de l'accueil", say=_quiet)
    agent = _fake_agent(tmp_path, DECLINING_AGENT)
    msgs = []

    ok, _errors = generate_with_cli_agent(str(project), command=agent,
                                          say=msgs.append, retouche_mode=True)

    sortie = "\n".join(msgs)
    assert not ok
    assert "elle vient du bloc 'landing' de la spec" in sortie, sortie
    # Et l'ancienne hypothèse ne doit PLUS s'afficher quand l'agent a parlé.
    assert "Reformuler la demande" not in sortie, sortie
    # …remplacée par le geste qui convient vraiment.
    assert "monl update" in sortie, sortie


def test_sans_explication_le_conseil_de_reformulation_reste(project, tmp_path):
    """Le témoin : un agent muet ne dit rien d'utile, et là le conseil de
    reformulation garde tout son sens. Le supprimer pour de bon aurait laissé
    l'utilisateur sans piste."""
    from monl.cli import cmd_retouche
    from monl.frontend_ai import generate_with_cli_agent

    _projet_avec_frontend(project)
    cmd_retouche(str(project), DEMANDE, say=_quiet)
    agent = _fake_agent(tmp_path, NOOP_AGENT)
    msgs = []

    generate_with_cli_agent(str(project), command=agent, say=msgs.append,
                            retouche_mode=True)

    assert "Reformuler la demande" in "\n".join(msgs)
