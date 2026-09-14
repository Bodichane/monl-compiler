"""Une barrière de couverture porte sur TOUTE la suite, ou elle ment.

La CI mesurait la plateforme sur une liste de fichiers écrite à la main :

    python -m pytest tests/test_platform_*.py tests/test_oauth.py
      tests/test_administration.py tests/test_codes_de_secours.py
      --cov=src/monl_platform --cov-fail-under=90

Mesuré avant de corriger : **cinq fichiers exerçaient la plateforme hors de
cette liste** — dont `tests/test_console_javascript.py`, qui garde les pages
mortes du point 163. Leurs lignes ne comptaient pas dans les 90 %, et un test
rangé sous un autre nom serait sorti de la mesure sans un mot. C'est le
point 169 pour la quatrième fois : une liste tenue à la main cesse de garder,
et son silence est complet.

La correction ne rallonge pas la liste, elle la SUPPRIME : la suite tourne une
fois en mesurant les deux paquets, puis `coverage report --include=…` tire deux
barrières de la même exécution.

Trois règles vivent ici, chacune dans une FONCTION que sa contre-épreuve
exerce sur un workflow fautif — et non dans le corps d'un test, ce qui
obligerait la contre-épreuve à réécrire la règle pour la vérifier (le témoin
retiré du point 170).
"""

import pytest
from support.ci_workflow import (
    CI,
    RACINE,
    commandes_coverage,
    commandes_pytest,
    fichiers_de_tests,
    options_de_couverture,
    selection_dune_commande,
    seuil_de_couverture_du_projet,
)


def _commandes(texte):
    commandes = commandes_pytest(texte)
    assert commandes, "aucune invocation pytest trouvée"
    return commandes


def fichiers_hors_mesure(texte):
    """Pour chaque commande qui MESURE une couverture, les fichiers de tests
    qu'elle n'exécute pas. Ces fichiers exercent le paquet sans compter dans
    la mesure : le pourcentage annoncé n'est pas celui du paquet."""
    tous = fichiers_de_tests()
    hors = {}
    for commande in _commandes(texte):
        if not any(o.startswith("--cov=") for o in options_de_couverture(commande)):
            continue
        manquants = tous - selection_dune_commande(commande)
        if manquants:
            hors[commande] = sorted(str(f) for f in manquants)
    return hors


def fichiers_jamais_executes(texte):
    """Les fichiers de tests qu'AUCUNE commande du workflow ne sélectionne."""
    executes = set()
    for commande in _commandes(texte):
        executes |= selection_dune_commande(commande)
    return sorted(str(f) for f in fichiers_de_tests() - executes)


def barrieres_par_paquet(texte):
    """Le seuil que le workflow oppose à chaque paquet de `src/`.

    Les paquets sont lus sur le DISQUE : les recopier ici referait, dans le
    témoin, la liste écrite à la main qu'il existe pour interdire.
    """
    paquets = {d.name for d in (RACINE / "src").iterdir()
               if d.is_dir() and (d / "__init__.py").exists()}
    assert paquets, "aucun paquet trouvé sous src/"
    barrieres = {}
    for commande in commandes_coverage(texte):
        seuils = [j for j in commande.split() if j.startswith("--fail-under=")]
        if not seuils:
            continue
        for paquet in paquets:
            if f"src/{paquet}/*" in commande:
                barrieres[paquet] = float(seuils[-1].split("=", 1)[1])
    return paquets, barrieres


# ─────────────────────────────────────────────────────────────────────────
# Les trois règles, sur le VRAI workflow.
# ─────────────────────────────────────────────────────────────────────────
def test_une_barriere_de_couverture_porte_sur_toute_la_suite():
    """Le cœur du fichier. Une couverture mesurée sur une SÉLECTION annonce un
    pourcentage du paquet en n'ayant exercé qu'une partie de ce qui l'exerce :
    le nombre est trop bas parce qu'il ignore des tests réels, et fragile
    parce que le prochain test rangé ailleurs en sortira en silence."""
    hors = fichiers_hors_mesure(CI.read_text(encoding="utf-8"))
    assert not hors, (
        "une barrière de couverture ne doit pas être mesurée sur une "
        "sélection de fichiers : les tests hors sélection exercent le paquet "
        "sans compter dans la mesure, et le prochain test rangé sous un autre "
        f"nom en sortira sans un mot (point 169). {hors}")


def test_la_ci_execute_chaque_fichier_de_tests():
    """L'autre bout du même défaut : un fichier que AUCUNE commande ne
    sélectionne est un fichier que personne n'exécute. Le dépôt n'en a aucun
    aujourd'hui — c'est justement pendant qu'il n'en a aucun qu'on pose la
    garde, sans quoi elle arriverait après (point 167bis)."""
    oublies = fichiers_jamais_executes(CI.read_text(encoding="utf-8"))
    assert not oublies, (
        f"aucune commande de ci.yml n'exécute ces fichiers : {oublies}")


def test_chaque_paquet_du_depot_porte_sa_barriere():
    """Une barrière retirée ne fait aucun bruit. Le seuil vient de
    `pyproject.toml` : l'inscrire une seconde fois ici le ferait diverger le
    jour où on le déplace."""
    paquets, barrieres = barrieres_par_paquet(CI.read_text(encoding="utf-8"))
    manquants = sorted(paquets - set(barrieres))
    assert not manquants, (
        f"ces paquets de src/ n'ont plus de barrière de couverture dans "
        f"ci.yml : {manquants}")
    plancher = seuil_de_couverture_du_projet()
    faibles = {p: v for p, v in barrieres.items() if v < plancher}
    assert not faibles, (
        f"`pyproject.toml` déclare une barrière à {plancher} % ; ci.yml mesure "
        f"moins que ça : {faibles}")


# ─────────────────────────────────────────────────────────────────────────
# Les contre-épreuves. Un test qui passe ne prouve pas qu'il mord (point 145),
# et les trois règles ci-dessus ne valent que ce que valent les extracteurs :
# un extracteur qui rendrait toujours l'ensemble complet les rendrait vertes
# en ne regardant rien (point 161).
# ─────────────────────────────────────────────────────────────────────────
CI_FAUTIF = """
      - name: Suite complète
        run: python -m pytest tests/ -rs --cov=src/monl

      - name: Couverture de la plateforme (barrière à 90 %)
        run: >-
          python -m pytest tests/test_platform_*.py tests/test_oauth.py
          tests/test_administration.py tests/test_codes_de_secours.py -rs
          --cov=src/monl_platform --cov-report=term --cov-fail-under=90
"""

CI_AMPUTE = """
      - name: On n'exécute qu'une partie de la suite
        run: python -m pytest tests/test_platform_*.py -rs

      - name: Une seule barrière, et trop basse
        run: |
          python -m coverage report --include='src/monl/*' --fail-under=10
"""


def test_la_regle_mord_sur_la_forme_que_la_ci_portait():
    """Sur le texte EXACT que `ci.yml` portait avant ce correctif."""
    hors = fichiers_hors_mesure(CI_FAUTIF)
    assert len(hors) == 1, hors
    manquants = next(iter(hors.values()))
    # Le fichier NOMMÉ par la mesure de cette séance doit en faire partie.
    assert "tests/test_console_javascript.py" in manquants
    # Et la commande qui, elle, prend toute la suite ne doit PAS être dénoncée.
    assert all("--cov=src/monl_platform" in c for c in hors)


def test_les_deux_autres_regles_mordent_sur_un_workflow_amputé():
    oublies = fichiers_jamais_executes(CI_AMPUTE)
    assert oublies, "un workflow qui n'exécute qu'un motif doit être dénoncé"
    assert "tests/test_golden_artifacts.py" in oublies

    paquets, barrieres = barrieres_par_paquet(CI_AMPUTE)
    assert sorted(paquets - set(barrieres)) == ["monl_platform"]
    assert barrieres["monl"] < seuil_de_couverture_du_projet()


def test_lextracteur_developpe_motifs_dossiers_et_absence_de_cible():
    """Les trois formes que le workflow peut prendre, sur de VRAIS chemins."""
    tous = fichiers_de_tests()
    # Un dossier se parcourt comme pytest le parcourt.
    assert selection_dune_commande("run: python -m pytest tests/ -rs") == tous
    # Sans cible, pytest retombe sur `testpaths` — donc le même ensemble.
    assert selection_dune_commande("run: python -m pytest -rs") == tous
    # Un motif ne développe QUE ce qu'il désigne.
    motif = selection_dune_commande(
        "run: python -m pytest tests/test_platform_*.py")
    assert motif and motif < tous
    assert all(f.name.startswith("test_platform_") for f in motif)


def test_lextracteur_leve_sur_une_cible_quil_ne_sait_pas_lire():
    """Une cible qu'on ne résout pas ne doit jamais s'évaporer : ignorée, elle
    ferait passer une commande étroite pour une commande large."""
    with pytest.raises(AssertionError, match="aucun fichier existant"):
        selection_dune_commande("run: python -m pytest tests/test_inexistant.py")


def test_lextracteur_separe_les_commandes_dun_bloc_litteral():
    """Un bloc « run: | » porte plusieurs commandes, une par ligne. Recollées
    en une seule, les deux barrières n'en feraient qu'une — et la règle
    ci-dessus déclarerait un paquet gardé alors qu'il ne l'est plus."""
    bloc = """
      - name: Deux barrières
        run: |
          python -m coverage report --include='src/monl/*' --fail-under=90
          python -m coverage report --include='src/monl_platform/*' --fail-under=90
"""
    commandes = commandes_coverage(bloc)
    assert len(commandes) == 2, commandes
    assert "src/monl/*" in commandes[0] and "src/monl_platform" not in commandes[0]
    assert "src/monl_platform/*" in commandes[1]

    # Et la commande PLIÉE, elle, reste recollée en entier : la distinction
    # porte sur le marqueur reporté, pas sur la présence d'une continuation.
    plie = """
      - name: Suite
        run: >-
          python -m pytest tests/ -rs
          --cov=src/monl --cov-fail-under=0
"""
    assert commandes_pytest(plie) == [
        "python -m pytest tests/ -rs --cov=src/monl --cov-fail-under=0"]
