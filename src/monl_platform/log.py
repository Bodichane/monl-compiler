"""The platform's operations log.

Without it, an incident leaves nothing to read: the platform stores
accounts and API keys, and nothing said who logged in, which key was
used, or why a compilation failed.

**The log CANNOT write a secret.** That is the decision this module
carries: `evenement()` masks any value whose NAME announces a secret, and
any value whose SHAPE is one (a `monl_…` key, a high-entropy token).
Relying on the discipline of each call site would have been enough until
the day someone logs `mot_de_passe=` for convenience — it is the same
logic as the SQL emission boundary of point 108: make the fault impossible
rather than recommend against it."""

from __future__ import annotations

import logging
import os
import re
import sys
from typing import Any

NAME = "monl.plateforme"
log = logging.getLogger(NAME)

# A field name that announces a secret. Compared in lowercase, by substring:
# `mot_de_passe`, `password`, `api_key`, `session_token` all fall into it.
NAMES_SENSITIVE = ("password", "mot_de_passe", "secret", "token", "jeton",
                  "key_raw", "cle_brute", "authorization", "cookie")

# A value that IS a secret, whatever the field's name. The platform's API keys
# start with `monl_`; session tokens are long URL-safe strings without spaces.
FORMES_SENSIBLES = re.compile(r"^(monl_[A-Za-z0-9_-]{8,}|[A-Za-z0-9_-]{32,})$")
SHAPES_SENSITIVE_IN_TEXT = re.compile(
    r"(?<![A-Za-z0-9_-])(?:monl_[A-Za-z0-9_-]{8,}|[A-Za-z0-9_-]{32,})"
    r"(?![A-Za-z0-9_-])"
)
PARAMETERS_SENSITIVE = re.compile(
    r"((?:^|[?&\s])(?:token|jeton|access_token|refresh_token|api_key|apikey|secret|"
    r"password|mot_de_passe|authorization|cookie|session)(?:=|%3d))[^&#\s]+",
    re.IGNORECASE,
)
AUTHENTICATION_SENSIBLE = re.compile(r"((?:bearer|basic)\s+)[^\s]+", re.IGNORECASE)

MASQUE = "[masked]"


def short(identifier: Any) -> str:
    """The prefix of an identifier, long enough to correlate, too short to look
    like a secret.

    Found by running, not by rereading: an account identifier is a
    32-character `uuid4().hex`, so `FORMES_SENSIBLES` swallowed it and the log
    wrote `compte=[masqué]` on EVERY line. A log that masks the account no
    longer says whether two hundred refused logins come from one account or
    two hundred — that is, it is no longer of any use.

    The remedy does NOT touch masking — weakening it with a list of exempted
    names would reopen exactly the hole this module closes. It is what is
    PASSED TO IT that changes: eight characters are enough to correlate lines
    with one another, and reconstruct no token."""
    text = str(identifier or "")
    return text[:8] or "-"


def configure(flux: Any = None) -> logging.Logger:
    """Arms the log once. Can be called again without side effects.

    The level comes from `MONL_LOG_LEVEL` (INFO by default). Output goes to
    standard error, which Docker, systemd and hosting providers all collect
    without configuration — a file would require a rotation nobody would
    write."""
    log.setLevel(os.environ.get("MONL_LOG_LEVEL", "INFO").upper())
    if not log.handlers:
        output = logging.StreamHandler(flux or sys.stderr)
        output.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)s %(message)s", datefmt="%Y-%m-%dT%H:%M:%S"))
        log.addHandler(output)
    log.propagate = False
    return log


def _value(name: str, valeur: Any) -> str:
    if any(motif in name.lower() for motif in NAMES_SENSITIVE):
        return MASQUE
    text = str(valeur)
    if FORMES_SENSIBLES.match(text):
        return MASQUE
    text = hide_text(text)
    if any(c.isspace() for c in text):
        return '"' + text.replace('"', "'").replace("\n", " ") + '"'
    return text or "-"


def hide_text(text: Any) -> str:
    """Masks secrets in free output, notably a URL.

    A site's logs are not structured as ``field=value``: a token can
    therefore sit in the middle of a URL. This boundary reuses the same two
    guarantees as ``evenement`` — sensitive parameter name and sensitive value
    shape — before the CLI returns the text."""
    text = str(text)
    text = PARAMETERS_SENSITIVE.sub(r"\1" + MASQUE, text)
    text = AUTHENTICATION_SENSIBLE.sub(r"\1" + MASQUE, text)
    return SHAPES_SENSITIVE_IN_TEXT.sub(MASQUE, text)


def event(_name: str, /, *, level: int = logging.INFO, **fields: Any) -> str:
    """Writes a `name key=value …` line and returns the emitted text.

    The return value exists for the tests: they check what COMES OUT, not
    what the caller believes it passed.

    The event name is **positional only** (`/`). Without it, a field called
    `nom=` — the most natural of all in French — collided with the parameter
    and raised a `TypeError` at the very moment one wants to log. Found by
    the test, not by rereading."""
    line = " ".join([_name] + [f"{key}={_value(key, val)}"
                               for key, val in fields.items() if val is not None])
    log.log(level, line)
    return line


def anomaly(_name: str, /, **fields: Any) -> str:
    return event(_name, level=logging.WARNING, **fields)


def failure(_name: str, /, **fields: Any) -> str:
    return event(_name, level=logging.ERROR, **fields)
