# Modèle de sécurité — monl (bêta)

Ce document décrit ce que monl garantit, ce qu'il ne garantit pas, et les
réglages de déploiement. Il complète `docs/design_decisions.md`.

## Principe : déterministe par défaut

Le chemin nominal est entièrement déterministe et hors-ligne :

    dialogue dirigé (règles, sans IA) → spec .ml → parseur → audit → backend

Aucun modèle d'IA n'intervient pour produire le backend. La spec est revalidée
par le vrai parseur avant d'être écrite, et l'audit statique refuse de compiler
une spec dont le contrôle d'accès est incohérent (collision de privilèges non
couverte par `sharedBy` / `ownedBy` / `accessibleBy`).

Les blocs `custom` de la spécification produisent des coquilles vides sûres dans
`sandbox_ai.py`. Leur logique métier est écrite à la main par le développeur ;
aucune génération de code n'est automatisée.

## Qui peut obtenir quel rôle

C'est la frontière la plus importante du modèle, et elle se déclare dans la
spec :

- `actor Client selfRegister` — n'importe qui peut créer un compte portant ce
  rôle via `POST /register`.
- `actor Admin` (sans marqueur) — aucune inscription possible (403). Les comptes
  sont créés sur la machine qui héberge la base :
  `python3 manage.py adduser patron Admin`.

Par défaut, un rôle n'est donc **pas** inscriptible : une spec qui oublie le
marqueur ferme l'inscription plutôt que de l'ouvrir. Le compilateur affiche le
périmètre retenu à chaque compilation, le contrat frontend le publie
(`self_register_actors`, pour que l'interface ne propose que ces rôles) et le
smoke test tente à chaque lancement d'inscrire un rôle provisionné — un succès
fait échouer le lancement.

`manage.py` couvre aussi le changement de rôle (`setactor`), le mot de passe
(`passwd`), l'inventaire des comptes (`users`) et la révocation globale
(`revoke-all`, qui renouvelle le secret et invalide toutes les sessions).

## Ce qui est garanti dans le backend généré

- **Aucune injection SQL par les valeurs** : toutes les valeurs runtime passent
  par des requêtes paramétrées (`?`). Les identifiants (tables/colonnes) sont
  contraints par la grammaire à `[A-Za-z_][A-Za-z0-9_]*` et interpolés entre
  guillemets — ils ne peuvent pas porter d'injection.
- **Authentification** : mots de passe hachés en PBKDF2-HMAC-SHA256 (100 000
  itérations, sel unique par compte), comparaison à **temps constant**
  (`hmac.compare_digest`) à la connexion. Un hachage factice est calculé même
  quand l'identifiant est inconnu, pour que le temps de réponse ne révèle pas
  quels comptes existent. JWT signé en HS256, décodé avec la
  liste d'algorithmes explicite (pas de confusion d'algorithme / `alg:none`),
  révocation par `jti` via `/logout`.
- **Contrôle d'accès** : rôle (`actor`) et identité (`user_id`) tirés du compte
  réel porté par le JWT, jamais d'une déclaration libre du client. Règles
  `ownedBy` / `accessibleBy` / `public` / `hidden` / `generated` appliquées au
  niveau des routes.
- **Intégrité transactionnelle** : la création d'un enregistrement et ses effets
  liés (`increments` / `decrements`) sont exécutés dans une seule transaction
  (commit unique, rollback en cas d'erreur).
- **Limitation de débit** persistée en base (partagée entre workers) sur
  `/register` et `/login`, comptée et enregistrée dans une seule transaction en
  écriture immédiate — un lot de requêtes simultanées ne franchit pas le quota.
- **Propriété par enregistrement** (`ownedBy`) : restreint la modification, la
  suppression **et la lecture** (liste filtrée en SQL, accès direct en 404) —
  pour le seul acteur désigné propriétaire. Un autre rôle autorisé à lire
  l'entité continue de tout voir : c'est ce qui permet à un gestionnaire de
  consulter les commandes de tous ses clients.
- **Intégrité référentielle** : les clés étrangères sont réellement appliquées
  (`PRAGMA foreign_keys`, désactivé par défaut dans SQLite) ; une violation
  répond 409 plutôt que 500.
- **Hygiène du secret** : `.jwt_secret` est créé avec les permissions 0600, et
  la liste noire des jetons révoqués est purgée de ses entrées expirées.

## Réglages de déploiement (variables d'environnement)

- `MONL_JWT_SECRET` : si définie, le secret JWT est lu depuis
  l'environnement et **ne touche jamais le disque**. C'est le mode recommandé en
  production. Sinon, monl retombe sur le fichier `.jwt_secret` généré à la
  compilation (jamais committé — voir `.gitignore`).
- `MONL_TRUST_PROXY=1` : à activer **uniquement** si l'application tourne
  derrière un reverse proxy de confiance. La limitation de débit lit alors la
  première IP de `X-Forwarded-For`. Sans ce réglage, l'en-tête est ignoré (un
  client direct ne peut pas l'usurper pour contourner le quota).

## Le bloc `custom` : code écrit à la main

Les blocs `custom` sont un point d'extension explicite : à la compilation, monl
génère pour chacun une coquille vide dans `sandbox_ai.py`, que le développeur
complète à la main. Ce code relève de sa responsabilité, au même titre que
n'importe quel code applicatif qu'il écrit — monl ne l'analyse ni ne le génère.
Les bonnes pratiques du backend généré restent la référence : requêtes SQL
paramétrées, pas d'exécution dynamique, pas d'accès système non maîtrisé.

Une isolation d'exécution dédiée pour ce code (sous-processus à privilèges
réduits, conteneur, ou WASM) est un objectif GA — voir `docs/BETA.md`.

## Limites connues de la bêta

- Base SQLite : convient au prototypage et aux déploiements légers ; la
  concurrence en écriture sous forte charge multi-workers reste limitée
  (objectif GA : couche PostgreSQL). Voir `docs/BETA.md`.
- Migrations additives uniquement (`ALTER ADD COLUMN`) ; les changements
  destructifs sont refusés volontairement (voir `docs/MIGRATIONS.md`).
- Auth sans réinitialisation de mot de passe ni vérification d'email (objectif
  post-bêta).
- Pas de CORS configurable ni d'en-têtes de sécurité HTTP : le frontend est
  servi par la même origine que l'API (`/site`). Une interface hébergée
  ailleurs relève du déploiement, pas encore du générateur (objectif GA).
