"""Le paquet publié décrit ce qu'il est, sans inventer son identité."""

import os

from monl_platform import legal


def _project():
    try:
        import tomllib
    except ModuleNotFoundError:  # Python 3.10
        import tomli as tomllib

    racine = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(racine, "pyproject.toml"), "rb") as fichier:
        return tomllib.load(fichier)["project"]


def _versions_de_la_ci():
    """Rend les versions de Python que la CI éprouve réellement.

    Lue sur `.github/workflows/ci.yml` plutôt que recopiée : deux listes de
    versions tenues séparément finissent toujours par diverger.
    """
    import re

    racine = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    chemin = os.path.join(racine, ".github", "workflows", "ci.yml")
    with open(chemin, encoding="utf-8") as fichier:
        contenu = fichier.read()
    ligne = re.search(r"python-version:\s*\[([^\]]*)\]", contenu)
    return re.findall(r"\d+\.\d+", ligne.group(1)) if ligne else []


def test_les_metadonnees_de_publication_decrivent_le_projet():
    project = _project()
    classifiers = set(project["classifiers"])

    assert {
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3 :: Only",
        "Topic :: Software Development :: Code Generators",
        "Topic :: Software Development :: Compilers",
    } <= classifiers
    # Les versions ne sont PAS écrites ici : elles sont lues sur la matrice de
    # la CI. Une liste tenue à la main dérive en silence le jour où la matrice
    # change — c'est le défaut que le point 164 a trouvé sur la page `/mcp`,
    # qui annonçait quatre outils inexistants parce que sa liste était écrite
    # à la main plutôt que confrontée à `TOOLS`.
    #
    # Le sens du contrôle compte : on exige que toute version ÉPROUVÉE soit
    # annoncée, jamais l'inverse. Annoncer 3.11 sans la tester serait une
    # promesse invérifiable ; la tester sans l'annoncer prive l'usager d'une
    # information vraie.
    testees = _versions_de_la_ci()
    assert testees, "matrice de la CI illisible : ce témoin ne garde plus rien"
    manquantes = [v for v in testees
                  if f"Programming Language :: Python :: {v}" not in classifiers]
    assert not manquantes, (
        f"versions éprouvées par la CI mais non annoncées sur l'index : "
        f"{manquantes}")
    assert project["urls"] == {
        "Repository": "https://github.com/Bodichane/monl-compiler",
        "Documentation": "https://github.com/Bodichane/monl-compiler/tree/main/docs",
        "Issues": "https://github.com/Bodichane/monl-compiler/issues",
    }


def test_la_licence_non_spdx_est_nomme_et_livree_sans_substitution():
    project = _project()

    # FSL-1.1-ALv2 n'est pas dans le catalogue SPDX : LicenseRef nomme
    # honnêtement cette licence personnalisée et le fichier reste sa source
    # de vérité dans chaque artefact.
    assert project["license"] == "LicenseRef-FSL-1.1-ALv2"
    assert project["license-files"] == ["LICENSE"]


def test_un_auteur_ne_peut_pas_etre_le_nom_du_paquet():
    project = _project()
    auteurs = project.get("authors", [])

    assert auteurs, "aucun auteur déclaré : ce témoin ne garderait plus rien"
    assert all(auteur["name"] != project["name"] for auteur in auteurs)


def test_l_auteur_de_la_distribution_est_l_editeur_legal():
    project = _project()

    assert project["authors"] == [{"name": legal.EDITEUR}], (
        "l'auteur de la distribution doit rester identique à legal.EDITEUR"
    )
