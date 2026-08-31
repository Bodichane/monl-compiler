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


def _versions_du_workflow(nom):
    """Rend les versions de Python qu'un workflow éprouve réellement.

    Lue sur le fichier plutôt que recopiée : deux listes de versions tenues
    séparément finissent toujours par diverger. Un seul lecteur pour les deux
    workflows, pour la même raison — en écrire un second reproduirait, au
    niveau de la mesure, le défaut que la mesure cherche à interdire.
    """
    import re

    racine = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    chemin = os.path.join(racine, ".github", "workflows", nom)
    with open(chemin, encoding="utf-8") as fichier:
        contenu = fichier.read()
    ligne = re.search(r"python-version:\s*\[([^\]]*)\]", contenu)
    return re.findall(r"\d+\.\d+", ligne.group(1)) if ligne else []


def _versions_de_la_ci():
    return _versions_du_workflow("ci.yml")


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


def test_la_publication_eprouve_le_tag_sur_les_memes_versions_que_la_ci():
    """Publier sur moins de versions que la CI rendrait sa propre phrase fausse.

    `publication.yml` justifie en commentaire qu'il rejoue tests et lint parce
    que « la CI de main ne suffit pas : elle a tourné sur un commit, pas
    forcément sur celui que le tag désigne ». Cette raison ne vaut que si le
    tag est éprouvé sur les MÊMES versions : n'en rejouer qu'une laisserait
    partir, définitivement, une version dont deux tiers du support annoncé
    n'ont jamais été vérifiés sur ce commit-là.

    Le sens du contrôle est l'égalité, pas l'inclusion. Une version publiée
    sans être annoncée n'aurait pas de classifieur (le témoin ci-dessus le
    refuse déjà) ; une version annoncée que la publication n'éprouve pas est
    exactement le trou que ce témoin ferme.
    """
    ci = _versions_du_workflow("ci.yml")
    publication = _versions_du_workflow("publication.yml")

    assert ci, "matrice de ci.yml illisible : ce témoin ne garde plus rien"
    assert publication, (
        "matrice de publication.yml illisible : ce témoin ne garde plus rien")
    assert publication == ci, (
        f"la publication éprouve {publication} quand la CI éprouve {ci} : "
        f"le tag partirait sans avoir été rejoué sur toutes les versions "
        f"annoncées sur l'index")
