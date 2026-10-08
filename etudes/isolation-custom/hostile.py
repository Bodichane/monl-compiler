import json
import os
import socket
import sqlite3
from pathlib import Path


def Publier(context):
    # Chemins connus de l'attaquant, jamais fournis dans le contexte métier.
    root = Path(__file__).resolve().parent / "backend"
    if not root.exists():
        root = Path(__file__).resolve().parent
    results = {}

    def attempt(name, fn):
        try:
            results[name] = {"ok": bool(fn())}
        except Exception as exc:
            results[name] = {"ok": False, "error": type(exc).__name__ + ": " + str(exc)}

    attempt("jwt_file", lambda: (root / ".jwt_secret").read_text() == "ETUDE_JWT_FICHIER")
    attempt("environment", lambda: os.environ.get("MONL_JWT_SECRET") == "ETUDE_JWT_ENV")

    def database():
        with sqlite3.connect("file:" + str(root / "app.db") + "?mode=ro", uri=True) as db:
            return db.execute("SELECT valeur FROM preuve").fetchone()[0] == "ETUDE_DB"

    attempt("database", database)

    def network():
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            s.listen(1)
            return True

    attempt("socket", network)
    return results


if __name__ == "__main__":
    print(json.dumps(Publier(json.loads(input()))))
