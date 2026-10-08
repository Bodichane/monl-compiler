"""Point 208 : la plateforme compile des specs, jamais du Python utilisateur."""

import ast
from pathlib import Path

import pytest

from monl_platform.service import CompilationService

RACINE = Path(__file__).resolve().parents[1]


def test_description_custom_reste_exactement_une_coquille(tmp_path):
    descriptions = ["x'); import os #", r'avant \"\"\" après', '${name}']
    blocs = '\n'.join(
        f'custom Bloc{i}\n    description: "{description}"\n'
        '    input: titre: String\n    output: resultat: String\n'
        for i, description in enumerate(descriptions)
    )
    spec = 'app GardeCustom\n\nentity Note\n    titre: String\n\n' + blocs
    service = CompilationService(tmp_path)
    resultat = service.compile(spec)
    source = (tmp_path / resultat['id'] / 'sandbox_ai.py').read_text(encoding='utf-8')
    attendu = "# BLOCS 'custom' — logique métier à compléter à la main (déterministe)\n\n"
    for i, description in enumerate(descriptions):
        description = description.replace('\\', '\\\\')
        attendu += (
            f'def Bloc{i}(context: dict) -> dict:\n    """\n'
            f'    Objectif : {description}\n    """\n    # TODO:\n'
            f"    return {{'message': 'Coquille vide déterministe pour Bloc{i}'}}\n"
            + ('\n' if i < len(descriptions) - 1 else '')
        )
    assert source == attendu
    arbre = ast.parse(source)
    assert len(arbre.body) == len(descriptions)
    assert not any(isinstance(n, (ast.Import, ast.ImportFrom)) for n in ast.walk(arbre))
    for i, fonction in enumerate(arbre.body):
        assert isinstance(fonction, ast.FunctionDef)
        assert fonction.name == f'Bloc{i}'
        assert len(fonction.body) == 2
        assert isinstance(fonction.body[0], ast.Expr)
        assert isinstance(fonction.body[0].value, ast.Constant)
        assert isinstance(fonction.body[0].value.value, str)
        assert isinstance(fonction.body[1], ast.Return)
        assert ast.literal_eval(fonction.body[1].value) == {
            'message': f'Coquille vide déterministe pour Bloc{i}'
        }


def _assert_ecritures_sans_custom(fichiers):
    assert fichiers, 'aucun fichier de plateforme inspecté'
    for fichier in fichiers:
        arbre = ast.parse(fichier.read_text(encoding='utf-8'))
        # Résolution conservatrice des variables de chemins : toute affectation
        # est suivie, même dans une autre branche. Ce garde ne prouve pas une
        # analyse de flux générale ni les chemins construits dynamiquement.
        valeurs = {}
        for noeud in ast.walk(arbre):
            if isinstance(noeud, ast.Assign):
                for cible in noeud.targets:
                    if isinstance(cible, ast.Name):
                        valeurs.setdefault(cible.id, []).append(noeud.value)

        def vise_custom(noeud, vus=frozenset(), valeurs=valeurs):
            if isinstance(noeud, ast.Constant) and isinstance(noeud.value, str):
                return 'sandbox_ai' in noeud.value
            if isinstance(noeud, ast.Name) and noeud.id not in vus:
                return any(vise_custom(v, vus | {noeud.id})
                           for v in valeurs.get(noeud.id, []))
            return any(vise_custom(enfant, vus) for enfant in ast.iter_child_nodes(noeud))

        for appel in ast.walk(arbre):
            if not isinstance(appel, ast.Call):
                continue
            fonction = appel.func
            nom = fonction.attr if isinstance(fonction, ast.Attribute) else (
                fonction.id if isinstance(fonction, ast.Name) else '')
            if nom in {'write_text', 'write_bytes', 'write', 'writelines', 'open',
                       'copy', 'copyfile', 'copy2', 'copytree', 'move', 'rename', 'replace'}:
                cibles = list(appel.args) + [k.value for k in appel.keywords]
                if isinstance(fonction, ast.Attribute):
                    cibles.append(fonction.value)
                assert not any(vise_custom(c) for c in cibles), (
                    f'{fichier}:{appel.lineno} : écriture visant sandbox_ai interdite'
                )


def test_plateforme_necrit_pas_sandbox_ai():
    _assert_ecritures_sans_custom(sorted((RACINE / 'src/monl_platform').rglob('*.py')))


def test_garde_refuse_un_perimetre_vide():
    with pytest.raises(AssertionError, match='aucun fichier'):
        _assert_ecritures_sans_custom([])
