# Journal des modifications

## 0.9.0-beta.3 — Correctifs d'audit et découpage du générateur

### Sécurité (seconde relecture, avant test externe)

- **`ownedBy` ne protégeait que l'écriture (fuite de données entre comptes).**
  `rule X.Update ownedBy A` restreignait bien la modification, mais `GET /x`
  renvoyait les enregistrements de *tous* les comptes à n'importe quel appelant
  autorisé, et `GET /x/{id}` répondait 200 sur l'enregistrement d'autrui. Sur le
  modèle « suivi de dépenses personnelles », dont le catalogue promet que chacun
  ne voit que les siennes, deux comptes suffisaient à se lire mutuellement.
  `ownedBy` filtre désormais la lecture — pour le seul acteur désigné
  propriétaire : un rôle tiers autorisé (gestionnaire de boutique face aux
  commandes, responsable face aux tâches) continue de tout voir. L'accès direct
  répond 404 et non 403, pour ne pas confirmer l'existence d'un enregistrement
  qu'on n'a pas le droit de lire.
- **Une règle sans effet est refusée à la compilation.** `rule X.Read ownedBy A`
  compilait sans rien produire, et `rule X.Create ownedBy A` était accepté alors
  que le générateur n'en fait rien : une règle de sécurité silencieusement
  ignorée est pire que son absence, l'auteur croyant la protection en place.
- **Bornes de taille sur les champs texte** : une chaîne de plusieurs Mo était
  acceptée et écrite en base. La borne Pydantic reflète la colonne SQL
  (255 / 320 pour Email / 20 000 pour Text), le refus arrive en 422.
- **`/docs` et `/openapi.json` désactivables** par `MONL_DOCS=off`.
- **Durée de jeton unifiée** : 2 h dans le code contre « 1 h » annoncée dans le
  contrat frontend. Valeur unique, réglable par `MONL_TOKEN_TTL_HOURS`, publiée
  telle quelle dans le contrat.
- **La CI exécute enfin le frontend** : sans Node.js sur le runner, le smoke
  test jsdom se dégradait en avertissement — la garantie la plus forte du projet
  ne s'exécutait jamais en intégration continue. Le paquet est aussi installé
  par `pip install -e .` et la commande `monl` est éprouvée.

Audit externe du dépôt bêta 2 : une faille critique, cinq défauts importants et
un défaut de déterminisme. Tous corrigés, chacun accompagné d'un test de
non-régression (`tests/test_beta3_regressions.py`).

### Sécurité

- **Élévation de privilège par l'inscription (critique).** `POST /register`
  acceptait n'importe quel rôle déclaré, choisi par le client : sur la boutique
  d'exemple, deux appels HTTP anonymes suffisaient à obtenir un compte
  `ShopManager` et à écrire dans le catalogue. Le rôle porté par le jeton venait
  bien du compte réel — mais ce compte se choisissait lui-même son rôle. Le DSL
  gagne un marqueur explicite : `actor Customer selfRegister` ouvre
  l'inscription libre, `actor ShopManager` (sans marqueur) ne l'ouvre pas. Refus
  par défaut : une spec qui oublie le marqueur ferme l'inscription au lieu de
  l'ouvrir en grand. Le compilateur affiche le périmètre retenu à chaque
  compilation, le contrat frontend le publie (`self_register_actors`) et le
  smoke test tente l'inscription d'un rôle provisionné à chaque lancement.
- **Provisionnement hors ligne.** Chaque compilation produit désormais
  `manage.py` (`adduser`, `setactor`, `passwd`, `users`, `revoke-all`) : les
  rôles privilégiés se créent sur la machine qui héberge la base, jamais par
  HTTP. `revoke-all` renouvelle le secret et invalide toutes les sessions.
- **Énumération de comptes par canal temporel.** `/login` répondait 401 sans
  dérouler les 100 000 itérations PBKDF2 quand l'identifiant n'existait pas ;
  l'écart de temps de réponse (~100 ms) révélait quels comptes existent. Un
  hachage factice est désormais toujours calculé.
- **Quota de tentatives contournable (TOCTOU).** Comptage et enregistrement se
  faisaient en deux exécutions autocommit distinctes : N requêtes parallèles
  lisaient le même compteur et franchissaient toutes le quota. Le tout est
  passé en transaction `BEGIN IMMEDIATE`.
- **Secret de signature lisible par tous.** `.jwt_secret` était créé avec les
  permissions par défaut (0644) : n'importe quel compte local pouvait lire la
  clé et forger des jetons. Création en 0600, et resserrage des permissions
  d'un projet existant à la recompilation.
- **Liste noire de jetons sans purge.** `_monl_revoked_tokens` grossissait
  indéfiniment et était consultée à chaque requête authentifiée. Colonne
  `expires_at` (avec migration de la table système) et purge des jetons déjà
  expirés — leur signature est de toute façon refusée.

### Fiabilité

- **Intégrité référentielle réellement appliquée.** SQLite ignore les clés
  étrangères par défaut : celles déclarées dans `schema.sql` n'étaient jamais
  vérifiées. Toutes les connexions de requête passent par `_connect()`
  (`PRAGMA foreign_keys`, `busy_timeout`, WAL). Une violation devient un 409
  explicite au lieu d'un 500.
- **Boucle d'événements bloquée.** Les handlers étaient `async def` alors que
  tous les appels SQLite sont bloquants : chaque requête gelait la boucle. Ils
  sont désormais synchrones, donc exécutés par le pool de threads de FastAPI.
- **Déterminisme.** La liste des acteurs transitait par un `set` : l'ordre
  dépendait de `PYTHONHASHSEED` et `VALID_ACTORS` pouvait changer d'une
  compilation à l'autre — la garantie « même spec, même backend à l'octet
  près » était fausse. Ordre de déclaration conservé, ensembles restants
  triés, et test de reproductibilité entre deux processus aux graines opposées.
- `@app.on_event('startup')` (déprécié) remplacé par un gestionnaire
  `lifespan` ; mot de passe borné à 256 caractères à l'inscription.

### Architecture

- `src/generator.py` (1 307 lignes) découpé en package `src/generator/` :
  `core` (état et orchestration), `runtime` (auth, base, migrations),
  `routes` (CRUD et contrôle d'accès), `schemas`, `sql_schema`, `theme`,
  `sandbox`, `admin_cli`. Composition par mixins ; l'import historique
  `from generator import MonlSecureGenerator` reste valide. Le découpage a été
  vérifié en comparant octet à octet la sortie générée sur les six specs.

### Interface

- **Le dialogue guidé a une présentation à part entière** (`src/tui.py`) :
  déroulé de l'entretien affiché avant la première question et étape en cours
  marquée, menus en colonnes alignées avec l'explication de chaque option,
  invite dédiée, récapitulatif de ce que la spec va déclarer avant compilation.
  Aucune dépendance ajoutée (séquences ANSI), et dégradation silencieuse :
  rendu nu hors terminal interactif, sans couleur si `NO_COLOR`, sans caractère
  de dessin si l'encodage ne les supporte pas. Le moteur ne connaît qu'une
  interface de présentation dont la version nue reproduit exactement les
  chaînes historiques — les dialogues scriptés sont insensibles à l'habillage.
- **Le dialogue pose la question de l'inscription** (régression corrigée) :
  depuis le marqueur `selfRegister`, l'émetteur écrivait `actor X` sans
  marqueur — toute application créée par le dialogue refusait donc *toute*
  inscription. La question est désormais explicite, et l'ordre des réponses
  porte la recommandation : d'abord les rôles qui n'écrivent que sur leurs
  propres enregistrements, jamais le gestionnaire des données communes.
- **La direction de design devient vérifiable quand la spec la déclare.** La
  clause `design` du contrat était la seule qu'aucun contrôle ne confrontait au
  livrable : un frontend pouvait l'ignorer en silence. Désormais, un thème
  épinglé par un bloc `ui … theme:` est contraignant — sa palette est publiée
  exacte (sans la variation de teinte propre au projet) et le smoke test exige
  de la retrouver dans les styles livrés. Un thème simplement déduit du
  vocabulaire des entités reste une proposition : l'écart est signalé, jamais
  bloquant.
- Sixième thème, `atelier` : papier technique quadrillé, trait fin, données en
  chasse fixe, un seul accent haute visibilité, et aucune police distante — il
  couvre le vocabulaire de la pièce détachée et de la réparation, mal servi par
  `market`. C'est celui qu'épingle désormais la démo.

### Documentation

- Les six specs livrées déclarent leur rôle auto-inscriptible.
- `docs/SECURITE.md` : périmètre d'inscription, provisionnement, réglages.

## 0.9.0-beta.2 — Retrait de l'IA générative locale

Le compilateur devient entièrement déterministe. La seule IA du cycle de vie est
désormais celle qui construit le frontend (Claude), contre le contrat.

### Retiré
- Suppression complète d'Ollama et des modules associés (`nl_interpreter.py`,
  `ai_translator.py`, `ai_sandbox_filler.py`).
- Options retirées : `--nl` (réponses libres au dialogue), `--prompt` (spec
  depuis une description), `--fill-custom` (remplissage des blocs `custom`).
- Le dialogue guidé est purement à saisie stricte ; les blocs `custom` sont des
  coquilles vides à compléter à la main (aucune génération de code automatisée).

### Corrigé
- Défaut de compilation mort supprimé (référence à un exemple inexistant).
- Documentation alignée (README, `docs/SECURITE.md`, `docs/BETA.md`) : plus
  aucune mention d'Ollama ni d'IA générative dans le cœur du produit.

## 0.9.0-beta.1 — Première bêta

Correction de tous les défauts bloquants identifiés à l'audit. Détail dans
`docs/BETA.md` ; modèle de sécurité dans `docs/SECURITE.md`.

> Note : certains éléments décrits ci-dessous (bloc `custom` par IA locale,
> garde-fou du code généré) ont été retirés en 0.9.0-beta.2. Entrée conservée
> comme historique.

### Sécurité
- Bloc `custom` désactivé par défaut ; activation explicite par `--fill-custom`.
  La compilation nominale est désormais 100 % déterministe et hors-ligne.
- Garde-fou statique du code `custom` durci : blocage des évasions par
  introspection (`__class__`, `__subclasses__`, `__globals__`, `__code__`,
  `__mro__`…), détection élargie des boucles à condition constamment vraie,
  liste d'imports bas-niveau étendue (`inspect`, `threading`, `marshal`, `gc`…).
- Comparaison à temps constant (`hmac.compare_digest`) des empreintes de mot de
  passe à la connexion.
- Secret JWT injectable par variable d'environnement `MONL_JWT_SECRET`
  (prioritaire sur le fichier `.jwt_secret`) — le secret peut ne jamais toucher
  le disque en production.
- Limitation de débit consciente du proxy via `MONL_TRUST_PROXY` ;
  `X-Forwarded-For` ignoré par défaut pour empêcher l'usurpation d'IP.

### Fiabilité
- Intégrité transactionnelle : création d'un enregistrement et effets liés
  (`increments`/`decrements`) exécutés dans une seule transaction avec rollback.

### Packaging & documentation
- `pyproject.toml` (métadonnées, entrée console `monl`, config pytest).
- Dépendances épinglées avec bornes hautes (`requirements.txt` + `pyproject.toml`).
- Nouveaux documents : `docs/SECURITE.md`, `docs/BETA.md`.
- Nouveau test : `tests/test_sandbox_guardrail.py` (20 cas, dont évasions par
  introspection).
- Archive de distribution nettoyée (aucun secret ni artefact généré).
