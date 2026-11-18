"""Lazy PostgreSQL pool of the generated runtime."""

from string import Template

from .runtime_socle import DB_POOL_MAX_ENV, DB_POOL_MIN_ENV


class PoolRuntimeMixin:
    """Emits the state and primitives of the PostgreSQL pool."""

    def _pool_runtime_lines(self):
        """Lines generated before `_connect()`, without touching the SQLite path."""
        return [
            # The constants let the documentation safeguard resolve the names
            # through AST, as in point 172.
            (Template(r"""_DB_POOL_MIN_ENV = ${DB_POOL_MIN_ENV}
_DB_POOL_MAX_ENV = ${DB_POOL_MAX_ENV}
_DB_POOL_DEFAULT_MIN = 1
_DB_POOL_DEFAULT_MAX = 10
_DB_POOL_LOCK = threading.Lock()
_DB_POOL = None
_DB_POOL_WARNING_EMITTED = False""").substitute(DB_POOL_MIN_ENV=repr(DB_POOL_MIN_ENV), DB_POOL_MAX_ENV=repr(DB_POOL_MAX_ENV))),
            Template(r"""""").substitute(),
            Template(r"""def _database_pool_size(raw, name):
    try:
        value = int(raw)
    except ValueError as error:
        raise RuntimeError(f'{name} must be a positive integer.') from error
    if value < 1:
        raise RuntimeError(f'{name} must be greater than or equal to 1.')
    return value""").substitute(),
            Template(r"""""").substitute(),
            Template(r"""def _database_pool():
    global _DB_POOL
    if _DB_POOL is not None:
        return _DB_POOL
    with _DB_POOL_LOCK:
        if _DB_POOL is None:
            _min_size = _database_pool_size((os.environ.get(_DB_POOL_MIN_ENV) or str(_DB_POOL_DEFAULT_MIN)).strip(), _DB_POOL_MIN_ENV)
            _max_size = _database_pool_size((os.environ.get(_DB_POOL_MAX_ENV) or str(_DB_POOL_DEFAULT_MAX)).strip(), _DB_POOL_MAX_ENV)
            if _max_size < _min_size:
                raise RuntimeError(f'{_DB_POOL_MAX_ENV} must be greater than or equal to {_DB_POOL_MIN_ENV}.')
            _DB_POOL = _psycopg_pool.ConnectionPool(conninfo=MONL_DATABASE_URL, min_size=_min_size, max_size=_max_size, kwargs={'connect_timeout': 10}, open=False)
            try:
                _DB_POOL.open(wait=True)
            except Exception:
                _DB_POOL.close()
                _DB_POOL = None
                raise
        return _DB_POOL""").substitute(),
            Template(r"""""").substitute(),
            Template(r"""def _announce_database_pool_fallback():
    global _DB_POOL_WARNING_EMITTED
    if not _DB_POOL_WARNING_EMITTED:
        print("⚠️ psycopg_pool missing: PostgreSQL stays on one connection per request. Install the '.[postgres]' extra (pip install 'monl-compiler[postgres]').")
        _DB_POOL_WARNING_EMITTED = True""").substitute(),
            Template(r"""""").substitute(),
            Template(r"""def _close_database_pool():
    global _DB_POOL
    with _DB_POOL_LOCK:
        if _DB_POOL is not None:
            _DB_POOL.close()
            _DB_POOL = None""").substitute(),
            Template(r"""""").substitute(),
        ]
