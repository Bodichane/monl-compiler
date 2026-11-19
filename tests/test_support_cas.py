"""`verifier_chaque_cas` carries the guarantee `parametrize` gave: a failing
case never hides the next ones, and every faulty case is named.

Forty functions of the suite depend on it; if it stopped at the first
failure or passed on an empty table, they would check less without going red.
"""
import pytest

from tests.support.cas import verifier_chaque_cas


def test_every_case_runs_and_every_failure_is_named():
    vus = []

    def cas(n):
        vus.append(n)
        assert n % 2 == 0, f"{n} est impair"
        if n == 4:
            pytest.fail("échec explicite sur 4")

    with pytest.raises(pytest.fail.Exception) as echec:
        verifier_chaque_cas([(1,), (2,), (3,), (4,), (6,)], cas,
                            ids=["un", "deux", "trois", "quatre", "six"])
    assert vus == [1, 2, 3, 4, 6], "un échec a interrompu les cas suivants"
    message = str(echec.value)
    assert "3/5 cas en échec" in message
    for nom in ("un", "trois", "quatre"):
        assert f"- {nom} :" in message
    for nom in ("deux", "six"):
        assert f"- {nom} :" not in message


def test_an_empty_table_does_not_pass():
    with pytest.raises(AssertionError, match="vide"):
        verifier_chaque_cas([], lambda: None)


def test_a_sound_table_passes_and_unpacks_each_tuple():
    recus = []
    verifier_chaque_cas([(1, "a"), (2, "b")], lambda n, s: recus.append((n, s)))
    assert recus == [(1, "a"), (2, "b")]
