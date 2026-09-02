"""Non-régressions de l'orchestration du pipeline de compilation."""

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


def test_compile_project_ne_parse_et_ne_valide_quune_fois(tmp_path, monkeypatch):
    """Backend et contrat doivent partager une seule compilation validée.

    Le compteur est posé à la frontière du parseur appelée par ``compile_monl``.
    Avant l'unification, ``compile_project`` appelait cette frontière une fois
    via ``compile_monl``, puis une seconde fois directement.
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
    # `sandbox_ai.py` a quitté cette liste : SPEC n'a aucun bloc `custom`, donc
    # le module n'est plus émis (voir tests/test_bloc_custom_absent.py). On
    # affirme son ABSENCE plutôt que de cesser de le regarder — une liste dont
    # on retire un nom ne dit plus rien de ce nom.
    assert not (tmp_path / "sandbox_ai.py").exists()


def test_compile_monl_retourne_le_modele_utilise_pour_generer(tmp_path):
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
