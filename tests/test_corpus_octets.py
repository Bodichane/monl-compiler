"""The bytes of every artifact stay identical to main."""

import json

from tests.support.corpus_octets import BASELINE, corpus_hashes


def test_corpus_octets():
    expected = json.loads(BASELINE.read_text(encoding="utf-8"))
    assert expected and all(expected.values()), "Empty corpus or case without file"
    assert corpus_hashes() == expected, (
        "Bytes changed. Regeneration: PYTHONPATH=src python3 -m tests.support.corpus_octets. "
        "A legitimate change requires a written justification, a proof "
        "of equivalence and the behavioral tests; never a hash "
        "update to hide a regression.")
