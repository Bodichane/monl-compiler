"""Makes the monl package importable from the tests (point 65).

Before: every test file started with a sys.path.insert towards src/, followed
by flat imports marked "noqa: E402" — the same incantation twenty times, and
an instruction order that had to be respected or else ImportError. The package
made the incantation useless; this file concentrates it in the only place
where it stays necessary, as long as the repository is not installed
(`pip install -e .`) in the environment running pytest.
"""
import os
import sys

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

# The shared helpers live in `section_helpers.py`, importable because the tests
# folder enters sys.path too: a helper in conftest.py cannot be imported with
# `from conftest import …`, pytest loads it through another path.
TESTS = os.path.dirname(os.path.abspath(__file__))
if TESTS not in sys.path:
    sys.path.insert(0, TESTS)
