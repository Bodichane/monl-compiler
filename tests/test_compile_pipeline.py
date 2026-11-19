"""Non-regressions of the compilation pipeline's orchestration."""

import monl.main as compiler_main
from monl.cli import compile_project

SPEC = """app PipelineUnique

entity Note
    titre: String

actor Auteur selfRegister

relation Auteur hasMany Note

rule Note.Read public

workflow Ecrire for Auteur
    Create Note
    Read Note
"""


def test_compile_project_parses_and_validates_only_once(tmp_path, monkeypatch):
    """Backend and contract must share a single validated compilation.

    The counter sits at the parser boundary called by ``compile_monl``. Before
    the unification, ``compile_project`` called that boundary once through
    ``compile_monl``, then a second time directly.
    """
    spec = tmp_path / "spec.ml"
    spec.write_text(SPEC, encoding="utf-8")
    appels = 0
    vrai_parse = compiler_main.parse_monl_file

    def compter_parse(chemin):
        nonlocal appels
        appels += 1
        return vrai_parse(chemin)

    monkeypatch.setattr(compiler_main, "parse_monl_file", compter_parse)

    contrat = compile_project(str(spec), str(tmp_path))

    assert appels == 1
    assert contrat["app"] == "PipelineUnique"
    for artefact in (
        "app.py",
        "schema.sql",
        "manage.py",
        "frontend_contract.json",
        "docs/FRONTEND_PROMPT.md",
        "monl.json",
    ):
        assert (tmp_path / artefact).is_file()
    # `sandbox_ai.py` left this list: SPEC has no `custom` block, so the module
    # is no longer emitted (see tests/test_bloc_custom_absent.py). We assert
    # its ABSENCE rather than stop looking at it — a list from which a name is
    # removed no longer says anything about that name.
    assert not (tmp_path / "sandbox_ai.py").exists()


def test_compile_monl_returns_the_model_used_to_generate(tmp_path):
    spec = tmp_path / "spec.ml"
    spec.write_text(SPEC, encoding="utf-8")

    compilation = compiler_main.compile_monl(
        str(spec), output_dir=str(tmp_path))

    assert compilation.ir["meta"]["appName"] == "PipelineUnique"
    assert compilation.generator.ast is compilation.ir
    assert compilation.generator.app_name == "PipelineUnique"
    assert compilation.plans.route_map is compilation.generator.route_plans
    assert compilation.plans is compilation.generator.compilation_plans
    assert compilation.generator.build_compilation_plans() is compilation.plans
    assert compilation.generator.emitters.generator is compilation.generator
