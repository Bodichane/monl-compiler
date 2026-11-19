"""Un accent mal échappé produit du NUL, et l'UTF-8 reste valide.

Trouvé sur un site RÉELLEMENT construit et déclaré réussi : « Animalière »
livré en « Animali\x00re », trente et un octets NUL dans index.html. Le
modèle avait écrit ``\\u0000`` là où il visait ``\\u00e8``.
"""

import json

import pytest

from monl.frontend_ai import FrontendAIError, parse_files_payload
from tests.support.cas import check_each_case

NUL = "\x00"


def _reponse(html):
    return json.dumps({"files": {"index.html": html}})


def test_a_nul_byte_makes_the_file_refused():
    with pytest.raises(FrontendAIError, match=r"U\+0000"):
        parse_files_payload(_reponse(f"<h1>Photographie Animali{NUL}re</h1>"))


def test_the_message_names_the_file_and_the_count():
    with pytest.raises(FrontendAIError) as erreur:
        parse_files_payload(_reponse(f"<p>o{NUL}{NUL} la nature</p>"))
    message = str(erreur.value)
    assert "index.html" in message
    assert "2 occurrence" in message


def test_a_json_escape_produces_nul_and_stays_valid_utf8():
    """The counter-proof: without the refusal, nothing downstream sees the defect."""
    brut = '{"files": {"index.html": "Animali\\u0000re"}}'
    contenu = json.loads(brut)["files"]["index.html"]
    assert contenu.encode("utf-8").decode("utf-8") == contenu  # UTF-8 valide
    assert NUL in contenu

    with pytest.raises(FrontendAIError):
        parse_files_payload(brut)


def test_correct_accented_letters_pass():
    html = "<h1>Photographie Animalière — où l'âme</h1>"
    assert parse_files_payload(_reponse(html))["index.html"] == html


def test_legitimate_whitespace_stays_allowed():
    table = ["\t", "\n", "\r"]

    def cas(blanc):
        html = f"<h1>Titre</h1>{blanc}<p>Corps</p>"
        assert parse_files_payload(_reponse(html))["index.html"] == html

    check_each_case([(valeur,) for valeur in table], cas)
