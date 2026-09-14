"""La sonde de sauvegarde vérifie le contenu, pas seulement le nom du fichier."""

import sqlite3
import time

from monl_platform.backup_healthcheck import sauvegarde_recente


def _copie_valide(chemin):
    with sqlite3.connect(chemin) as connexion:
        connexion.execute("CREATE TABLE preuve (id INTEGER PRIMARY KEY)")
        connexion.commit()


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
