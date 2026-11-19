"""The top of app.py: imports, application, secret, quota, SQLite wrapper,
and what the generated server can do on its own (timestamping, numbering)."""
from string import Template

DB_POOL_MIN_ENV = "MONL_DB_POOL_MIN"
DB_POOL_MAX_ENV = "MONL_DB_POOL_MAX"


class SocleRuntimeMixin:
    """The top of app.py: imports, application, secret, quota, SQLite wrapper,"""

    def _socle_et_schemas(self):
        """Imports, FastAPI application, secret, quota, Pydantic schemas."""
        actors_literal = ", ".join(Template(r'''"${actor}"''').substitute(actor=actor) for actor in self.actors)
        self_register_literal = ", ".join(Template(r'''"${actor}"''').substitute(actor=actor) for actor in self.self_register_actors)
        message_imports = ([
            *Template(r'''import logging
import smtplib
from email.message import EmailMessage''').substitute().split("\n"),
        ] if (self.message_rules_by_trigger or self.auth_features.get("password_reset") or self.auth_features.get("verify_email")) else [])
        totp_imports = ([*Template(r'''import base64
import struct''').substitute().split("\n")]
                        if self.auth_features.get("totp") else [])
        api_lines = ([*self._socle_imports_et_connexion(message_imports, totp_imports), *self._socle_outils_generes(actors_literal, self_register_literal), *self._socle_jetons()])
        return api_lines

    def _socle_imports_et_connexion(self, message_imports, totp_imports):
        """Imports, FastAPI application, secret, quota, and the SQLite wrapper."""
        return [
            *Template(r'''# Deterministic API, secure by default - Do not edit by hand
from fastapi import FastAPI, HTTPException, Header, Depends, Request${upload_imports}
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field, field_validator''').substitute(upload_imports=', UploadFile, File' if self.upload_fields else '').split("\n"),
            # BRICK 19 (point 96): 'Literal' carries the allowed value lists in
            # the Pydantic schemas. Without it, the generated app.py does not
            # start — the same defect as 're' in point 95, found the same way
            # by starting the server.
            *Template(r'''from typing import List, Optional, Any, Literal
import sqlite3
import jwt
import datetime
import hashlib
import hmac
import os
import secrets
import time
import threading''').substitute().split("\n"),
            *message_imports,
            *totp_imports,
            # POINT 95: the form of the account identifier is checked with a
            # pattern. Without it, the generated app.py did not even start
            # (NameError on 're') — found by starting the server, never visible
            # when rereading the generator.
            *Template(r'''import re''').substitute().split("\n"),
            # PAYMENT BRICK (point 74): the generated backend's first OUTGOING
            # call. json/urllib served no purpose while monl stayed offline;
            # charging changes that, and it must be said.
            *Template(r'''import json
import urllib.parse
import urllib.request
import urllib.error''').substitute().split("\n"),
            # The import is written ONLY if the spec carries `custom` blocks.
            # Hard-coded, it made `sandbox_ai.py` mandatory for every project:
            # a ONE-line file, never called, whose deletion made startup fail
            # with `ModuleNotFoundError` — a file that does nothing and cannot
            # be removed.
            *([*Template(r'''import sandbox_ai  # Hand-written 'custom' functions (isolated module)
''').substitute().split("\n")]
              if self.custom_functions else []),
            *Template(r'''from contextlib import asynccontextmanager

DB_FILE = 'app.db'
''').substitute().split("\n"),
            # A1: the engine is a STARTUP choice, never a compile-time one. The
            # sealed artifact can therefore run on SQLite in development and on
            # PostgreSQL in production without being recompiled.
            *Template(r'''MONL_DATABASE_URL = (os.environ.get('MONL_DATABASE_URL') or '').strip()
_DATABASE_KIND = 'sqlite'
_psycopg = None
_psycopg_pool = None
if MONL_DATABASE_URL:
    if not MONL_DATABASE_URL.startswith(('postgresql://', 'postgres://')):
        raise RuntimeError("MONL_DATABASE_URL must start with postgresql:// or postgres://.")
    try:
        import psycopg as _psycopg
    except ImportError as _err:
        raise RuntimeError("PostgreSQL requires the optional dependency '.[postgres]' (pip install monl-compiler[postgres]).") from _err
    try:
        import psycopg_pool as _psycopg_pool
    except ImportError:
        _psycopg_pool = None
    _DATABASE_KIND = 'postgresql'
    if MONL_DATABASE_URL.startswith('postgres://'):
        MONL_DATABASE_URL = 'postgresql://' + MONL_DATABASE_URL[len('postgres://'):]
_DATABASE_INTEGRITY_ERRORS = ((sqlite3.IntegrityError,) if _psycopg is None else
    (sqlite3.IntegrityError, _psycopg.IntegrityError))

class _DatabaseCursor:
    def __init__(self, raw):
        self._raw = raw

    def execute(self, statement, params=()):
        if _DATABASE_KIND == 'postgresql':
            # POINT 108 — WHY THIS REWRITE IS SAFE: since point 108, NO client
            # value enters the TEXT of a query. sql.py literally offers no API
            # to do so, and tests/test_sql_emission.py +
            # tests/test_invariants_securite.py forbid it in the generated
            # code. Translating '?' into '%s' therefore cannot move a value:
            # the text contains only fixed SQL. Without this invariant, this
            # translation would be a flaw; with it, it is mechanical.
            statement = statement.replace('?', '%s')
            if statement == 'BEGIN IMMEDIATE':
                statement = 'BEGIN'
        self._raw.execute(statement, params)
        return self

    def executemany(self, statement, params_seq):
        if _DATABASE_KIND == 'postgresql':
            statement = statement.replace('?', '%s')
        self._raw.executemany(statement, params_seq)
        return self

    def fetchone(self):
        return self._raw.fetchone()

    def fetchall(self):
        return self._raw.fetchall()

    def __iter__(self):
        return iter(self._raw)

    @property
    def rowcount(self):
        return self._raw.rowcount

    @property
    def description(self):
        return self._raw.description

    def __getattr__(self, name):
        return getattr(self._raw, name)

class _DatabaseConnection:
    def __init__(self, raw):
        self._raw = raw
        self._pool = None
        self._closed = False
    @classmethod
    def from_pool(cls, raw, pool):
        connection = cls(raw)
        connection._pool = pool
        return connection

    def cursor(self):
        return _DatabaseCursor(self._raw.cursor())

    def execute(self, statement, params=()):
        cursor = self.cursor()
        return cursor.execute(statement, params)

    def executescript(self, script):
        for statement in script.split(';'):
            statement = '\n'.join(line for line in statement.splitlines()
                                      if not line.strip().startswith('--')).strip()
            if statement:
                self.execute(statement)
        return self

    def commit(self):
        return self._raw.commit()

    def rollback(self):
        return self._raw.rollback()

    def close(self):
        if self._closed:
            return None
        self._closed = True
        if self._pool is not None:
            # `putconn()` returns to the pool after its reset: psycopg_pool rolls back INTRANS/INERROR
            # transactions.
            return self._pool.putconn(self._raw)
        return self._raw.close()

    @property
    def isolation_level(self):
        return getattr(self._raw, 'isolation_level', None)

    @isolation_level.setter
    def isolation_level(self, value):
        if _DATABASE_KIND == 'sqlite':
            self._raw.isolation_level = value

    def __getattr__(self, name):
        return getattr(self._raw, name)
''').substitute().split("\n"),
        ]

    def _socle_outils_generes(self, actors_literal, self_register_literal):
        """What the generated server can do on its own: schema, timestamp, number."""
        return [
            *self._pool_runtime_lines(),
            *Template(r'''def _schema_for_database(script):
    if _DATABASE_KIND == 'postgresql':
        # schema.sql stays directly executable by SQLite. For
        # PostgreSQL, AUTOINCREMENT becomes an identity in the same
        # artifact, at the moment the dialect is known.
        return script.replace("INTEGER PRIMARY KEY AUTOINCREMENT",
                              "INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY")
    return script

def _connect():
    if _DATABASE_KIND == 'postgresql':
        if _psycopg_pool is None:
            _announce_database_pool_fallback()
            return _DatabaseConnection(_psycopg.connect(MONL_DATABASE_URL, connect_timeout=10))
        _pool = _database_pool()
        return _DatabaseConnection.from_pool(_pool.getconn(), _pool)
    # FIX (beta 3): every request connection goes through this helper. It
    # enables referential integrity (SQLite disables it by default) and a
    # lock timeout.
    conn = _DatabaseConnection(sqlite3.connect(DB_FILE, timeout=10.0))
    conn.execute('PRAGMA foreign_keys = ON')
    conn.execute('PRAGMA busy_timeout = 10000')
    return conn


def _database_integrity_kind(error, once_names=(), once_signatures=()):
    """Classifies an integrity violation without parsing a PostgreSQL message.
    PostgreSQL exposes SQLSTATE and diag.constraint_name; SQLite stays
    compatible with its historical message as a fallback."""
    sqlstate = getattr(error, 'sqlstate', None)
    constraint = getattr(getattr(error, 'diag', None), 'constraint_name', None)
    if sqlstate == '23505':
        return 'once_per' if constraint in once_names else 'unique'
    if sqlstate == '23503':
        return 'foreign_key'
    message = str(error)
    if 'UNIQUE constraint failed' in message:
        return 'once_per' if any(sig in message for sig in once_signatures) else 'unique'
    if 'FOREIGN KEY constraint failed' in message:
        return 'foreign_key'
    return None
''').substitute().split("\n"),
            # ADDED (brick 16, point 89): the moment a record was created, in
            # ISO 8601 UTC. Two choices hold the brick together:
            # - UTC, never the server's local time: a machine redeployed
            #   elsewhere must not make dates go backwards.
            # - text sorted lexicographically = sorted chronologically, because
            #   the offset is ALWAYS '+00:00' and the format has a fixed width.
            #   That is what makes 'ORDER BY' correct on a TEXT column, hence
            #   what spares us a SQLite type that does not exist.
            #
            # The millisecond is not precision for its own sake: to the second,
            # two orders placed back to back carry the SAME date and can no
            # longer be ordered — which empties the property just announced of
            # its meaning. Four more characters, and the sort is total again.
            *Template(r'''def _horodatage():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='milliseconds')
''').substitute().split("\n"),
            # BRICK 22 (point 102): the readable number. The counter lives in a
            # SYSTEM table and not in the business table: counting the existing
            # rows would give back the number of a deleted record, and
            # `MAX(...) + 1` would go wrong as soon as two creations cross.
            #
            # The conditional UPDATE then the `rowcount` test are the same
            # pattern as the stock count (point 86): a single statement carries
            # the read and the write, so two transactions cannot read the same
            # counter. The bootstrap INSERT comes FIRST, and its 'ON CONFLICT
            # DO NOTHING' makes the order irrelevant.
            *Template(r'''def _periode_courante(gabarit_periode):
    if not gabarit_periode:
        return ''
    _m = datetime.datetime.now(datetime.timezone.utc)
    _parts = {'YYYY': f'{_m.year:04d}', 'MM': f'{_m.month:02d}',
              'DD': f'{_m.day:02d}'}
    return '-'.join(_parts[_j] for _j in gabarit_periode.split('-'))

def _attribuer_numero(cursor, entite, champ, gabarit, gabarit_periode):
    periode = _periode_courante(gabarit_periode)
    cursor.execute('INSERT INTO _monl_sequences (entite, champ, periode, dernier)'
                   ' VALUES (?, ?, ?, 0) ON CONFLICT DO NOTHING',
                   (entite, champ, periode))
    cursor.execute('UPDATE _monl_sequences SET dernier = dernier + 1'
                   ' WHERE entite = ? AND champ = ? AND periode = ?',
                   (entite, champ, periode))
    cursor.execute('SELECT dernier FROM _monl_sequences'
                   ' WHERE entite = ? AND champ = ? AND periode = ?',
                   (entite, champ, periode))
    rang = cursor.fetchone()[0]
    numero = gabarit
    _m = datetime.datetime.now(datetime.timezone.utc)
    for _jalon, _valeur in (('YYYY', f'{_m.year:04d}'),
                            ('MM', f'{_m.month:02d}'),
                            ('DD', f'{_m.day:02d}')):
        numero = numero.replace('{' + _jalon + '}', _valeur)''').substitute().split("\n"),
            # The width comes from the number of N written in the template. A
            # rank that exceeds it is NOT truncated: a longer number is better
            # than two records carrying the same one.
            *Template(r'''    _seq = re.search(r'\{(N+)\}', numero)
    if _seq:
        numero = numero.replace(_seq.group(0), str(rang).zfill(len(_seq.group(1))))
    return numero
''').substitute().split("\n"),
            # FIX (beta, secret hygiene): the JWT secret is read first from the
            # MONL_JWT_SECRET environment variable (recommended in production —
            # the secret never touches the disk or a repository), and otherwise
            # falls back to the '.jwt_secret' file. An archive shipped without
            # a secret can thus create one on first start, on the machine that
            # hosts it.
            *Template(r'''JWT_SECRET = (os.environ.get('MONL_JWT_SECRET') or '').strip()
_MONL_ENV = os.environ.get('MONL_ENV', '').strip().lower()
if _MONL_ENV == 'production' and not JWT_SECRET:
    raise RuntimeError(
        'MONL_ENV=production requires the MONL_JWT_SECRET variable; '
        'no JWT secret will be generated or read from .jwt_secret.'
    )
if not JWT_SECRET:
    try:
        with open('.jwt_secret', 'r', encoding='utf-8') as _f:
            JWT_SECRET = _f.read().strip()
        if not JWT_SECRET:
            raise ValueError('.jwt_secret is empty')
    except FileNotFoundError:
        JWT_SECRET = secrets.token_hex(32)
        try:
            _fd = os.open('.jwt_secret', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            with open('.jwt_secret', 'r', encoding='utf-8') as _f:
                JWT_SECRET = _f.read().strip()
        except OSError as _e:
            raise RuntimeError("Unable to create .jwt_secret: set "
                               "MONL_JWT_SECRET or make the folder writable.") from _e
        else:
            with os.fdopen(_fd, 'w', encoding='utf-8') as _f:
                _f.write(JWT_SECRET)
    if not JWT_SECRET:
        raise RuntimeError('The .jwt_secret file is empty')
JWT_ALGORITHM = 'HS256'
VALID_ACTORS = [${actors}]''').substitute(actors=actors_literal).split("\n"),
            # FIX (beta 3, critical privilege-escalation flaw): '/register'
            # accepted any declared role sent by the client. The role carried
            # by the token did come from the real account, but that account
            # chose its own role: registering as an administrator was enough.
            # Only roles marked 'selfRegister' in the spec are now open to
            # registration; the others are provisioned offline (manage.py).
            # Empty list = no open registration.
            *Template(r'''SELF_REGISTER_ACTORS = [${self_register_actors}]''').substitute(self_register_actors=self_register_literal).split("\n"),
            # FIX (beta 3): the lifetime was hard-coded (2 h) while the
            # contract given to the frontend AI announced 1 h. A single value,
            # configurable at deployment, and published as is in the contract —
            # an unverifiable security promise is worth nothing.
            *Template(r'''TOKEN_TTL_HOURS = int(os.environ.get('MONL_TOKEN_TTL_HOURS', '2'))
''').substitute().split("\n"),
            *( [*Template(r'''TOKEN_TTL_SECONDS = int(os.environ.get('MONL_TOKEN_TTL_SECONDS', str(TOKEN_TTL_HOURS * 3600)))
''').substitute().split("\n")] if self.auth_features.get('refresh_tokens') else [] ),
        ]
