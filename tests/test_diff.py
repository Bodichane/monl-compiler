"""`monl diff` : voir le delta avant d'écrire — point 103.

`monl update` écrit PUIS rapporte. Tant que le rapport dit ce qu'on attendait,
l'ordre est sans conséquence ; le jour où il annonce un écran entier à réécrire,
on aimerait l'avoir su avant d'avoir recompilé et remplacé le contrat de
référence. `monl diff` répond à la même question sans rien toucher.

Ce que le geste décide :

* **le rapport a UNE source.** `_rapporter_delta` est extrait de `cmd_update` et
  partagé : deux calculs de delta finiraient par diverger, et c'est justement le
  calcul dont six points (88 à 91, 94, 99) ont montré qu'il est difficile à
  tenir juste. Le test qui l'atteste est
  `test_diff_et_update_disent_exactement_la_meme_chose` ;
* **le dossier de sortie est jetable, mais `base_dir` reste le VRAI projet.**
  Les assets déclarés vivent dans le projet ; les chercher dans un dossier
  temporaire ferait échouer la compilation pour une raison qui n'existe pas
  (brique 13, point 83). C'est le piège que ce geste devait éviter, et il a
  fallu ouvrir `compile_project` pour ça ;
* **aucun fichier du projet n'est écrit** — ni `app.py`, ni le contrat, ni
  `monl.json`, ni la consigne d'évolution. Vérifié par empreinte de l'ARBRE
  entier, pas par une liste de noms qu'on pourrait oublier de compléter.
"""
import hashlib
import os

import pytest

from monl.cli import cmd_diff, cmd_update, compile_project

SPEC = """app BancDiff

entity Article
    titre: String
    corps: Text

actor Auteur selfRegister

relation Auteur hasMany Article

rule Article.Read public
rule Article.Update ownedBy Auteur

workflow Ecrire for Auteur
    Create Article
    Read Article
    Update Article
"""


def _empreinte(dossier):
    """Empreinte de l'ARBRE entier — chemins, tailles et contenus.

    Lister les fichiers qu'on s'attend à ne pas voir bouger laisserait passer
    celui auquel on n'a pas pensé ; c'est le raisonnement du garde-fou
    d'empreinte du point 73, appliqué en sens inverse."""
    condensat = hashlib.sha256()
    for racine, _sous, fichiers in sorted(os.walk(dossier)):
        for nom in sorted(fichiers):
            chemin = os.path.join(racine, nom)
            condensat.update(os.path.relpath(chemin, dossier).encode())
            with open(chemin, "rb") as fh:
                condensat.update(fh.read())
    return condensat.hexdigest()


@pytest.fixture
def projet(tmp_path, capsys):
    (tmp_path / "spec.ml").write_text(SPEC, encoding="utf-8")
    compile_project(str(tmp_path / "spec.ml"), str(tmp_path))
    capsys.readouterr()
    return tmp_path


def _lignes_de_delta(sortie):
    """Les lignes du rapport, sans le bruit de compilation ni les bandeaux
    propres à chacun des deux gestes."""
    gardees, dedans = [], False
    for ligne in sortie.splitlines():
        if ligne.startswith("─── Delta"):
            dedans = True
            continue
        if dedans:
            if ligne.startswith("───"):
                break
            if "Consigne prête" in ligne:
                continue  # propre à `update`, qui écrit le brief
            gardees.append(ligne.rstrip())
    return gardees


def _modifier(projet):
    spec = (projet / "spec.ml").read_text(encoding="utf-8")
    spec = spec.replace("    corps: Text", "    corps: Text\n    chapeau: String")
    spec = spec.replace("rule Article.Read public",
                        "rule Article.Read public\n"
                        'rule Article.statut oneOf "brouillon", "publie"')
    spec = spec.replace("    titre: String", "    titre: String\n    statut: String")
    (projet / "spec.ml").write_text(spec, encoding="utf-8")


# --------------------------------------------------------------------------
# Ce que le dry-run ne doit PAS faire
# --------------------------------------------------------------------------

def test_diff_necrit_rien_quand_la_spec_a_change(projet, capsys):
    """LE test qui porte le geste. L'empreinte porte sur l'arbre entier."""
    _modifier(projet)
    avant = _empreinte(projet)
    cmd_diff(str(projet))
    capsys.readouterr()
    assert _empreinte(projet) == avant


def test_diff_necrit_pas_la_consigne_devolution(projet, capsys):
    """`update` écrit FRONTEND_UPDATE_PROMPT.md quand il y a de quoi réécrire.
    `diff` doit annoncer le même changement et ne rien déposer."""
    _modifier(projet)
    cmd_diff(str(projet))
    capsys.readouterr()
    assert not (projet / "docs/FRONTEND_UPDATE_PROMPT.md").exists()

    cmd_update(str(projet))
    capsys.readouterr()
    assert (projet / "docs/FRONTEND_UPDATE_PROMPT.md").exists()


def test_diff_ne_touche_pas_au_contrat_de_reference(projet, capsys):
    """Le contrat déjà posé est la RÉFÉRENCE de la comparaison : l'écraser
    pendant un dry-run rendrait le geste suivant aveugle."""
    _modifier(projet)
    avant = (projet / "frontend_contract.json").read_text(encoding="utf-8")
    cmd_diff(str(projet))
    capsys.readouterr()
    assert (projet / "frontend_contract.json").read_text(encoding="utf-8") == avant


# --------------------------------------------------------------------------
# Ce qu'il doit dire
# --------------------------------------------------------------------------

def test_diff_et_update_disent_exactement_la_meme_chose(projet, capsys):
    """Le test que le geste réclamait dès sa conception : un rapport, une
    source. Deux implémentations du delta finiraient par diverger."""
    _modifier(projet)
    cmd_diff(str(projet))
    par_diff = _lignes_de_delta(capsys.readouterr().out)
    cmd_update(str(projet))
    par_update = _lignes_de_delta(capsys.readouterr().out)

    assert par_diff == par_update
    assert par_diff, "le banc doit produire un delta, sinon il ne compare rien"


def test_diff_se_tait_quand_la_spec_na_pas_bouge(projet, capsys):
    cmd_diff(str(projet))
    sortie = capsys.readouterr().out
    assert "aucun changement d'interface" in sortie
    assert "monl update" not in sortie, \
        "ne pas envoyer appliquer un changement qui n'existe pas"


def test_diff_annonce_quil_na_rien_ecrit(projet, capsys):
    _modifier(projet)
    cmd_diff(str(projet))
    sortie = capsys.readouterr().out
    assert "[DRY-RUN]" in sortie
    assert "Aucun fichier modifié" in sortie


def test_diff_renvoie_vers_update_quand_il_y_a_de_quoi(projet, capsys):
    _modifier(projet)
    cmd_diff(str(projet))
    assert "monl update" in capsys.readouterr().out


def test_diff_sans_etat_de_projet_sarrete(tmp_path, capsys):
    with pytest.raises(SystemExit):
        cmd_diff(str(tmp_path))
    assert "introuvable" in capsys.readouterr().out


# --------------------------------------------------------------------------
# Le piège que le dossier temporaire tendait
# --------------------------------------------------------------------------

SPEC_AVEC_ASSET = SPEC.replace("entity Article", """assets
    logo: "medias/logo.svg"

entity Article""")


def test_diff_trouve_les_assets_du_vrai_projet(tmp_path, capsys):
    """Le piège du dossier jetable. `compile_project` vérifiait l'existence des
    assets dans son dossier de SORTIE ; en compilant ailleurs, un projet
    parfaitement valide aurait échoué en annonçant un fichier manquant qui, lui,
    est bien là. C'est pour ça que `base_dir` a dû devenir un paramètre."""
    (tmp_path / "medias").mkdir()
    (tmp_path / "medias" / "logo.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg"></svg>', encoding="utf-8")
    (tmp_path / "spec.ml").write_text(SPEC_AVEC_ASSET, encoding="utf-8")
    compile_project(str(tmp_path / "spec.ml"), str(tmp_path))
    capsys.readouterr()

    cmd_diff(str(tmp_path))
    sortie = capsys.readouterr().out
    assert "aucun changement d'interface" in sortie
    assert "introuvable" not in sortie
    assert "manquant" not in sortie


def test_une_spec_cassee_montre_le_message_du_compilateur(projet, capsys):
    """Quand la compilation d'essai échoue, c'est SON message qui est utile —
    le nôtre ne dirait que « ça n'a pas marché »."""
    spec = (projet / "spec.ml").read_text(encoding="utf-8")
    (projet / "spec.ml").write_text(
        spec + "rule Article.fantome hidden\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        cmd_diff(str(projet))
    assert "fantome" in capsys.readouterr().out
