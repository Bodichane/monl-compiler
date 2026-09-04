"""Pool PostgreSQL paresseux du runtime généré."""

from .runtime_socle import DB_POOL_MAX_ENV, DB_POOL_MIN_ENV


class PoolRuntimeMixin:
    """Émet l'état et les primitives du pool PostgreSQL."""

    def _pool_runtime_lines(self):
        """Lignes générées avant `_connect()`, sans toucher au chemin SQLite."""
        return [
            # Les constantes permettent au garde-fou de documentation de
            # résoudre les noms par AST, comme au point 172.
            (f"_DB_POOL_MIN_ENV = {DB_POOL_MIN_ENV!r}\n"
             f"_DB_POOL_MAX_ENV = {DB_POOL_MAX_ENV!r}\n"
             "_DB_POOL_DEFAULT_MIN = 1\n"
             "_DB_POOL_DEFAULT_MAX = 10\n"
             "_DB_POOL_LOCK = threading.Lock()\n"
             "_DB_POOL = None\n"
             "_DB_POOL_WARNING_EMITTED = False"),
            "",
            "def _database_pool_size(raw, name):\n"
            "    try:\n"
            "        value = int(raw)\n"
            "    except ValueError as error:\n"
            "        raise RuntimeError(f'{name} doit être un entier positif.') from error\n"
            "    if value < 1:\n"
            "        raise RuntimeError(f'{name} doit être supérieur ou égal à 1.')\n"
            "    return value",
            "",
            "def _database_pool():\n"
            "    global _DB_POOL\n"
            "    if _DB_POOL is not None:\n"
            "        return _DB_POOL\n"
            "    with _DB_POOL_LOCK:\n"
            "        if _DB_POOL is None:\n"
            "            _min_size = _database_pool_size((os.environ.get(_DB_POOL_MIN_ENV) or str(_DB_POOL_DEFAULT_MIN)).strip(), _DB_POOL_MIN_ENV)\n"
            "            _max_size = _database_pool_size((os.environ.get(_DB_POOL_MAX_ENV) or str(_DB_POOL_DEFAULT_MAX)).strip(), _DB_POOL_MAX_ENV)\n"
            "            if _max_size < _min_size:\n"
            "                raise RuntimeError(f'{_DB_POOL_MAX_ENV} doit être supérieur ou égal à {_DB_POOL_MIN_ENV}.')\n"
            "            _DB_POOL = _psycopg_pool.ConnectionPool(conninfo=MONL_DATABASE_URL, min_size=_min_size, max_size=_max_size, kwargs={'connect_timeout': 10}, open=False)\n"
            "            try:\n"
            "                _DB_POOL.open(wait=True)\n"
            "            except Exception:\n"
            "                _DB_POOL.close()\n"
            "                _DB_POOL = None\n"
            "                raise\n"
            "        return _DB_POOL",
            "",
            "def _announce_database_pool_fallback():\n"
            "    global _DB_POOL_WARNING_EMITTED\n"
            "    if not _DB_POOL_WARNING_EMITTED:\n"
            "        print(\"⚠️ psycopg_pool absent : PostgreSQL reste en connexion par requête. Installez l'extra '.[postgres]' (pip install 'monl-compiler[postgres]').\")\n"
            "        _DB_POOL_WARNING_EMITTED = True",
            "",
            "def _close_database_pool():\n"
            "    global _DB_POOL\n"
            "    with _DB_POOL_LOCK:\n"
            "        if _DB_POOL is not None:\n"
            "            _DB_POOL.close()\n"
            "            _DB_POOL = None",
            "",
        ]
