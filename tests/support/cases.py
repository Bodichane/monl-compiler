"""Run a table of cases in ONE test, without one case hiding the others.

`@pytest.mark.parametrize` counts each row as a test: 89 functions of the
suite produced 370. For a pure check (no server, no file nor setting shared
between cases), it is the same work, spread over as many items.

`check_each_case` keeps what makes a parametrization useful: ALL cases
run, even after a failure, and the message names each faulty case with its
cause. It does not keep the count: a case is not a test.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence

import pytest


def check_each_case(table: Iterable[tuple], check: Callable, *,
                        ids: Sequence[str] | None = None) -> None:
    """Calls `verifier(*cas)` for each tuple of `table`.

    Fails ONCE, at the end, listing each faulty case. An empty table fails too:
    a test that checks nothing must not pass (point 161). A `pytest.skip` inside
    a case is NOT caught: it would skip the whole test, hence the refusal to
    convert a body that contains one.
    """
    table = [tuple(cas) for cas in table]
    assert table, "empty case table: this test would check nothing"
    if ids is not None:
        assert len(ids) == len(table), "un nom par cas"
    failures = []
    for rang, cas in enumerate(table):
        try:
            check(*cas)
        except (Exception, pytest.fail.Exception) as exc:  # aggregate, do not hide
            name = ids[rang] if ids is not None else repr(cas)[:160]
            failures.append(f"- {name} : {type(exc).__name__}: {exc}")
    if failures:
        pytest.fail(f"{len(failures)}/{len(table)} cases failed:\n" + "\n".join(failures),
                    pytrace=False)
