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

NOM = "monl.plateforme"
journal = logging.getLogger(NOM)

# A field name that announces a secret. Compared in lowercase, by substring:
# `mot_de_passe`, `password`, `api_key`, `session_token` all fall into it.
NOMS_SENSIBLES = ("password", "mot_de_passe", "secret", "token", "jeton",
                  "key_raw", "cle_brute", "authorization", "cookie")

# A value that IS a secret, whatever the field's name. The platform's API keys
# start with `monl_`; session tokens are long URL-safe strings without spaces.
FORMES_SENSIBLES = re.compile(r"^(monl_[A-Za-z0-9_-]{8,}|[A-Za-z0-9_-]{32,})$")
FORMES_SENSIBLES_DANS_TEXTE = re.compile(
    r"(?<![A-Za-z0-9_-])(?:monl_[A-Za-z0-9_-]{8,}|[A-Za-z0-9_-]{32,})"
    r"(?![A-Za-z0-9_-])"
)
PARAMETRES_SENSIBLES = re.compile(
    r"((?:^|[?&\s])(?:token|jeton|access_token|refresh_token|api_key|apikey|secret|"
    r"password|mot_de_passe|authorization|cookie|session)(?:=|%3d))[^&#\s]+",
    re.IGNORECASE,
)
AUTHENTIFICATION_SENSIBLE = re.compile(r"((?:bearer|basic)\s+)[^\s]+", re.IGNORECASE)

MASQUE = "[masked]"


def court(identifiant: Any) -> str:
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
    texte = str(identifiant or "")
    return texte[:8] or "-"


def configurer(flux: Any = None) -> logging.Logger:
    """Arms the log once. Can be called again without side effects.

    The level comes from `MONL_LOG_LEVEL` (INFO by default). Output goes to
    standard error, which Docker, systemd and hosting providers all collect
    without configuration — a file would require a rotation nobody would
    write."""
    journal.setLevel(os.environ.get("MONL_LOG_LEVEL", "INFO").upper())
    if not journal.handlers:
        sortie = logging.StreamHandler(flux or sys.stderr)
        sortie.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)s %(message)s", datefmt="%Y-%m-%dT%H:%M:%S"))
        journal.addHandler(sortie)
    journal.propagate = False
    return journal


def _valeur(nom: str, valeur: Any) -> str:
    if any(motif in nom.lower() for motif in NOMS_SENSIBLES):
        return MASQUE
    texte = str(valeur)
    if FORMES_SENSIBLES.match(texte):
        return MASQUE
    texte = masquer_texte(texte)
    if any(c.isspace() for c in texte):
        return '"' + texte.replace('"', "'").replace("\n", " ") + '"'
    return texte or "-"


def masquer_texte(texte: Any) -> str:
    """Masks secrets in free output, notably a URL.

    A site's logs are not structured as ``field=value``: a token can
    therefore sit in the middle of a URL. This boundary reuses the same two
    guarantees as ``evenement`` — sensitive parameter name and sensitive value
    shape — before the CLI returns the text."""
    texte = str(texte)
    texte = PARAMETRES_SENSIBLES.sub(r"\1" + MASQUE, texte)
    texte = AUTHENTIFICATION_SENSIBLE.sub(r"\1" + MASQUE, texte)
    return FORMES_SENSIBLES_DANS_TEXTE.sub(MASQUE, texte)


def evenement(_nom: str, /, *, niveau: int = logging.INFO, **champs: Any) -> str:
    """Writes a `name key=value …` line and returns the emitted text.

    The return value exists for the tests: they check what COMES OUT, not
    what the caller believes it passed.

    The event name is **positional only** (`/`). Without it, a field called
    `nom=` — the most natural of all in French — collided with the parameter
    and raised a `TypeError` at the very moment one wants to log. Found by
    the test, not by rereading."""
    ligne = " ".join([_nom] + [f"{cle}={_valeur(cle, val)}"
                               for cle, val in champs.items() if val is not None])
    journal.log(niveau, ligne)
    return ligne


def anomalie(_nom: str, /, **champs: Any) -> str:
    return evenement(_nom, niveau=logging.WARNING, **champs)


def panne(_nom: str, /, **champs: Any) -> str:
    return evenement(_nom, niveau=logging.ERROR, **champs)
