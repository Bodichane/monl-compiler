"""Stopping a test server started by `subprocess.Popen`: stop AND close.

`terminate()` then `wait()` stop the process, but a `stdout=PIPE` or
`stderr=PIPE` leaves a descriptor open that nothing closes: it goes to the
garbage collector (`ResourceWarning: unclosed file <_io.BufferedReader ...>`).
The shipped smoke test already closes it (`smoke_test/__init__.py`); eleven
fixtures of the suite did not.
"""

from __future__ import annotations

import subprocess


def fermer_tubes(processus: subprocess.Popen) -> None:
    """Closes the pipes still open, without touching the process."""
    for tube in (processus.stdin, processus.stdout, processus.stderr):
        if tube is not None and not tube.closed:
            tube.close()


def arreter_processus(processus: subprocess.Popen, delai: float = 10) -> None:
    """`terminate`, bounded wait, `kill` as a last resort, then close.

    After a `kill`, we WAIT again: without `wait`, the process stays a zombie and
    `Popen.__del__` reports it too.
    """
    if processus.poll() is None:
        processus.terminate()
        try:
            processus.wait(timeout=delai)
        except subprocess.TimeoutExpired:
            processus.kill()
            processus.wait()
    fermer_tubes(processus)
