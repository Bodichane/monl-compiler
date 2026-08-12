"""Socle runtime de l'application générée : imports, secret JWT,
init_db/migrations/seed, inscription, connexion, révocation de jeton,
limitation de débit.

Extrait de l'ancien module monolithique src/generator.py (1307 lignes)
lors du découpage en package — voir docs/design_decisions.md.
"""


class RuntimeMixin:
    def _cors_methods(self):
        """Méthodes réellement émises par l'application générée."""
        methods = {"GET", "POST"}  # racine, santé et authentification
        action_methods = {
            "Read": "GET",
            "Create": "POST",
            "Update": "PUT",
            "Delete": "DELETE",
            "Execute": "POST",
        }
        for plan in self._compute_route_map().values():
            method = action_methods.get(plan.action)
            if method:
                methods.add(method)
        if self.payable_by_entity:
            methods.add("POST")
        if self.postpayment_writable_by_entity:
            methods.add("PUT")
        return [method for method in ("GET", "POST", "PUT", "DELETE")
                if method in methods]

    def _generate_identifier_helpers(self):
        """Normalisation + contrôle de forme de l'identifiant de compte (95).

        Émis MÊME sans déclaration : la fonction existe alors et rend la valeur
        inchangée. Un seul chemin de code dans le app.py généré vaut mieux que
        deux, dont un jamais exercé — et `/register`, `/login` et `manage.py`
        DOIVENT s'accorder, sinon on crée des comptes auxquels on ne peut pas
        se connecter."""
        formes = self.auth_identifier or []
        return [
            f"AUTH_IDENTIFIER_FORMS = {formes!r}",
            f"AUTH_PHONE_PREFIX = {self.auth_phone_prefix!r}",
            "",
            "def _normalize_identifier(valeur: str) -> str:",
            "    \"\"\"Forme canonique de l'identifiant : c'est elle qui est STOCKÉE",
            "    et c'est sur elle que porte l'unicité.\"\"\"",
            "    valeur = (valeur or '').strip()",
            "    if not AUTH_IDENTIFIER_FORMS:",
            "        return valeur",
            "    if '@' in valeur:",
            "        # Seul le domaine est officiellement insensible à la casse,",
            "        # mais aucun fournisseur réel ne distingue la partie locale :",
            "        # ne pas l'abaisser laisserait ouvrir deux comptes pour une",
            "        # seule boîte, ce que l'unicité est censée empêcher.",
            "        return valeur.lower()",
            "    if _RE_PHONE.match(valeur):",
            "        # Un numéro se tape avec des espaces, des points, des tirets",
            "        # ou des parenthèses — jamais deux fois pareil.",
            "        chiffres = ''.join(c for c in valeur if c.isdigit())",
            "        if valeur.lstrip().startswith('+'):",
            "            return '+' + chiffres",
            # Un numéro NATIONAL ('06 12 34 56 78') désigne la même ligne que sa
            # forme internationale — mais seulement si l'on sait de quel pays.
            # Déclaré, on canonicalise ; sinon on laisse tel quel, et les deux
            # notations restent deux comptes (limite énoncée, pas devinée).
            "        if AUTH_PHONE_PREFIX and chiffres.startswith('0'):",
            "            return AUTH_PHONE_PREFIX + chiffres[1:]",
            "        return chiffres",
            "    return valeur",
            "",
            # Motif d'e-mail identique à celui du type `Email` (point 91) : deux
            # motifs différents pour la même chose finiraient par diverger.
            r"_RE_EMAIL = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]{2,}$')",
            # Volontairement large : indicatif optionnel, séparateurs usuels,
            # 6 à 15 chiffres (E.164 plafonne à 15). monl vérifie la FORME ; il
            # ne peut pas attester qu'une ligne existe — cela demanderait un
            # appel sortant, que le compilateur s'interdit partout ailleurs que
            # chez le prestataire de paiement (même limite qu'au point 91 pour
            # l'e-mail).
            r"_RE_PHONE = re.compile(r'^\+?[0-9][0-9 .\-()]{4,20}$')",
            "",
            "def _forme_valide(valeur: str) -> bool:",
            "    \"\"\"Prédicat pur : sert au refus de '/register' ET au décompte des",
            "    comptes antérieurs au démarrage. Deux implémentations de « est-ce",
            "    une adresse ? » finiraient par ne plus dire la même chose.\"\"\"",
            "    if not AUTH_IDENTIFIER_FORMS or 'libre' in AUTH_IDENTIFIER_FORMS:",
            "        return True",
            "    if 'email' in AUTH_IDENTIFIER_FORMS and _RE_EMAIL.match(valeur):",
            "        return True",
            "    if 'phone' in AUTH_IDENTIFIER_FORMS and _RE_PHONE.match(valeur):",
            "        return 6 <= sum(c.isdigit() for c in valeur) <= 15",
            "    return False",
            "",
            "def _conflit_identifiant() -> str:",
            "    if AUTH_IDENTIFIER_FORMS == ['email']:",
            "        return 'Cette adresse e-mail est déjà utilisée.'",
            "    if AUTH_IDENTIFIER_FORMS == ['phone']:",
            "        return 'Ce numéro de téléphone est déjà utilisé.'",
            "    if AUTH_IDENTIFIER_FORMS and 'libre' not in AUTH_IDENTIFIER_FORMS:",
            "        return 'Cet identifiant est déjà utilisé.'",
            "    return \"Ce nom d'utilisateur existe déjà.\"",
            "",
            "def _check_identifier(valeur: str) -> None:",
            "    if not _forme_valide(valeur):",
            "        _attendu = {'email': 'une adresse e-mail',",
            "                    'phone': 'un numéro de téléphone'}",
            "        _libelle = ' ou '.join(_attendu[f] for f in AUTH_IDENTIFIER_FORMS",
            "                               if f in _attendu)",
            "        raise HTTPException(status_code=422, detail=(",
            "            f\"L'identifiant de compte doit être {_libelle}.\"))",
            "",
        ]

    def _generate_runtime_lines(self):
        """Lignes de app.py jusqu'aux schémas Pydantic (incluses)."""
        actors_literal = ", ".join(f'"{a}"' for a in self.actors)
        self_register_literal = ", ".join(f'"{a}"' for a in self.self_register_actors)
        api_lines = [
            "# API Déterministe Sécurisée par défaut - Ne pas modifier à la main",
            "from fastapi import FastAPI, HTTPException, Header, Depends, Request",
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
            # CORRECTIF (bêta 3) : toutes les connexions de requête passent par
            # ce helper. Il active l'intégrité référentielle (SQLite la désactive
            # par défaut : les clés étrangères déclarées dans schema.sql
            # n'étaient jamais vérifiées) et un délai d'attente sur verrou, pour
            # que deux écritures concurrentes patientent au lieu d'échouer
            # immédiatement en 'database is locked'.
            "def _connect():",
            "    conn = sqlite3.connect(DB_FILE, timeout=10.0)",
            "    conn.execute('PRAGMA foreign_keys = ON')",
            "    conn.execute('PRAGMA busy_timeout = 10000')",
            "    return conn\n",
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
            "# AJOUT (roadmap long terme, migrations sans perte de données) :",
            "# schéma de colonnes attendu par table (hors 'id'), consommé par",
            "# init_db() pour appliquer les ALTER TABLE ADD COLUMN manquants au",
            "# démarrage. Injecté via repr() pour un littéral Python toujours",
            "# valide, quel que soit le nom des colonnes.",
            f"_EXPECTED_COLUMNS = {self._compute_expected_columns()!r}\n",
            "# AJOUT (roadmap frontend, bloc 'seed') : données de démonstration",
            "# regroupées par table, injectées via repr() pour un littéral toujours",
            "# valide. Consommées par init_db() (insertion idempotente si vide).",
            f"_SEED_DATA = {self._compute_seed_data()!r}\n",
            # POINT 85 : 'rule Entite.champ unique' ne produisait RIEN — deux
            # lignes de même valeur étaient acceptées (vérifié contre un vrai
            # serveur). Un INDEX plutôt qu'une contrainte de colonne, pour une
            # raison qui commande : SQLite ne sait pas ajouter UNIQUE à une
            # colonne existante, alors que CREATE UNIQUE INDEX IF NOT EXISTS
            # s'applique à une table déjà peuplée et reste idempotent. La
            # promesse de migration additive (point 32) est donc tenue.
            f"_UNIQUE_INDEXES = {self._compute_unique_indexes()!r}\n",
            "# Unicités métier multi-colonnes (ex. un vote par compte et par entrée).\n",
            f"_ONCE_PER_INDEXES = {self._compute_once_per_indexes()!r}\n",
            # POINT 89 : les colonnes horodatées, pour que le démarrage puisse
            # DIRE combien d'enregistrements n'auront jamais de date. Voir le
            # bloc de migration : c'est le seul cas du compilateur où une
            # colonne ajoutée ne peut pas être rattrapée.
            f"_TIMESTAMP_COLUMNS = {self._compute_timestamp_columns()!r}\n",
            f"_NUMBERED_COLUMNS = {self._compute_numbered_columns()!r}\n",
            "security_bearer = HTTPBearer()\n",
            # CORRECTIF (roadmap, révocation de token) : la vérification du
            # token est centralisée dans une seule fonction, appelée par les
            # deux dépendances ci-dessous — avant, chacune redécodait le token
            # indépendamment, ce qui aurait pu faire oublier la vérification
            # de révocation dans l'une des deux lors d'une future modification.
            "# CORRECTIF (bêta 3) : purge des jetons révoqués déjà expirés — leur",
            "# signature n'est plus acceptée de toute façon, les garder ne faisait",
            "# que gonfler la table consultée à chaque requête authentifiée.",
            "def _purge_revoked_tokens(cursor):",
            "    cursor.execute('DELETE FROM _monl_revoked_tokens WHERE expires_at IS NOT NULL AND expires_at < ?',",
            "                   (datetime.datetime.now(datetime.timezone.utc).timestamp(),))\n",
            "def _decode_and_verify_token(credentials: HTTPAuthorizationCredentials) -> dict:",
            "    try:",
            "        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])",
            "    except jwt.PyJWTError:",
            "        raise HTTPException(status_code=401, detail='Token invalide ou expiré')",
            "    jti = payload.get('jti')",
            "    if jti:",
            "        conn = _connect(); cursor = conn.cursor()",
            "        cursor.execute('SELECT 1 FROM _monl_revoked_tokens WHERE jti = ?', (jti,))",
            "        revoked = cursor.fetchone(); conn.close()",
            "        if revoked:",
            "            raise HTTPException(status_code=401, detail='Ce token a été révoqué (déconnexion effectuée).')",
            "    return payload\n",

            "def verify_jwt_and_get_actor(credentials: HTTPAuthorizationCredentials = Depends(security_bearer)) -> str:",
            "    return _decode_and_verify_token(credentials).get('actor')\n",

            # AJOUT (post-v6, roadmap) : dépendance séparée pour récupérer l'identité
            # numérique (user_id) portée par le token, utilisée par le contrôle
            # d'accès par propriété ('ownedBy') et par le peuplement automatique
            # des colonnes de clé étrangère à la création d'un enregistrement.
            "def get_current_user_id(credentials: HTTPAuthorizationCredentials = Depends(security_bearer)) -> int:",
            "    return _decode_and_verify_token(credentials).get('user_id', 0)\n",

            # AJOUT (roadmap, écosystème de capacités -- suite de la brique 1) :
            # dépendance séparée pour récupérer le pseudonyme anonyme stable
            # du compte courant, utilisée par les champs 'generated' -- déjà
            # porté par le JWT depuis /login (voir plus bas), pas besoin
            # d'une requête DB supplémentaire à chaque appel.
            "def get_current_anon_handle(credentials: HTTPAuthorizationCredentials = Depends(security_bearer)) -> str:",
            "    return _decode_and_verify_token(credentials).get('anon_handle', '')\n",
        ]
        # POINT 116 : identité FACULTATIVE, et elle n'existe que pour les
        # lectures publiques conditionnées ('publicWhen'). Une route publique
        # ne doit JAMAIS répondre 401 : un jeton absent, invalide ou révoqué
        # laisse simplement l'appelant anonyme. Cette dépendance ne peut donc
        # que DONNER des droits (superviseur, propriétaire), jamais en retirer
        # — c'est ce qui la rend sûre sur une route ouverte à tous. Émise
        # seulement si une EXEMPTION existe (`_condition_exemptions`, source
        # unique) : sans superviseur ni propriétaire, aucune route ne l'appelle
        # et l'app.py produit reste celui d'avant le point 116.
        if self._condition_identity_needed():
            api_lines += [
                "def get_optional_identity(request: Request) -> dict:",
                "    _auth = request.headers.get('authorization') or ''",
                "    if not _auth.lower().startswith('bearer '):",
                "        return {}",
                "    _creds = HTTPAuthorizationCredentials(scheme='Bearer', credentials=_auth[7:].strip())",
                "    try:",
                "        return _decode_and_verify_token(_creds)",
                "    except HTTPException:",
                "        return {}\n",
            ]
        api_lines += [
            # CORRECTIF (bêta 3) : '@app.on_event' est déprécié par Starlette et
            # disparaîtra ; le cycle de vie passe par un gestionnaire 'lifespan'.
            # init_db() ouvre volontairement une connexion SANS contrainte de clé
            # étrangère : création du schéma, migrations additives et données de
            # démonstration doivent pouvoir s'exécuter dans n'importe quel ordre.
            "def init_db():",
            "    conn = sqlite3.connect(DB_FILE, timeout=10.0)",
            "    conn.execute('PRAGMA journal_mode = WAL')",
            "    try:",
            "        with open('schema.sql', 'r', encoding='utf-8') as f:",
            "            conn.executescript(f.read())",
            "    except Exception as e:",
            "        print(f'ℹ️ DB déjà initialisée ou erreur de script: {e}')",
            "    # AJOUT (roadmap long terme, migrations sans perte de données) :",
            "    # après le CREATE TABLE IF NOT EXISTS (qui ne modifie jamais une",
            "    # table déjà présente), on rattrape les colonnes ajoutées à la",
            "    # spec depuis la dernière compilation. Pour chaque table, on",
            "    # compare les colonnes attendues aux colonnes réelles",
            "    # (PRAGMA table_info) et on ajoute les manquantes par ALTER TABLE",
            "    # ADD COLUMN — opération purement additive : aucune donnée",
            "    # existante n'est lue, déplacée ou supprimée. Les colonnes",
            "    # retirées de la spec sont laissées en place (SQLite ne supporte",
            "    # pas DROP COLUMN sans reconstruction, et les supprimer",
            "    # détruirait des données — voir docs/MIGRATIONS.md).",
            "    try:",
            "        _cur = conn.cursor()",
            "        for _table, _cols in _EXPECTED_COLUMNS.items():",
            "            _cur.execute('SELECT name FROM sqlite_master WHERE type=\"table\" AND name=?', (_table,))",
            "            if _cur.fetchone() is None:",
            "                continue  # table absente : le CREATE l'a déjà couverte, ou spec sans données",
            "            _cur.execute(f'PRAGMA table_info(\"{_table}\")')",
            "            _existing = {_row[1] for _row in _cur.fetchall()}",
            "            for _col, _sql_type in _cols:",
            "                if _col not in _existing:",
            "                    _cur.execute(f'ALTER TABLE \"{_table}\" ADD COLUMN \"{_col}\" {_sql_type}')",
            "                    print(f'🔧 Migration : colonne \"{_col}\" ajoutée à \"{_table}\" ({_sql_type}).')",
            "        conn.commit()",
            "    except Exception as e:",
            "        print(f'⚠️ Migration additive ignorée : {e}')",
            # POINT 85 : les index uniques, APRÈS la migration additive (la
            # colonne à indexer peut venir d'être ajoutée). Chacun dans son
            # propre try : un échec doit nommer SON champ, pas faire taire les
            # suivants. Sur une base qui contient déjà des doublons, l'index ne
            # peut pas être créé -- c'est un changement non automatisable
            # (docs/MIGRATIONS.md), donc on le DIT au lieu de l'avaler.
            "    for _table, _col, _index in _UNIQUE_INDEXES:",
            "        try:",
            "            conn.execute(f'CREATE UNIQUE INDEX IF NOT EXISTS \"{_index}\" ON \"{_table}\" (\"{_col}\")')",
            "            conn.commit()",
            "        except sqlite3.IntegrityError:",
            "            _dups = conn.execute(f'SELECT COUNT(*) FROM (SELECT \"{_col}\" FROM \"{_table}\" GROUP BY \"{_col}\" HAVING COUNT(*) > 1)').fetchone()[0]",
            "            print(f'❌ \"{_table}\".\"{_col}\" est déclaré unique dans la spec, mais la base contient déjà {_dups} valeur(s) en double : l\\'unicité NE PEUT PAS être appliquée. Dédoublonner, puis redémarrer (docs/MIGRATIONS.md).')",
            "        except Exception as e:",
            "            print(f'⚠️ Index unique sur \"{_table}\".\"{_col}\" ignoré : {e}')",
            "    for _table, _cols, _index in _ONCE_PER_INDEXES:",
            "        try:",
            "            _columns = ', '.join(f'\"{_col}\"' for _col in _cols)",
            "            conn.execute(f'CREATE UNIQUE INDEX IF NOT EXISTS \"{_index}\" ON \"{_table}\" ({_columns})')",
            "            conn.commit()",
            "        except sqlite3.IntegrityError:",
            "            _columns = ', '.join(f'\"{_col}\"' for _col in _cols)",
            "            print(f'❌ Unicité métier déjà violée sur \"{_table}\" ({_columns}) : corriger les doublons avant de redémarrer.')",
            "        except Exception as e:",
            "            print(f'⚠️ Index oncePer sur \"{_table}\" ignoré : {e}')",
            # POINT 89 : la migration additive rattrape une colonne, jamais son
            # contenu. Pour toutes les autres briques ça n'a aucune importance
            # (une colonne vide est une colonne vide) ; pour une date de
            # création, c'est irréparable — l'instant est passé et le serveur ne
            # l'a pas vu. La remplir avec l'heure du démarrage daterait toutes
            # les vieilles commandes d'aujourd'hui : ce serait une base de
            # données qui MENT, ce qui est pire que des cases vides. On compte,
            # on nomme, et on laisse à NULL.
            "    for _table, _col in _TIMESTAMP_COLUMNS:",
            "        try:",
            "            _sans = conn.execute(f'SELECT COUNT(*) FROM \"{_table}\" WHERE \"{_col}\" IS NULL').fetchone()[0]",
            "            if _sans:",
            "                print(f'ℹ️ \"{_table}\".\"{_col}\" : {_sans} enregistrement(s) créé(s) avant l\\'ajout de l\\'horodatage restent sans date. Elle ne peut pas être reconstituée — les dater après coup serait faux.')",
            "        except Exception:",
            "            pass  # table absente : rien à compter",
            # POINT 102 : même constat, même raison, sur les numéros lisibles.
            # Numéroter après coup prétendrait un ordre d'arrivée que le serveur
            # n'a pas observé — et sur un carnet de commandes, un numéro inventé
            # se retrouve sur une facture.
            "    for _table, _col in _NUMBERED_COLUMNS:",
            "        try:",
            "            _sans = conn.execute(f'SELECT COUNT(*) FROM \"{_table}\" WHERE \"{_col}\" IS NULL').fetchone()[0]",
            "            if _sans:",
            "                print(f'ℹ️ \"{_table}\".\"{_col}\" : {_sans} enregistrement(s) créé(s) avant l\\'ajout de la numérotation restent sans numéro. La séquence repart de 1 ; leur attribuer un numéro maintenant inventerait un ordre d\\'arrivée.')",
            "        except Exception:",
            "            pass  # table absente : rien à compter",
            # POINT 95 : même honnêteté que ci-dessus, sur les comptes. Déclarer
            # 'identifier: email' n'efface pas les comptes ouverts avant : ils
            # existent, leur mot de passe est valide, et ils continuent de se
            # connecter. Les convertir serait impossible (on n'invente pas une
            # adresse) et les supprimer serait pire. On les COMPTE et on le dit
            # — sans quoi l'auteur croirait sa règle appliquée partout.
            "    if AUTH_IDENTIFIER_FORMS and 'libre' not in AUTH_IDENTIFIER_FORMS:",
            "        try:",
            "            _anciens = [r[0] for r in conn.execute('SELECT username FROM _monl_users').fetchall()]",
            "            _hors = [u for u in _anciens if not _forme_valide(u)]",
            "            if _hors:",
            "                print(f'ℹ️ {len(_hors)} compte(s) existant(s) ne suivent pas la forme d\\'identifiant déclarée ({\", \".join(AUTH_IDENTIFIER_FORMS)}) : {\", \".join(_hors[:5])}{\"…\" if len(_hors) > 5 else \"\"}. Ils continuent de fonctionner ; la règle ne vaut que pour les inscriptions à venir.')",
            "        except Exception:",
            "            pass",
            "    # AJOUT (roadmap frontend, bloc 'seed') : insertion des données de",
            "    # démonstration si (et seulement si) la table est VIDE — idempotent,",
            "    # donc un redémarrage n'empile pas les doublons, et des données",
            "    # réelles créées par l'utilisateur ne sont jamais écrasées.",
            "    try:",
            "        _scur = conn.cursor()",
            "        for _table, _rows in _SEED_DATA.items():",
            "            _scur.execute(f'SELECT COUNT(*) FROM \"{_table}\"')",
            "            if _scur.fetchone()[0] > 0:",
            "                continue  # déjà des données : on ne touche à rien",
            "            _poses = 0",
            "            for _entree in _rows:",
            "                _row = dict(_entree['values'])",
            # BRIQUE 21 (point 100) : le rattachement se résout ICI, par une
            # lecture du parent, et jamais par un rang calculé à la compilation.
            # Le parent peut avoir été semé à l'instant (cas normal) comme
            # préexister dans une base déjà peuplée : dans les deux cas c'est son
            # `id` réel qu'on écrit.
            "                _p = _entree.get('parent')",
            "                if _p:",
            "                    _scur.execute(f'SELECT id FROM \"{_p[\"table\"]}\" WHERE \"{_p[\"field\"]}\" = ?', (_p['value'],))",
            "                    _cible = _scur.fetchone()",
            "                    if not _cible:",
            # Jamais en silence : une vitrine amputée sans un mot enverrait
            # chercher la panne dans le frontend.
            "                        print(f'⚠️ Donnée de démonstration ignorée : aucun \"{_p[\"table\"]}\" dont {_p[\"field\"]} vaut \"{_p[\"value\"]}\" pour y rattacher une ligne de \"{_table}\".')",
            "                        continue",
            "                    _row[_p['column']] = _cible[0]",
            "                _cols = list(_row.keys())",
            "                _placeholders = ', '.join(['?'] * len(_cols))",
            "                _colnames = ', '.join(f'\"{_c}\"' for _c in _cols)",
            "                _scur.execute(f'INSERT INTO \"{_table}\" ({_colnames}) VALUES ({_placeholders})', tuple(_row.values()))",
            "                _poses += 1",
            "            if _poses:",
            "                print(f'🌱 Données de démonstration insérées dans \"{_table}\" ({_poses}).')",
            "        conn.commit()",
            "    except Exception as e:",
            "        print(f'⚠️ Données de démonstration ignorées : {e}')",
            "    # CORRECTIF (bêta 3) : migration de la table système des jetons",
            "    # révoqués (colonne 'expires_at' ajoutée en bêta 3), pour qu'une",
            "    # base créée par une version antérieure continue de fonctionner.",
            "    try:",
            "        _sys_cur = conn.cursor()",
            "        _sys_cur.execute('PRAGMA table_info(_monl_revoked_tokens)')",
            "        if 'expires_at' not in {_r[1] for _r in _sys_cur.fetchall()}:",
            "            _sys_cur.execute('ALTER TABLE _monl_revoked_tokens ADD COLUMN expires_at REAL')",
            "        _purge_revoked_tokens(_sys_cur)",
            "        conn.commit()",
            "    except Exception as e:",
            "        print(f'⚠️ Migration système ignorée : {e}')",
            "    finally:",
            "        conn.close()\n",

            "@asynccontextmanager",
            "async def _lifespan(_app: FastAPI):",
            "    init_db()",
            "    yield\n",
            # CORRECTIF (bêta 3) : '/docs' et '/openapi.json' publiaient la
            # surface complète de l'API en toutes circonstances. Indispensable
            # en développement, rarement souhaitable en déploiement :
            # MONL_DOCS=off les désactive sans toucher au code généré.
            "_docs_actives = os.environ.get('MONL_DOCS', 'on').lower() != 'off'",
            f"app = FastAPI(title='{self.app_name} - Secure Core', lifespan=_lifespan,",
            "               docs_url='/docs' if _docs_actives else None,",
            "               redoc_url='/redoc' if _docs_actives else None,",
            "               openapi_url='/openapi.json' if _docs_actives else None)\n",

            # Déploiement : CORS est opt-in. Une liste explicite est la seule
            # forme acceptée ; '*' ouvrirait l'API à n'importe quelle origine.
            "_CORS_ORIGINS = [origin.strip() for origin in os.environ.get(",
            "    'MONL_CORS_ORIGINS', '').split(',') if origin.strip()]",
            "if '*' in _CORS_ORIGINS:",
            "    raise RuntimeError(",
            "        \"MONL_CORS_ORIGINS refuse l'origine '*' : listez des origines \"",
            "        'explicites, séparées par des virgules.'",
            "    )",
            "if _CORS_ORIGINS:",
            "    from fastapi.middleware.cors import CORSMiddleware",
            "    app.add_middleware(",
            "        CORSMiddleware,",
            "        allow_origins=_CORS_ORIGINS,",
            "        allow_credentials=True,",
            f"        allow_methods={self._cors_methods()!r},",
            "        allow_headers=['Authorization', 'Content-Type', 'X-Request-ID'],",
            "        expose_headers=['X-Request-ID'],",
            "    )\n",

            # Healthchecks infra : ils ne sont ni dans les workflows ni dans
            # le contrat frontend. La vivacité ne touche jamais SQLite ; la
            # readiness exécute une seule requête triviale.
            "@app.get('/health', include_in_schema=False)",
            "def health():",
            "    return {'status': 'ok'}\n",
            "@app.get('/health/ready', include_in_schema=False)",
            "def health_ready():",
            "    conn = None",
            "    try:",
            "        conn = _connect()",
            "        conn.execute('SELECT 1')",
            "        return {'status': 'ready'}",
            "    except Exception:",
            "        raise HTTPException(status_code=503, detail='Service indisponible') from None",
            "    finally:",
            "        if conn is not None:",
            "            conn.close()\n",

            # Logs structurés opt-in. Aucun corps ni en-tête entrant n'est
            # copié dans le journal ; le chemin est privé de sa query string.
            "_LOG_JSON = os.environ.get('MONL_LOG_FORMAT', '').strip().lower() == 'json'",
            "_REQUEST_ID_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$')",
            "def _request_id(request):",
            "    candidate = request.headers.get('x-request-id', '')",
            "    if _REQUEST_ID_RE.fullmatch(candidate):",
            "        return candidate",
            "    return secrets.token_hex(16)\n",
            "def _write_request_log(request, request_id, status_code, started):",
            "    print(json.dumps({",
            "        'timestamp': datetime.datetime.now(datetime.timezone.utc).isoformat(),",
            "        'method': request.method,",
            "        'path': request.url.path,",
            "        'status_code': status_code,",
            "        'duration_ms': round((time.perf_counter() - started) * 1000, 3),",
            "        'request_id': request_id,",
            "    }, ensure_ascii=False), flush=True)\n",
            "if _LOG_JSON:",
            "    @app.middleware('http')",
            "    async def _structured_request_log(request: Request, call_next):",
            "        started = time.perf_counter()",
            "        request_id = _request_id(request)",
            "        try:",
            "            response = await call_next(request)",
            "        except Exception:",
            "            _write_request_log(request, request_id, 500, started)",
            "            raise",
            "        response.headers['X-Request-ID'] = request_id",
            "        _write_request_log(request, request_id, response.status_code, started)",
            "        return response\n",

            # Redirection de la racine vers la documentation Swagger/OpenAPI
            # auto-générée par FastAPI — le seul front que monl fournit
            # encore (pivot, point 41) : l'interface réelle vient de l'IA
            # frontend, servie sur '/site' par 'monl run' (wrapper serve.py).
            "from fastapi.responses import RedirectResponse\n",
            "@app.get('/', include_in_schema=False)",
            "async def root():",
            "    return RedirectResponse(url='/docs')\n",
        ]

        api_lines += [

            # CORRECTIF (roadmap) : remplacement du modèle "actor/user_id
            # auto-déclarés par le client" par un vrai registre d'utilisateurs
            # (table _monl_users, mot de passe haché avec sel via PBKDF2-
            # HMAC-SHA256, 100 000 itérations — pas de dépendance externe type
            # bcrypt nécessaire). LIMITE ASSUMÉE (prototype) : pas de politique
            # de mot de passe, pas de vérification d'email, pas de récupération
            # de compte — voir docs/design_decisions.md.
            "class RegisterRequest(BaseModel):",
            "    username: str",
            "    password: str",
            "    actor: str\n",
        ]

        # ── POINT 95 : la forme de l'identifiant de compte ──────────────
        # Le champ reste nommé 'username' SUR LE FIL. Le renommer en 'email'
        # aurait cassé le formulaire d'inscription de tout projet existant,
        # pour un gain cosmétique ; c'est le CONTRAT qui dit désormais quelle
        # forme il attend, et l'IA d'interface qui étiquette le champ.
        #
        # LA substance de la brique n'est pas la validation, c'est la
        # NORMALISATION. 'Jean@Ex.com' et 'jean@ex.com' sont la même boîte,
        # '06 12 34 56 78' et '+33612345678' le même numéro : sans forme
        # canonique, le contrôle d'unicité est contournable (deux comptes pour
        # une personne) et la connexion échoue selon la façon dont on tape.
        api_lines += self._generate_identifier_helpers()

        api_lines += [
            "def _hash_password(password: str, salt_hex: str) -> str:",
            "    return hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), bytes.fromhex(salt_hex), 100_000).hex()\n",
            "# CORRECTIF (bêta 3, énumération de comptes par canal temporel) :",
            "# '/login' renvoyait 401 immédiatement quand le compte n'existait pas,",
            "# sans dérouler les 100 000 itérations PBKDF2 — l'écart de temps de",
            "# réponse (~100 ms) révélait quels noms d'utilisateur existent.",
            "# On hache donc toujours, contre ce sel factice fixe le cas échéant.",
            "_DUMMY_SALT_HEX = '6d6f6e6c2d64756d6d792d73616c742d'",
            "_DUMMY_HASH = _hash_password('monl-dummy-password', _DUMMY_SALT_HEX)\n",

            # CORRECTIF (roadmap) : limitation de débit généralisée à un
            # nom de "bucket" (au lieu d'être câblée uniquement pour /login),
            # pour pouvoir protéger /register également — sans ça, /register
            # pouvait être utilisée pour créer des comptes en masse ou pour
            # énumérer les noms d'utilisateur déjà pris (via le code 409).
            # LIMITE ASSUMÉE (prototype) : compteur en mémoire du processus,
            # non distribué, remis à zéro au redémarrage du serveur —
            # suffisant pour freiner un script naïf, pas une attaque distribuée
            # à grande échelle (nécessiterait Redis ou équivalent en prod).
            "RATE_LIMIT_WINDOW_SECONDS = 60",
            "RATE_LIMIT_MAX_ATTEMPTS = 5\n",
            "# AJOUT (bêta, déploiement derrière un proxy) : par défaut on utilise",
            "# l'IP de la connexion directe (request.client.host). Si l'application",
            "# tourne derrière un reverse proxy de confiance (nginx, Traefik...),",
            "# activer MONL_TRUST_PROXY=1 fait lire la première IP de l'en-tête",
            "# X-Forwarded-For — sinon un client direct pourrait usurper cet en-tête",
            "# pour contourner la limitation de débit. On ne fait donc confiance à",
            "# l'en-tête QUE si l'opérateur l'a explicitement autorisé.",
            "_TRUST_PROXY = os.environ.get('MONL_TRUST_PROXY', '').lower() in ('1', 'true', 'yes')",
            "def _client_ip(request: Request) -> str:",
            "    if _TRUST_PROXY:",
            "        fwd = request.headers.get('x-forwarded-for')",
            "        if fwd:",
            "            return fwd.split(',')[0].strip() or 'unknown'",
            "    return request.client.host if request.client else 'unknown'\n",
            "# AJOUT (roadmap long terme, rate limiting multi-workers) : compteur",
            "# de tentatives persisté en base plutôt qu'en mémoire de processus,",
            "# pour que le quota soit partagé par tous les workers uvicorn/gunicorn",
            "# (voir _monl_rate_limit dans schema.sql). Fenêtre glissante :",
            "# on compte les tentatives récentes, on purge les anciennes, puis on",
            "# enregistre la tentative courante.",
            "# CORRECTIF (bêta 3, TOCTOU) : le comptage et l'enregistrement de la",
            "# tentative se faisaient en deux exécutions autocommit distinctes —",
            "# N requêtes parallèles lisaient toutes le même compteur avant que",
            "# l'une d'elles ne l'incrémente, et passaient donc toutes le quota.",
            "# Le tout est désormais dans une transaction en écriture immédiate :",
            "# SQLite sérialise les writers, le quota redevient exact, y compris",
            "# entre workers puisqu'il est persisté en base.",
            "def _check_rate_limit(bucket: str, client_ip: str):",
            "    now = datetime.datetime.now(datetime.timezone.utc).timestamp()",
            "    cutoff = now - RATE_LIMIT_WINDOW_SECONDS",
            "    conn = _connect(); conn.isolation_level = None; cursor = conn.cursor()",
            "    try:",
            "        cursor.execute('BEGIN IMMEDIATE')",
            "        cursor.execute('DELETE FROM _monl_rate_limit WHERE attempted_at < ?', (cutoff,))",
            "        cursor.execute('SELECT COUNT(*) FROM _monl_rate_limit WHERE bucket = ? AND client_ip = ? AND attempted_at >= ?', (bucket, client_ip, cutoff))",
            "        recent = cursor.fetchone()[0]",
            "        if recent >= RATE_LIMIT_MAX_ATTEMPTS:",
            "            cursor.execute('COMMIT')",
            "            raise HTTPException(status_code=429, detail=f'Trop de tentatives ({bucket}). "
            "Réessayez dans {RATE_LIMIT_WINDOW_SECONDS} secondes.')",
            "        cursor.execute('INSERT INTO _monl_rate_limit (bucket, client_ip, attempted_at) VALUES (?, ?, ?)', (bucket, client_ip, now))",
            "        cursor.execute('COMMIT')",
            "    finally:",
            "        conn.close()\n",

            "@app.post('/register', tags=['Authentication'])",
            "def register(req: RegisterRequest, request: Request):",
            "    _check_rate_limit('register', _client_ip(request))",
            "    if req.actor not in VALID_ACTORS:",
            "        raise HTTPException(status_code=400, detail=f\"Acteur invalide. Acteurs valides : {VALID_ACTORS}\")",
            "    if req.actor not in SELF_REGISTER_ACTORS:",
            "        raise HTTPException(status_code=403, detail=(",
            "            f\"Le rôle '{req.actor}' n'est pas ouvert à l'inscription libre. \"",
            "            'Les comptes de ce rôle sont créés hors ligne : python3 manage.py adduser.'",
            "        ))",
            "    if len(req.password) < 8:",
            "        raise HTTPException(status_code=400, detail='Le mot de passe doit contenir au moins 8 caractères.')",
            "    if len(req.password) > 256:",
            "        raise HTTPException(status_code=400, detail='Mot de passe trop long (256 caractères maximum).')",
            # POINT 95 : la forme est contrôlée AVANT toute écriture, et la
            # valeur normalisée AVANT le contrôle d'unicité — l'inverse
            # laisserait 'Jean@Ex.com' passer à côté de 'jean@ex.com'.
            "    _identifiant = _normalize_identifier(req.username)",
            "    _check_identifier(_identifiant)",
            "    conn = _connect(); cursor = conn.cursor()",
            "    cursor.execute('SELECT id FROM _monl_users WHERE username = ?', (_identifiant,))",
            "    if cursor.fetchone():",
            "        conn.close()",
            # Le message doit nommer ce qui est réellement en conflit : sur une
            # inscription par e-mail, « ce nom d'utilisateur » ne veut rien dire
            # — et le conflit est souvent invisible pour l'appelant, puisqu'il
            # porte sur la forme NORMALISÉE de ce qu'il a tapé.
            "        raise HTTPException(status_code=409, detail=_conflit_identifiant())",
            "    salt_hex = os.urandom(16).hex()",
            "    pwd_hash = _hash_password(req.password, salt_hex)",
            # AJOUT (roadmap, écosystème de capacités -- suite de la brique 1) :
            # pseudonyme anonyme stable, généré une seule fois ici (jamais
            # recalculé, jamais fourni par le client) -- 'Anon#' suivi de 4
            # chiffres aléatoires, avec quelques tentatives en cas de
            # collision (contrainte UNIQUE sur la colonne) plutôt qu'un échec
            # d'inscription pour une coïncidence statistiquement rare.
            "    anon_handle = None",
            "    for _ in range(10):",
            "        _candidate = f'Anon#{secrets.randbelow(9000) + 1000}'",
            "        cursor.execute('SELECT 1 FROM _monl_users WHERE anon_handle = ?', (_candidate,))",
            "        if not cursor.fetchone():",
            "            anon_handle = _candidate",
            "            break",
            "    if anon_handle is None:",
            "        conn.close()",
            "        raise HTTPException(status_code=500, detail='Impossible de générer un pseudonyme unique, réessayez.')",
            "    cursor.execute('INSERT INTO _monl_users (username, password_hash, salt, actor, anon_handle) VALUES (?, ?, ?, ?, ?)',",
            "                   (_identifiant, pwd_hash, salt_hex, req.actor, anon_handle))",
            "    conn.commit(); new_user_id = cursor.lastrowid; conn.close()",
            "    return {'status': 'success', 'user_id': new_user_id}\n",

            "class LoginRequest(BaseModel):",
            "    username: str",
            "    password: str\n",

            "@app.post('/login', tags=['Authentication'])",
            "def login(req: LoginRequest, request: Request):",
            "    _check_rate_limit('login', _client_ip(request))",
            # POINT 95 : MÊME normalisation qu'à l'inscription, et c'est la
            # moitié qui compte. Normaliser d'un seul côté crée des comptes
            # auxquels on ne peut plus se connecter — la casse d'une adresse ne
            # se retient pas. Aucun contrôle de FORME ici en revanche : un
            # identifiant mal formé n'existe simplement pas en base, et le 401
            # habituel répond sans révéler la règle.
            "    _identifiant = _normalize_identifier(req.username)",
            "    conn = _connect(); cursor = conn.cursor()",
            "    cursor.execute('SELECT id, password_hash, salt, actor, anon_handle FROM _monl_users WHERE username = ?', (_identifiant,))",
            "    row = cursor.fetchone(); conn.close()",
            "    if not row:",
            "        hmac.compare_digest(_hash_password(req.password[:256], _DUMMY_SALT_HEX), _DUMMY_HASH)",
            "        raise HTTPException(status_code=401, detail='Identifiants invalides.')",
            "    db_user_id, stored_hash, salt_hex, actor, anon_handle = row",
            "    if not hmac.compare_digest(_hash_password(req.password, salt_hex), stored_hash):",
            "        raise HTTPException(status_code=401, detail='Identifiants invalides.')",
            "    payload = {",
            "        'sub': _identifiant,",
            "        'actor': actor,",
            "        'user_id': db_user_id,",
            # AJOUT (roadmap, écosystème de capacités -- suite de la brique 1) :
            # porté par le JWT comme 'actor'/'user_id', pour que les champs
            # 'generated' n'aient jamais besoin d'une requête DB séparée.
            "        'anon_handle': anon_handle,",
            # AJOUT (roadmap, révocation de token) : identifiant unique par
            # token (jti), nécessaire pour pouvoir le révoquer individuellement
            # via /logout sans avoir à invalider tous les tokens de l'utilisateur.
            "        'jti': secrets.token_hex(16),",
            "        'exp': datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=TOKEN_TTL_HOURS)",
            "    }",
            "    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)",
            "    return {'access_token': token, 'token_type': 'bearer'}\n",

            # AJOUT (roadmap, révocation de token) : /logout enregistre le jti
            # du token courant dans une liste noire persistante — toute
            # présentation ultérieure de ce même token est alors rejetée,
            # même s'il n'a pas encore atteint sa date d'expiration naturelle.
            "@app.post('/logout', tags=['Authentication'])",
            "def logout(credentials: HTTPAuthorizationCredentials = Depends(security_bearer)):",
            "    payload = _decode_and_verify_token(credentials)",
            "    jti = payload.get('jti')",
            "    if not jti:",
            "        raise HTTPException(status_code=400, detail='Ce token ne supporte pas la révocation (jti manquant).')",
            "    conn = _connect(); cursor = conn.cursor()",
            "    cursor.execute('INSERT OR IGNORE INTO _monl_revoked_tokens (jti, revoked_at, expires_at) VALUES (?, ?, ?)',",
            "                   (jti, datetime.datetime.now(datetime.timezone.utc).isoformat(), payload.get('exp')))",
            "    _purge_revoked_tokens(cursor)",
            "    conn.commit(); conn.close()",
            "    return {'status': 'success', 'detail': 'Token révoqué.'}\n",
            "# --- VALIDATION STRICTE DES DONNÉES CRUD (PYDANTIC) ---"
        ]
        return api_lines
