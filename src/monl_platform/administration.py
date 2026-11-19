"""`monl-platform admin` — operational actions on accounts.

**Why a command line and not a web panel.** Every intervention on an
account went through `sqlite3` by hand, with the server stopped: workable
at ten accounts, not at a hundred, and each action risked a mistyped
query, with no trace of who made it. A web panel would have required its
own authentication, a privilege column in `users`, and would have become
the service's most interesting target — the one where a single flaw gives
away every account.

Yet **whoever owns the shell already owns the database**. The command
line therefore adds no attack surface: it makes safe and traceable actions
that were already done, only worse.

**Every action that writes is logged**, with the same log as the server.
Without it, "who deleted this account?" has no answer — and that is
precisely the question asked the day things go wrong.

**Nothing is asked twice, except what cannot be undone.** Deleting an
account requires `--confirmer`: it erases the account, its keys, its
projects in the database and the folders on disk, with nothing that can
be given back."""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timezone

from .builder_runtime import create_runtime
from .deletion import supprimer_compte
from .hosting import SITE_LOG_MAX_BYTES, SiteHostingError, site_log_path
from .identity import IdentityStore
from .journal import configurer, court, evenement, masquer_texte
from .paths import ProjectPathError
from .service import CompilationService

JOUR = 24 * 3600


def _date(instant: int | None) -> str:
    if not instant:
        return "—"
    return datetime.fromtimestamp(instant, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")


def _echeance(instant: int | None) -> str:
    """The date, and above all what it means today.

    A column of dates alone forces one to subtract in one's head, on the very
    line where one decides whether to extend. The word "expired" reads at a
    glance."""
    if instant is None:
        return "never"
    reste = instant - int(time.time())
    if reste <= 0:
        return f"{_date(instant)} (expired)"
    return f"{_date(instant)} (in {reste // JOUR} d)"


def _magasin(workspace):
    service = CompilationService(workspace)
    return service, IdentityStore(service.workspace)


def _compte_ou_sortir(magasin: IdentityStore, adresse: str) -> dict:
    compte = magasin.compte_par_adresse(adresse)
    if not compte:
        print(f"No account for {adresse!r}.", file=sys.stderr)
        raise SystemExit(1)
    return compte


# ---------------------------------------------------------------------------
# Lectures
# ---------------------------------------------------------------------------

def _comptes(magasin: IdentityStore, _service, args) -> int:
    lignes = magasin.comptes()
    if not lignes:
        print("No accounts.")
        return 0
    print(f"{'ADDRESS':38s} {'CREATED':17s} {'PROJECTS':>7s} {'KEYS':>5s} {'CODES':>6s}")
    for ligne in lignes:
        print(f"{ligne['email'][:38]:38s} {_date(ligne['created_at']):17s} "
              f"{ligne['projets']:>7d} {ligne['cles']:>5d} {ligne['codes']:>6d}")
    manquants = [ligne["email"] for ligne in lignes if ligne["codes"] == 0]
    if manquants:
        # An account without codes has NO way to recover from a lost password.
        # It is the only column of this table that announces a coming data
        # loss: it is repeated in plain words.
        print(f"\n{len(manquants)} account(s) without recovery codes: "
              f"a lost password would be final there.")
    return 0


def _compte(magasin: IdentityStore, _service, args) -> int:
    compte = _compte_ou_sortir(magasin, args.email)
    print(f"Account  {compte['email']}")
    print(f"         {compte['id']}")
    print(f"Recovery codes left: {magasin.count_recovery_codes(compte['id'])}")

    projets = magasin.tous_les_projets(compte["id"])
    print(f"\nProjects ({len(projets)})")
    for projet in projets:
        print(f"  {projet['project_id']}  {projet['name'][:30]:30s} "
              f"{_echeance(projet['expires_at'])}")

    cles = magasin.cles_du_compte(compte["id"])
    vivantes = [cle for cle in cles if not cle["revoked_at"]]
    print(f"\nAPI keys ({len(vivantes)} active of {len(cles)})")
    for cle in cles:
        etat = "revoked" if cle["revoked_at"] else "active"
        print(f"  {cle['id']}  {cle['prefix']}…  {cle['name'][:24]:24s} {etat:9s} "
              f"last used {_date(cle['last_used_at'])}")
    return 0


def _projets(magasin: IdentityStore, _service, args) -> int:
    compte = _compte_ou_sortir(magasin, args.compte) if args.compte else None
    projets = magasin.tous_les_projets(compte["id"] if compte else None)
    if not projets:
        print("No projects.")
        return 0
    print(f"{'IDENTIFIER':34s} {'ACCOUNT':28s} {'NAME':22s} EXPIRES")
    for projet in projets:
        print(f"{projet['project_id']:34s} {projet['email'][:28]:28s} "
              f"{projet['name'][:22]:22s} {_echeance(projet['expires_at'])}")
    return 0


def _journal(magasin: IdentityStore, service: CompilationService, args) -> int:
    """Reads a site's output from the shell, after masking secrets."""
    projet = next(
        (ligne for ligne in magasin.tous_les_projets()
         if ligne["project_id"] == args.projet),
        None,
    )
    if projet is None:
        print(f"No project {args.projet!r}.", file=sys.stderr)
        return 1
    try:
        chemin = site_log_path(service.workspace, projet)
    except (ProjectPathError, SiteHostingError) as exc:
        print(f"Unreadable log: {exc}", file=sys.stderr)
        return 1
    if chemin.is_symlink():
        print("Unreadable log: the file is a symbolic link.", file=sys.stderr)
        return 1
    if not chemin.is_file():
        evenement("journal_site_lu_par_exploitant", projet=court(args.projet), octets=0)
        print(f"No log for project {args.projet}.")
        return 0

    brut = chemin.read_bytes()[:SITE_LOG_MAX_BYTES].decode("utf-8", errors="replace")
    evenement("journal_site_lu_par_exploitant", projet=court(args.projet),
              octets=len(brut.encode("utf-8")))
    rendu = masquer_texte(brut)
    print(rendu, end="" if rendu.endswith("\n") else "\n")
    return 0


# ---------------------------------------------------------------------------
# Writes — all logged
# ---------------------------------------------------------------------------

def _codes(magasin: IdentityStore, _service, args) -> int:
    """The troubleshooting action: someone lost their password AND their codes.

    It is the most powerful command of the set — it gives access to the
    account. It is logged for that precise reason: an account takeover by the
    operator must leave a trace that can be reread afterwards."""
    compte = _compte_ou_sortir(magasin, args.email)
    codes = magasin.create_recovery_codes(compte["id"], revoke_access=True)
    evenement("codes_regeneres_par_exploitant", compte=court(compte["id"]))
    print(f"New set for {compte['email']} — the old one no longer works.")
    print("All sessions are deleted and all MCP keys are revoked.")
    print("These codes will never be shown again:\n")
    for code in codes:
        print(f"  {code}")
    return 0


def _prolonger(magasin: IdentityStore, _service, args) -> int:
    secondes = None if args.jamais else args.jours * JOUR
    if not magasin.deplacer_echeance(args.projet, secondes):
        print(f"No project {args.projet!r}.", file=sys.stderr)
        return 1
    evenement("echeance_deplacee", projet=court(args.projet),
              jours=None if args.jamais else args.jours)
    quand = "never" if args.jamais else f"in {args.jours} days"
    print(f"Project {args.projet}: expires {quand}.")
    return 0


def _expirer(magasin: IdentityStore, _service, args) -> int:
    """Expires without erasing: the purge will clean up.

    Erasing here would duplicate the deletion path, and two paths end up
    diverging — the one taken least being the one that breaks."""
    if not magasin.deplacer_echeance(args.projet, -1):
        print(f"No project {args.projet!r}.", file=sys.stderr)
        return 1
    evenement("projet_expire_par_exploitant", projet=court(args.projet))
    print(f"Project {args.projet} marked expired. The purge will remove it on its next run.")
    return 0


def _revoquer(magasin: IdentityStore, _service, args) -> int:
    cle = magasin.revoquer_cle_par_id(args.cle)
    if not cle:
        print(f"No active key {args.cle!r}.", file=sys.stderr)
        return 1
    evenement("cle_revoquee_par_exploitant", cle=court(args.cle))
    print(f"Key {cle['name']!r} of {cle['email']} revoked.")
    return 0


def _supprimer(magasin: IdentityStore, service: CompilationService, args) -> int:
    compte = _compte_ou_sortir(magasin, args.email)
    if not args.confirmer:
        projets = magasin.tous_les_projets(compte["id"])
        print(f"{compte['email']} — {len(projets)} project(s), "
              f"{len(magasin.cles_du_compte(compte['id']))} key(s).")
        print("Nothing was done. Add --confirmer to permanently erase "
              "the account, its keys, its projects and their files.")
        return 1
    runtime = create_runtime(service, magasin)
    projets = supprimer_compte(runtime, compte["id"])
    effaces = len(projets)
    evenement("compte_supprime_par_exploitant", compte=court(compte["id"]),
              projets=len(projets), dossiers=effaces)
    print(f"{compte['email']} deleted — {len(projets)} project(s) in the database, "
          f"{effaces} folder(s) on disk.")
    return 0


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

def construire_parseur() -> argparse.ArgumentParser:
    parseur = argparse.ArgumentParser(
        prog="monl-platform admin",
        description="Operator actions on accounts and projects.")
    # `--workspace` is declared TWICE: on the main parser and on each sub-verb,
    # through a shared parent. Found by running it — argparse only accepts a
    # top-level option BEFORE the sub-verb, whereas one naturally types it at
    # the end. Refusing the command because of an argument's position makes
    # people look for a mistake where there is none.
    commun = argparse.ArgumentParser(add_help=False)
    # `SUPPRESS` and not `None`: with an ordinary default, the sub-parser
    # overwrites the value given BEFORE the sub-verb with its own default, and
    # `admin --workspace X comptes` stops working. Fixing one position by
    # breaking the other is not a fix.
    commun.add_argument("--workspace", default=argparse.SUPPRESS,
                        help="Workspace (default: MONL_PLATFORM_WORKSPACE).")
    parseur.add_argument("--workspace", default=None, help=argparse.SUPPRESS)
    sous = parseur.add_subparsers(dest="geste", required=True)

    sous.add_parser("accounts", aliases=["comptes"], parents=[commun],
                    help="List all accounts.").set_defaults(faire=_comptes)

    detail = sous.add_parser(
"account", aliases=["compte"], parents=[commun],
        help="Account details: projects and keys.")
    detail.add_argument("email")
    detail.set_defaults(faire=_compte)

    liste = sous.add_parser(
"projects", aliases=["projets"], parents=[commun], help="List projects.")
    liste.add_argument("--account", "--compte", dest="compte", default=None,
                       metavar="EMAIL")
    liste.set_defaults(faire=_projets)

    journal = sous.add_parser(
        "log", aliases=["journal", "journaux"], parents=[commun],
        help="Read the site output from the shell.")
    journal.add_argument("projet")
    journal.set_defaults(faire=_journal)

    codes = sous.add_parser(
"codes", parents=[commun], help="New set of recovery codes for a locked-out account.")
    codes.add_argument("email")
    codes.set_defaults(faire=_codes)

    prolonger = sous.add_parser(
"extend", aliases=["prolonger"], parents=[commun],
        help="Push back a project's expiry.")
    prolonger.add_argument("projet")
    prolonger.add_argument("--days", "--jours", dest="jours", type=int, default=30)
    prolonger.add_argument("--never", "--jamais", dest="jamais", action="store_true",
                           help="The project no longer expires.")
    prolonger.set_defaults(faire=_prolonger)

    expirer = sous.add_parser(
"expire", aliases=["expirer"], parents=[commun],
        help="Mark a project expired; the purge will clean it up.")
    expirer.add_argument("projet")
    expirer.set_defaults(faire=_expirer)

    revoquer = sous.add_parser(
"revoke-key", aliases=["revoquer-cle"], parents=[commun],
        help="Revoke an API key by its identifier.")
    revoquer.add_argument("cle")
    revoquer.set_defaults(faire=_revoquer)

    supprimer = sous.add_parser(
"delete-account", aliases=["supprimer-compte"], parents=[commun],
        help="Erase an account and everything that belongs to it.")
    supprimer.add_argument("email")
    supprimer.add_argument("--confirm", "--confirmer", dest="confirmer",
                           action="store_true")
    supprimer.set_defaults(faire=_supprimer)

    return parseur


def main(argv: list[str]) -> int:
    configurer()
    args = construire_parseur().parse_args(argv)
    service, magasin = _magasin(args.workspace)
    return args.faire(magasin, service, args)
