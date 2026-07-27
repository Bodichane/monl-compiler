"""Le parcours de commandes de l'orchestrateur — compile → run --check →
update (point 64).

`cli.py` était le point bas de la couverture (35 %) : ses chemins n'étaient
éprouvés qu'indirectement, à travers d'autres tests ou des sous-processus que
l'instrument ne suit pas. Le choix fait ici n'est PAS de faire monter un
chiffre, mais de couvrir ce qu'un utilisateur traverse réellement, et ce dont
l'échec serait silencieux : l'état écrit dans monl.json, la détection d'une
incohérence entre la spec et le backend, et le delta de contrat sur lequel
repose `monl update`.

Le smoke test est délibérément écarté (`skip_smoke=True`) : il démarre un
serveur et est déjà éprouvé par tests/test_smoke_and_frontend_ai.py — le
rejouer ici n'ajouterait que de la lenteur.
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from cli import STATE_FILENAME, check_coherence, cmd_run, cmd_update, compile_project

SPEC = """app Carnet

entity Note
    title: String

actor Admin selfRegister

rule Note.Read public

workflow GererNote for Admin
    Create Note
    Read Note
"""

SPEC_ETENDUE = SPEC.replace("    title: String",
                            "    title: String\n    body: Text")


@pytest.fixture
def projet(tmp_path):
    (tmp_path / "spec.ml").write_text(SPEC, encoding="utf-8")
    compile_project(str(tmp_path / "spec.ml"), str(tmp_path))
    return tmp_path


def test_compile_ecrit_l_etat_et_le_contrat(projet):
    for artefact in ("app.py", "schema.sql", "manage.py",
                     "frontend_contract.json", "FRONTEND_PROMPT.md",
                     STATE_FILENAME):
        assert (projet / artefact).exists(), artefact
    etat = json.loads((projet / STATE_FILENAME).read_text(encoding="utf-8"))
    assert etat["spec"].endswith("spec.ml")


def test_la_coherence_passe_juste_apres_une_compilation(projet):
    ok, erreurs, _avertissements = check_coherence(str(projet))
    assert ok, erreurs


def test_un_backend_modifie_a_la_main_est_detecte(projet):
    """La promesse de `monl run` : app.py est SCELLÉ. Une retouche manuelle
    doit être vue, sinon la spec cesse d'être la source de vérité sans que
    personne ne le sache."""
    chemin = projet / "app.py"
    chemin.write_text(chemin.read_text(encoding="utf-8") + "\n# retouche\n",
                      encoding="utf-8")
    ok, erreurs, _ = check_coherence(str(projet))
    assert not ok
    assert any("app.py" in e for e in erreurs), erreurs


def test_run_check_s_arrete_sur_une_incoherence(projet):
    """Et il s'arrête AVANT de lancer quoi que ce soit : sortie non nulle,
    pas de serveur démarré."""
    chemin = projet / "schema.sql"
    chemin.write_text(chemin.read_text(encoding="utf-8") + "\n-- retouche\n",
                      encoding="utf-8")
    with pytest.raises(SystemExit) as sortie:
        cmd_run(str(projet), check_only=True, skip_smoke=True)
    assert sortie.value.code == 1


def test_run_check_passe_sur_un_projet_sain(projet):
    cmd_run(str(projet), check_only=True, skip_smoke=True)   # ne doit pas sortir


def test_update_rapporte_le_champ_ajoute_et_prepare_la_consigne(projet, capsys):
    (projet / "spec.ml").write_text(SPEC_ETENDUE, encoding="utf-8")
    cmd_update(str(projet))
    sortie = capsys.readouterr().out
    assert "Note.body" in sortie, sortie
    assert "champ ajouté" in sortie, sortie
    assert (projet / "FRONTEND_UPDATE_PROMPT.md").exists()
    # Le delta doit aussi être arrivé dans le contrat lui-même.
    contrat = json.loads((projet / "frontend_contract.json").read_text(encoding="utf-8"))
    assert "body" in str(contrat)


def test_update_sans_changement_ne_fabrique_pas_de_consigne(projet, capsys):
    """Une consigne de mise à jour envoyée pour rien ferait retravailler
    l'IA frontend sur une interface déjà juste."""
    cmd_update(str(projet))
    sortie = capsys.readouterr().out
    assert "aucun changement d'interface" in sortie, sortie
    assert not (projet / "FRONTEND_UPDATE_PROMPT.md").exists()


def test_update_refuse_un_dossier_qui_n_est_pas_un_projet(tmp_path):
    with pytest.raises(SystemExit) as sortie:
        cmd_update(str(tmp_path))
    assert sortie.value.code == 1
