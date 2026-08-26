"""Le suivi de construction rapporte des étapes RÉELLES, jamais devinées.

Une progression inventée est pire qu'une progression absente : elle fait
croire que le serveur sait où il en est. Les étapes viennent donc du journal
que la couche IA écrit au fur et à mesure, et le rattachement se fait par
HORODATAGE — l'identifiant d'exécution n'est enregistré qu'à la FIN de la
construction, or c'est pendant qu'elle tourne qu'on veut la suivre.
"""

import json

import pytest

from monl.usage import USAGE_FILENAME
from monl_platform.progress import PLANNED_STAGES, planned_remaining, read_stages


def _evenement(stage, horodatage, **extra):
    evenement = {
        "stage": stage,
        "timestamp": horodatage,
        "model": "modele/latest",
        "duration_seconds": 1.5,
        "input_tokens": 100,
        "output_tokens": 42,
        "retry": 0,
        "run_id": "abc",
    }
    evenement.update(extra)
    return evenement


@pytest.fixture()
def projet(tmp_path):
    def ecrire(evenements):
        lignes = [json.dumps(e, ensure_ascii=False) for e in evenements]
        (tmp_path / USAGE_FILENAME).write_text("\n".join(lignes) + "\n", encoding="utf-8")
        return tmp_path
    return ecrire


def test_les_etapes_d_une_construction_en_cours_sont_lisibles(projet):
    """Sans finished_at, on prend tout ce qui est arrivé depuis le début."""
    dossier = projet([
        _evenement("index.html", "2026-08-18T10:00:05+00:00"),
        _evenement("styles.css", "2026-08-18T10:00:40+00:00"),
    ])

    etapes = read_stages(dossier, "2026-08-18T10:00:00+00:00", None)

    assert [e["name"] for e in etapes] == ["index.html", "styles.css"]
    assert etapes[0]["model"] == "modele/latest"
    assert etapes[0]["output_tokens"] == 42


def test_une_construction_anterieure_n_est_pas_recomptee(projet):
    """C'est tout l'enjeu : le journal accumule les constructions successives."""
    dossier = projet([
        _evenement("index.html", "2026-08-17T09:00:00+00:00"),
        _evenement("index.html", "2026-08-18T10:00:05+00:00"),
    ])

    etapes = read_stages(dossier, "2026-08-18T10:00:00+00:00", None)

    assert len(etapes) == 1
    assert etapes[0]["at"] == "2026-08-18T10:00:05+00:00"


def test_une_construction_terminee_s_arrete_a_sa_fin(projet):
    dossier = projet([
        _evenement("index.html", "2026-08-18T10:00:05+00:00"),
        _evenement("app.js", "2026-08-18T10:09:00+00:00"),
    ])

    etapes = read_stages(
        dossier, "2026-08-18T10:00:00+00:00", "2026-08-18T10:01:00+00:00"
    )

    assert [e["name"] for e in etapes] == ["index.html"]


def test_une_ligne_tronquee_est_une_ecriture_en_cours_pas_une_erreur(tmp_path):
    """Le journal est lu pendant qu'il est écrit : la dernière ligne peut être coupée."""
    (tmp_path / USAGE_FILENAME).write_text(
        json.dumps(_evenement("index.html", "2026-08-18T10:00:05+00:00")) + "\n"
        + '{"stage": "styles.c',
        encoding="utf-8",
    )

    etapes = read_stages(tmp_path, "2026-08-18T10:00:00+00:00", None)

    assert [e["name"] for e in etapes] == ["index.html"]


def test_un_journal_absent_rend_une_liste_vide(tmp_path):
    """Un projet peut n'avoir jamais appelé d'IA."""
    assert read_stages(tmp_path, "2026-08-18T10:00:00+00:00", None) == []


def test_un_debut_inconnu_ne_devine_rien(projet):
    dossier = projet([_evenement("index.html", "2026-08-18T10:00:05+00:00")])

    assert read_stages(dossier, None, None) == []


def test_une_image_est_distinguee_d_un_fichier(projet):
    dossier = projet([
        _evenement("image", "2026-08-18T10:00:02+00:00"),
        _evenement("index.html", "2026-08-18T10:00:05+00:00"),
    ])

    etapes = read_stages(dossier, "2026-08-18T10:00:00+00:00", None)

    assert [e["kind"] for e in etapes] == ["image", "fichier"]


def test_le_reste_a_faire_vient_des_cibles_declarees():
    """La console n'invente pas la suite : monl déclare ce qu'il produit."""
    etapes = [{"name": "index.html"}, {"name": "styles.css"}]

    assert planned_remaining(etapes) == ["app.js"]
    assert planned_remaining([]) == list(PLANNED_STAGES)
    assert planned_remaining([{"name": n} for n in PLANNED_STAGES]) == []
