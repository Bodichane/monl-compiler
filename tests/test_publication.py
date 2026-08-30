"""La publication est sans secret et ses témoins mordent vraiment."""

import os
import re
from pathlib import Path

import pytest
import yaml

from scripts.check_publication_version import PublicationVersionError, validate_tag_version


def _racine():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _guide():
    with open(os.path.join(_racine(), "docs", "PUBLICATION.md"), encoding="utf-8") as fichier:
        return fichier.read()


def _workflow():
    chemin = Path(_racine()) / ".github" / "workflows" / "publication.yml"
    with chemin.open(encoding="utf-8") as fichier:
        return yaml.safe_load(fichier)


def _project():
    try:
        import tomllib
    except ModuleNotFoundError:  # Python 3.10
        import tomli as tomllib

    with open(os.path.join(_racine(), "pyproject.toml"), "rb") as fichier:
        return tomllib.load(fichier)["project"]


def test_le_guide_publie_la_meme_version_dans_le_bon_ordre():
    guide = _guide()
    project = _project()

    assert project["name"] in guide
    assert project["version"] in guide
    commandes = (
        "python -m build",
        "python -m twine check dist/*",
        "python -m twine upload --repository testpypi dist/*",
        "python -m twine upload dist/*",
    )
    positions = [guide.index(commande) for commande in commandes]
    assert positions == sorted(positions)
    assert "https://test.pypi.org/simple/" in guide
    assert "https://pypi.org/simple/" in guide
    assert "https://test.pypi.org/legacy/" in guide
    assert "https://upload.pypi.org/legacy/" in guide


def test_le_guide_isole_les_identifiants_du_depot_et_des_commandes():
    guide = _guide()

    assert "~/.pypirc" in guide
    assert "TWINE_PASSWORD" in guide
    assert "--password" in guide
    assert "jamais dans ce dépôt" in guide
    assert "Ne pas reconstruire entre les deux envois" in guide


def test_le_guide_fait_vider_dist_avant_de_construire():
    """`dist/` survit d'une construction à l'autre, et `twine upload dist/*`
    envoie TOUT ce qu'il y trouve.

    Le dossier est ignoré par git, donc absent d'un dépôt fraîchement cloné —
    mais présent sur la machine qui publie, qui est précisément celle qui a
    déjà construit. Mesuré au moment d'écrire ce témoin : `dist/` portait
    `monl_compiler-0.9.0b7` alors que la version à publier était `0.9.0b8`.
    Sans nettoyage, les deux partent, et **un numéro de version envoyé à PyPI
    ne peut plus être réutilisé, même après suppression** : la faute est
    définitive.

    Le témoin exige le nettoyage AVANT `python -m build` — l'ordre EST la
    garantie, un `rm -rf dist/` écrit après ne protégerait de rien.
    """
    guide = _guide()

    assert "rm -rf dist/" in guide, (
        "le guide construit sans vider dist/ : une version périmée déjà "
        "présente serait publiée avec la nouvelle")
    assert guide.index("rm -rf dist/") < guide.index("python -m build"), (
        "le nettoyage est écrit APRÈS la construction : il ne protège de rien")
    # La conséquence doit être écrite, sinon la commande passe pour une
    # coquetterie et le premier qui publie sous pression la saute.
    assert "ne peut plus" in guide or "ne permet pas de republier" in guide, (
        "le guide ne dit pas qu'un numéro de version envoyé est définitif")


def test_le_tag_qui_correspond_est_accepte():
    validate_tag_version("v0.9.0-beta.8", "0.9.0-beta.8")


def test_le_tag_qui_diverge_est_refuse_et_nomme_les_deux_valeurs():
    with pytest.raises(PublicationVersionError, match=r"v0\.9\.0b9.*0\.9\.0-beta\.8"):
        validate_tag_version("v0.9.0b9", "0.9.0-beta.8")


@pytest.mark.parametrize(
    ("tag", "declared_version"),
    [
        ("v0.9.0b8", "0.9.0-beta.8"),
        ("v0.9.0-beta.8", "0.9.0b8"),
    ],
)
def test_les_deux_ecritures_d_une_meme_version_sont_acceptees(tag, declared_version):
    validate_tag_version(tag, declared_version)


def test_le_workflow_est_parse_et_porte_la_chaine_sans_secret():
    workflow = _workflow()
    jobs = workflow["jobs"]
    triggers = workflow.get("on", workflow.get(True))

    assert triggers == {"push": {"tags": ["v*"]}}
    assert set(jobs) == {
        "verify-tag",
        "tests",
        "build",
        "publish-testpypi",
        "publish-pypi",
    }
    assert jobs["build"]["needs"] == ["verify-tag", "tests"]
    assert jobs["publish-testpypi"]["needs"] == "build"
    assert jobs["publish-pypi"]["needs"] == "publish-testpypi"

    assert jobs["verify-tag"]["permissions"] == {"contents": "read"}
    assert jobs["tests"]["permissions"] == {"contents": "read"}
    assert jobs["build"]["permissions"] == {"contents": "read"}
    assert jobs["publish-testpypi"]["permissions"] == {"id-token": "write"}
    assert jobs["publish-pypi"]["permissions"] == {"id-token": "write"}
    assert jobs["publish-testpypi"]["environment"] == "testpypi"
    assert jobs["publish-pypi"]["environment"] == "pypi"

    contenu = (Path(_racine()) / ".github" / "workflows" / "publication.yml").read_text(
        encoding="utf-8"
    )
    assert "secrets." not in contenu
    assert contenu.count("python -m build") == 1
    assert "actions/upload-artifact@v4.6.2" in contenu
    assert contenu.count("actions/download-artifact@v4.3.0") == 2
    assert "pypa/gh-action-pypi-publish@v1.14.2" in contenu
    actions = re.findall(r"uses:\s+([^\s]+)", contenu)
    assert actions and all(re.search(r"@v\d+\.\d+\.\d+$", action) for action in actions)


def test_le_lint_et_les_tests_sont_des_dependances_de_la_construction():
    workflow = _workflow()
    build = workflow["jobs"]["build"]
    tests_steps = workflow["jobs"]["tests"]["steps"]
    commandes = [etape.get("run", "") for etape in tests_steps]

    assert "ruff check src tests" in commandes
    assert any("pytest tests/" in commande for commande in commandes)
    assert set(build["needs"]) >= {"tests", "verify-tag"}


def test_le_guide_nomme_le_workflow_et_les_environnements_reels():
    guide = _guide()
    workflow = _workflow()
    environnements = {
        job["environment"]
        for job in workflow["jobs"].values()
        if "environment" in job
    }

    assert ".github/workflows/publication.yml" in guide
    assert "publication.yml" in guide
    assert "| Workflow | `publication.yml` |" in guide
    assert "| Environnement | `pypi` |" in guide
    assert "| Environnement | `testpypi` |" in guide
    assert {"testpypi", "pypi"} <= environnements
    for environnement in environnements:
        assert f"`{environnement}`" in guide


def test_le_tableau_de_l_editeur_de_confiance_dit_le_vrai_depot():
    """Un champ faux dans ce tableau produit `invalid-publisher`, sans plus.

    PyPI ne vérifie pas l'éditeur de confiance au moment où on le déclare : il
    le confronte au jeton OIDC lors de l'envoi. Une faute sur le propriétaire,
    le dépôt ou le nom du projet ne se voit donc qu'à la publication, sous la
    forme d'un refus qui ne dit pas LEQUEL des champs est faux — et le
    mainteneur n'a aucun moyen de le deviner depuis GitHub.

    Le tableau est donc confronté à `[project.urls].Repository`, qui est déjà
    figé par `tests/test_package_metadata.py`. Deux vérités tenues séparément
    finissent toujours par se contredire : ici l'une est une métadonnée
    publiée, l'autre une consigne à recopier à la main dans un formulaire.
    """
    import re

    project = _project()
    depot = project["urls"]["Repository"]
    correspondance = re.fullmatch(
        r"https://github\.com/([^/]+)/([^/]+?)(?:\.git)?/?", depot)
    assert correspondance, f"URL de dépôt illisible : {depot!r}"
    proprietaire, nom_du_depot = correspondance.groups()

    guide = _guide()
    # Deux tableaux : PyPI et TestPyPI. Les DEUX doivent porter la valeur —
    # n'en vérifier qu'un laisserait l'instance d'essai diverger, et c'est
    # justement celle qu'on remplit en premier.
    for etiquette, valeur in (
        ("Projet", project["name"]),
        ("Propriétaire du dépôt", proprietaire),
        ("Dépôt", nom_du_depot),
    ):
        ligne = f"| {etiquette} | `{valeur}` |"
        assert guide.count(ligne) == 2, (
            f"le guide devrait porter deux fois {ligne!r} (PyPI et TestPyPI), "
            f"il le porte {guide.count(ligne)} fois — l'éditeur de confiance "
            f"refuserait l'envoi sans dire quel champ est faux")
