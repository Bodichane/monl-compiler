# Journal des modifications

## Après 0.9.0-beta.6 — Stabilisation du compilateur

- Les fonctions de bibliothèque lèvent désormais une famille commune
  `MonlError` ; la conversion en code de sortie reste à la frontière CLI.
- `CompilationPlans` est calculé une seule fois par générateur et devient le
  catalogue canonique partagé par les renderers backend et le contrat frontend.
- Des golden tests verrouillent les artefacts déterministes d'une compilation
  représentative, y compris le contrat et l'état du projet.
- `requests` est déplacé dans l'extra optionnel `.[ai]` et les compatibilités
  historiques sont documentées dans `docs/DEPRECATIONS.md`.

### Briques 27 et 28 remises d'aplomb (point 116)

- **`publicWhen` ne cache plus le contenu à qui doit le voir.** Un `sharedBy`
  sur la même référence nomme les rôles superviseurs, et le propriétaire
  retrouve toujours ses enregistrements. Avant ce correctif, masquer un contenu
  le retirait AUSSI au modérateur qui venait de le masquer, et à son auteur.
- **`oncePer` refusait parfois sans rien protéger.** Un index composite posé sur
  une colonne que la route `Create` n'écrit jamais laissait passer tous les
  doublons ; la génération refuse désormais ce cas en nommant la relation à
  déplacer. Son 409 ne vole plus le message de `unique`.
- **`monl update` voit les deux règles.** Elles vivaient dans `business_rules`,
  que la signature de contrat ne lisait pas : le delta répondait « aucun
  changement d'interface ». Contrat en version 9.
- **La suite passe sur un clone neuf.** `tests/test_projets_metier.py` lisait
  `projets/`, ignoré par git : six tests échouaient en CI. Les specs sont
  désormais dans le fichier de test.
- Les deux briques sont éprouvées contre un vrai serveur
  (`tests/test_publication_conditionnelle.py`, `tests/test_unicite_composite.py`)
  et compilées par `exemples/03_reseau_social.ml`.

### La colonne du compteur ne dépend plus de l'ordre des relations (point 117)

- **Correction de données.** Une entité à deux relations entrantes dont celle du
  compteur était déclarée en premier créait ses lignes avec la clé étrangère de
  la cible à `NULL` : le compteur montait, mais l'enregistrement ne savait pas
  sur quoi il portait. Inverser les deux relations suffisait à tout réparer —
  bug d'ordre, invisible sur la spec qui l'a fait naître.
- `_counter_fk_columns` dérive désormais cette colonne de `_decrement_fk_column`
  pour chaque règle, et le schéma Pydantic, les clés étrangères client et
  l'INSERT la lisent tous les trois : écrite exactement une fois, jamais zéro.
- Le repli silencieux vers la première relation entrante devient une erreur de
  génération explicite.
- **Le catalogue déclare le superviseur de lecture** : les modèles Blog et
  Communauté livraient une modération à sens unique, le modérateur perdant de vue
  ce qu'il venait de masquer.

### Les migrations non additives sont nommées, appliquées à la main, réversibles (point 120)

- **Le moteur ne devine plus rien.** Un renommage était vu comme une
  suppression suivie d'un ajout : l'ancienne colonne restait pleine, la
  nouvelle arrivait vide, et rien ne le disait. Un changement de type n'était
  pas appliqué du tout. Une colonne retirée restait indéfiniment sans être
  rapportée.
- **Une syntaxe déclarative et NOMMÉE** : `migration <nom>` avec `rename`,
  `alter … from … to …` et `drop`, appliquée par `monl migrate PROJET --name
  <nom>` et défaite par `--down`.
- **Un changement destructif ne s'applique jamais tout seul au démarrage.**
  Le serveur REFUSE de démarrer en nommant la colonne et la commande à lancer,
  au lieu d'avaler l'échec et de servir une base à moitié migrée.
- **Une table d'historique** `_monl_migrations` enregistre chaque opération
  avec l'empreinte du schéma résultant. La descente d'un `drop` est refusée :
  elle ne se défait pas sans sauvegarde, et prétendre le contraire serait pire
  que ne rien offrir.
- La migration additive reste automatique : elle ne détruit rien. Une base
  créée par le compilateur d'avant démarre sans rien perdre — vérifié.
- **Un défaut trouvé en revue** : `manage.py` sortait sur une trace de quinze
  lignes qui noyait le diagnostic. Il nomme désormais le remède et le dossier.

### La couche données choisit son dialecte au démarrage (point 119)

- **PostgreSQL à côté de SQLite.** `MONL_DATABASE_URL` absente : SQLite,
  comportement strictement inchangé. `postgresql://` : psycopg v3. Le choix est
  fait au DÉMARRAGE et non à la compilation, pour que le même artefact scellé
  tourne en développement et en production sans être recompilé. `psycopg` est
  une dépendance optionnelle (`.[postgres]`), et son absence avec un DSN est
  nommée explicitement.
- **La traduction `?` → `%s` est sûre par le point 108** : aucune valeur client
  n'entre jamais dans le texte d'une requête, donc le texte traduit ne contient
  que du SQL fixe. Sans cet invariant, la traduction serait une faille.
- `AUTOINCREMENT` devient une identité PostgreSQL, `PRAGMA table_info` devient
  `information_schema`, `lastrowid` devient `RETURNING id`, `Float` devient
  `DOUBLE PRECISION`. `Money` reste `NUMERIC(10, 2)` : un flottant binaire
  n'est pas un type d'argent.
- **Les erreurs d'intégrité sont lues structurées** (SQLSTATE `23505`/`23503`
  et nom de contrainte) au lieu du message SQLite, qui n'existe pas sur
  PostgreSQL. Les trois 409 restent distincts.
- La CI lance un vrai service PostgreSQL ; les tests se sautent proprement sans
  `MONL_TEST_DATABASE_URL`.
- **Deux défauts trouvés en revue et corrigés.** Le bloc d'intégrité ne se
  terminait plus par un `raise` : une erreur d'une quatrième espèce en sortait
  sans rien lever et la route allait jusqu'à `return success` après un
  `rollback` (mesuré : 500 `UnboundLocalError` sur une référence `numbered` en
  double). Et `manage.py`, important `app` en tête de fichier, ne fonctionnait
  plus depuis un autre dossier — or c'est le seul chemin pour créer un compte à
  rôle privilégié.

### Le backend généré est déployable (point 118)

- **CORS opt-in.** `MONL_CORS_ORIGINS` liste des origines explicites ; absente,
  aucun en-tête CORS n'est émis et le comportement est inchangé. L'origine `*`
  fait échouer le démarrage : combinée aux identifiants, elle laisserait
  n'importe quel site lire les réponses authentifiées d'un utilisateur connecté.
  Les méthodes annoncées sont calculées depuis les routes réellement émises.
- **Deux healthchecks.** `/health` ne touche pas la base (vivacité),
  `/health/ready` exécute un `SELECT 1` et rend 503 si elle ne répond pas
  (disponibilité). Les deux restent hors du contrat frontend.
- **Journaux structurés.** `MONL_LOG_FORMAT=json` émet une ligne JSON par
  requête. Aucun corps, aucun en-tête entrant, aucune query string n'y entre —
  le corps de `/register` contient le mot de passe en clair. L'`X-Request-ID`
  fourni n'est repris que s'il passe un motif étroit, sinon il est régénéré.
- **`MONL_ENV=production` exige `MONL_JWT_SECRET`.** Le refus vaut même si un
  `.jwt_secret` est présent : ce repli fait dépendre tous les jetons émis d'un
  fichier qui ne suit pas l'image, donc perdu au premier redéploiement.
- **`Dockerfile` et `.dockerignore` sont produits, jamais scellés.** Écrits
  s'ils manquent, préservés ensuite, et hors des empreintes d'artefacts
  protégés : adapter l'image est le cas normal d'un déploiement réel.
- Éprouvé par `tests/test_deploiement.py` (9 tests) et par une construction
  d'image réelle : conteneur refusant de démarrer sans secret, puis servant
  inscription, connexion, création et lecture, secret absent de l'image.

## 0.9.0-beta.6 — Capacités métier et contrôle d'accès approfondi

Cette version complète le noyau déclaratif avec les capacités ajoutées depuis
la bêta 5 : calculs serveur (`derivedFrom`, `sumOf`), propriété transitive,
décompte de stock, horodatage et numérotation serveur, contraintes de champs,
valeurs énumérées, profils obligatoires, verrouillage après paiement et
outillage de retouche du frontend. Le contrôle d'accès SQL typé et ses
invariants de sécurité sont également consolidés.

La version du paquet, du contrat de suivi (`monl.json`) et de la documentation
est désormais alignée sur `0.9.0-beta.6`.

## 0.9.0-beta.5 — N'importe quelle clé API, n'importe quel agent

**Le compilateur reste inchangé.** Aucune règle, aucune route générée, aucun
contrat ne diffère de la bêta 4. Cette version ouvre le dernier maillon — celui
où une IA écrit le frontend — à autre chose qu'Anthropic. Détail et raisons
complètes au point 69 de `docs/design_decisions.md`.

### Voie API : n'importe quelle clé

- **Fournisseurs au dialecte OpenAI.** `groq`, `openai`, `openrouter`,
  `deepseek`, `mistral`, `together`, `xai` et `ollama` sont préréglés, chacun
  lisant **sa propre** variable d'environnement (`GROQ_API_KEY`,
  `OPENAI_API_KEY`…) — une clé absente nomme la variable attendue plutôt que de
  renvoyer « clé manquante » sans dire laquelle.
- **Échappatoire totale** pour un point de terminaison absent de la table
  (serveur maison, vLLM, llama.cpp) : `--provider openai-compatible` avec
  `MONL_AI_BASE_URL` et `MONL_AI_API_KEY`.
- Un seul fournisseur paramétré plutôt qu'un par marque : écrire du code par
  acteur aurait produit de la duplication et une liste éternellement en retard.
  Deux dialectes — Anthropic Messages et OpenAI Chat Completions — couvrent le
  marché.
- **`--model` est exigé hors voie Anthropic**, à dessein. Inscrire `gpt-4o` ou
  `llama-3.3-70b-versatile` en dur aurait transformé une erreur claire en 404
  obscur six mois plus tard, chez un utilisateur qui n'a rien changé.
- La clé reste lue dans l'environnement, jamais en argument de ligne de
  commande : la règle posée pour la voie Anthropic n'avait aucune raison d'être
  plus laxiste ailleurs.

### Voie agent : Codex, Gemini, et tout autre

- **`--provider codex` et `--provider gemini`** s'ajoutent à `claude-code`.
- **`--agent-command "<cmd> {instruction}"`** câble n'importe quel agent en
  ligne de commande, et permet aussi de corriger un préréglage devenu faux sans
  attendre une version de monl. Un gabarit dépourvu de `{instruction}` est
  refusé plutôt que lancé muet.
- **Aucun garde-fou n'est relâché pour un agent tiers.** L'empreinte des
  artefacts protégés, la re-vérification (cohérence + smoke test) et la
  correction unique sont exactement celles écrites pour Claude Code : seule la
  ligne de commande change. Deux tests l'établissent en faisant tenter à un
  agent factice « codex » l'intrusion dans `app.py` que l'agent Claude factice
  ne pouvait pas commettre — elle est bloquée de la même façon.
- **Ce qui est vérifié, dit franchement** : seul `claude` est éprouvé contre le
  vrai binaire. Les préréglages `codex` et `gemini` suivent l'invocation non
  interactive publiée par ces outils, mais aucun des deux n'était installé sur
  la machine de développement. Ce sont des préréglages, pas des garanties, et
  le commentaire de la table le dit à cet endroit précis.
- Les noms d'origine (`run_claude_code`, `generate_with_claude_code`) sont
  conservés comme cas particuliers : la voie du point 43 reste ce qu'elle était.

### Vérification

- **164 tests** (11 nouveaux) : requête réellement formée pour la voie API
  (URL, en-tête `Bearer`, corps, extraction de la réponse), variable de clé
  nommée pour chaque préréglage, ligne de commande de chaque agent, gabarit
  libre traversant la boucle complète, et les deux tests d'intrusion.
- Couverture maintenue à 85 %, `ruff` sans signalement, frontières
  d'architecture inchangées.

## 0.9.0-beta.4 — Ouverture publique : licence, documentation, démonstration

**Le compilateur est inchangé.** Aucune règle, aucune route générée, aucun
contrat ne diffère de la bêta 3 : cette version rend le dépôt lisible par
quelqu'un qui le découvre, maintenant qu'il est public. Mettre à jour ne
demande donc rien de plus qu'un `pip install -e .`.

### Licence et gouvernance

- **`LICENSE` ajouté.** Le dépôt est devenu public *sans* fichier de licence.
  Juridiquement, l'absence vaut déjà « tous droits réservés » — mais le lecteur
  ne peut pas distinguer un choix d'un oubli, et cette ambiguïté ne sert
  personne. Le fichier met par écrit ce que `pyproject.toml` déclare depuis
  toujours (`license = "Proprietary"`) : public pour lecture et évaluation, pas
  libre. Précision qui n'allait pas de soi : les applications *produites* par
  monl-compiler appartiennent à leur auteur — la licence porte sur le compilateur, pas
  sur sa sortie.
- **`CONTRIBUTING.md` ajouté.** Documente la méthode plutôt qu'il n'invite aux
  contributions, qui ne sont pas ouvertes : preuve par exécution réelle,
  checklist avant PR, frontières exécutables, format des messages de commit,
  table « où intervenir ». S'adresse au mainteneur, à un futur collaborateur
  autorisé, et à toute IA de développement travaillant sur le dépôt.
- **`demo/.jwt_secret` et `demo/app.db` retirés du suivi.** Le `.jwt_secret` de
  la racine était ignoré depuis toujours ; l'exception avait suivi le dossier de
  démonstration. Portée réelle faible (rien n'est déployé), portée symbolique
  non : le projet publiait ce qu'il traite comme sensible. Les deux se
  régénèrent au premier démarrage. L'historique n'est **pas** réécrit — le
  secret d'une démo locale ne justifie pas de casser les clones existants.

### Démonstration

- **`demo/` ne versionne plus sa propre sortie.** Neuf fichiers générés
  (`app.py`, `schema.sql`, `manage.py`, le contrat, le brief, `serve.py`…)
  étaient commités à côté de la spec dont ils découlent — une contradiction en
  page d'accueil, dans un projet dont la thèse est que la spec est l'unique
  source de vérité. Le dommage était constaté : le contrat livré datait d'avant
  les points 51, 52 et 56 (URL absolue avec port en dur, police à télécharger,
  aucun ton dérivé). Ne restent que `spec.ml` et `frontend/`, les deux seuls
  écrits qu'aucune recompilation ne reproduit. Les tests ne perdent rien : ils
  compilaient déjà dans un dossier temporaire à partir de ces deux entrées.
- **StudioNova remplace AtelierVélo** — un portfolio de photographe dont le
  frontend a été écrit par Claude Code contre le contrat.
- **`tests/test_design_contract.py` est retourné plutôt que supprimé.**
  L'ancienne démo épinglait un thème et le test s'en servait pour vérifier
  qu'un frontend livré respecte une palette imposée ; StudioNova n'épingle
  rien, et son IA s'est autorisé une palette entièrement différente. Le test
  prouve désormais, sur un livrable réel, que monl-compiler se **tait** quand le thème
  n'est que déduit — la moitié la moins intuitive du point 58. La contrainte
  reste éprouvée juste à côté, sur un frontend construit pour l'occasion.

### Documentation

- **README refait.** Démarrage rapide en trois lignes au-dessus de la ligne de
  flottaison, qui n'exige aucun fichier préexistant et mène à une application à
  soi — l'entrée réelle du produit est le dialogue guidé, pas la compilation de
  l'exemple de quelqu'un d'autre. Badges, sommaire, tableaux pour les commandes
  et les règles d'accès, section « Qualité et vérification ». Faits
  resynchronisés : `src/` est devenu le paquet `src/monl/` (point 65).
- **Le schéma d'architecture devient une vraie image** : deux SVG (clair et
  sombre) servis par `<picture>` selon le thème du lecteur, générés depuis un
  seul modèle pour qu'ils ne puissent pas diverger. La géométrie est vérifiée —
  aucune boîte chevauchée, aucun trait traversant une boîte *ou un texte*, aucun
  libellé plus large que sa boîte.
- **La section « Pourquoi » compare enfin monl-compiler à quelque chose.** Elle critiquait
  un framework et un générateur d'IA sans jamais dire ce que monl-compiler fait ; c'est
  désormais un tableau à trois colonnes où monl-compiler a la sienne, ligne par ligne.
- **`exemples/` gagne un README** : le dossier ne contient pas cinq applications
  mais les cinq fichiers `.ml` qui suffisent à les décrire. Un lecteur qui croit
  ouvrir des applications passe à côté de la thèse du projet.
- **Les ouvertures affirment leur contenu au lieu de le nier.** Plusieurs
  passages commençaient par une absence (« ce dossier ne contient pas… », « monl-compiler
  ne génère aucune interface ») : le lecteur devait retenir ce qui manquait
  avant d'apprendre ce qu'il avait sous les yeux.
- Nomenclature unifiée : **monl-compiler** dans les titres et la prose, `monl` pour la
  commande et le paquet.

### Tests et intégration continue

- **Le test du canal temporel ne dépend plus de la charge de la machine.** Il
  échouait par intermittence en CI (deux fois de suite sur 3.12, puis vert au
  troisième essai, sur une branche qui ne touchait que de la documentation) :
  il comparait deux mesures HTTP à la moitié du coût d'un PBKDF2, et une seule
  préemption du runner suffisait à faire exploser l'écart. Élargir le seuil
  aurait rendu le test aveugle à la fuite qu'il surveille ; à la place, cinq
  échantillons par groupe dont on retient le minimum (le bruit ne peut
  qu'ajouter du temps), mesure entière rejouée jusqu'à trois fois (une vraie
  fuite est systématique, le bruit non), quota vidé entre les groupes.
- **Un serveur de test n'est plus laissé orphelin en cas d'échec.** Son arrêt
  était écrit après les mesures : tout échec abandonnait un `uvicorn` et un
  dossier temporaire sur une machine qui allait enchaîner d'autres tests. Passé
  sous `try/finally`.
- **La CI écoute toutes les branches.** Elle ne se déclenchait que sur `main` et
  les pull requests : pousser une branche de travail ne lançait rien, et la page
  Actions restait vide en donnant l'illusion d'un dépôt sans intégration
  continue.
- `dist/` et `build/` sont ignorés par git — la sortie de `python -m build` et
  le dossier de sortie que le démarrage rapide propose n'ont jamais à être
  versionnés.

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
