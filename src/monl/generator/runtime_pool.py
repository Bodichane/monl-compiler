"""Pool PostgreSQL paresseux du runtime généré."""

from string import Template

from .runtime_socle import DB_POOL_MAX_ENV, DB_POOL_MIN_ENV


class PoolRuntimeMixin:
    """Émet l'état et les primitives du pool PostgreSQL."""

    def _pool_runtime_lines(self):
        """Lignes générées avant `_connect()`, sans toucher au chemin SQLite."""
        return [
            # Les constantes permettent au garde-fou de documentation de
            # résoudre les noms par AST, comme au point 172.
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
        raise RuntimeError(f'{name} doit être un entier positif.') from error
    if value < 1:
        raise RuntimeError(f'{name} doit être supérieur ou égal à 1.')
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
                raise RuntimeError(f'{_DB_POOL_MAX_ENV} doit être supérieur ou égal à {_DB_POOL_MIN_ENV}.')
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
        print("⚠️ psycopg_pool absent : PostgreSQL reste en connexion par requête. Installez l'extra '.[postgres]' (pip install 'monl-compiler[postgres]').")
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
