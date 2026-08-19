# Tests du smoke test comportemental (point 1) et de la boucle IA frontend
# (point 4). Fidèles à la méthode du projet : serveurs réels éphémères,
# jamais de simple relecture — seul le FOURNISSEUR d'IA est factice
# (l'orchestration, elle, s'exécute pour de vrai de bout en bout).
import json

import pytest

from monl.cli import compile_project
from monl.design_system import activate_asset_manifest
from monl.frontend_ai import (
    RETOUCHE_PROMPT_FILENAME,
    FrontendAIError,
    generate_and_verify,
    parse_files_payload,
    parse_single_file_payload,
)
from monl.smoke_test import run_smoke_test

SPEC = """app SmokeApp

entity Item
    label: String
    price: Money

# Admin est provisionné hors ligne ; le frontend minimal de ces tests ne
# constitue pas une promesse de back-office public.
actor Admin

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


def test_coherence_refuse_une_image_locale_absente(project):
    front = project / "frontend"
    front.mkdir()
    (front / "index.html").write_text(
        '<!doctype html><html><body><img src="missing.svg"></body></html>',
        encoding="utf-8")
    activate_asset_manifest(str(project))
    from monl.frontend_ai import _frontend_local_reference_errors
    errors = _frontend_local_reference_errors(str(project))
    assert any("ressource locale absente" in error for error in errors)


def test_coherence_refuse_chacun_des_trois_svg_locaux_absents(project):
    front = project / "frontend"
    front.mkdir()
    chemins = (
        "assets/product/vase-rondeur.svg",
        "assets/product/bol-terre.svg",
        "assets/product/plateau-ligne.svg",
    )
    sources = "".join(f'<img src="{chemin}">' for chemin in chemins)
    (front / "index.html").write_text(
        f"<!doctype html><html><body>{sources}</body></html>",
        encoding="utf-8")
    from monl.frontend_ai import _frontend_local_reference_errors

    errors = _frontend_local_reference_errors(str(project))
    missing = [error for error in errors if "ressource locale absente" in error]
    assert len(missing) == len(chemins)
    for chemin in chemins:
        assert sum(chemin in error for error in missing) == 1


def test_un_gabarit_de_rendu_nest_pas_un_chemin_de_fichier(project):
    # Le corps d'un <script> n'est pas du balisage : `src="${...}"` y désigne
    # une image que l'API renverra. Lu comme une balise, il faisait refuser la
    # forme même que le contrat RÉCLAME (rendre les vraies images de l'API) —
    # c'est la forme de demo/ et de projets/CodexShop.
    front = project / "frontend"
    front.mkdir()
    (front / "index.html").write_text(
        '<!doctype html><html><body><div id="l"></div>'
        '<script>const carte = (p) => `<img src="${esc(p.imageUrl)}" alt="">`;'
        '</script><script src="app.js"></script></body></html>',
        encoding="utf-8")
    (front / "app.js").write_text("const esc = (s) => String(s);", encoding="utf-8")
    from monl.frontend_ai import _frontend_local_reference_errors
    assert _frontend_local_reference_errors(str(project)) == []


def test_le_chemin_absolu_du_montage_site_est_servi_mais_pas_celui_hors_site(project):
    # serve.py monte frontend/ sur /site : `/site/hero.svg` est exactement ce
    # que sert le wrapper (forme de projets/StudioNova, vérifiée en 200 contre
    # un vrai serveur). C'est `/hero.svg`, servi par personne, qui est fautif.
    front = project / "frontend"
    front.mkdir()
    (front / "hero.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1 1"/>',
        encoding="utf-8")
    from monl.frontend_ai import _frontend_local_reference_errors
    (front / "index.html").write_text(
        '<!doctype html><html><body><img src="/site/hero.svg"></body></html>',
        encoding="utf-8")
    assert _frontend_local_reference_errors(str(project)) == []
    (front / "index.html").write_text(
        '<!doctype html><html><body><img src="/hero.svg"></body></html>',
        encoding="utf-8")
    assert any("jamais servie" in error
               for error in _frontend_local_reference_errors(str(project)))


def test_un_dossier_dassets_declare_mais_absent_retombe_sur_frontend(project):
    # Le wrapper ne monte le dossier d'assets que s'il EXISTE sur le disque.
    # Déclaré dans la spec ne veut pas dire présent : quand il manque, la
    # requête retombe sur /site et `assets/x.svg` est servi depuis
    # frontend/assets/. Croire le contrat sur parole faisait refuser trois
    # images de projets/KoraMaison qui répondent 200.
    contract_path = project / "frontend_contract.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    contract["assets"] = {"dir": "assets"}
    contract_path.write_text(json.dumps(contract), encoding="utf-8")
    front = project / "frontend"
    (front / "assets").mkdir(parents=True)
    (front / "assets" / "photo.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1 1"/>',
        encoding="utf-8")
    (front / "index.html").write_text(
        '<!doctype html><html><body><img src="assets/photo.svg"></body></html>',
        encoding="utf-8")
    from monl.frontend_ai import _frontend_local_reference_errors
    assert _frontend_local_reference_errors(str(project)) == []

    # Le dossier racine existe : c'est LUI qui est monté, et le fichier
    # cherché là — un frontend/assets/ homonyme ne le sauve plus.
    (project / "assets").mkdir()
    assert any("ressource locale absente" in error
               for error in _frontend_local_reference_errors(str(project)))


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


def test_parse_single_file_payload_accepte_un_css_sans_index():
    payload = json.dumps({"files": {"styles.css": "body { color: #111; }"}})
    assert parse_single_file_payload(payload, "styles.css") == {
        "styles.css": "body { color: #111; }"
    }
    with pytest.raises(FrontendAIError):
        parse_single_file_payload(
            json.dumps({"files": {"app.js": "ok"}}), "styles.css")


def test_svg_standard_est_accepte_mais_une_ressource_distante_est_refusee():
    svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 8 8"><circle cx="4" cy="4" r="3"/></svg>'
    assert parse_single_file_payload(
        json.dumps({"files": {"hero.svg": svg}}), "hero.svg")["hero.svg"] == svg
    distant = '<svg xmlns="http://www.w3.org/2000/svg"><image href="https://exemple.test/photo.png"/></svg>'
    with pytest.raises(FrontendAIError, match="ressource externe"):
        parse_single_file_payload(
            json.dumps({"files": {"hero.svg": distant}}), "hero.svg")


def test_coherence_repere_un_id_dataset_compare_sans_conversion(project):
    front = project / "frontend"
    front.mkdir()
    (front / "app.js").write_text(
        "const id = button.dataset.id; state.items.find((item) => item.id === id);",
        encoding="utf-8")
    from monl.frontend_ai import _frontend_behavioral_quality_errors
    errors = _frontend_behavioral_quality_errors(str(project))
    assert any("identifiant DOM non normalisé" in error for error in errors)

    (front / "app.js").write_text(
        "const id = Number(button.dataset.id); state.items.find((item) => item.id === id);",
        encoding="utf-8")
    assert _frontend_behavioral_quality_errors(str(project)) == []


def test_design_refuse_image_generee_reutilisee_et_texte_editorial_duplique(project):
    front = project / "frontend"
    front.mkdir()
    (front / "index.html").write_text(
        '<img src="hero.svg"><img src="hero.svg">', encoding="utf-8")
    from monl.frontend_ai import (
        _editorial_content_errors,
        _generated_asset_reuse_errors,
    )
    image_errors = _generated_asset_reuse_errors(
        str(front), [{"path": "hero.svg"}])
    assert any("asset généré réutilisé" in error for error in image_errors)

    section_body = ("Maison Serein propose une parenthèse calme, avec des gestes "
                    "précis et une écoute attentive pour chaque personne reçue.")
    (project / "frontend_contract.json").write_text(json.dumps({
        "sections": [{"title": "À propos", "body": section_body}],
    }), encoding="utf-8")
    text_errors = _editorial_content_errors(
        str(project), section_body + " " + section_body)
    assert any("contenu éditorial répété" in error for error in text_errors)


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


#: Deux chemins fantômes au lieu d'un : strictement pire que BAD_FRONT, sur
#: la même échelle et sans rien changer d'autre.
PIRE_FRONT = ("<!doctype html><html><body><script>"
              "fetch('/fantome/1'); fetch('/autre-fantome');"
              "</script></body></html>")


def test_une_correction_qui_degrade_ne_remplace_pas_la_tentative_precedente(project):
    """monl gardait la DERNIÈRE tentative ; il garde la MEILLEURE.

    Mesuré sur une construction réelle payante : à qui on demandait de
    réparer deux lignes, le modèle a réécrit le site entier et perdu
    quatorze routes sur quinze — deux parcours utilisateur complets avec.
    La première tentative, elle, était presque bonne. L'utilisateur payait
    deux passes et repartait avec la pire des deux.
    """
    rendus = [BAD_FRONT, PIRE_FRONT]
    dits = []

    def provider(_prompt):
        return json.dumps({"files": {"index.html": rendus.pop(0)}})

    ok, errors = generate_and_verify(str(project), provider, say=dits.append)

    assert not ok, "les deux tentatives échouent : le verdict reste un échec"
    conserve = (project / "frontend" / "index.html").read_text(encoding="utf-8")
    assert conserve == BAD_FRONT, (
        "la tentative dégradée a été conservée alors qu'elle est pire")
    assert any("Tentative 1 restaurée" in ligne for ligne in dits), dits
    # Les erreurs RAPPORTÉES doivent décrire les fichiers conservés : rendre
    # celles de la tentative écartée décrirait un frontend absent du disque.
    assert not any("/autre-fantome" in e for e in errors), errors
    assert any("/fantome/1" in e for e in errors), errors


def test_une_correction_qui_ameliore_est_bien_conservee(project):
    """Contre-épreuve indispensable : un garde-fou qui figerait toujours la
    première tentative annulerait la correction automatique entière, et
    passerait pour bon."""
    rendus = [PIRE_FRONT, BAD_FRONT]
    dits = []

    def provider(_prompt):
        return json.dumps({"files": {"index.html": rendus.pop(0)}})

    ok, errors = generate_and_verify(str(project), provider, say=dits.append)

    assert not ok
    conserve = (project / "frontend" / "index.html").read_text(encoding="utf-8")
    assert conserve == BAD_FRONT, "la meilleure des deux est la seconde ici"
    assert not any("restaurée" in ligne for ligne in dits), dits


def test_la_restauration_ne_laisse_aucun_fichier_de_la_tentative_ecartee(project):
    """Un mélange des deux tentatives serait pire que l'une ou l'autre : le
    fichier restauré appellerait un script que sa version n'a pas écrit."""
    rendus = [
        {"index.html": BAD_FRONT},
        {"index.html": PIRE_FRONT, "extra.js": "console.log('tentative 2');"},
    ]
    dits = []

    def provider(_prompt):
        return json.dumps({"files": rendus.pop(0)})

    generate_and_verify(str(project), provider, say=dits.append)

    assert (project / "frontend" / "index.html").read_text(
        encoding="utf-8") == BAD_FRONT
    assert not (project / "frontend" / "extra.js").exists(), (
        "un fichier de la tentative écartée survit dans le frontend conservé")


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


def test_yandex_emploie_son_authentification_et_mesure_les_jetons(monkeypatch):
    """Yandex parle Chat Completions, mais exige Api-Key et le dossier Cloud."""
    monkeypatch.setenv("YANDEX_API_KEY", "cle-yandex")
    monkeypatch.setenv("YANDEX_FOLDER_ID", "dossier-yandex")
    monkeypatch.delenv("MONL_AI_CHUNK_MAX_TOKENS", raising=False)
    vu = {}

    class Reponse:
        status_code = 200
        text = ""

        def json(self):
            return {
                "choices": [{"message": {"content": "{\"files\": {}}"}}],
                "usage": {"prompt_tokens": 101, "completion_tokens": 23,
                          "total_tokens": 124},
            }

    def faux_post(url, headers=None, json=None, timeout=None):
        vu.update(url=url, headers=headers, body=json)
        return Reponse()

    import requests
    monkeypatch.setattr(requests, "post", faux_post)
    model = "gpt://dossier-yandex/yandexgpt/latest"
    call = PROVIDERS["yandex"](model=model)

    assert call("brief") == '{"files": {}}'
    assert vu["url"] == "https://ai.api.cloud.yandex.net/v1/chat/completions"
    assert vu["headers"]["Authorization"] == "Api-Key cle-yandex"
    assert vu["headers"]["OpenAI-Project"] == "dossier-yandex"
    assert vu["body"]["model"] == model
    assert vu["body"]["temperature"] == 0.3
    assert vu["body"]["max_tokens"] == 8000
    # RENVERSEMENT, mesuré contre le vrai service : Yandex REFUSE
    # reasoning_effort='none' en HTTP 400 (« Input should be 'low', 'medium'
    # or 'high' »), donc cette assertion décrivait un corps de requête que le
    # service n'a jamais accepté — toute construction --provider yandex
    # mourait au premier appel. Omettre le champ est ce que le commentaire du
    # préréglage voulait dire, et ce que le service accepte.
    assert "reasoning_effort" not in vu["body"]
    assert vu["body"]["response_format"]["type"] == "json_schema"
    assert vu["body"]["response_format"]["json_schema"]["strict"] is True
    assert call.last_usage["input_tokens"] == 101
    assert call.last_usage["output_tokens"] == 23
    assert call.last_usage["total_tokens"] == 124


def test_yandex_frontend_est_genere_fichier_par_fichier(project, monkeypatch):
    """Le préréglage séquentiel conserve le contrat et vérifie les trois
    fichiers ensemble après leur assemblage."""
    calls = []

    class Fournisseur:
        provider_name = "yandex"
        model = "deepseek-v4-flash/latest"
        chunked_generation = True
        last_usage = None

        def __call__(self, prompt):
            calls.append(prompt)
            ligne = next(texte for texte in prompt.splitlines()
                         if texte.startswith("Le fichier cible est exactement : "))
            cible = ligne.rsplit(": ", 1)[1]
            contenus = {
                "index.html": GOOD_SPLIT_HTML,
                "styles.css": "body { color: #111; }",
                "app.js": GOOD_SPLIT_JS,
            }
            self.last_usage = {"duration_seconds": 0.1,
                               "input_tokens": 100, "output_tokens": 200,
                               "total_tokens": 300}
            return json.dumps({"files": {cible: contenus[cible]}})

    provider = Fournisseur()
    ok, errors = generate_and_verify(str(project), provider, say=_quiet)
    assert ok, errors
    assert len(calls) == 3
    assert all("une seule pièce" in prompt for prompt in calls)
    assert (project / "frontend" / "index.html").exists()
    assert (project / "frontend" / "styles.css").exists()
    assert (project / "frontend" / "app.js").exists()


def test_yandex_nomme_le_dossier_manquant(monkeypatch):
    monkeypatch.setenv("YANDEX_API_KEY", "cle-yandex")
    monkeypatch.delenv("YANDEX_FOLDER_ID", raising=False)
    with pytest.raises(FrontendAIError) as erreur:
        PROVIDERS["yandex"](model="gpt://dossier/yandexgpt/latest")
    assert "YANDEX_FOLDER_ID" in str(erreur.value)


def test_le_plafond_api_est_reglable_par_lenvironnement(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "cle-de-test")
    monkeypatch.setenv("MONL_AI_MAX_TOKENS", "8000")
    vu = {}

    class Reponse:
        status_code = 200
        text = ""

        def json(self):
            return {"choices": [{"message": {"content": "ok"}}]}

    import requests
    monkeypatch.setattr(requests, "post",
                        lambda _url, **kw: (vu.update(kw), Reponse())[1])
    assert PROVIDERS["groq"](model="un-modele")("brief") == "ok"
    assert vu["json"]["max_tokens"] == 8000


def test_la_telemetrie_ne_conserve_ni_prompt_ni_reponse(project, monkeypatch):
    """Le journal sert au prix produit, pas à recopier le contenu du client."""
    from monl.frontend_ai import USAGE_FILENAME

    class Fournisseur:
        provider_name = "yandex"
        model = "modele-test"
        last_usage = None

        def __call__(self, prompt):
            assert "SmokeApp" in prompt
            self.last_usage = {"duration_seconds": 0.25, "input_tokens": 100,
                               "output_tokens": 20, "total_tokens": 120}
            return json.dumps({"files": {"index.html": GOOD_FRONT}})

    ok, errors = generate_and_verify(str(project), Fournisseur(), say=_quiet)
    assert ok, errors
    contenu = (project / USAGE_FILENAME).read_text(encoding="utf-8")
    evenement = json.loads(contenu)
    assert evenement["provider"] == "yandex"
    assert evenement["operation"] == "construction"
    assert evenement["total_tokens"] == 120
    assert "SmokeApp" not in contenu
    assert GOOD_FRONT not in contenu


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
