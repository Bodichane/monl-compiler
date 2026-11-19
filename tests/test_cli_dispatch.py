"""The wiring of `monl <subcommand>` — cli.py's main() function.

`tests/test_cli_commandes.py` (point 64) tests what `compile_project`,
`check_coherence`, `cmd_run` and `cmd_update` DO. Nobody tested what CALLS
them: the hundred lines of argparse and dispatch in `main()` were crossed by
no test, while it is the only path a user really takes.

A wiring error there is silent by nature. A `--skip-smoke` not passed on runs
the smoke test anyway; a `--port` lost on the way brings everyone back to
8000 — and point 51 did a whole job precisely so the port would not be
fixed; an exit code 0 on failure turns green any CI calling
`monl run --check`. None of this breaks an existing test, and nothing shows
it on reading.

Commands that start a server or call an AI are intercepted: this file checks
the routing and the arguments passed, not the work at the end — that already
has its own tests.
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


# --------------------------------------------- compile: where does it write --
def test_compile_without_output_writes_next_to_the_spec(spec, tmp_path, capsys):
    """Point 65's defect: the generator deduced its root from the location of its
    own file, which would have written the application into the middle of
    site-packages once monl was installed. The reference is the spec's folder —
    the assertion is here, not in the calculation."""
    cli.main(["compile", str(spec)])
    capsys.readouterr()
    assert (tmp_path / "app.py").exists()
    assert (tmp_path / cli.STATE_FILENAME).exists()


def test_compile_with_output_writes_to_the_requested_folder(spec, tmp_path, capsys):
    ailleurs = tmp_path / "build" / "carnet"
    cli.main(["compile", str(spec), "--output", str(ailleurs)])
    capsys.readouterr()
    assert (ailleurs / "app.py").exists()
    assert not (tmp_path / "app.py").exists(), (
        "--output ignoré : le projet a été écrit à côté de la spec")


# -------------------------------------------------- run : options transmises --
def test_run_passes_its_options_as_is(monkeypatch):
    recu = {}
    monkeypatch.setattr(cli.lancement, "cmd_run", lambda d, **kw: recu.update(dir=d, **kw))

    cli.main(["run", "/quelque/part", "--check", "--skip-smoke", "--port", "9143"])

    assert recu == {"dir": "/quelque/part", "check_only": True,
                    "skip_smoke": True, "port": 9143}


def test_run_without_option_targets_the_current_folder_on_port_8000(monkeypatch):
    """The defaults are part of the contract: plain `monl run` must stay the
    QUICKSTART command."""
    recu = {}
    monkeypatch.setattr(cli.lancement, "cmd_run", lambda d, **kw: recu.update(dir=d, **kw))

    cli.main(["run"])

    assert recu == {"dir": ".", "check_only": False,
                    "skip_smoke": False, "port": 8000}


def test_update_receives_the_requested_folder(monkeypatch):
    recu = []
    monkeypatch.setattr(cli.delta, "cmd_update", recu.append)
    cli.main(["update", "/un/projet"])
    assert recu == ["/un/projet"]


def test_without_subcommand_the_guided_dialogue_opens(monkeypatch):
    """Plain `monl` is the entry announced by the README: no subcommand must get
    in the way, and `monl init` must lead to the same place."""
    recu = []
    monkeypatch.setattr(cli.construction, "cmd_init", recu.append)

    cli.main([])
    cli.main(["init", "--dir", "/ici"])

    assert recu == [None, "/ici"]


def test_the_version_is_available_without_subcommand(capsys):
    with pytest.raises(SystemExit) as sortie:
        cli.main(["--version"])

    assert sortie.value.code == 0
    from monl.parser.version import LANGUAGE_VERSION
    assert f"monl {__version__} (language {LANGUAGE_VERSION})" in capsys.readouterr().out


# -------------------------------------------- frontend: which path is taken --
@pytest.fixture
def voies(monkeypatch):
    """Intercepts the two paths of `monl frontend` and notes which one served."""
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
    # The real providers require their key as soon as they are built (Anthropic
    # path included): without this stub, dispatch would fail before even
    # choosing its path, and the test would measure the missing key.
    monkeypatch.setattr(frontend_ai, "PROVIDERS",
                        {nom: (lambda model=None, _n=nom: f"fournisseur:{_n}")
                         for nom in frontend_ai.PROVIDERS})
    return trace


def test_frontend_takes_the_agent_path_for_a_known_agent(voies):
    cli.main(["frontend", "/projet", "--provider", "codex"])
    assert voies["voie"] == "agent"
    assert voies["agent"] == "codex"
    assert voies["dir"] == "/projet"


def test_agent_command_takes_precedence_over_provider(voies):
    """Point 69: the free template also exists to fix a preset that became wrong
    without waiting for a monl release. If it did not take precedence over
    `--provider`, it could fix nothing."""
    cli.main(["frontend", "/projet", "--agent-command", "mon-agent {instruction}"])
    assert voies["voie"] == "agent"
    assert voies["agent_command"] == "mon-agent {instruction}"


def test_frontend_takes_the_api_path_by_default(voies):
    cli.main(["frontend", "/projet"])
    assert voies["voie"] == "api"


def test_the_anthropic_path_has_a_default_model_the_others_do_not(monkeypatch, voies):
    """Point 69: no default model outside the Anthropic path, on purpose — a
    hard-coded stale identifier turns a clear error into an obscure 404 six
    months later."""
    from monl import frontend_ai
    demandes = []
    monkeypatch.setattr(frontend_ai, "PROVIDERS", {
        nom: (lambda model=None, _n=nom: demandes.append((_n, model)))
        for nom in ("claude", "groq")})

    cli.main(["frontend", "/projet"])
    cli.main(["frontend", "/projet", "--provider", "groq"])

    assert demandes == [("claude", frontend_ai.DEFAULT_MODEL), ("groq", None)]


def test_a_provider_error_exits_with_code_1(monkeypatch, capsys):
    """Point 69's error message ("specify --model") is only worth something if
    it comes with a non-zero exit code: otherwise a script chaining commands goes
    on as if the frontend existed."""
    from monl import frontend_ai

    def _explose(model=None):
        raise frontend_ai.FrontendAIError("préciser --model")

    monkeypatch.setattr(frontend_ai, "PROVIDERS", {"claude": _explose})

    with pytest.raises(SystemExit) as sortie:
        cli.main(["frontend", "/projet"])
    assert sortie.value.code == 1
    assert "préciser --model" in capsys.readouterr().out


def test_a_failed_verification_exits_with_code_1(monkeypatch):
    """The re-check (consistency + smoke test) is the AI path's safeguard. A
    refused frontend returning 0 cancels the whole point of the safeguard."""
    from monl import frontend_ai
    monkeypatch.setattr(frontend_ai, "PROVIDERS", {"claude": lambda model=None: None})
    monkeypatch.setattr(frontend_ai, "generate_and_verify",
                        lambda *a, **kw: (False, ["smoke test échoué"]))

    with pytest.raises(SystemExit) as sortie:
        cli.main(["frontend", "/projet"])
    assert sortie.value.code == 1


# ------------------------------------------------------------------ import --
def test_import_passes_the_source_and_folder(monkeypatch):
    from monl import frontend_ai
    recu = {}

    def _import(project_dir, source):
        recu.update(dir=project_dir, source=source)
        return True, []

    monkeypatch.setattr(frontend_ai, "import_and_verify", _import)
    cli.main(["import", "/tel/chargement.zip", "/projet"])
    assert recu == {"dir": "/projet", "source": "/tel/chargement.zip"}


def test_a_refused_import_exits_with_code_1(monkeypatch):
    from monl import frontend_ai
    monkeypatch.setattr(frontend_ai, "import_and_verify",
                        lambda *a, **kw: (False, ["frontend incohérent"]))
    with pytest.raises(SystemExit) as sortie:
        cli.main(["import", "/tel/chargement.zip", "/projet"])
    assert sortie.value.code == 1


def test_an_agent_without_valid_template_is_refused_before_starting(monkeypatch, capsys):
    """Point 69: a template without {instruction} is refused rather than started
    silent. The refusal comes from frontend_ai; what is checked here is that
    main() lets it come up as exit code 1 instead of swallowing it."""
    from monl import frontend_ai

    def _agent(*a, **kw):
        raise frontend_ai.FrontendAIError("gabarit sans {instruction}")

    monkeypatch.setattr(frontend_ai, "generate_with_cli_agent", _agent)
    with pytest.raises(SystemExit) as sortie:
        cli.main(["frontend", "/projet", "--agent-command", "mon-agent --auto"])
    assert sortie.value.code == 1
    assert "gabarit" in capsys.readouterr().out


def test_the_current_folder_is_the_project_commands_default(monkeypatch):
    """`monl update` and `monl frontend` without arguments must target the
    current folder, like any command-line tool — the convention point 65 restored
    for the compiler's output."""
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


def test_retouche_prompt_only_writes_the_instruction_without_calling_the_ai(monkeypatch):
    """`--prompt-only` (and its French alias `--consigne-seule`) writes the
    instruction and stops; without it, the AI path is taken. Nothing tested
    this option before: removing it would have left the suite green."""
    from monl.cli import retouche as module_retouche
    trace = []
    monkeypatch.setattr(module_retouche, "cmd_retouche",
                        lambda d, demande: trace.append(("consigne", d, demande)))
    monkeypatch.setattr(module_retouche, "_lancer_ia",
                        lambda args, **kw: trace.append(("ia", args.dir)))

    for option in ("--prompt-only", "--consigne-seule"):
        cli.main(["retouche", "le titre déborde", "/un/projet", option])
    assert trace == [("consigne", "/un/projet", "le titre déborde")] * 2
    cli.main(["retouche", "le titre déborde", "/un/projet"])
    assert trace[-1] == ("ia", "/un/projet")
