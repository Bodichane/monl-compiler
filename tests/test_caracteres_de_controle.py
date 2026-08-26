"""Un accent mal échappé produit du NUL, et l'UTF-8 reste valide.

Trouvé sur un site RÉELLEMENT construit et déclaré réussi : « Animalière »
livré en « Animali\x00re », trente et un octets NUL dans index.html. Le
modèle avait écrit ``\\u0000`` là où il visait ``\\u00e8``.
"""

import json

import pytest

from monl.frontend_ai import FrontendAIError, parse_files_payload

NUL = "\x00"


def _reponse(html):
    return json.dumps({"files": {"index.html": html}})


def test_un_octet_nul_fait_refuser_le_fichier():
    with pytest.raises(FrontendAIError, match=r"U\+0000"):
        parse_files_payload(_reponse(f"<h1>Photographie Animali{NUL}re</h1>"))


def test_le_message_nomme_le_fichier_et_le_nombre():
    with pytest.raises(FrontendAIError) as erreur:
        parse_files_payload(_reponse(f"<p>o{NUL}{NUL} la nature</p>"))
    message = str(erreur.value)
    assert "index.html" in message
    assert "2 occurrence" in message


def test_un_echappement_json_produit_du_nul_et_reste_de_l_utf8_valide():
    """La contre-épreuve : sans le refus, rien en aval ne voit le défaut."""
    brut = '{"files": {"index.html": "Animali\\u0000re"}}'
    contenu = json.loads(brut)["files"]["index.html"]
    assert contenu.encode("utf-8").decode("utf-8") == contenu  # UTF-8 valide
    assert NUL in contenu

    with pytest.raises(FrontendAIError):
        parse_files_payload(brut)


def test_les_accents_corrects_passent():
    html = "<h1>Photographie Animalière — où l'âme</h1>"
    assert parse_files_payload(_reponse(html))["index.html"] == html


@pytest.mark.parametrize("blanc", ["\t", "\n", "\r"])
def test_les_blancs_legitimes_restent_autorises(blanc):
    html = f"<h1>Titre</h1>{blanc}<p>Corps</p>"
    assert parse_files_payload(_reponse(html))["index.html"] == html
