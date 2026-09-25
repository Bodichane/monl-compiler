"""Issue #84 : `monl-platform --help` doit annoncer les verbes servis.

L'aide de premier niveau ne décrivait que `--host` et `--port` : `admin` et
`sauvegarde` n'étaient découvrables que dans `docs/EXPLOITATION.md`, qui ne
voyage pas dans la roue. L'exploitant d'une plateforme installée depuis
l'index croyait devoir passer par `sqlite3`, serveur arrêté — la falaise que
le point 142 a fermée.
"""

import pytest

from monl_platform import __main__ as point_d_entree


def _aide(capsys):
    with pytest.raises(SystemExit) as sortie:
        point_d_entree.main(["--help"])
    assert sortie.value.code == 0
    return capsys.readouterr().out


def test_l_aide_annonce_chaque_verbe_du_dispatch(capsys):
    aide = _aide(capsys)
    # Non-vacuité : une table vide rendrait la boucle muette (point 161).
    assert point_d_entree.VERBES
    for nom, fonction in point_d_entree.VERBES.items():
        # Le verbe ET son résumé : un nom sans phrase ne dit pas à quoi il sert.
        assert nom in aide, aide
        assert point_d_entree._resume(fonction) in aide, aide


def test_un_verbe_ajoute_a_la_table_apparait_dans_l_aide(capsys, monkeypatch):
    """La garantie tient à la LECTURE de la table, pas à une liste écrite pour
    le témoin (point 190) : un verbe neuf apparaît sans autre modification."""
    def _essai(argv):
        """Verbe d'essai ajouté par le témoin."""
        return 0

    monkeypatch.setitem(point_d_entree.VERBES, "essai", _essai)
    aide = _aide(capsys)
    assert "essai" in aide and "Verbe d'essai ajouté par le témoin." in aide


def test_un_verbe_sans_docstring_fait_echouer_l_aide(monkeypatch):
    """Une aide muette est précisément le défaut de l'issue : plutôt échouer
    que d'afficher un verbe sans rien en dire."""
    monkeypatch.setitem(point_d_entree.VERBES, "muet", lambda argv: 0)
    with pytest.raises(ValueError, match="docstring"):
        point_d_entree.main(["--help"])
