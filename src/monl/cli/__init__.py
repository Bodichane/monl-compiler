"""`./monl`: the orchestrator, one module per subcommand.

The public surface did not move when it became a package. INTERNAL RULE
(point 153): a reference between modules goes through the MODULE object
(`emplacement._load_state(...)`), never through a bound name — so a test
writes `monkeypatch.setattr(cli.dispatch, "cmd_run", ...)` and not
`setattr(cli, ...)`, which would no longer bite."""

import subprocess

from ..serving import rendre_wrapper
from .coherence import check_coherence
from .consommation import _usage_total_line
from .construction import cmd_init, compile_project
from .couverture import _frontend_fetch_calls
from .delta import _rapporter_delta, cmd_diff, cmd_update
from .dispatch import main
from .emplacement import _erreur_de_chemin, _load_state
from .lancement import cmd_run
from .nomenclature import DOCKERFILES_HERITES, STATE_FILENAME
from .retouche import _arguments_inverses, _write_retouche_brief, cmd_retouche
from .signature import _contract_signature

__all__ = [
    "DOCKERFILES_HERITES",
    "STATE_FILENAME",
    "_arguments_inverses",
    "_contract_signature",
    "_erreur_de_chemin",
    "_frontend_fetch_calls",
    "_load_state",
    "_rapporter_delta",
    "_usage_total_line",
    "_write_retouche_brief",
    "check_coherence",
    "cmd_diff",
    "cmd_init",
    "cmd_retouche",
    "cmd_run",
    "cmd_update",
    "compile_project",
    "main",
    "rendre_wrapper",
    "subprocess",
]
