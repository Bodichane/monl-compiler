# État bêta et route vers la GA

## Ce que corrige la bêta 0.9.0-beta.6

Cette version ajoute les capacités métier et le contrôle d'accès approfondi
développés depuis la bêta 5 : calculs serveur (`derivedFrom`, `sumOf`),
agrégations (`sumOf`), propriété transitive, stock, horodatage, numérotation,
contraintes de champs, valeurs énumérées, profils obligatoires et verrouillage
des enregistrements après paiement. Elle ajoute aussi l'outillage de retouche
du frontend et aligne les métadonnées de version du paquet et des projets
compilés.

## Ce que corrige la bêta 0.9.0-beta.5

Un défaut d'ouverture, pas de correction : le dernier maillon du cycle — l'IA
qui écrit le frontend — n'acceptait qu'Anthropic, alors que le module promettait
depuis le pivot une abstraction « extensible sans toucher à la boucle
d'orchestration ». Elle l'est désormais : n'importe quelle clé au dialecte
OpenAI (`groq`, `openai`, `openrouter`, `deepseek`, `mistral`, `together`,
`xai`, `ollama`, plus une échappatoire pour tout autre point de terminaison), et
n'importe quel agent en ligne de commande (`codex`, `gemini`, ou `--agent-command`).
Aucun garde-fou n'est relâché au passage — c'est le point 69. Le compilateur
lui-même est inchangé.

## Ce que corrige la bêta 0.9.0-beta.4

Rien dans le compilateur : aucune règle, aucune route générée, aucun contrat ne
diffère de la bêta 3. Cette version rend le dépôt lisible par quelqu'un qui le
découvre, maintenant qu'il est public — `LICENSE` et `CONTRIBUTING.md` ajoutés,
README refait, `demo/` cesse de versionner sa propre sortie. Deux correctifs
réels tout de même, côté vérification : le test du canal temporel ne dépend plus
de la charge de la machine (il échouait par intermittence en CI), et il ne
laisse plus de serveur orphelin en cas d'échec. Détail dans `CHANGELOG.md`.

## Ce que corrige la bêta 0.9.0-beta.3

Audit externe du dépôt : une faille critique (auto-attribution d'un rôle
privilégié à l'inscription), cinq défauts importants (énumération par timing,
quota non atomique, secret en 0644, liste noire non purgée, clés étrangères
jamais appliquées) et un défaut de déterminisme (ordre d'acteurs issu d'un
`set`). Tous corrigés et couverts par `tests/test_beta3_regressions.py` ;
détail dans `CHANGELOG.md`. Le générateur monolithique a été découpé en
package `src/generator/`.

## Ce que corrige la bêta 0.9.0-beta.1

Tous les défauts bloquants identifiés à l'audit ont été corrigés :

1. **IA générative locale retirée.** Suppression complète d'Ollama et des trois
   fonctions qui en dépendaient (`--nl`, `--prompt`, remplissage `--fill-custom`
   des blocs `custom`). Le compilateur est désormais entièrement déterministe et
   hors-ligne ; les blocs `custom` sont des coquilles vides écrites à la main. La
   seule IA du cycle de vie est celle qui construit le frontend (Claude).
2. **Intégrité transactionnelle.** Création + effets `increments`/`decrements`
   dans une seule transaction (commit unique, rollback sur erreur).
3. **Hygiène de secret.** Le secret JWT peut être injecté par
   `MONL_JWT_SECRET` (jamais sur disque). Aucun artefact généré ni secret
   n'est inclus dans l'archive de distribution.
4. **Comparaison à temps constant** des empreintes de mot de passe à la connexion.
5. **Limitation de débit consciente du proxy** (`MONL_TRUST_PROXY`), sans quoi
   `X-Forwarded-For` est ignoré (pas d'usurpation par un client direct).
6. **Packaging.** `pyproject.toml`, dépendances épinglées avec bornes hautes,
   commande `monl` via `pip install -e .`.
7. **Documentation** : `docs/SECURITE.md` (modèle de sécurité), ce fichier.

## Critères de sortie de la bêta (Definition of Done) — atteints

- [x] `pip install -r requirements.txt` puis compilation d'un `.ml` produit un
      backend fonctionnel, sans aucune IA ni dépendance réseau.
- [x] Suite de tests verte, incluant l'audit offensif rejoué sur tous les
      exemples (usurpation de rôle, JWT forgé, élévation de privilège).
- [x] Aucun secret ni artefact généré dans l'archive livrée.
- [x] Secret injectable par variable d'environnement.
- [x] Opérations multi-étapes atomiques.

## Ce qui est fait depuis que cette liste a été écrite

- [x] **Empaquetage en vrai paquet Python** — le code vit dans `src/monl/`,
      `pip install -e .` fournit la commande `monl`, et `import monl` fonctionne
      depuis n'importe quel dossier. Le shim et les `sys.path.insert` ont
      disparu ; la CI rejoue l'installation à chaque push. Voir le point 65.
      C'était l'item 7 de la liste ci-dessous, et le laisser parmi les chantiers
      restants faisait passer pour dû ce qui était livré.
- [x] **Audit offensif généralisé et vert** — `test_exploit_all.py` rejoue les
      trois attaques sur chaque exemple (usurpation de rôle, JWT forgé,
      élévation de privilège) : aucune ne passe. Les deux signaux étudiés en
      profondeur sont des faux positifs (route publique, rôle non auto-inscrit),
      et les `CRITICAL_WARNING` statiques sont couverts au runtime (rôle,
      ownership, verrou de paiement, intégrité référentielle). Détail et statut
      dans `docs/SECURITE.md`.

## Ce qui reste pour une GA « outil professionnel »

Par ordre de priorité :

1. ~~**Couche données de production**~~ — **FAIT (chantier A1)** : le même
   `app.py` choisit SQLite ou PostgreSQL au démarrage via
   `MONL_DATABASE_URL`; `psycopg` reste optionnel dans `.[postgres]`. Les
   migrations additives, intégrités, numérotation et décompte de stock sont
   éprouvés contre un vrai PostgreSQL et la CI lance le service. **Reste
   ouvert** : pooling de connexions et migrations descendantes destructives.
2. **Générateur par templates/AST** en remplacement de la construction du code
   par concaténation de chaînes, avec *golden-file tests* sur la sortie générée
   et fuzzing du parseur. Le découpage en package (bêta 3) a séparé les couches
   (`runtime`, `routes`, `schemas`, `sql_schema`) : c'est le préalable, chaque
   module pouvant migrer vers des templates indépendamment.
3. ~~**Prêt déploiement**~~ — **FAIT (point 118)** : CORS opt-in par
   `MONL_CORS_ORIGINS` (`*` refusé au démarrage), logs JSON avec identifiant de
   requête par `MONL_LOG_FORMAT=json`, healthchecks `/health` et
   `/health/ready`, `Dockerfile`/`.dockerignore` produits et préservés, refus de
   démarrer si `MONL_ENV=production` sans `MONL_JWT_SECRET`. Prouvé par une
   construction d'image réelle. **Reste ouvert** : l'intégration à un
   gestionnaire de secrets dédié (Vault, SSM) — le secret vient aujourd'hui de
   l'environnement, ce qui est le contrat attendu par ces gestionnaires mais ne
   les remplace pas.
4. ~~**Auth complète**~~ — **FAIT (point 124)** : verrouillage PAR COMPTE (la
   limitation du point 9 était par IP), réinitialisation de mot de passe
   (débloquée par le point 122), jetons de rafraîchissement AVEC ROTATION, et
   double facteur TOTP hors ligne. Le verrou n'est pas un oracle d'existence :
   compte verrouillé et compte inexistant rendent la même réponse, à 1,28 ms
   près. **Reste ouvert** : la vérification d'adresse à l'inscription — monl
   sait désormais envoyer, mais confirmer une adresse est une décision de
   parcours (que fait-on d'un compte non confirmé ?) qui n'a pas été prise.
5. **Gouvernance du DSL** : versionner la grammaire, garantir la
   rétrocompatibilité, politique de dépréciation.
6. **Isolation d'exécution du code `custom`** (sous-processus à privilèges
   réduits / conteneur / WASM). **Descendu de la première à cette place, et
   pourquoi** : cette priorité datait de l'époque où les blocs `custom` étaient
   remplis par une IA locale — fonction retirée en bêta 1. Le générateur n'y
   écrit plus que des coquilles vides que l'auteur du projet complète lui-même
   (`src/monl/generator/sandbox.py`). Isoler du code que l'auteur a écrit
   sciemment n'est plus la même frontière de sécurité qu'isoler du code produit
   par un modèle ; l'item reste légitime pour une exécution multi-tenant, il
   n'est simplement plus le chantier qui débloque le reste.
7. **Audit/pentest externe** et modèle de menace écrit.

## Positionnement

Le cœur de valeur est le **compilateur d'intention backend, déterministe et
sûr**. La seule IA du cycle de vie est celle qui construit le frontend, contre
un contrat vérifié. La couche données de production est désormais éprouvée;
l'effort GA peut donc se concentrer sur le pooling, les migrations
destructives et les autres chantiers ci-dessus plutôt que sur un « générateur
d'app complet par IA ».
