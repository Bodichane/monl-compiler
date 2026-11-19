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
from .deletion import delete_account
from .hosting import SITE_LOG_MAX_BYTES, SiteHostingError, site_log_path
from .identity import IdentityStore
from .log import configure, event, hide_text, short
from .paths import ProjectPathError
from .service import CompilationService

DAY = 24 * 3600


def _date(instant: int | None) -> str:
    if not instant:
        return "—"
    return datetime.fromtimestamp(instant, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")


def _deadline(instant: int | None) -> str:
    """The date, and above all what it means today.

    A column of dates alone forces one to subtract in one's head, on the very
    line where one decides whether to extend. The word "expired" reads at a
    glance."""
    if instant is None:
        return "never"
    reste = instant - int(time.time())
    if reste <= 0:
        return f"{_date(instant)} (expired)"
    return f"{_date(instant)} (in {reste // DAY} d)"


def _store(workspace):
    service = CompilationService(workspace)
    return service, IdentityStore(service.workspace)


def _account_ou_exit(store: IdentityStore, address: str) -> dict:
    account = store.account_by_address(address)
    if not account:
        print(f"No account for {address!r}.", file=sys.stderr)
        raise SystemExit(1)
    return account


# ---------------------------------------------------------------------------
# Lectures
# ---------------------------------------------------------------------------

def _accounts(store: IdentityStore, _service, args) -> int:
    lines = store.accounts()
    if not lines:
        print("No accounts.")
        return 0
    print(f"{'ADDRESS':38s} {'CREATED':17s} {'PROJECTS':>7s} {'KEYS':>5s} {'CODES':>6s}")
    for line in lines:
        print(f"{line['email'][:38]:38s} {_date(line['created_at']):17s} "
              f"{line['projets']:>7d} {line['cles']:>5d} {line['codes']:>6d}")
    missing = [line["email"] for line in lines if line["codes"] == 0]
    if missing:
        # An account without codes has NO way to recover from a lost password.
        # It is the only column of this table that announces a coming data
        # loss: it is repeated in plain words.
        print(f"\n{len(missing)} account(s) without recovery codes: "
              f"a lost password would be final there.")
    return 0


def _account(store: IdentityStore, _service, args) -> int:
    account = _account_ou_exit(store, args.email)
    print(f"Account  {account['email']}")
    print(f"         {account['id']}")
    print(f"Recovery codes left: {store.count_recovery_codes(account['id'])}")

    projects = store.all_the_projects(account["id"])
    print(f"\nProjects ({len(projects)})")
    for project in projects:
        print(f"  {project['project_id']}  {project['name'][:30]:30s} "
              f"{_deadline(project['expires_at'])}")

    keys = store.keys_of_account(account["id"])
    live = [key for key in keys if not key["revoked_at"]]
    print(f"\nAPI keys ({len(live)} active of {len(keys)})")
    for key in keys:
        state = "revoked" if key["revoked_at"] else "active"
        print(f"  {key['id']}  {key['prefix']}…  {key['name'][:24]:24s} {state:9s} "
              f"last used {_date(key['last_used_at'])}")
    return 0


def _projects(store: IdentityStore, _service, args) -> int:
    account = _account_ou_exit(store, args.compte) if args.compte else None
    projects = store.all_the_projects(account["id"] if account else None)
    if not projects:
        print("No projects.")
        return 0
    print(f"{'IDENTIFIER':34s} {'ACCOUNT':28s} {'NAME':22s} EXPIRES")
    for project in projects:
        print(f"{project['project_id']:34s} {project['email'][:28]:28s} "
              f"{project['name'][:22]:22s} {_deadline(project['expires_at'])}")
    return 0


def _log(store: IdentityStore, service: CompilationService, args) -> int:
    """Reads a site's output from the shell, after masking secrets."""
    project = next(
        (line for line in store.all_the_projects()
         if line["project_id"] == args.projet),
        None,
    )
    if project is None:
        print(f"No project {args.projet!r}.", file=sys.stderr)
        return 1
    try:
        path = site_log_path(service.workspace, project)
    except (ProjectPathError, SiteHostingError) as exc:
        print(f"Unreadable log: {exc}", file=sys.stderr)
        return 1
    if path.is_symlink():
        print("Unreadable log: the file is a symbolic link.", file=sys.stderr)
        return 1
    if not path.is_file():
        event("journal_site_lu_par_exploitant", projet=short(args.projet), octets=0)
        print(f"No log for project {args.projet}.")
        return 0

    brut = path.read_bytes()[:SITE_LOG_MAX_BYTES].decode("utf-8", errors="replace")
    event("journal_site_lu_par_exploitant", projet=short(args.projet),
              octets=len(brut.encode("utf-8")))
    rendered = hide_text(brut)
    print(rendered, end="" if rendered.endswith("\n") else "\n")
    return 0


# ---------------------------------------------------------------------------
# Writes — all logged
# ---------------------------------------------------------------------------

def _codes(store: IdentityStore, _service, args) -> int:
    """The troubleshooting action: someone lost their password AND their codes.

    It is the most powerful command of the set — it gives access to the
    account. It is logged for that precise reason: an account takeover by the
    operator must leave a trace that can be reread afterwards."""
    account = _account_ou_exit(store, args.email)
    codes = store.create_recovery_codes(account["id"], revoke_access=True)
    event("codes_regeneres_par_exploitant", compte=short(account["id"]))
    print(f"New set for {account['email']} — the old one no longer works.")
    print("All sessions are deleted and all MCP keys are revoked.")
    print("These codes will never be shown again:\n")
    for code in codes:
        print(f"  {code}")
    return 0


def _extend(store: IdentityStore, _service, args) -> int:
    secondes = None if args.jamais else args.jours * DAY
    if not store.move_deadline(args.projet, secondes):
        print(f"No project {args.projet!r}.", file=sys.stderr)
        return 1
    event("echeance_deplacee", projet=short(args.projet),
              jours=None if args.jamais else args.jours)
    quand = "never" if args.jamais else f"in {args.jours} days"
    print(f"Project {args.projet}: expires {quand}.")
    return 0


def _expire(store: IdentityStore, _service, args) -> int:
    """Expires without erasing: the purge will clean up.

    Erasing here would duplicate the deletion path, and two paths end up
    diverging — the one taken least being the one that breaks."""
    if not store.move_deadline(args.projet, -1):
        print(f"No project {args.projet!r}.", file=sys.stderr)
        return 1
    event("projet_expire_par_exploitant", projet=short(args.projet))
    print(f"Project {args.projet} marked expired. The purge will remove it on its next run.")
    return 0


def _revoke(store: IdentityStore, _service, args) -> int:
    key = store.revoke_key_by_id(args.cle)
    if not key:
        print(f"No active key {args.cle!r}.", file=sys.stderr)
        return 1
    event("cle_revoquee_par_exploitant", cle=short(args.cle))
    print(f"Key {key['name']!r} of {key['email']} revoked.")
    return 0


def _delete(store: IdentityStore, service: CompilationService, args) -> int:
    account = _account_ou_exit(store, args.email)
    if not args.confirmer:
        projects = store.all_the_projects(account["id"])
        print(f"{account['email']} — {len(projects)} project(s), "
              f"{len(store.keys_of_account(account['id']))} key(s).")
        print("Nothing was done. Add --confirmer to permanently erase "
              "the account, its keys, its projects and their files.")
        return 1
    runtime = create_runtime(service, store)
    projects = delete_account(runtime, account["id"])
    effaces = len(projects)
    event("compte_supprime_par_exploitant", compte=short(account["id"]),
              projets=len(projects), dossiers=effaces)
    print(f"{account['email']} deleted — {len(projects)} project(s) in the database, "
          f"{effaces} folder(s) on disk.")
    return 0


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="monl-platform admin",
        description="Operator actions on accounts and projects.")
    # `--workspace` is declared TWICE: on the main parser and on each sub-verb,
    # through a shared parent. Found by running it — argparse only accepts a
    # top-level option BEFORE the sub-verb, whereas one naturally types it at
    # the end. Refusing the command because of an argument's position makes
    # people look for a mistake where there is none.
    common = argparse.ArgumentParser(add_help=False)
    # `SUPPRESS` and not `None`: with an ordinary default, the sub-parser
    # overwrites the value given BEFORE the sub-verb with its own default, and
    # `admin --workspace X comptes` stops working. Fixing one position by
    # breaking the other is not a fix.
    common.add_argument("--workspace", default=argparse.SUPPRESS,
                        help="Workspace (default: MONL_PLATFORM_WORKSPACE).")
    parser.add_argument("--workspace", default=None, help=argparse.SUPPRESS)
    sous = parser.add_subparsers(dest="geste", required=True)

    sous.add_parser("accounts", aliases=["comptes"], parents=[common],
                    help="List all accounts.").set_defaults(faire=_accounts)

    detail = sous.add_parser(
"account", aliases=["compte"], parents=[common],
        help="Account details: projects and keys.")
    detail.add_argument("email")
    detail.set_defaults(faire=_account)

    list_ = sous.add_parser(
"projects", aliases=["projets"], parents=[common], help="List projects.")
    list_.add_argument("--account", "--compte", dest="compte", default=None,
                       metavar="EMAIL")
    list_.set_defaults(faire=_projects)

    log = sous.add_parser(
        "log", aliases=["journal", "journaux"], parents=[common],
        help="Read the site output from the shell.")
    log.add_argument("projet")
    log.set_defaults(faire=_log)

    codes = sous.add_parser(
"codes", parents=[common], help="New set of recovery codes for a locked-out account.")
    codes.add_argument("email")
    codes.set_defaults(faire=_codes)

    extend = sous.add_parser(
"extend", aliases=["prolonger"], parents=[common],
        help="Push back a project's expiry.")
    extend.add_argument("projet")
    extend.add_argument("--days", "--jours", dest="jours", type=int, default=30)
    extend.add_argument("--never", "--jamais", dest="jamais", action="store_true",
                           help="The project no longer expires.")
    extend.set_defaults(faire=_extend)

    expire = sous.add_parser(
"expire", aliases=["expirer"], parents=[common],
        help="Mark a project expired; the purge will clean it up.")
    expire.add_argument("projet")
    expire.set_defaults(faire=_expire)

    revoke = sous.add_parser(
"revoke-key", aliases=["revoquer-cle"], parents=[common],
        help="Revoke an API key by its identifier.")
    revoke.add_argument("cle")
    revoke.set_defaults(faire=_revoke)

    delete = sous.add_parser(
"delete-account", aliases=["supprimer-compte"], parents=[common],
        help="Erase an account and everything that belongs to it.")
    delete.add_argument("email")
    delete.add_argument("--confirm", "--confirmer", dest="confirmer",
                           action="store_true")
    delete.set_defaults(faire=_delete)

    return parser


def main(argv: list[str]) -> int:
    configure()
    args = build_parser().parse_args(argv)
    service, store = _store(args.workspace)
    return args.faire(store, service, args)
