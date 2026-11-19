"""`./monl`: the orchestrator, one module per subcommand.

The public surface did not move when it became a package. INTERNAL RULE
(point 153): a reference between modules goes through the MODULE object
(`emplacement._load_state(...)`), never through a bound name — so a test
writes `monkeypatch.setattr(cli.dispatch, "cmd_run", ...)` and not
`setattr(cli, ...)`, which would no longer bite."""

import subprocess

from ..serving import render_wrapper
from .coherence import check_coherence
from .construction import cmd_init, compile_project
from .consumption import _usage_total_line
from .coverage import _frontend_fetch_calls
from .delta import _report_delta, cmd_diff, cmd_update
from .dispatch import main
from .launch import cmd_run
from .location import _error_of_path, _load_state
from .nomenclature import DOCKERFILES_INHERITED, STATE_FILENAME
from .retouch import _arguments_inverses, _write_retouch_brief, cmd_retouch
from .signature import _contract_signature

__all__ = [
    "DOCKERFILES_INHERITED",
    "STATE_FILENAME",
    "_arguments_inverses",
    "_contract_signature",
    "_error_of_path",
    "_frontend_fetch_calls",
    "_load_state",
    "_report_delta",
    "_usage_total_line",
    "_write_retouch_brief",
    "check_coherence",
    "cmd_diff",
    "cmd_init",
    "cmd_retouch",
    "cmd_run",
    "cmd_update",
    "compile_project",
    "main",
    "render_wrapper",
    "subprocess",
]
