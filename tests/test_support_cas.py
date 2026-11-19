"""`check_each_case` carries the guarantee `parametrize` gave: a failing
case never hides the next ones, and every faulty case is named.

Forty functions of the suite depend on it; if it stopped at the first
failure or passed on an empty table, they would check less without going red.
"""
import pytest

from tests.support.cases import check_each_case


def test_every_case_runs_and_every_failure_is_named():
    seen = []

    def cas(n):
        seen.append(n)
        assert n % 2 == 0, f"{n} is odd"
        if n == 4:
            pytest.fail("explicit failure on 4")

    with pytest.raises(pytest.fail.Exception) as failure:
        check_each_case([(1,), (2,), (3,), (4,), (6,)], cas,
                            ids=["un", "deux", "trois", "quatre", "six"])
    assert seen == [1, 2, 3, 4, 6], "a failure interrupted the following cases"
    message = str(failure.value)
    assert "3/5 cases failed" in message
    for name in ("un", "trois", "quatre"):
        assert f"- {name} :" in message
    for name in ("deux", "six"):
        assert f"- {name} :" not in message


def test_an_empty_table_does_not_pass():
    with pytest.raises(AssertionError, match="empty"):
        check_each_case([], lambda: None)


def test_a_sound_table_passes_and_unpacks_each_tuple():
    received = []
    check_each_case([(1, "a"), (2, "b")], lambda n, s: received.append((n, s)))
    assert received == [(1, "a"), (2, "b")]
