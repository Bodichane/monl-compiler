"""La sonde de sauvegarde vérifie le contenu, pas seulement le nom du fichier."""

import os
import pathlib
import sqlite3
import time

import pytest

from monl_platform.backup_healthcheck import _sqlite_valide, sauvegarde_recente


def _copie_valide(chemin):
    # Fermeture explicite (point 141) : `with sqlite3.connect(...)` valide la
    # transaction mais ne ferme pas — sans `.close()`, cette aide de test
    # laissait elle-même un descripteur ouvert sur le fichier qu'elle vient
    # de créer, faussant le test ci-dessous qui compte ceux de la SONDE.
    connexion = sqlite3.connect(chemin)
    try:
        with connexion:
            connexion.execute("CREATE TABLE preuve (id INTEGER PRIMARY KEY)")
    finally:
        connexion.close()


def test_une_copie_sqlite_recente_et_intègre_est_healthy(tmp_path):
    chemin = tmp_path / "base-20260914-120000.sqlite3"
    _copie_valide(chemin)

    assert sauvegarde_recente(tmp_path, maintenant=time.time(), age_maximal=60)


def test_une_copie_vide_ou_corrompue_est_unhealthy(tmp_path):
    (tmp_path / "base-vide.sqlite3").write_bytes(b"")
    (tmp_path / "base-corrompue.sqlite3").write_bytes(b"pas une base sqlite")

    assert not sauvegarde_recente(tmp_path, maintenant=time.time(), age_maximal=60)


def test_une_copie_trop_ancienne_est_unhealthy(tmp_path):
    chemin = tmp_path / "base-20260914-120000.sqlite3"
    _copie_valide(chemin)

    assert not sauvegarde_recente(tmp_path, maintenant=time.time() + 61, age_maximal=60)


def _descripteurs(chemin):
    """Combien de descripteurs ce processus tient ouverts sur ce fichier."""
    dossier = pathlib.Path("/proc") / str(os.getpid()) / "fd"
    total = 0
    for entree in dossier.iterdir():
        try:
            if str(chemin) in os.readlink(entree):
                total += 1
        except OSError:                       # descripteur refermé entre-temps
            continue
    return total


@pytest.mark.skipif(not os.path.isdir("/proc/self/fd"),
                    reason="le décompte de descripteurs demande /proc")
def test_la_sonde_ne_laisse_aucune_connexion_ouverte_derriere_elle(tmp_path):
    """`with sqlite3.connect(...)` valide la transaction, mais ne FERME pas
    (point 141, identity_database.py) — un objet `Connection` de CPython
    prend part à des cycles de références, il n'est rendu qu'au ramasse-
    miettes cyclique. Cette sonde tourne toutes les 30 s dans le conteneur de
    sauvegarde : sans fermeture explicite, elle accumule un descripteur par
    appel jusqu'à heurter la limite du conteneur.

    Reproduit et mesuré AVANT correction sur ce fichier même : 300 appels
    laissaient 260 descripteurs ouverts, 193 encore présents après un
    `gc.collect()` manuel.
    """
    chemin = tmp_path / "base-20260914-120000.sqlite3"
    _copie_valide(chemin)

    for _ in range(200):
        assert _sqlite_valide(chemin)

    ouverts = _descripteurs(chemin)
    assert ouverts == 0, f"{ouverts} descripteurs restent ouverts sur la sauvegarde"
