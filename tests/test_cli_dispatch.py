"""Le câblage de `monl <sous-commande>` — la fonction main() de cli.py.

`tests/test_cli_commandes.py` (point 64) éprouve ce que FONT `compile_project`,
`check_coherence`, `cmd_run` et `cmd_update`. Personne n'éprouvait ce qui les
APPELLE : les cent lignes d'argparse et de dispatch de `main()` n'étaient
traversées par aucun test, alors que c'est le seul chemin qu'un utilisateur
emprunte réellement.

Une erreur de câblage y est silencieuse par nature. Un `--skip-smoke` non
transmis lance le smoke test quand même ; un `--port` perdu en route ramène
tout le monde sur 8000 — et le point 51 a fait tout un travail pour que le port
ne soit justement pas figé ; un code de sortie 0 sur échec fait passer au vert
n'importe quelle CI qui appelle `monl run --check`. Rien de tout cela ne casse
un test existant, et rien ne le montre à la lecture.

Les commandes qui démarrent un serveur ou appellent une IA sont interceptées :
ce fichier vérifie l'aiguillage et les arguments transmis, pas le travail au
bout — celui-ci a déjà ses propres tests.
"""
import os

import pytest

from monl import __version__, cli

SPEC = """app Carnet

entity Note
    title: String

actor Admin selfRegister

rule Note.Read public

workflow GererNote for Admin
    Create Note
    Read Note
"""


@pytest.fixture
def spec(tmp_path):
    chemin = tmp_path / "spec.ml"
    chemin.write_text(SPEC, encoding="utf-8")
    return chemin


# ------------------------------------------------------ compile : où écrit-il --
def test_compile_sans_output_ecrit_a_cote_de_la_spec(spec, tmp_path, capsys):
    """Le défaut du point 65 : le générateur déduisait sa racine de
    l'emplacement de son propre fichier, ce qui aurait écrit l'application au
    milieu de site-packages une fois monl installé. Le repère est le dossier de
    la spec — l'assertion est ici, pas dans le calcul."""
    cli.main(["compile", str(spec)])
    capsys.readouterr()
    assert (tmp_path / "app.py").exists()
    assert (tmp_path / cli.STATE_FILENAME).exists()


def test_compile_avec_output_ecrit_dans_le_dossier_demande(spec, tmp_path, capsys):
    ailleurs = tmp_path / "build" / "carnet"
    cli.main(["compile", str(spec), "--output", str(ailleurs)])
    capsys.readouterr()
    assert (ailleurs / "app.py").exists()
    assert not (tmp_path / "app.py").exists(), (
        "--output ignoré : le projet a été écrit à côté de la spec")


# -------------------------------------------------- run : options transmises --
def test_run_transmet_ses_options_telles_quelles(monkeypatch):
    recu = {}
    monkeypatch.setattr(cli.lancement, "cmd_run", lambda d, **kw: recu.update(dir=d, **kw))

    cli.main(["run", "/quelque/part", "--check", "--skip-smoke", "--port", "9143"])

    assert recu == {"dir": "/quelque/part", "check_only": True,
                    "skip_smoke": True, "port": 9143}


def test_run_sans_option_vise_le_dossier_courant_sur_le_port_8000(monkeypatch):
    """Les défauts font partie du contrat : `monl run` tout court doit rester
    la commande du QUICKSTART."""
    recu = {}
    monkeypatch.setattr(cli.lancement, "cmd_run", lambda d, **kw: recu.update(dir=d, **kw))

    cli.main(["run"])

    assert recu == {"dir": ".", "check_only": False,
                    "skip_smoke": False, "port": 8000}


def test_update_recoit_le_dossier_demande(monkeypatch):
    recu = []
    monkeypatch.setattr(cli.delta, "cmd_update", recu.append)
    cli.main(["update", "/un/projet"])
    assert recu == ["/un/projet"]


def test_sans_sous_commande_le_dialogue_guide_s_ouvre(monkeypatch):
    """`monl` seul est l'entrée annoncée par le README : aucune sous-commande
    ne doit s'interposer, et `monl init` doit mener au même endroit."""
    recu = []
    monkeypatch.setattr(cli.construction, "cmd_init", recu.append)

    cli.main([])
    cli.main(["init", "--dir", "/ici"])

    assert recu == [None, "/ici"]


def test_la_version_est_disponible_sans_sous_commande(capsys):
    with pytest.raises(SystemExit) as sortie:
        cli.main(["--version"])

    assert sortie.value.code == 0
    assert f"monl {__version__}" in capsys.readouterr().out


# ------------------------------------------- frontend : quelle voie est prise --
@pytest.fixture
def voies(monkeypatch):
    """Intercepte les deux voies de `monl frontend` et note laquelle a servi."""
    from monl import frontend_ai
    trace = {}

    def _agent(project_dir, **kw):
        trace["voie"] = "agent"
        trace.update(kw, dir=project_dir)
        return True, []

    def _api(project_dir, provider, **kw):
        trace["voie"] = "api"
        trace.update(kw, dir=project_dir, provider=provider)
        return True, []

    monkeypatch.setattr(frontend_ai, "generate_with_cli_agent", _agent)
    monkeypatch.setattr(frontend_ai, "generate_and_verify", _api)
    # Les vrais fournisseurs exigent leur clé dès leur construction (voie
    # Anthropic comprise) : sans ce stub, le dispatch échouerait avant même
    # d'avoir choisi sa voie, et le test mesurerait l'absence de clé.
    monkeypatch.setattr(frontend_ai, "PROVIDERS",
                        {nom: (lambda model=None, _n=nom: f"fournisseur:{_n}")
                         for nom in frontend_ai.PROVIDERS})
    return trace


def test_frontend_prend_la_voie_agent_pour_un_agent_connu(voies):
    cli.main(["frontend", "/projet", "--provider", "codex"])
    assert voies["voie"] == "agent"
    assert voies["agent"] == "codex"
    assert voies["dir"] == "/projet"


def test_agent_command_l_emporte_sur_provider(voies):
    """Point 69 : le gabarit libre existe aussi pour corriger un préréglage
    devenu faux sans attendre une version de monl. S'il ne l'emportait pas sur
    `--provider`, il ne pourrait rien corriger."""
    cli.main(["frontend", "/projet", "--agent-command", "mon-agent {instruction}"])
    assert voies["voie"] == "agent"
    assert voies["agent_command"] == "mon-agent {instruction}"


def test_frontend_prend_la_voie_api_par_defaut(voies):
    cli.main(["frontend", "/projet"])
    assert voies["voie"] == "api"


def test_la_voie_anthropic_a_un_modele_par_defaut_les_autres_non(monkeypatch, voies):
    """Point 69 : aucun modèle par défaut hors voie Anthropic, à dessein — un
    identifiant périmé en dur transforme une erreur claire en 404 obscur six
    mois plus tard."""
    from monl import frontend_ai
    demandes = []
    monkeypatch.setattr(frontend_ai, "PROVIDERS", {
        nom: (lambda model=None, _n=nom: demandes.append((_n, model)))
        for nom in ("claude", "groq")})

    cli.main(["frontend", "/projet"])
    cli.main(["frontend", "/projet", "--provider", "groq"])

    assert demandes == [("claude", frontend_ai.DEFAULT_MODEL), ("groq", None)]


def test_une_erreur_de_fournisseur_sort_en_code_1(monkeypatch, capsys):
    """Le message d'erreur du point 69 (« préciser --model ») n'a de valeur que
    s'il s'accompagne d'un code de sortie non nul : sinon un script qui
    enchaîne les commandes continue comme si le frontend existait."""
    from monl import frontend_ai

    def _explose(model=None):
        raise frontend_ai.FrontendAIError("préciser --model")

    monkeypatch.setattr(frontend_ai, "PROVIDERS", {"claude": _explose})

    with pytest.raises(SystemExit) as sortie:
        cli.main(["frontend", "/projet"])
    assert sortie.value.code == 1
    assert "préciser --model" in capsys.readouterr().out


def test_une_verification_en_echec_sort_en_code_1(monkeypatch):
    """La re-vérification (cohérence + smoke test) est le garde-fou de la voie
    IA. Un frontend refusé qui rend 0 annule tout l'intérêt du garde-fou."""
    from monl import frontend_ai
    monkeypatch.setattr(frontend_ai, "PROVIDERS", {"claude": lambda model=None: None})
    monkeypatch.setattr(frontend_ai, "generate_and_verify",
                        lambda *a, **kw: (False, ["smoke test échoué"]))

    with pytest.raises(SystemExit) as sortie:
        cli.main(["frontend", "/projet"])
    assert sortie.value.code == 1


# ------------------------------------------------------------------ import --
def test_import_transmet_la_source_et_le_dossier(monkeypatch):
    from monl import frontend_ai
    recu = {}

    def _import(project_dir, source):
        recu.update(dir=project_dir, source=source)
        return True, []

    monkeypatch.setattr(frontend_ai, "import_and_verify", _import)
    cli.main(["import", "/tel/chargement.zip", "/projet"])
    assert recu == {"dir": "/projet", "source": "/tel/chargement.zip"}


def test_un_import_refuse_sort_en_code_1(monkeypatch):
    from monl import frontend_ai
    monkeypatch.setattr(frontend_ai, "import_and_verify",
                        lambda *a, **kw: (False, ["frontend incohérent"]))
    with pytest.raises(SystemExit) as sortie:
        cli.main(["import", "/tel/chargement.zip", "/projet"])
    assert sortie.value.code == 1


def test_un_agent_sans_gabarit_valide_est_refuse_avant_tout_lancement(monkeypatch, capsys):
    """Point 69 : un gabarit dépourvu de {instruction} est refusé plutôt que
    lancé muet. Le refus vient de frontend_ai ; ce qui se vérifie ici est que
    main() le laisse remonter en code 1 au lieu de l'avaler."""
    from monl import frontend_ai

    def _agent(*a, **kw):
        raise frontend_ai.FrontendAIError("gabarit sans {instruction}")

    monkeypatch.setattr(frontend_ai, "generate_with_cli_agent", _agent)
    with pytest.raises(SystemExit) as sortie:
        cli.main(["frontend", "/projet", "--agent-command", "mon-agent --auto"])
    assert sortie.value.code == 1
    assert "gabarit" in capsys.readouterr().out


def test_le_dossier_courant_est_le_defaut_des_commandes_de_projet(monkeypatch):
    """`monl update` et `monl frontend` sans argument doivent viser le dossier
    courant, comme n'importe quel outil en ligne de commande — c'est la
    convention que le point 65 a rétablie pour la sortie du compilateur."""
    from monl import frontend_ai
    vus = {}
    monkeypatch.setattr(cli.delta, "cmd_update", lambda d: vus.update(update=d))
    monkeypatch.setattr(frontend_ai, "PROVIDERS", {"claude": lambda model=None: None})
    monkeypatch.setattr(frontend_ai, "generate_and_verify",
                        lambda d, *a, **kw: (vus.update(frontend=d), (True, []))[1])

    cli.main(["update"])
    cli.main(["frontend"])

    assert vus == {"update": ".", "frontend": "."}
    assert os.path.isdir(".")
