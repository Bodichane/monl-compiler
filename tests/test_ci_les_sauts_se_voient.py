"""La CI doit NOMMER ses tests sautés, pas les noyer dans un mur de points.

`pyproject.toml` pose déjà `-q` dans `addopts`. Chaque commande de
`.github/workflows/ci.yml` en posait un SECOND, et deux `-q` valent `-qq` :
pytest supprime alors la ligne de décompte ET la section de résumé. Un saut
ne se voyait plus que comme un `s` unique au milieu de mille points.

Ce n'est pas une hypothèse. Le test de réencodage JPEG a sauté dans cette CI
pendant toute la vie du dépôt — Pillow ne vivait que dans l'extra `ai`, que
la CI n'installe pas — et rien ne l'a jamais dit. Un saut ne dit pas « rien
à vérifier ici », il dit « je n'ai pas vérifié » (point 140).

Ce fichier garde donc DEUX propriétés, parce que l'une sans l'autre ne suffit
pas : aucune commande ne repose `-q` (sinon le résumé disparaît de nouveau),
et chacune porte `-rs` (sinon le résumé existe mais ne nomme personne).
"""

import re
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
CI = RACINE / ".github" / "workflows" / "ci.yml"
PYPROJECT = RACINE / "pyproject.toml"

# Un élément de liste YAML (« - name: ... ») ou une clé (« run: ... ») ferme
# la commande en cours. « --cov=... » commence aussi par un tiret : c'est le
# tiret SUIVI D'UNE ESPACE qui fait la liste, et la distinction n'est pas
# cosmétique — sans elle, une commande repliée serait coupée en son milieu.
NOUVEL_ELEMENT = re.compile(r"^\s*-\s")
NOUVELLE_CLE = re.compile(r"^\s*[A-Za-z_][\w -]*:(\s|$)")


def commandes_pytest(texte):
    """Les invocations pytest du workflow, chacune recollée sur une ligne.

    Le workflow emploie les deux formes : « run: python -m pytest ... » sur
    une ligne, et un scalaire replié « run: >- » dont la commande occupe
    plusieurs lignes de MÊME indentation.
    """
    commandes, courante = [], None
    for ligne in texte.splitlines():
        if not ligne.strip() or ligne.strip().startswith("#"):
            continue
        if courante is not None:
            if not NOUVEL_ELEMENT.match(ligne) and not NOUVELLE_CLE.match(ligne):
                courante += " " + ligne.strip()
                continue
            commandes.append(courante)
            courante = None
        if "python -m pytest" in ligne:
            courante = ligne.strip()
    if courante is not None:
        commandes.append(courante)
    return commandes


def addopts_du_projet():
    try:
        import tomllib
    except ModuleNotFoundError:      # 3.10 : `tomllib` n'arrive qu'en 3.11
        import tomli as tomllib      # noqa: I001  (déclaré dans l'extra `dev`)
    with PYPROJECT.open("rb") as fh:
        config = tomllib.load(fh)
    return config["tool"]["pytest"]["ini_options"]["addopts"].split()


def test_le_projet_pose_bien_un_q_dans_addopts():
    """Le témoin de la prémisse. Si `addopts` cessait de porter `-q`, le test
    ci-dessous garderait une règle devenue sans objet — il refuserait un `-q`
    qui, seul, serait légitime. Mieux vaut l'apprendre ici."""
    assert "-q" in addopts_du_projet(), (
        "addopts ne porte plus `-q` : relire la règle de ce fichier avant de "
        "continuer à interdire `-q` dans les commandes de la CI.")


def test_aucune_commande_de_ci_ne_repose_un_q():
    commandes = commandes_pytest(CI.read_text(encoding="utf-8"))
    assert commandes, "aucune invocation pytest trouvée dans ci.yml"
    fautives = [c for c in commandes if "-q" in c.split()]
    assert not fautives, (
        "`addopts` pose déjà `-q` : un second donne `-qq`, qui supprime la "
        f"ligne de décompte et la section de résumé. Commande(s) : {fautives}")


def test_chaque_commande_de_ci_nomme_les_tests_sautes():
    commandes = commandes_pytest(CI.read_text(encoding="utf-8"))
    assert commandes, "aucune invocation pytest trouvée dans ci.yml"
    muettes = [c for c in commandes
               if not any(o.startswith("-r") and "s" in o[2:] for o in c.split())]
    assert not muettes, (
        "sans `-rs`, un saut n'apparaît que comme un `s` au milieu des points "
        f"et personne ne le lit. Commande(s) : {muettes}")


# Les deux tests ci-dessus ne valent que ce que vaut `commandes_pytest`. Un
# extracteur qui ne trouve RIEN les rendrait verts en ne regardant rien — la
# forme d'erreur exacte que ce fichier existe pour interdire ailleurs.
CI_TEMOIN = """
      - name: Une étape sur une ligne
        run: python -m pytest tests/ -q --cov=src/monl

      - name: Une étape repliée
        # Un commentaire, qui n'appartient pas à la commande.
        run: >-
          python -m pytest tests/test_platform_*.py
          tests/test_oauth.py -q
          --cov=src/monl_platform --cov-fail-under=90

      - name: Une étape sans pytest
        run: ruff check src tests
"""


def test_lextracteur_trouve_les_deux_formes_et_ne_les_melange_pas():
    commandes = commandes_pytest(CI_TEMOIN)
    assert len(commandes) == 2, commandes
    assert commandes[0].endswith("--cov=src/monl")
    # La commande repliée est recollée EN ENTIER : sans ça le `-q` de sa
    # deuxième ligne échapperait au contrôle.
    assert "tests/test_oauth.py -q" in commandes[1]
    assert "--cov-fail-under=90" in commandes[1]
    assert "ruff" not in commandes[1]


def test_les_deux_regles_mordent_sur_un_workflow_fautif():
    """La contre-épreuve : sur le témoin ci-dessus, qui pose `-q` et n'a pas
    de `-rs`, les deux règles doivent DÉNONCER. Un test qui passe ne prouve
    pas qu'il mord (point 145)."""
    commandes = commandes_pytest(CI_TEMOIN)
    assert [c for c in commandes if "-q" in c.split()] == commandes
    assert [c for c in commandes
            if not any(o.startswith("-r") and "s" in o[2:] for o in c.split())] == commandes
