import sqlite3
from pathlib import Path

from monl.ast_validator import MonlAST
from monl.generator import MonlSecureGenerator
from monl.parser import parse_monl_string

p = Path(__file__).resolve().parent
MonlSecureGenerator(
    MonlAST(parse_monl_string((p / "spec.ml").read_text())).validate_and_audit(),
    output_dir=str(p / "backend"),
).generate_all()
(p / "backend/sandbox_ai.py").write_text((p / "hostile.py").read_text())
(p / "backend/.jwt_secret").write_text("ETUDE_JWT_FICHIER")
(p / "backend/.jwt_secret").chmod(0o600)
with sqlite3.connect(p / "backend/app.db") as db:
    db.execute("CREATE TABLE IF NOT EXISTS preuve (valeur TEXT)")
    db.execute("DELETE FROM preuve")
    db.execute("INSERT INTO preuve VALUES ('ETUDE_DB')")
print(__import__("monl").__file__)
