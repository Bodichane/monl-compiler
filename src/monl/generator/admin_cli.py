"""Generation of manage.py: offline account provisioning.

ADDED (beta 3, privilege-escalation fix). Roles not marked 'selfRegister'
can no longer be chosen at registration. A legitimate path to create those
accounts is therefore needed: this file, run by the operator on the
machine that hosts the database — owning the server becomes the condition
for obtaining a privileged role, instead of a mere anonymous HTTP call."""


from string import Template


class AdminCliMixin:
    def _generate_manage_cli(self):
        """Returns the source of manage.py for this application."""
        actors = ", ".join(repr(a) for a in self.actors)
        self_reg = ", ".join(repr(a) for a in self.self_register_actors)
        # POINT 95: manage.py must apply the SAME normalization as '/register'
        # and
        # '/login'. Without it, an account created offline as 'Patron@Ex.com'
        # would
        # be stored as is, and login — which does normalize — would look up
        # 'patron@ex.com': an account just created that nobody can log into.
        # The
        # form check, however, is NOT applied here: the administrator works on
        # the
        # machine that hosts the database, and sometimes provisions service
        # roles
        # ('monitoring', 'backup') that have neither an address nor a number.
        formes = self.auth_identifier or []
        prefixe = self.auth_phone_prefix
        password_invalidation = []
        if any(self.auth_features.get(name) for name in
               ("password_reset", "refresh_tokens", "lockout", "totp", "verify_email")):
            password_invalidation.append(Template(r'''    user_id = cur.execute("SELECT id FROM _monl_users WHERE username = ?", (_normalize_identifier(args.username),)).fetchone()[0]
''').substitute())
        if self.auth_features.get("password_reset"):
            password_invalidation.append(Template(r'''    cur.execute("UPDATE _monl_password_reset_tokens SET used_at = COALESCE(used_at, ?) WHERE user_id = ?", (datetime.datetime.now(datetime.timezone.utc).timestamp(), user_id))
''').substitute())
        if self.auth_features.get("refresh_tokens"):
            password_invalidation.append(Template(r'''    cur.execute("UPDATE _monl_refresh_tokens SET revoked_at = ? WHERE user_id = ? AND revoked_at IS NULL", (datetime.datetime.now(datetime.timezone.utc).timestamp(), user_id))
''').substitute())
        if self.auth_features.get("lockout"):
            password_invalidation.append(Template(r'''    cur.execute("UPDATE _monl_account_lockouts SET failed_count = 0, first_failed_at = ?, locked_until = NULL WHERE user_id = ?", (datetime.datetime.now(datetime.timezone.utc).timestamp(), user_id))
''').substitute())
        if self.auth_features:
            password_invalidation.append(Template(r'''    cur.execute("UPDATE _monl_users SET token_version = token_version + 1 WHERE id = ?", (user_id,))
''').substitute())
        totp_command = ""
        totp_function = ""
        totp_entry = ""
        if self.auth_features.get("totp"):
            totp_command = Template(r'''    python3 manage.py totp-reset <user>                 # revokes sessions
''').substitute()
            totp_function = Template(r'''
def cmd_totp_reset(args):
    conn = _connect()
    cur = conn.cursor()
    cur.execute("SELECT id FROM _monl_users WHERE username = ?", (_normalize_identifier(args.username),))
    if not cur.fetchone():
        conn.close()
        sys.exit(f"Account not found: {{args.username}}")
    cur.execute("UPDATE _monl_users SET totp_secret = NULL, totp_enabled = NULL, totp_last_step = NULL WHERE username = ?", (_normalize_identifier(args.username),))
${password_invalidation}    conn.commit()
    conn.close()
    print(f"✅ Two-factor authentication removed for '{{args.username}}'; sessions revoked.")


''').substitute(password_invalidation=''.join(password_invalidation))
            totp_entry = (
                Template(r'''    p = sub.add_parser("totp-reset", help="remove two-factor authentication and revoke sessions")
    p.add_argument("username")
    p.set_defaults(func=cmd_totp_reset)

''').substitute()
            )
        unlock_command = ""
        unlock_parser = ""
        if self.auth_features.get("lockout"):
            unlock_command = (
                Template(r'''    python3 manage.py unlock <user>                        # lifts a lockout
''').substitute()
            )
            unlock_parser = Template(r'''

def cmd_unlock(args):
    conn = _connect()
    cur = conn.cursor()
    username = _normalize_identifier(args.username)
    cur.execute("SELECT id FROM _monl_users WHERE username = ?", (username,))
    row = cur.fetchone()
    if not row:
        sys.exit(f"Account not found: {{args.username}}")
    now = datetime.datetime.now(datetime.timezone.utc).timestamp()
    cur.execute(
        "UPDATE _monl_account_lockouts SET failed_count = 0, first_failed_at = ?, "
        "locked_until = NULL WHERE user_id = ?",
        (now, row[0]),
    )
    conn.commit()
    print(f"✅ Lockout lifted for '{{args.username}}'.")
    conn.close()
''').substitute()
        unlock_parser_entry = ""
        if self.auth_features.get("lockout"):
            unlock_parser_entry = (
                Template(r'''    p = sub.add_parser("unlock", help="lift an account lockout")
    p.add_argument("username")
    p.set_defaults(func=cmd_unlock)

''').substitute()
            )
        return Template(r'''"""Offline administration of ${app_name} — generated by monl.

Roles open to self-registration (${self_register_description}) are created through
'POST /register'. Every other role is created HERE, on the machine that
hosts the database: this is the boundary that stops an anonymous client from
granting itself a privileged role.

    python3 manage.py adduser <user> <role>            # password prompted
    python3 manage.py setactor <user> <role>
    python3 manage.py passwd <user>
${totp_command}${unlock_command}    python3 manage.py users
    python3 manage.py revoke-all                       # invalidates sessions
"""
import argparse
import datetime
import getpass
import hashlib
import os
import re
import secrets
import sys

DB_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app.db")
VALID_ACTORS = [${actors}]
AUTH_IDENTIFIER_FORMS = ${identifier_forms}
AUTH_PHONE_PREFIX = ${phone_prefix}
_RE_PHONE = re.compile(r'^\+?[0-9][0-9 .\-()]{4,20}$$')


def _normalize_identifier(valeur):
    """SAME canonical form as '/register' and '/login' in the generated app.py.
    Diverging here creates accounts nobody can sign in to."""
    valeur = (valeur or "").strip()
    if not AUTH_IDENTIFIER_FORMS:
        return valeur
    if "@" in valeur:
        return valeur.lower()
    if _RE_PHONE.match(valeur):
        chiffres = "".join(c for c in valeur if c.isdigit())
        if valeur.lstrip().startswith("+"):
            return "+" + chiffres
        # POINT 138: a leading zero is not universal — see runtime.py.
        # These two functions MUST stay identical: diverging here creates an
        # account 'manage.py' can write and nobody can open.
        if AUTH_PHONE_PREFIX:
            if chiffres.startswith("0"):
                return AUTH_PHONE_PREFIX + chiffres[1:]
            if chiffres.startswith(AUTH_PHONE_PREFIX.lstrip("+")):
                return "+" + chiffres
            return AUTH_PHONE_PREFIX + chiffres
        return chiffres
    return valeur


SELF_REGISTER_ACTORS = [${self_register_actors}]
MIN_PASSWORD_LENGTH = 8


def _hash_password(password, salt_hex):
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), 100_000
    ).hex()


def _connect():
    """Opens the database, creating the schema if the application never started.

    The first account must be provisionable before the very first server
    start: otherwise an application with no self-registration role would have
    no way to get its first user.

    A1: the connection comes from the generated app.py, the only holder of the
    dialect choice (SQLite or PostgreSQL depending on MONL_DATABASE_URL).
    Without this sharing, manage.py would write to a different database than
    '/register' and '/login'. The import happens HERE and not at the top of the
    file: app.py reads '.jwt_secret' and 'schema.sql' relative to the current
    folder, so it can only be imported once placed in the project folder.
    Imported at the top, manage.py stopped working from any other folder —
    and it is the ONLY way to create an account with a privileged role.
    """
    dossier = os.path.dirname(DB_FILE)
    courant = os.getcwd()
    try:
        os.chdir(dossier)
        if dossier not in sys.path:
            sys.path.insert(0, dossier)
        from app import _connect as _database_connect
        from app import init_db as _init_db
        try:
            _init_db()
        except RuntimeError as erreur:
            # A2: a database waiting for a non-additive migration is not
            # served, and not administered either — writing accounts into a
            # pending schema would put them at the same risk. But app.py's
            # diagnosis has just been printed above: following it with a
            # fifteen-line traceback would drown it, and a traceback teaches
            # nothing to whoever must decide. Exit NAMING the remedy and the
            # folder, never on a traceback.
            sys.exit(f"{erreur}\n"
                     f"Remedy: declare the migration in the spec, then "
                     f"run 'monl migrate {dossier} --name <migration>'.")
        return _database_connect()
    finally:
        os.chdir(courant)


def _ask_password():
    pwd = getpass.getpass("Password: ")
    if len(pwd) < MIN_PASSWORD_LENGTH:
        sys.exit(f"Password too short ({MIN_PASSWORD_LENGTH} characters minimum).")
    if pwd != getpass.getpass("Confirm: "):
        sys.exit("The two entries differ.")
    return pwd


def _check_actor(actor):
    if actor not in VALID_ACTORS:
        sys.exit(f"Unknown role: {actor}. Declared roles: {VALID_ACTORS}")


def _unique_anon_handle(cur):
    for _ in range(50):
        candidate = f"Anon#{secrets.randbelow(9000) + 1000}"
        cur.execute("SELECT 1 FROM _monl_users WHERE anon_handle = ?", (candidate,))
        if not cur.fetchone():
            return candidate
    sys.exit("Unable to generate a unique pseudonym.")


def cmd_adduser(args):
    _check_actor(args.actor)
    conn = _connect()
    cur = conn.cursor()
    _identifiant = _normalize_identifier(args.username)
    cur.execute("SELECT 1 FROM _monl_users WHERE username = ?", (_identifiant,))
    if cur.fetchone():
        sys.exit(f"The account '{_identifiant}' already exists.")
    password = _ask_password()
    salt_hex = os.urandom(16).hex()
    cur.execute(
        "INSERT INTO _monl_users (username, password_hash, salt, actor, anon_handle) "
        "VALUES (?, ?, ?, ?, ?)",
        (_identifiant, _hash_password(password, salt_hex), salt_hex, args.actor,
         _unique_anon_handle(cur)),
    )
    conn.commit()
    print(f"✅ Account '{_identifiant}' created with the role '{args.actor}'.")
    conn.close()


def cmd_setactor(args):
    _check_actor(args.actor)
    conn = _connect()
    cur = conn.cursor()
    cur.execute("UPDATE _monl_users SET actor = ? WHERE username = ?", (args.actor, _normalize_identifier(args.username)))
    if cur.rowcount == 0:
        sys.exit(f"Account not found: {args.username}")
    conn.commit()
    print(
        f"✅ '{args.username}' now has the role '{args.actor}'. "
        "Tokens already issued keep the old role until they expire "
        "(revoke-all to invalidate them immediately)."
    )
    conn.close()


def cmd_passwd(args):
    conn = _connect()
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM _monl_users WHERE username = ?", (_normalize_identifier(args.username),))
    if not cur.fetchone():
        sys.exit(f"Account not found: {args.username}")
    password = _ask_password()
    salt_hex = os.urandom(16).hex()
    cur.execute(
        "UPDATE _monl_users SET password_hash = ?, salt = ? WHERE username = ?",
        (_hash_password(password, salt_hex), salt_hex,
         _normalize_identifier(args.username)),
    )
${password_invalidation}    conn.commit()
    print(f"✅ Password of '{args.username}' updated.")
    conn.close()


${totp_function}${unlock_parser}def cmd_users(_args):
    conn = _connect()
    cur = conn.cursor()
    cur.execute("SELECT id, username, actor FROM _monl_users ORDER BY id")
    rows = cur.fetchall()
    if not rows:
        print("No accounts.")
    for uid, username, actor in rows:
        libre = " (self-registered)" if actor in SELF_REGISTER_ACTORS else " (provisioned)"
        print(f"{uid:>4}  {username:<24} {actor}{libre}")
    conn.close()


def cmd_revoke_all(_args):
    """Invalidates every current session by changing the signing secret."""
    secret_path = os.path.join(os.path.dirname(DB_FILE), ".jwt_secret")
    if os.environ.get("MONL_JWT_SECRET"):
        sys.exit(
            "The secret comes from MONL_JWT_SECRET: change the environment "
            "variable, then restart the application."
        )
    fd = os.open(secret_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(secrets.token_hex(32))
    print("✅ New JWT secret written. Restart the application: every current "
          "session becomes invalid.")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("adduser", help="create an account with a given role")
    p.add_argument("username")
    p.add_argument("actor")
    p.set_defaults(func=cmd_adduser)

    p = sub.add_parser("setactor", help="change an account's role")
    p.add_argument("username")
    p.add_argument("actor")
    p.set_defaults(func=cmd_setactor)

    p = sub.add_parser("passwd", help="change an account's password")
    p.add_argument("username")
    p.set_defaults(func=cmd_passwd)

${totp_entry}${unlock_parser_entry}    sub.add_parser("users", help="list accounts").set_defaults(func=cmd_users)
    sub.add_parser("revoke-all", help="invalidate every session").set_defaults(func=cmd_revoke_all)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
''').substitute(app_name=self.app_name, self_register_description=self_reg or "none", totp_command=totp_command, unlock_command=unlock_command, actors=actors, identifier_forms=repr(formes), phone_prefix=repr(prefixe), self_register_actors=self_reg, password_invalidation=''.join(password_invalidation), totp_function=totp_function, unlock_parser=unlock_parser, totp_entry=totp_entry, unlock_parser_entry=unlock_parser_entry)
