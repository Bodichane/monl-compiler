"""Témoins du pool PostgreSQL et de la séparation stricte avec SQLite."""

import os
import subprocess
import sys
from pathlib import Path

from monl.cli import compile_project
from monl.generator.runtime_socle import DB_POOL_MAX_ENV, DB_POOL_MIN_ENV

RACINE = Path(__file__).parents[1]
SPEC = """app Pool

entity User
    name: String

actor User selfRegister
workflow W for User
    Create User
    Read User
"""


def _application(tmp_path):
    spec = tmp_path / "spec.ml"
    spec.write_text(SPEC, encoding="utf-8")
    compile_project(str(spec), str(tmp_path))


def _probe(tmp_path, source, database_url=None, **variables):
    environment = os.environ.copy()
    if database_url is None:
        environment.pop("MONL_DATABASE_URL", None)
    else:
        environment["MONL_DATABASE_URL"] = database_url
    environment.update(variables)
    pythonpath = [str(RACINE / "src")]
    if environment.get("PYTHONPATH"):
        pythonpath.append(environment["PYTHONPATH"])
    environment["PYTHONPATH"] = os.pathsep.join(pythonpath)
    return subprocess.run(
        [sys.executable, "-c", source],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


def test_sqlite_n_emprunte_jamais_le_pool(tmp_path):
    """Même des tailles invalides ne doivent rien changer à SQLite."""
    _application(tmp_path)
    result = _probe(
        tmp_path,
        """
import app

class ForbiddenPool:
    def getconn(self):
        raise AssertionError("SQLite a emprunté le pool PostgreSQL")

app._psycopg_pool = ForbiddenPool()
assert app._DATABASE_KIND == "sqlite"
connexion = app._connect()
try:
    assert app._DB_POOL is None
    assert connexion._pool is None
    assert connexion.execute("SELECT 1").fetchone()[0] == 1
finally:
    connexion.close()
""",
        **{DB_POOL_MIN_ENV: "pas-un-entier", DB_POOL_MAX_ENV: "0"},
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_creation_du_pool_est_unique_verrouillee_et_configuree(tmp_path):
    _application(tmp_path)
    result = _probe(
        tmp_path,
        """
import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor
import app

class Raw:
    pass

class FakePool:
    instances = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.returned = []
        self.closed = False
        self.opened = False
        self.instances.append(self)

    def open(self, wait=False):
        assert wait is True
        self.opened = True

    def getconn(self):
        return Raw()

    def putconn(self, raw):
        self.returned.append(raw)

    def close(self):
        self.closed = True

class FakePoolModule:
    ConnectionPool = FakePool

app._DATABASE_KIND = "postgresql"
app.MONL_DATABASE_URL = "postgresql://fake"
app._psycopg_pool = FakePoolModule()
with ThreadPoolExecutor(max_workers=20) as workers:
    connexions = list(workers.map(lambda _: app._connect(), range(40)))
assert len(FakePool.instances) == 1
pool = FakePool.instances[0]
assert pool.opened is True
assert pool.kwargs["min_size"] == 2
assert pool.kwargs["max_size"] == 7
assert pool.kwargs["kwargs"] == {"connect_timeout": 10}
assert pool.kwargs["open"] is False
for connexion in connexions:
    connexion.close()
assert len(pool.returned) == 40

app.init_db = lambda: None
async def stop():
    async with app._lifespan(None):
        pass
asyncio.run(stop())
assert pool.closed is True
assert app._DB_POOL is None
""",
        **{DB_POOL_MIN_ENV: "2", DB_POOL_MAX_ENV: "7"},
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_repli_sans_psycopg_pool_et_diagnostic_une_seule_fois(tmp_path):
    _application(tmp_path)
    result = _probe(
        tmp_path,
        """
import sys

class MissingPool:
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "psycopg_pool":
            raise ModuleNotFoundError("psycopg_pool absent pour ce témoin")
        return None

sys.meta_path.insert(0, MissingPool())
import app

class Raw:
    def close(self):
        pass

class FakePsycopg:
    calls = 0

    @classmethod
    def connect(cls, *_args, **_kwargs):
        cls.calls += 1
        return Raw()

app._psycopg = FakePsycopg
for _ in range(2):
    connexion = app._connect()
    connexion.close()
assert FakePsycopg.calls == 2
""",
        database_url="postgresql://fake",
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.count("psycopg_pool absent") == 1, result.stdout
