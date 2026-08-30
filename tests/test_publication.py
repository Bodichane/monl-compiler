"""Le guide de publication reste aligné sur les métadonnées et les commandes."""

import os


def _racine():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _project():
    try:
        import tomllib
    except ModuleNotFoundError:  # Python 3.10
        import tomli as tomllib

    with open(os.path.join(_racine(), "pyproject.toml"), "rb") as fichier:
        return tomllib.load(fichier)["project"]


def test_le_guide_publie_la_meme_version_dans_le_bon_ordre():
    with open(os.path.join(_racine(), "docs", "PUBLICATION.md"), encoding="utf-8") as fichier:
        guide = fichier.read()
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
    with open(os.path.join(_racine(), "docs", "PUBLICATION.md"), encoding="utf-8") as fichier:
        guide = fichier.read()

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
    with open(os.path.join(_racine(), "docs", "PUBLICATION.md"),
              encoding="utf-8") as fichier:
        guide = fichier.read()

    assert "rm -rf dist/" in guide, (
        "le guide construit sans vider dist/ : une version périmée déjà "
        "présente serait publiée avec la nouvelle")
    assert guide.index("rm -rf dist/") < guide.index("python -m build"), (
        "le nettoyage est écrit APRÈS la construction : il ne protège de rien")
    # La conséquence doit être écrite, sinon la commande passe pour une
    # coquetterie et le premier qui publie sous pression la saute.
    assert "ne peut plus" in guide or "ne permet pas de republier" in guide, (
        "le guide ne dit pas qu'un numéro de version envoyé est définitif")
