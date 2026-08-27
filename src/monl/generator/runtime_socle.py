"""Le haut de app.py : imports, application, secret, quota, enveloppe SQLite,
et ce que le serveur généré sait faire seul (horodatage, numérotation)."""

class SocleRuntimeMixin:
    """Le haut de app.py : imports, application, secret, quota, enveloppe SQLite,"""

    def _socle_et_schemas(self):
        """Imports, application FastAPI, secret, quota, schémas Pydantic."""
        actors_literal = ", ".join(f'"{a}"' for a in self.actors)
        self_register_literal = ", ".join(f'"{a}"' for a in self.self_register_actors)
        message_imports = ([
            "import logging",
            "import smtplib",
            "import threading",
            "from email.message import EmailMessage",
        ] if (self.message_rules_by_trigger or self.auth_features.get("password_reset")) else [])
        totp_imports = (["import base64", "import struct"]
                        if self.auth_features.get("totp") else [])
        totp_migration_lines = []
        if self.auth_features.get("totp"):
            totp_migration_lines = [
                "    # BRIQUE B4 : les colonnes TOTP restent NULL pour les comptes",
                "    # historiques ; elles sont comptées, jamais remplies au démarrage.",
                "    try:",
                "        _totp_columns = _table_columns(_sys_cur, '_monl_users')",
                "        for _name, _type in (('totp_secret', 'VARCHAR(64)'), ('totp_enabled', 'BOOLEAN'), ('totp_last_step', 'BIGINT')):",
                "            if _name not in _totp_columns:",
                "                _sys_cur.execute(f'ALTER TABLE _monl_users ADD COLUMN {_name} {_type}')",
                "                print(f'🔧 Migration : colonne \\\"{_name}\\\" ajoutée à \\\"_monl_users\\\" ({_type}).')",
                "        conn.commit()",
                "        _sans_totp = conn.execute(\"SELECT COUNT(*) FROM _monl_users WHERE totp_secret IS NULL\").fetchone()[0]",
                "        if _sans_totp:",
                "            print(f'ℹ️ {_sans_totp} compte(s) restent sans double facteur TOTP : aucune activation n\'est inventée.')",
                "    except Exception as _error:",
                "        conn.rollback()",
                "        raise RuntimeError(f'Migration TOTP échouée : {_error}') from _error",
            ]
        api_lines = (self._socle_imports_et_connexion(message_imports, totp_imports)
                     + self._socle_outils_generes(actors_literal, self_register_literal)
                     + self._socle_jetons())
        return api_lines, totp_migration_lines

    def _socle_imports_et_connexion(self, message_imports, totp_imports):
        """Imports, application FastAPI, secret, quota, et l'enveloppe SQLite."""
        return [
            "# API Déterministe Sécurisée par défaut - Ne pas modifier à la main",
            f"from fastapi import FastAPI, HTTPException, Header, Depends, Request{', UploadFile, File' if self.upload_fields else ''}",
            "from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials",
            "from pydantic import BaseModel, Field",
            # BRIQUE 19 (point 96) : 'Literal' porte les listes de valeurs
            # autorisées dans les schémas Pydantic. Absent, le app.py généré
            # ne démarre pas — même défaut que 're' au point 95, et trouvé
            # pareillement en lançant le serveur.
            "from typing import List, Optional, Any, Literal",
            "import sqlite3",
            "import jwt",
            "import datetime",
            "import hashlib",
            "import hmac",
            "import os",
            "import secrets",
            "import time",
            *message_imports,
            *totp_imports,
            # POINT 95 : la forme de l'identifiant de compte se vérifie par
            # motif. Absent, le app.py généré ne démarrait même pas
            # (NameError sur 're') — trouvé en lançant le serveur, jamais
            # visible en relisant le générateur.
            "import re",
            # BRIQUE PAIEMENT (point 74) : premier appel SORTANT du backend
            # généré. json/urllib ne servaient à rien tant que monl restait
            # hors-ligne ; encaisser change cela, et il faut le dire.
            "import json",
            "import urllib.parse",
            "import urllib.request",
            "import urllib.error",
            "import sandbox_ai  # Fonctions 'custom' écrites à la main (module isolé)\n",
            "from contextlib import asynccontextmanager\n",
            "DB_FILE = 'app.db'\n",
            # A1 : le moteur est un choix de DÉMARRAGE, jamais de compilation.
            # L'artefact scellé peut donc tourner en développement sur SQLite
            # et en production sur PostgreSQL sans être recompilé.
            "MONL_DATABASE_URL = (os.environ.get('MONL_DATABASE_URL') or '').strip()",
            "_DATABASE_KIND = 'sqlite'",
            "_psycopg = None",
            "if MONL_DATABASE_URL:",
            "    if not MONL_DATABASE_URL.startswith(('postgresql://', 'postgres://')):",
            "        raise RuntimeError(\"MONL_DATABASE_URL doit commencer par postgresql:// ou postgres://.\")",
            "    try:",
            "        import psycopg as _psycopg",
            "    except ImportError as _err:",
            "        raise RuntimeError(\"PostgreSQL demande la dépendance optionnelle '.[postgres]' (pip install monl-compiler[postgres]).\") from _err",
            "    _DATABASE_KIND = 'postgresql'",
            "    if MONL_DATABASE_URL.startswith('postgres://'):",
            "        MONL_DATABASE_URL = 'postgresql://' + MONL_DATABASE_URL[len('postgres://'):]",
            "_DATABASE_INTEGRITY_ERRORS = ((sqlite3.IntegrityError,) if _psycopg is None else",
            "    (sqlite3.IntegrityError, _psycopg.IntegrityError))",
            "",
            "class _DatabaseCursor:",
            "    def __init__(self, raw):",
            "        self._raw = raw",
            "",
            "    def execute(self, statement, params=()):",
            "        if _DATABASE_KIND == 'postgresql':",
            "            # POINT 108 — POURQUOI CETTE RÉÉCRITURE EST SÛRE : depuis le",
            "            # point 108, AUCUNE valeur client n'entre dans le TEXTE d'une",
            "            # requête. sql.py n'offre littéralement pas d'API pour le faire,",
            "            # et tests/test_sql_emission.py + tests/test_invariants_securite.py",
            "            # l'interdisent sur le code généré. Traduire '?' en '%s' ne peut",
            "            # donc pas déplacer une valeur : le texte ne contient que du SQL",
            "            # fixe. Sans cet invariant, cette traduction serait une faille ;",
            "            # avec lui, elle est mécanique.",
            "            statement = statement.replace('?', '%s')",
            "            if statement == 'BEGIN IMMEDIATE':",
            "                statement = 'BEGIN'",
            "        self._raw.execute(statement, params)",
            "        return self",
            "",
            "    def executemany(self, statement, params_seq):",
            "        if _DATABASE_KIND == 'postgresql':",
            "            statement = statement.replace('?', '%s')",
            "        self._raw.executemany(statement, params_seq)",
            "        return self",
            "",
            "    def fetchone(self):",
            "        return self._raw.fetchone()",
            "",
            "    def fetchall(self):",
            "        return self._raw.fetchall()",
            "",
            "    def __iter__(self):",
            "        return iter(self._raw)",
            "",
            "    @property",
            "    def rowcount(self):",
            "        return self._raw.rowcount",
            "",
            "    @property",
            "    def description(self):",
            "        return self._raw.description",
            "",
            "    def __getattr__(self, name):",
            "        return getattr(self._raw, name)",
            "",
            "class _DatabaseConnection:",
            "    def __init__(self, raw):",
            "        self._raw = raw",
            "",
            "    def cursor(self):",
            "        return _DatabaseCursor(self._raw.cursor())",
            "",
            "    def execute(self, statement, params=()):",
            "        cursor = self.cursor()",
            "        return cursor.execute(statement, params)",
            "",
            "    def executescript(self, script):",
            "        for statement in script.split(';'):",
            "            statement = '\\n'.join(line for line in statement.splitlines()",
            "                                      if not line.strip().startswith('--')).strip()",
            "            if statement:",
                "                self.execute(statement)",
            "        return self",
            "",
            "    def commit(self):",
            "        return self._raw.commit()",
            "",
            "    def rollback(self):",
            "        return self._raw.rollback()",
            "",
            "    def close(self):",
            "        return self._raw.close()",
            "",
            "    @property",
            "    def isolation_level(self):",
            "        return getattr(self._raw, 'isolation_level', None)",
            "",
            "    @isolation_level.setter",
            "    def isolation_level(self, value):",
            "        if _DATABASE_KIND == 'sqlite':",
            "            self._raw.isolation_level = value",
            "",
            "    def __getattr__(self, name):",
            "        return getattr(self._raw, name)",
            "",
        ]

    def _socle_outils_generes(self, actors_literal, self_register_literal):
        """Ce que le serveur généré sait faire seul : schéma, horodatage, numéro."""
        return [
            "def _schema_for_database(script):",
            "    if _DATABASE_KIND == 'postgresql':",
            "        # schema.sql reste directement exécutable par SQLite. Pour",
            "        # PostgreSQL, AUTOINCREMENT devient une identité dans le même",
            "        # artefact, au moment où le dialecte est connu.",
            "        return script.replace(\"INTEGER PRIMARY KEY AUTOINCREMENT\",",
            "                              \"INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY\")",
            "    return script",
            "",
            "def _connect():",
            "    if _DATABASE_KIND == 'postgresql':",
            "        return _DatabaseConnection(_psycopg.connect(MONL_DATABASE_URL, connect_timeout=10))",
            "    # CORRECTIF (bêta 3) : toutes les connexions de requête passent par",
            "    # ce helper. Il active l'intégrité référentielle (SQLite la désactive",
            "    # par défaut) et un délai d'attente sur verrou.",
            "    conn = _DatabaseConnection(sqlite3.connect(DB_FILE, timeout=10.0))",
            "    conn.execute('PRAGMA foreign_keys = ON')",
            "    conn.execute('PRAGMA busy_timeout = 10000')",
            "    return conn\n",
            "",
            "def _database_integrity_kind(error, once_names=(), once_signatures=()):",
            "    \"\"\"Classe une intégrité violée sans parser un message PostgreSQL.",
            "    PostgreSQL expose SQLSTATE et diag.constraint_name ; SQLite reste",
            "    compatible avec son message historique comme solution de repli.\"\"\"",
            "    sqlstate = getattr(error, 'sqlstate', None)",
            "    constraint = getattr(getattr(error, 'diag', None), 'constraint_name', None)",
            "    if sqlstate == '23505':",
            "        return 'once_per' if constraint in once_names else 'unique'",
            "    if sqlstate == '23503':",
            "        return 'foreign_key'",
            "    message = str(error)",
            "    if 'UNIQUE constraint failed' in message:",
            "        return 'once_per' if any(sig in message for sig in once_signatures) else 'unique'",
            "    if 'FOREIGN KEY constraint failed' in message:",
            "        return 'foreign_key'",
            "    return None",
            "",
            # AJOUT (brique 16, point 89) : l'instant de création d'un
            # enregistrement, en ISO 8601 UTC. Deux choix qui tiennent la
            # brique :
            #  - UTC, jamais l'heure locale du serveur : une machine
            #    redéployée ailleurs ne doit pas faire reculer les dates.
            #  - texte trié lexicographiquement = trié chronologiquement,
            #    parce que le décalage est TOUJOURS '+00:00' et le format de
            #    largeur fixe. C'est ce qui rend 'ORDER BY' juste sur une
            #    colonne TEXT, donc ce qui dispense d'un type SQLite qui
            #    n'existe pas.
            # La milliseconde n'est pas de la précision pour la précision :
            # à la seconde, deux commandes passées coup sur coup portent la
            # MÊME date et ne sont plus ordonnables — ce qui vide de son sens
            # la propriété qu'on vient d'annoncer. Quatre caractères de plus,
            # et le tri redevient total.
            "def _horodatage():",
            "    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='milliseconds')\n",
            # BRIQUE 22 (point 102) : le numéro lisible. Le compteur vit dans une
            # table SYSTÈME et non dans la table métier : compter les lignes
            # existantes redonnerait le numéro d'un enregistrement supprimé, et
            # `MAX(...) + 1` se tromperait dès que deux créations se croisent.
            #
            # L'UPDATE conditionnel puis le test de `rowcount` sont le même
            # motif qu'au décompte de stock (point 86) : une seule instruction
            # porte la lecture et l'écriture, donc deux transactions ne peuvent
            # pas lire le même compteur. L'INSERT d'amorçage vient AVANT, et son
            # 'ON CONFLICT DO NOTHING' rend l'ordre indifférent.
            "def _periode_courante(gabarit_periode):",
            "    if not gabarit_periode:",
            "        return ''",
            "    _m = datetime.datetime.now(datetime.timezone.utc)",
            "    _parts = {'YYYY': f'{_m.year:04d}', 'MM': f'{_m.month:02d}',",
            "              'DD': f'{_m.day:02d}'}",
            "    return '-'.join(_parts[_j] for _j in gabarit_periode.split('-'))\n",
            "def _attribuer_numero(cursor, entite, champ, gabarit, gabarit_periode):",
            "    periode = _periode_courante(gabarit_periode)",
            "    cursor.execute('INSERT INTO _monl_sequences (entite, champ, periode, dernier)'",
            "                   ' VALUES (?, ?, ?, 0) ON CONFLICT DO NOTHING',",
            "                   (entite, champ, periode))",
            "    cursor.execute('UPDATE _monl_sequences SET dernier = dernier + 1'",
            "                   ' WHERE entite = ? AND champ = ? AND periode = ?',",
            "                   (entite, champ, periode))",
            "    cursor.execute('SELECT dernier FROM _monl_sequences'",
            "                   ' WHERE entite = ? AND champ = ? AND periode = ?',",
            "                   (entite, champ, periode))",
            "    rang = cursor.fetchone()[0]",
            "    numero = gabarit",
            "    _m = datetime.datetime.now(datetime.timezone.utc)",
            "    for _jalon, _valeur in (('YYYY', f'{_m.year:04d}'),",
            "                            ('MM', f'{_m.month:02d}'),",
            "                            ('DD', f'{_m.day:02d}')):",
            "        numero = numero.replace('{' + _jalon + '}', _valeur)",
            # La largeur vient du nombre de N écrits dans le gabarit. Un rang qui
            # la dépasse n'est PAS tronqué : mieux vaut un numéro plus long que
            # deux enregistrements portant le même.
            "    _seq = re.search(r'\\{(N+)\\}', numero)",
            "    if _seq:",
            "        numero = numero.replace(_seq.group(0), str(rang).zfill(len(_seq.group(1))))",
            "    return numero\n",
            # CORRECTIF (bêta, hygiène de secret) : le secret JWT est lu en
            # priorité depuis la variable d'environnement MONL_JWT_SECRET
            # (recommandé en production — le secret ne touche jamais le disque
            # ni un dépôt), et retombe sinon sur le fichier '.jwt_secret'
            # généré à la compilation. Un projet peut ainsi être livré SANS
            # secret embarqué et se le voir injecter au déploiement.
            "JWT_SECRET = (os.environ.get('MONL_JWT_SECRET') or '').strip()",
            "_MONL_ENV = os.environ.get('MONL_ENV', '').strip().lower()",
            "if _MONL_ENV == 'production' and not JWT_SECRET:",
            "    raise RuntimeError(",
            "        'MONL_ENV=production exige la variable MONL_JWT_SECRET ; '",
            "        'aucun secret JWT ne sera généré ni lu depuis .jwt_secret.'",
            "    )",
            "if not JWT_SECRET:",
            "    try:",
            "        with open('.jwt_secret', 'r', encoding='utf-8') as _f:",
            "            JWT_SECRET = _f.read().strip()",
            "        if not JWT_SECRET:",
            "            raise ValueError('.jwt_secret est vide')",
            "    except (FileNotFoundError, ValueError) as _e:",
            "        raise RuntimeError(",
            "            \"Aucun secret JWT : définissez la variable d'environnement \"",
            "            \"MONL_JWT_SECRET, ou laissez le compilateur monl générer \"",
            "            \"'.jwt_secret' (relancez 'python3 src/main.py <spec.ml>' depuis la \"",
            "            \"racine du projet avant de démarrer le serveur).\"",
            "        ) from _e",
            "JWT_ALGORITHM = 'HS256'",
            f"VALID_ACTORS = [{actors_literal}]",
            # CORRECTIF (bêta 3, faille critique d'élévation de privilège) :
            # '/register' acceptait n'importe quel rôle déclaré, envoyé par le
            # client. Le rôle porté par le jeton provenait bien du compte réel,
            # mais ce compte se choisissait lui-même son rôle : s'inscrire
            # comme administrateur suffisait. Seuls les rôles marqués
            # 'selfRegister' dans la spec sont désormais ouverts à
            # l'inscription ; les autres sont provisionnés hors ligne
            # (manage.py). Liste vide = aucune inscription libre.
            f"SELF_REGISTER_ACTORS = [{self_register_literal}]",
            # CORRECTIF (bêta 3) : la durée de vie était écrite en dur (2 h)
            # alors que le contrat remis à l'IA frontend annonçait 1 h. Valeur
            # unique, réglable au déploiement, et publiée telle quelle dans le
            # contrat — une promesse de sécurité invérifiable ne vaut rien.
            "TOKEN_TTL_HOURS = int(os.environ.get('MONL_TOKEN_TTL_HOURS', '2'))\n",
            *( ["TOKEN_TTL_SECONDS = int(os.environ.get('MONL_TOKEN_TTL_SECONDS', str(TOKEN_TTL_HOURS * 3600)))\n"] if self.auth_features.get('refresh_tokens') else [] ),
        ]
