"""Deux messages qui envoyaient corriger ce qui n'était pas cassé — point 105.

Constat du mainteneur, en lançant une retouche sur un vrai projet :

    monl retouche /projets/SneakerLab "utilise plutôt des icônes …"
    ❌ monl.json introuvable — ce dossier n'est pas un projet monl.

Deux fautes dans une seule réponse.

**Le dossier n'existait pas du tout.** `_load_state` répond `None` aussi bien
pour « dossier absent » que pour « dossier sans monl.json », et tous les appels
concluaient à la seconde. `monl frontend` allait jusqu'à conseiller « lancer
'monl compile' » : le message envoyait recompiler un projet que monl n'avait
jamais trouvé. C'est le reproche du point 97, sur un autre message — une
hypothèse affichée comme un diagnostic est pire qu'un message vague.

**Et les deux arguments étaient inversés.** `retouche` est le SEUL geste dont le
premier argument n'est pas le dossier : `run`, `update`, `diff`, `compile` et
`frontend` le prennent tous en tête. Écrire le dossier d'abord est donc le
réflexe, et monl répondait « ce dossier n'est pas un projet monl » en parlant de
la PHRASE.

Ce que les deux corrections ont en commun : elles NOMMENT ce qui bloque et ne
corrigent rien toutes seules. Remettre les arguments en place à la place de
l'auteur, ce serait deviner — et se tromper le jour où une demande ressemble à
un chemin.
"""
import pytest

from monl.cli import (
    _arguments_inverses,
    _erreur_de_chemin,
    check_coherence,
    cmd_diff,
    cmd_retouche,
    cmd_update,
    compile_project,
)

SPEC = """app BancChemin

entity Note
    titre: String

actor Auteur selfRegister

relation Auteur hasMany Note

rule Note.Read public

workflow Ecrire for Auteur
    Create Note
    Read Note
"""


@pytest.fixture
def projet(tmp_path, capsys):
    (tmp_path / "spec.ml").write_text(SPEC, encoding="utf-8")
    compile_project(str(tmp_path / "spec.ml"), str(tmp_path))
    capsys.readouterr()
    return tmp_path


# --------------------------------------------------------------------------
# Le dossier qui n'existe pas
# --------------------------------------------------------------------------

def test_un_dossier_absent_est_nomme_comme_tel(tmp_path):
    """Le cœur du point : ne pas parler du CONTENU d'un dossier qu'on n'a pas
    trouvé."""
    message = _erreur_de_chemin(str(tmp_path / "nulle-part"))
    assert "Dossier introuvable" in message
    assert "monl.json" not in message
    assert "compile" not in message.lower().replace("compilation", "")


def test_un_dossier_absent_dit_que_le_contenu_na_pas_ete_regarde(tmp_path):
    """Sans cette phrase, l'auteur cherche encore ce qui manque DANS le
    dossier."""
    message = _erreur_de_chemin(str(tmp_path / "nulle-part"))
    assert "pas encore été regardé" in message


def test_un_dossier_existant_ne_declenche_rien(tmp_path):
    """Le témoin : la question du projet doit rester posée là où elle a un
    sens."""
    assert _erreur_de_chemin(str(tmp_path)) is None


def test_la_barre_oblique_de_tete_est_expliquee(tmp_path, monkeypatch):
    """LA faute qui a motivé le point. '/projets/X' n'est pas « projets/X
    ici » : c'est X à la racine du SYSTÈME."""
    (tmp_path / "projets" / "SneakerLab").mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    message = _erreur_de_chemin("/projets/SneakerLab")
    assert "racine du système" in message
    assert "projets/SneakerLab" in message.split("Vouliez-vous dire :")[1]


def test_sans_voisin_plausible_aucune_suggestion_nest_inventee(tmp_path, monkeypatch):
    """Le garde-fou de la suggestion : proposer un chemin qui n'existe pas
    non plus renverrait chercher une deuxième fois pour rien."""
    monkeypatch.chdir(tmp_path)
    message = _erreur_de_chemin("/vraiment/nulle/part")
    assert "Vouliez-vous dire" not in message


@pytest.mark.parametrize("geste", [cmd_update, cmd_diff])
def test_les_gestes_sarretent_sur_le_chemin_pas_sur_letat(geste, tmp_path, capsys):
    """Les deux gestes qui lisent l'état doivent poser les questions dans
    l'ordre : le dossier existe-t-il, PUIS porte-t-il un projet."""
    with pytest.raises(SystemExit):
        geste(str(tmp_path / "nulle-part"))
    sortie = capsys.readouterr().out
    assert "Dossier introuvable" in sortie
    assert "monl.json introuvable" not in sortie


def test_la_verification_de_coherence_distingue_aussi(tmp_path):
    """`monl frontend` passe par là, et c'est lui qui conseillait de
    recompiler un projet jamais trouvé."""
    ok, erreurs, _avertissements = check_coherence(str(tmp_path / "nulle-part"))
    assert not ok
    assert any("Dossier introuvable" in e for e in erreurs)
    assert not any("monl compile" in e for e in erreurs)


# --------------------------------------------------------------------------
# Les arguments inversés
# --------------------------------------------------------------------------

def test_linversion_est_detectee(tmp_path, monkeypatch):
    (tmp_path / "projets" / "SneakerLab").mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    assert _arguments_inverses("/projets/SneakerLab",
                               "utilise plutôt des icônes et un peu de texte")
    assert _arguments_inverses("projets/SneakerLab", "la FAQ est collée")


def test_lordre_correct_ne_declenche_rien():
    """Le témoin, et il compte : un faux positif ici REFUSERAIT une retouche
    parfaitement écrite."""
    assert not _arguments_inverses("la FAQ est collée", ".")
    assert not _arguments_inverses("les images sont mal cadrées", "projets/X")


def test_une_demande_sans_espace_ne_suffit_pas_a_conclure():
    """Une demande d'un seul mot est bizarre mais légitime ; ce qui fait
    l'inversion, c'est qu'elle ressemble à un chemin ET que le dossier
    ressemble à une phrase."""
    assert not _arguments_inverses("illisible", ".")


def test_le_message_dinversion_propose_une_commande_utilisable(tmp_path, monkeypatch,
                                                               capsys):
    """La commande proposée doit MARCHER telle quelle : recopier un chemin dont
    on sait déjà qu'il est faux ferait buter une deuxième fois."""
    (tmp_path / "projets" / "SneakerLab").mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    lignes = []
    with pytest.raises(SystemExit):
        cmd_retouche("utilise plutôt des icônes", "/projets/SneakerLab",
                     say=lignes.append)
    capsys.readouterr()
    rendu = "\n".join(lignes)
    assert "inversés" in rendu
    propose = next(li for li in lignes if li.strip().startswith("monl retouche"))
    assert '"utilise plutôt des icônes"' in propose
    assert "/projets/SneakerLab" not in propose
    assert propose.strip().endswith("projets/SneakerLab")


def test_une_retouche_bien_ecrite_passe_le_controle(projet, capsys):
    """Le témoin de bout en bout : la détection ne doit pas s'interposer sur
    l'usage normal. On s'arrête faute de frontend, pas sur les arguments."""
    with pytest.raises(SystemExit):
        cmd_retouche(str(projet), "les images sont mal cadrées")
    sortie = capsys.readouterr().out
    assert "inversés" not in sortie
    assert "Aucun frontend à retoucher" in sortie
