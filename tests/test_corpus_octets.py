"""Les octets de tous les artefacts restent identiques à main."""

import json

from tests.support.corpus_octets import BASELINE, corpus_hashes


def test_corpus_octets():
    expected = json.loads(BASELINE.read_text(encoding="utf-8"))
    assert expected and all(expected.values()), "Corpus vide ou cas sans fichier"
    assert corpus_hashes() == expected, (
        "Octets modifiés. Régénération : PYTHONPATH=src python3 -m tests.support.corpus_octets. "
        "Un changement légitime exige une justification écrite, une preuve "
        "d'équivalence et les tests comportementaux ; jamais une mise à jour "
        "des hashes pour masquer une régression.")
