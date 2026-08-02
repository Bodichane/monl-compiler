"""Génération de manage.py : provisionnement hors ligne des comptes.

AJOUT (bêta 3, correctif d'élévation de privilège). Les rôles non marqués
'selfRegister' ne peuvent plus être choisis à l'inscription. Il faut donc un
chemin légitime pour créer ces comptes : c'est ce fichier, exécuté par
l'opérateur sur la machine qui héberge la base — la possession du serveur
devient la condition d'obtention d'un rôle privilégié, au lieu d'un simple
appel HTTP anonyme.
"""


class AdminCliMixin:
    def _generate_manage_cli(self):
        """Retourne le source de manage.py pour cette application."""
        actors = ", ".join(repr(a) for a in self.actors)
        self_reg = ", ".join(repr(a) for a in self.self_register_actors)
        # POINT 95 : manage.py doit appliquer la MÊME normalisation que
        # '/register' et '/login'. Sans elle, un compte créé hors ligne avec
        # 'Patron@Ex.com' serait stocké tel quel, et la connexion — qui
        # normalise, elle — chercherait 'patron@ex.com' : un compte qu'on vient
        # de créer et auquel on ne peut pas se connecter. Le contrôle de forme,
        # en revanche, n'est PAS appliqué ici : l'administrateur travaille sur
        # la machine qui héberge la base, et provisionne parfois des rôles de
        # service ('supervision', 'sauvegarde') qui n'ont ni adresse ni numéro.
        formes = self.auth_identifier or []
        prefixe = self.auth_phone_prefix
        return f'''"""Administration hors ligne de {self.app_name} — généré par monl.

Les rôles ouverts à l'inscription libre ({self_reg or "aucun"}) se créent par
'POST /register'. Tous les autres rôles se créent ICI, sur la machine qui
héberge la base : c'est la frontière qui empêche un client anonyme de
s'attribuer un rôle privilégié.

    python3 manage.py adduser <utilisateur> <role>     # mot de passe demandé
    python3 manage.py setactor <utilisateur> <role>
    python3 manage.py passwd <utilisateur>
    python3 manage.py users
    python3 manage.py revoke-all                       # invalide les sessions
"""
import argparse
import datetime
import getpass
import hashlib
import os
import re
import secrets
import sqlite3
import sys

DB_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app.db")
VALID_ACTORS = [{actors}]
AUTH_IDENTIFIER_FORMS = {formes!r}
AUTH_PHONE_PREFIX = {prefixe!r}
_RE_PHONE = re.compile(r'^\\+?[0-9][0-9 .\\-()]{{4,20}}$')


def _normalize_identifier(valeur):
    """MÊME forme canonique que '/register' et '/login' du app.py généré.
    Diverger ici crée des comptes auxquels on ne peut pas se connecter."""
    valeur = (valeur or "").strip()
    if not AUTH_IDENTIFIER_FORMS:
        return valeur
    if "@" in valeur:
        return valeur.lower()
    if _RE_PHONE.match(valeur):
        chiffres = "".join(c for c in valeur if c.isdigit())
        if valeur.lstrip().startswith("+"):
            return "+" + chiffres
        if AUTH_PHONE_PREFIX and chiffres.startswith("0"):
            return AUTH_PHONE_PREFIX + chiffres[1:]
        return chiffres
    return valeur


SELF_REGISTER_ACTORS = [{self_reg}]
MIN_PASSWORD_LENGTH = 8


def _hash_password(password, salt_hex):
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), 100_000
    ).hex()


def _connect():
    """Ouvre la base, en créant le schéma si l'application n'a jamais démarré.

    Le premier compte doit pouvoir être provisionné avant le tout premier
    lancement du serveur : sans cela, une application sans rôle en inscription
    libre n'aurait aucun moyen d'obtenir son premier utilisateur.
    """
    schema_path = os.path.join(os.path.dirname(DB_FILE), "schema.sql")
    fresh = not os.path.exists(DB_FILE)
    conn = sqlite3.connect(DB_FILE, timeout=10.0)
    if fresh:
        if not os.path.exists(schema_path):
            sys.exit("Ni 'app.db' ni 'schema.sql' : lancez d'abord la compilation monl.")
        with open(schema_path, encoding="utf-8") as f:
            conn.executescript(f.read())
        conn.commit()
        print("🗄️  Base initialisée depuis schema.sql.")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _ask_password():
    pwd = getpass.getpass("Mot de passe : ")
    if len(pwd) < MIN_PASSWORD_LENGTH:
        sys.exit(f"Mot de passe trop court ({{MIN_PASSWORD_LENGTH}} caractères minimum).")
    if pwd != getpass.getpass("Confirmation : "):
        sys.exit("Les deux saisies diffèrent.")
    return pwd


def _check_actor(actor):
    if actor not in VALID_ACTORS:
        sys.exit(f"Rôle inconnu : {{actor}}. Rôles déclarés : {{VALID_ACTORS}}")


def _unique_anon_handle(cur):
    for _ in range(50):
        candidate = f"Anon#{{secrets.randbelow(9000) + 1000}}"
        cur.execute("SELECT 1 FROM _monl_users WHERE anon_handle = ?", (candidate,))
        if not cur.fetchone():
            return candidate
    sys.exit("Impossible de générer un pseudonyme unique.")


def cmd_adduser(args):
    _check_actor(args.actor)
    conn = _connect()
    cur = conn.cursor()
    _identifiant = _normalize_identifier(args.username)
    cur.execute("SELECT 1 FROM _monl_users WHERE username = ?", (_identifiant,))
    if cur.fetchone():
        sys.exit(f"Le compte '{{_identifiant}}' existe déjà.")
    password = _ask_password()
    salt_hex = os.urandom(16).hex()
    cur.execute(
        "INSERT INTO _monl_users (username, password_hash, salt, actor, anon_handle) "
        "VALUES (?, ?, ?, ?, ?)",
        (_identifiant, _hash_password(password, salt_hex), salt_hex, args.actor,
         _unique_anon_handle(cur)),
    )
    conn.commit()
    print(f"✅ Compte '{{_identifiant}}' créé avec le rôle '{{args.actor}}'.")
    conn.close()


def cmd_setactor(args):
    _check_actor(args.actor)
    conn = _connect()
    cur = conn.cursor()
    cur.execute("UPDATE _monl_users SET actor = ? WHERE username = ?", (args.actor, _normalize_identifier(args.username)))
    if cur.rowcount == 0:
        sys.exit(f"Compte introuvable : {{args.username}}")
    conn.commit()
    print(
        f"✅ '{{args.username}}' porte désormais le rôle '{{args.actor}}'. "
        "Les jetons déjà émis gardent l'ancien rôle jusqu'à expiration "
        "(revoke-all pour les invalider immédiatement)."
    )
    conn.close()


def cmd_passwd(args):
    conn = _connect()
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM _monl_users WHERE username = ?", (_normalize_identifier(args.username),))
    if not cur.fetchone():
        sys.exit(f"Compte introuvable : {{args.username}}")
    password = _ask_password()
    salt_hex = os.urandom(16).hex()
    cur.execute(
        "UPDATE _monl_users SET password_hash = ?, salt = ? WHERE username = ?",
        (_hash_password(password, salt_hex), salt_hex,
         _normalize_identifier(args.username)),
    )
    conn.commit()
    print(f"✅ Mot de passe de '{{args.username}}' mis à jour.")
    conn.close()


def cmd_users(_args):
    conn = _connect()
    cur = conn.cursor()
    cur.execute("SELECT id, username, actor FROM _monl_users ORDER BY id")
    rows = cur.fetchall()
    if not rows:
        print("Aucun compte.")
    for uid, username, actor in rows:
        libre = " (inscription libre)" if actor in SELF_REGISTER_ACTORS else " (provisionné)"
        print(f"{{uid:>4}}  {{username:<24}} {{actor}}{{libre}}")
    conn.close()


def cmd_revoke_all(_args):
    """Invalide toutes les sessions en cours en changeant le secret de signature."""
    secret_path = os.path.join(os.path.dirname(DB_FILE), ".jwt_secret")
    if os.environ.get("MONL_JWT_SECRET"):
        sys.exit(
            "Le secret vient de MONL_JWT_SECRET : changez la variable "
            "d'environnement puis redémarrez l'application."
        )
    fd = os.open(secret_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(secrets.token_hex(32))
    print("✅ Nouveau secret JWT écrit. Redémarrez l'application : toutes les "
          "sessions en cours deviennent invalides.")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("adduser", help="créer un compte avec un rôle donné")
    p.add_argument("username")
    p.add_argument("actor")
    p.set_defaults(func=cmd_adduser)

    p = sub.add_parser("setactor", help="changer le rôle d'un compte")
    p.add_argument("username")
    p.add_argument("actor")
    p.set_defaults(func=cmd_setactor)

    p = sub.add_parser("passwd", help="changer le mot de passe d'un compte")
    p.add_argument("username")
    p.set_defaults(func=cmd_passwd)

    sub.add_parser("users", help="lister les comptes").set_defaults(func=cmd_users)
    sub.add_parser("revoke-all", help="invalider toutes les sessions").set_defaults(func=cmd_revoke_all)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
'''
