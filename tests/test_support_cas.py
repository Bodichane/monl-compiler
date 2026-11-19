"""`check_each_case` carries the guarantee `parametrize` gave: a failing
case never hides the next ones, and every faulty case is named.

Forty functions of the suite depend on it; if it stopped at the first
failure or passed on an empty table, they would check less without going red.
"""
import pytest

from tests.support.cases import check_each_case


def test_every_case_runs_and_every_failure_is_named():
    vus = []

    def cas(n):
        vus.append(n)
        assert n % 2 == 0, f"{n} is odd"
        if n == 4:
            pytest.fail("explicit failure on 4")

    with pytest.raises(pytest.fail.Exception) as echec:
        check_each_case([(1,), (2,), (3,), (4,), (6,)], cas,
                            ids=["un", "deux", "trois", "quatre", "six"])
    assert vus == [1, 2, 3, 4, 6], "a failure interrupted the following cases"
    message = str(echec.value)
    assert "3/5 cases failed" in message
    for nom in ("un", "trois", "quatre"):
        assert f"- {nom} :" in message
    for nom in ("deux", "six"):
        assert f"- {nom} :" not in message


def test_an_empty_table_does_not_pass():
    with pytest.raises(AssertionError, match="empty"):
        check_each_case([], lambda: None)


def test_a_sound_table_passes_and_unpacks_each_tuple():
    recus = []
    check_each_case([(1, "a"), (2, "b")], lambda n, s: recus.append((n, s)))
    assert recus == [(1, "a"), (2, "b")]
