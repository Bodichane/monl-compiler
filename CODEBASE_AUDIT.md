# Audit de cohérence, maintenabilité et nettoyage de MONL-Compiler

Date de l'audit initial : 11 août 2026  
Périmètre : `src/monl/`, `tests/`, configuration, documentation et dépendances. Les applications générées sous `projets/` sont des sorties/démonstrations et ne sont pas considérées comme le code du compilateur.  
État documenté ici : audit initial, puis vérification de clôture après les refactorings réalisés dans l'arbre de travail.

## Résumé exécutif

MONL-Compiler est fonctionnel et très bien couvert par des tests comportementaux : la suite complète compte désormais **812 tests, tous réussis**, avec **91,62 % de couverture**. Le pipeline conceptuel est sain (Lark → dictionnaire brut → validation/normalisation → générateur déterministe → artefacts) et les principaux risques de l'audit ont été traités : compilation unique, résultat IR nommé, plan de routes partagé, passes de validation explicites, publication transactionnelle, erreurs typées et infrastructure HTTP de tests mutualisée.

Les risques résiduels sont désormais concentrés dans la migration complète des dictionnaires internes vers l'IR, les mixins historiques du générateur et les helpers privés entre outils. Les routes CRUD, paiement et post-paiement ont des renderers distincts ; le contrat frontend consomme `CompilationPlans` et ne lit plus les méthodes privées du générateur. Les tests restent intégrationnels et dépendent de sockets locales, mais leur mécanique est mutualisée.

Aucun défaut **CRITICAL** démontré n'a été trouvé. Les problèmes **HIGH** de double compilation, publication partielle, couplage du contrat et monolithe de routes sont résolus ou fortement réduits ; reste à finir la migration des représentations internes.

## Méthode et limites

- Lecture de tous les points d'entrée, inventaire AST des classes/fonctions et reconstruction des dépendances internes.
- Recherche de symboles, appels, marqueurs historiques, exceptions générales, écritures disque et sous-processus avec `rg` et analyse Python `ast`.
- `ruff check src tests` : **propre** après correction de l'ordre d'import.
- `pytest` dans la sandbox : résultat non interprétable, car les sockets locales sont interdites (`PermissionError`).
- `pytest` hors sandbox : **812 passed, 1 warning**, avec sockets locales autorisées ; l'unique avertissement est le warning JWT volontaire du test de signature falsifiée.
- `pytest-cov` : **91,62 %** (92 % arrondis), seuil CI fixé à 90 %.
- `mypy src/monl/ir.py src/monl/errors.py src/monl/generator/emitters.py --strict` : propre.
- `vulture src/monl --min-confidence 90` : aucun signalement.
- Les méthodes du `Transformer` Lark et les dispatchs du générateur ont été vérifiés comme dynamiques ; aucun résultat Vulture n'a été supprimé automatiquement.

## Pipeline réel

### Voie basse : `python -m monl.main`

```text
fichier source MONL
  → parse_monl_file()
  → parse_monl_string()
  → nettoyage des commentaires seuls
  → Lark LALR + MonlIndenter
  → arbre Lark
  → MonlTransformer
  → dictionnaire AST brut
  → MonlAST(raw, base_dir)
  → `ValidationPipeline` (passes métier, sécurité, contenu et UI)
  → `CompilationIR` normalisée
  → MonlSecureGenerator(normalized)
  → `CompilationPlans` partagés + calculs internes historiques
  → schema.sql + app.py + sandbox_ai.py + manage.py + .jwt_secret
```

### Voie produit : commande `monl compile`, `init` ou `update`

```text
compile_project()
  → compile_monl()
      → parsing → ValidationPipeline → IR → générateur + plans → artefacts backend
  → build_contract(IR, plans déjà calculés)
  → frontend_contract.json + FRONTEND_PROMPT.md + CLAUDE.md
  → monl.json (empreintes d'état)
```

Le contrat frontend consomme désormais le `CompilationResult` du premier parcours ; il n'y a plus de reparsing, de second audit ni de seconde instance de générateur.

## Carte des modules actuels

| Module | Responsabilité actuelle | Dépendances principales | Appelé par | Produit | Responsabilité unique ? |
|---|---|---|---|---|---|
| `parser.py` | Grammaire, indentation, transformation et diagnostic syntaxique | Lark | `main`, `cli`, outils et tests | Dictionnaire brut | Presque ; grammaire et diagnostics pourraient être séparés, sans urgence |
| `ast_validator.py` | Façade AST, validations spécialisées, résolution d'assets et normalisation | `os`, `re`, `validation_pipeline` | `main`, `cli`, outils | `CompilationIR` | Encore mutable, mais l'orchestration est sortie dans `ValidationPipeline` |
| `generator/core.py` | Construction de l'état dérivé, orchestration, fichiers, secret et helpers sémantiques | six mixins, SQL | `main`, contrat, tests | Artefacts et calculs partagés | Non |
| `generator/sql_schema.py` | DDL SQLite | état implicite de `MonlSecureGenerator` | `core` via mixin | `schema.sql` en chaîne | Oui, mais couplage implicite élevé |
| `generator/runtime.py` | Runtime FastAPI/auth/migrations/rate limit généré | état implicite | `core` via mixin | lignes Python | Responsabilité large |
| `generator/schemas.py` | Modèles Pydantic générés | état implicite | `core` via mixin | lignes Python | Oui |
| `generator/routes.py` | Renderers CRUD, accès, effets métier, paiement et post-paiement | SQL, état implicite, `RoutePlan` | `core` via mixin | lignes Python | Responsabilités séparées ; certains renderers restent verbeux |
| `generator/emitters.py` | Façade composée des sorties backend | protocole du générateur | `core` | `BackendSources` | Oui ; étape de migration des mixins |
| `generator/admin_cli.py` | CLI d'administration générée | état implicite | `core` via mixin | `manage.py` | Oui |
| `generator/sandbox.py` | Stubs de logique personnalisée | état implicite | `core` via mixin | `sandbox_ai.py` | Oui |
| `frontend_contract.py` | Projection IR/plans→contrat, sémantique UI, prompt et fichiers | IR, plans partagés, design skills | `cli`, tests | JSON, Markdown, CLAUDE.md | Oui pour la projection ; compatibilité legacy acceptée à la frontière |
| `cli.py` | Parsing CLI, orchestration, état, diff, cohérence, serveur, frontend, assets, contenu | presque tout le paquet | console script | effets disque/processus | Non |
| `main.py` | API de compilation backend et CLI secondaire | parser, validateur, générateur | `cli`, invocation directe | `CompilationResult` ou erreur typée | Chevauche encore `cli.py` pour l'entrée historique |
| `dialogue_engine.py` | Questions, état du dialogue, templates et émission MONL | templates via imports locaux | CLI/TUI/tests | source MONL | Non |
| `app_templates.py` | Catalogue de domaines et effets | aucun | dialogue/tests | données de template | Oui, mais gros fichier de données Python |
| `assets_tool.py` | Édition textuelle sûre de la spec et gestion d'assets | parser/validateur | CLI/tests | spec + fichiers | Non, mais cohérent comme outil transactionnel |
| `content_tool.py` | CSV ↔ blocs `seed` | internals d'`assets_tool` | CLI/tests | CSV/spec | Non : dépend d'API privées |
| `frontend_ai.py` | Fournisseurs API, import frontend, agents CLI, vérification | extra `ai` pour requests, CLI/smoke via imports locaux | CLI/tests | frontend | Non |
| `smoke_test.py` | Démarrage app, appels API et contrôle JS/DOM | uvicorn, Node/npm | CLI/tests | diagnostic | Non, mais outil transversal assumé |
| `serving.py` | Gabarit FastAPI de service statique | aucune au runtime du compilateur | CLI/smoke | `serve.py` | Oui |
| `tui.py` | Rendu terminal | stdlib | dialogue/tests | affichage | Oui |

## Découvertes détaillées

### HIGH-01 — Le pipeline principal compilait deux fois la même source — RÉSOLU

- **Fichier / symbole :** `src/monl/cli.py:129-159`, `compile_project`; `src/monl/main.py:10-62`, `compile_monl`.
- **Raison :** `compile_project()` appelle d'abord `compile_monl()`, qui parse, valide, instancie le générateur et écrit le backend. Il reparcourt ensuite exactement la même source, revalide et reconstruit un générateur pour produire le contrat.
- **Preuve :** appels successifs visibles à `cli.py:142-149`; le premier parcours est à `main.py:31-45`.
- **Impact probable :** coût doublé, logs d'audit doublés, deux instances pouvant diverger, difficulté à rendre la compilation transactionnelle, risque futur qu'un validateur non pur donne deux résultats différents.
- **Recommandation :** créer un service pur `compile_spec(path, base_dir) -> CompilationModel` exécutant une fois parse/validation/analyse ; deux émetteurs consomment ensuite le même résultat. La couche CLI seule gère affichage et erreurs.
- **Confiance :** 100 %.
- **État de clôture :** `compile_monl()` retourne `CompilationResult(ir, generator, plans)` et `compile_project()` réutilise ce résultat pour produire le backend, le contrat et l'état. Le second parsing, le second audit et la seconde instance ont disparu.

### HIGH-02 — L'IR normalisée n'avait aucun schéma ni type explicite — PARTIELLEMENT RÉSOLU

- **Fichier / symbole :** `ast_validator.py:2274-2327`, `to_normalized_ast`; `generator/core.py:36-223`, constructeur ; `frontend_contract.py:215-746`, `build_contract`.
- **Raison :** le contrat entre les passes est un dictionnaire imbriqué dont les clés sont connues implicitement par plusieurs modules. Le générateur ajoute ensuite une deuxième IR implicite sous forme de dizaines d'attributs mutables.
- **Preuve :** accès directs tels que `normalized_ast["security"][...]`, nombreux `.get(...)` défensifs, et `getattr(generator, ..., {})` dans le contrat.
- **Impact probable :** erreurs de clé détectées tard, évolutions incomplètes entre validateur/générateur/frontend, mypy presque impuissant même s'il était installé, duplication des représentations.
- **Recommandation :** introduire progressivement des `dataclass(frozen=True, slots=True)` ou `TypedDict` aux frontières : `ParsedSpec`, `ValidatedSpec`, `EntityModel`, `RouteModel`, `FieldPolicy`. Sérialiser seulement à la frontière JSON.
- **Confiance :** 98 %.
- **État de clôture :** `src/monl/ir.py` fournit maintenant `CompilationIR`, `EntityModel`, `RelationModel`, `FieldPolicy`, `AccessPolicy`, `EffectPlan`, `RoutePlan` et `CompilationResult`. Les attributs internes historiques du générateur et certains dictionnaires restent à migrer.

### HIGH-03 — Le validateur était un objet mutable concentrant plusieurs domaines — PARTIELLEMENT RÉSOLU

- **Fichier / symbole au début du chantier :** `src/monl/ast_validator.py`, `MonlAST`; surtout l'ancienne méthode `_validate_structures`.
- **Raison :** une seule classe valide types, relations, accès, paiements, agrégations, numérotation, seeds, assets, UI, landing et capacités, tout en construisant progressivement l'état consommé par la normalisation.
- **Preuve initiale :** `_validate_structures` dépassait 1 000 lignes et initialisait de nombreux attributs à mesure des règles ; l'ordre des validations faisait partie du comportement implicite.
- **Impact probable :** modifications risquées, invariants temporels, conflits de responsabilité, faible testabilité unitaire des passes.
- **Recommandation :** conserver une façade, mais extraire des passes pures ordonnées (`schema`, `relations`, `access`, `effects`, `content`, `presentation`) retournant des diagnostics et enrichissements typés.
- **Confiance :** 99 %.
- **État de clôture :** `ValidationPipeline` possède désormais 25 passes nommées, dans un ordre testé, et `_validate_structures`/`StructuralValidationPass` ont été supprimés. Les méthodes spécialisées vivent encore sur `MonlAST` afin de préserver les diagnostics et l'API interne ; une extraction vers des fonctions pures reste une étape ultérieure.

### HIGH-04 — La génération de routes concentrait trop de logique métier et de rendu texte — RÉSOLU EN GRANDE PARTIE

- **Fichier / symbole :** `generator/routes.py:16-1166`, `_generate_route_lines`; `1168-1462`, paiements et post-paiement.
- **Raison :** la même couche choisit les routes, reconstitue les politiques, produit du SQL, gère transactions/erreurs et assemble du Python ligne par ligne.
- **Preuve :** méthode principale de 1 151 lignes ; dépendance à presque tous les attributs dérivés de `MonlSecureGenerator`.
- **Impact probable :** branches combinatoires difficiles à raisonner, duplication create/update/delete, bugs d'indentation ou d'échappement détectés seulement sur le code généré.
- **Recommandation :** produire d'abord un `RoutePlan` typé par action, puis rendre chaque famille avec de petits émetteurs. Ne pas changer le comportement tant que des golden tests n'encadrent pas les sorties.
- **Confiance :** 98 %.
- **État de clôture :** `_generate_route_lines` assemble maintenant des renderers séparés pour CRUD/effets, paiement et post-paiement ; `Create`, `Read`, `Update`, `Delete` et `Execute` ont chacun leur méthode. Les méthodes restent génératrices de texte, mais leur responsabilité est isolée et `RoutePlan` est partagé.

### HIGH-05 — La génération des artefacts n'était pas atomique comme un ensemble — RÉSOLU

- **Fichier / symbole :** `generator/core.py:658-722`, `generate_all`; `frontend_contract.py:1219-1241`.
- **Raison :** les fichiers sont écrits directement, un par un, dans le projet. Une interruption ou une erreur après les premières écritures peut laisser un backend et un contrat de générations différentes.
- **Preuve :** quatre `open(..., "w")` successifs à `core.py:714-717`, puis fichiers frontend écrits séparément ; l'état `monl.json` arrive encore après dans `compile_project`.
- **Impact probable :** projet incohérent après panne disque, interruption ou exception tardive ; `check_coherence` peut détecter mais pas prévenir l'état partiel.
- **Recommandation :** générer dans un dossier temporaire du même filesystem, vérifier, puis remplacer les artefacts de façon coordonnée avec manifeste/empreintes et restauration en cas d'échec.
- **Confiance :** 95 %.
- **État de clôture :** `artifacts.py` stage backend, contrat et état dans un dossier voisin ; `publish_files` sauvegarde les anciennes versions et restaure le projet si un remplacement échoue. Les assets et `frontend/` ne sont jamais touchés.

### MEDIUM-01 — Deux CLI et une API de bibliothèque qui appelait `sys.exit` — RÉSOLU POUR LA COMPILATION

- **Fichier / symbole :** `main.py:10-82`; `cli.py:1185-1371`.
- **Raison :** `main.py` reste à la fois fonction de compilation, CLI secondaire et dépendance de la CLI officielle. `compile_monl()` attrape toute exception et termine le processus.
- **Preuve initiale :** `except Exception` puis `sys.exit(1)` à `main.py:59-62`; console script officiel dirigé vers `monl.cli:main` dans `pyproject.toml:35`.
- **Impact probable :** impossible pour un appelant Python de traiter proprement les erreurs ; chevauchement des responsabilités et tests plus difficiles.
- **Recommandation :** faire de la compilation une fonction qui lève des exceptions typées ; traduire en code de sortie uniquement dans `cli.main`. Déprécier ensuite l'invocation directe de `monl.main`.
- **Confiance :** 99 %.
- **État de clôture :** `compile_monl()` lève `MonlError` et `main.py` traduit cette erreur uniquement dans sa frontière CLI. `monl.cli` conserve les `SystemExit` de ses commandes utilisateur ; `cmd_diff` ne capture plus `BaseException`.

### MEDIUM-02 — Mixins de génération : découpage physique sans interfaces explicites

- **Fichier / symbole :** `generator/core.py:28-35` et tous les `generator/*_*.py`.
- **Raison :** les mixins ont réduit la taille de l'ancien fichier monolithique, mais chaque méthode lit librement l'état du descendant. Aucun constructeur, protocole ou type ne documente les prérequis.
- **Preuve :** six héritages multiples ; modules de mixin sans imports du modèle qu'ils consomment ; commentaires « extrait de l'ancien module monolithique ».
- **Impact probable :** couplage caché, réutilisation illusoire, erreurs d'attribut au runtime, analyse statique limitée.
- **Recommandation :** préférer la composition : un `CompilationModel` immuable injecté à `SchemaEmitter`, `RuntimeEmitter`, `RouteEmitter`, etc.
- **Confiance :** 96 %.
- **État de clôture :** `BackendEmitter` fournit désormais une façade composée et un `BackendSources` immuable avant staging. Les mixins restent l'implémentation historique et leur migration individuelle est encore à faire.

### MEDIUM-03 — Le contrat frontend dépendait des internals du générateur — RÉSOLU EN PRODUCTION

- **Fichier / symbole :** `frontend_contract.py:215-746`, `build_contract`.
- **Raison :** le contrat appelle `_compute_fk_placements()` et `_compute_route_map()` et lit de nombreux attributs privés du générateur. Il ne dépend donc pas seulement de l'AST validé.
- **Preuve :** docstring de `build_contract` reconnaissant que le générateur est réutilisé « uniquement pour ses calculs » ; appels à méthodes préfixées `_`.
- **Impact probable :** impossibilité de faire évoluer le backend et le contrat indépendamment ; seconde construction du générateur ; API privée devenue contractuelle.
- **Recommandation :** déplacer placements FK et plans de routes dans une passe d'analyse commune, consommée par les deux émetteurs.
- **Confiance :** 100 %.
- **État de clôture :** `CompilationPlans` porte la carte de routes, placements FK, clés d'identité, clés client, verrous de paiement et politiques nécessaires. La compilation produit transmet ces plans ; l'API legacy accepte encore un générateur et le convertit à l'entrée.

### MEDIUM-04 — Plusieurs concepts ont deux ou trois représentations successives

- **Fichier / symbole :** `ast_validator.py:2274-2327`, `generator/core.py:36-223`, `frontend_contract.py:215-746`.
- **Raison :** règles brutes → structures du validateur → dict normalisé → attributs regroupés du générateur → projection JSON frontend.
- **Preuve :** `public_actions`, `ownership`, champs masqués, dérivés, agrégés, horodatés et numérotés sont convertis entre listes de chaînes, tuples, dictionnaires et listes groupées.
- **Impact probable :** conversions répétées, perte de type, défauts de synchronisation ; commentaires indiquant plusieurs corrections successives du contrat pour chaque famille de champs serveur.
- **Recommandation :** une représentation canonique par concept dans l'IR ; vues/index calculés une fois et immuables.
- **Confiance :** 97 %.
- **État de clôture :** `CompilationPlans` est calculé une seule fois dans `MonlSecureGenerator`, mis en cache et consommé par les routes et le contrat frontend. Les dictionnaires historiques restent exposés aux autres mixins pendant la migration.

### MEDIUM-05 — Duplication massive de l'infrastructure des tests d'intégration — RÉSOLU EN GRANDE PARTIE

- **Fichier / symbole :** au moins 22 définitions de `_port_libre`, 11 de `_appel`, 11 fixtures `application`, 4 faux prestataires Stripe, réparties dans `tests/test_*.py`.
- **Raison :** chaque domaine réimplémente compilation, port libre, lancement uvicorn, attente, inscription, connexion et requêtes.
- **Preuve :** analyse AST : `_port_libre` apparaît dans 22 fichiers ; les mêmes motifs `subprocess.Popen([..., "uvicorn"...])` et boucles d'attente sont répétés.
- **Impact probable :** plus de 30 000 lignes au total, suite de 3 min 47 s, corrections de robustesse à reporter partout, nombreux échecs parasites quand les sockets sont interdites.
- **Recommandation :** fixtures partagées dans `tests/support/` : `compiled_app`, `UvicornServer`, client HTTP, fournisseur de paiement, fabrique de comptes. Garder les scénarios métier dans leurs fichiers.
- **Confiance :** 100 %.
- **État de clôture :** `tests/support/server.py` mutualise le choix de port, le démarrage, l'attente et l'arrêt d'uvicorn. Les scénarios restent séparés ; quelques helpers historiques spécifiques subsistent volontairement pour limiter le risque.

### MEDIUM-06 — Couverture annoncée mais non reproductible avec l'installation présente — RÉSOLU

- **Fichier / symbole :** `README.md:7-10`, badge 88 % ; `pyproject.toml:39-44`, extra dev.
- **Raison :** `pytest-cov` est déclaré mais absent de l'environnement `.venv`; aucune configuration de seuil minimal n'est présente.
- **Preuve :** `pytest --cov=src/monl` échoue avec « unrecognized arguments » ; la suite sans couverture passe.
- **Impact probable :** la couverture affichée peut devenir obsolète sans faire échouer la CI.
- **Recommandation :** installer le vrai extra dev en CI, publier `coverage.xml`, fixer un seuil et/ou retirer le badge statique au profit d'un badge issu de CI.
- **Confiance :** 100 %.
- **État de clôture :** `pytest-cov` est dans l'extra dev, la CI mesure la couverture, le seuil est fixé à 90 %, et le dernier passage donne 92 %. Les badges README indiquent désormais CI plutôt qu'un chiffre figé.

### MEDIUM-07 — Contrôle de types limité aux nouvelles frontières — PARTIELLEMENT RÉSOLU

- **Fichier / symbole :** ensemble de `src/monl`; `pyproject.toml`.
- **Raison :** mypy n'est ni déclaré ni configuré, et les API publiques n'ont presque aucune annotation. Les dictionnaires imbriqués rendent les erreurs de structure invisibles au linter.
- **Preuve initiale :** mypy était absent ; signatures telles que `build_contract(normalized_ast, generator)` et `MonlAST(raw_json, base_dir=None)` n'étaient pas annotées.
- **Impact probable :** refactorings risqués et défauts détectés seulement à l'exécution.
- **Recommandation :** commencer par les frontières de passes et nouveaux types, en mode progressif ; ne pas chercher à annoter immédiatement les longues méthodes génératrices.
- **Confiance :** 100 %.
- **État de clôture :** `mypy --strict` est activé en CI sur `src/monl/ir.py`, `src/monl/errors.py` et `src/monl/generator/emitters.py`. La migration progressive des modules historiques reste volontairement ouverte.

### MEDIUM-08 — `content_tool` importe des helpers privés d'`assets_tool`

- **Fichier / symbole :** `content_tool.py:7-16`.
- **Raison :** `_blocs_seed`, `_charger`, `_litteral` et `_revalider` sont des détails privés réutilisés comme API intermodule.
- **Preuve :** imports directs de quatre noms préfixés `_`.
- **Impact probable :** refactoring local d'assets susceptible de casser l'import/export CSV ; responsabilités de manipulation de source réparties arbitrairement.
- **Recommandation :** extraire un module public `spec_editing.py` avec parse/revalidate/block ranges/literal emission.
- **Confiance :** 100 %.

### MEDIUM-09 — Documentation historique contradictoire avec le code actuel

- **Fichier / symbole :** `docs/phase_5_generator.md:6-31`, `docs/phase_6_systeme_complet.md:7-17`, `docs/phase_3_parser.md:15`, README badges.
- **Raison :** les documents parlent de `src/generator.py`, `src/main.py`, d'un contrôle d'accès par `x_actor`, de `01_todo_list.ml` et `02_blog.ml`, alors que le paquet, JWT et exemples actuels sont différents.
- **Preuve :** chemins absents et avertissement de sécurité déjà rendu faux par `generator/runtime.py` qui génère JWT et vérification de compte.
- **Impact probable :** lecteurs orientés vers des commandes inexistantes et croyance erronée que le backend actuel est un PoC non authentifié.
- **Recommandation :** déplacer les phases dans `docs/history/` avec bannière « archive », ou les réécrire ; ajouter une vérification CI des chemins/commandes documentés.
- **Confiance :** 100 %.

### MEDIUM-10 — Exceptions générales et erreurs parfois masquées

- **Fichier / symbole :** `main.py:59`, `cli.py:211`, `cli.py:874`, `assets_tool.py:122,138,572`, `tui.py:42`; code généré dans `runtime.py` et `routes.py`.
- **Raison :** plusieurs `except Exception`, un `except BaseException`, et certains retours `None` rendent des causes différentes indiscernables.
- **Preuve initiale :** `cmd_diff` capturait `BaseException` à `cli.py:874`; `_empreintes_regenerees` transforme toute erreur en absence d'empreinte ; `main` traduisait tout en sortie processus. `cmd_diff` est maintenant limité à `MonlError`.
- **Impact probable :** interruption clavier avalée dans le dry-run, diagnostics incomplets, erreurs de programmation présentées comme erreurs utilisateur. Dans le code généré, certaines captures larges sont transactionnelles et justifiées, mais doivent rester testées.
- **Recommandation :** définir `MonlError` et sous-types (`Parse`, `Validation`, `Generation`, `ProjectState`, `Frontend`), capturer uniquement aux frontières CLI ; conserver les captures transactionnelles avec re-raise explicite.
- **Confiance :** 94 %.
- **État de clôture :** `MonlError` et ses catégories (`ParseError`, `ValidationError`, `GenerationError`, `ProjectStateError`, `ToolError`, `FrontendError`) structurent désormais les frontières ; `compile_monl` et `cmd_diff` ont des comportements distincts de bibliothèque et de CLI.

### MEDIUM-11 — Le catalogue de templates et le dialogue codent des règles parallèles au validateur

- **Fichier / symbole :** `app_templates.py:67-487`, `dialogue_engine.py:397-1131`, `ast_validator.py`.
- **Raison :** le dialogue connaît types, relations, inscription, paiement et construit directement du texte MONL. Le validateur reste heureusement l'autorité finale, mais les contraintes de saisie sont dupliquées.
- **Preuve :** constantes `FIELD_TYPES`, `RELATION_TYPES`, logique `_ensure_ownership_structure`, `_ask_payable`, puis revalidation complète de la spec émise.
- **Impact probable :** une nouvelle règle du langage peut être valide dans le compilateur mais indisponible ou mal représentée dans le dialogue.
- **Recommandation :** exposer un petit catalogue sémantique partagé (types, capacités, contraintes de forme), sans tenter de générer toute l'UI depuis la grammaire.
- **Confiance :** 88 %.

### LOW-01 — Méthode morte `_get_row_column_names`

- **Classification suppression :** **SAFE_TO_REMOVE >95 %**.
- **Fichier / symbole :** `generator/core.py:947-958`.
- **Raison :** aucune référence dans `src` ni `tests`; sa docstring décrit une ancienne conversion de tuples alors que les routes actuelles construisent autrement leurs réponses.
- **Preuve :** recherche exacte du symbole : seule sa définition existe.
- **Impact probable :** aucun comportement ; retrait de 12 lignes et d'un commentaire obsolète.
- **Recommandation :** supprimer après un test complet, dans la phase de nettoyage seulement.
- **Confiance :** 99 %.

### LOW-02 — Wrapper historique `run_claude_code`

- **Classification suppression :** **LIKELY_REMOVABLE 70–95 %**.
- **Fichier / symbole :** `frontend_ai.py:644-649`.
- **Raison :** aucune référence interne ou dans les tests ; `generate_with_claude_code` reste, lui, utilisé et délègue directement à la voie générique.
- **Preuve :** recherche exacte : définition unique. La documentation de décision indique que d'anciens noms sont conservés pour compatibilité.
- **Impact probable :** aucun dans le dépôt, mais rupture possible pour un consommateur externe non connu.
- **Recommandation :** annoncer une dépréciation avant suppression ou vérifier l'API publique publiée.
- **État de clôture :** l'alias est documenté comme compatibilité dans `docs/DEPRECATIONS.md` et son docstring renvoie vers `run_cli_agent`.
- **Confiance :** 90 %.

### LOW-03 — Compatibilité `landing.mode/template` sans effet

- **Classification suppression :** **UNCERTAIN <70 %**.
- **Fichier / symbole :** `parser.py:276-279`; `ast_validator.py:2009-2012`.
- **Raison :** syntaxe explicitement acceptée mais ignorée, avec avertissement.
- **Preuve :** commentaire et boucle `for obsolete in ("mode", "template")`.
- **Impact probable :** simplification faible ; suppression casserait d'anciennes specs.
- **Recommandation :** documenter une fenêtre de dépréciation et mesurer les specs existantes avant retrait.
- **Confiance :** 60 %.

### LOW-04 — Ancienne extension `.yaml` encore acceptée/documentée

- **Classification suppression :** **UNCERTAIN <70 %**.
- **Fichier / symbole :** `main.py:68-69`, tests et documentation.
- **Raison :** compatibilité historique sans logique spécifique visible : le contenu reste MONL.
- **Preuve :** aide CLI et tests mentionnent l'extension ancienne ; le parser lit le contenu indépendamment du suffixe.
- **Impact probable :** très faible dette technique, mais confusion de format et maintenance documentaire.
- **Recommandation :** conserver tant qu'une politique de dépréciation globale n'existe pas ; ce n'est pas une priorité de nettoyage.
- **Confiance :** 55 %.

### LOW-05 — Ruff signalait un unique ordre d'import — RÉSOLU

- **Classification suppression :** sans objet.
- **Fichier / symbole :** `frontend_contract.py:25-33`.
- **Raison :** import local `design_skills` placé après `generator.core` contrairement au tri configuré.
- **Preuve :** Ruff `I001`, auto-corrigeable.
- **Impact probable :** cosmétique, mais la CI lint devrait être verte.
- **Recommandation :** appliquer le tri lors de la phase de nettoyage.
- **Confiance :** 100 %.
- **État de clôture :** `ruff check src tests` est vert.

### LOW-06 — `requirements.txt` mélangeait runtime et test — RÉSOLU

- **Fichier / symbole :** `requirements.txt:7-12`; `pyproject.toml:17-23,38-43`.
- **Raison :** `pytest` est dans `requirements.txt` mais pas dans les dépendances runtime du paquet ; les deux fichiers sont annoncés « synchronisés » alors qu'ils ne décrivent pas le même usage.
- **Preuve :** `requirements.txt` ajoute `pytest`; `pyproject` le place correctement dans l'extra `dev`.
- **Impact probable :** installations inutilement lourdes et commentaire trompeur.
- **Recommandation :** faire de `pyproject.toml` la source unique ; garder éventuellement `requirements-dev.txt` généré.
- **Confiance :** 100 %.
- **État de clôture :** `requirements.txt` ne contient plus pytest ni les outils de développement ; `pyproject.toml` porte les extras `dev` et `ai`.

### LOW-07 — `requests` était obligatoire pour deux fournisseurs frontend seulement — RÉSOLU

- **Classification suppression :** **UNCERTAIN <70 %** comme dépendance globale ; elle est réellement utilisée.
- **Fichier / symbole :** `frontend_ai.py:56-155`; `pyproject.toml:22`.
- **Raison :** le compilateur déterministe et le smoke test n'en ont pas besoin ; seuls les appels API Claude/OpenAI l'importent localement.
- **Preuve :** imports `requests` à l'intérieur des deux factories ; le reste utilise `urllib`.
- **Impact probable :** dépendance runtime additionnelle pour tous les utilisateurs, même hors IA.
- **Recommandation :** envisager un extra `ai` ou standardiser sur `urllib`; ne pas supprimer sans préserver les fournisseurs.
- **Confiance :** 85 % sur l'optionalisation, 0 % sur une suppression brute.
- **État de clôture :** `requests` est dans `.[ai]` et dans `.[dev]` pour les tests ; l'absence de l'extra produit maintenant une `FrontendAIError` explicite.

### LOW-08 — Les dépendances du compilateur et celles des applications générées sont confondues

- **Fichier / symbole :** `pyproject.toml:17-23`.
- **Raison :** FastAPI, uvicorn et PyJWT ne sont pas importés par le processus de compilation normal, mais sont nécessaires pour exécuter les artefacts et le smoke test. Le paquet les installe toutes ensemble.
- **Preuve :** leurs imports apparaissent dans les chaînes de code généré, le wrapper de service ou les sous-processus, pas dans le cœur du compilateur.
- **Impact probable :** installation plus lourde mais expérience `monl run` simple.
- **Recommandation :** décision produit explicite : conserver le bundle « batteries incluses », ou séparer `compiler`, `runtime` et `ai`. Le gain ne justifie pas seul une rupture.
- **Confiance :** 95 %.

### LOW-09 — Commentaires de refactoring et numéros de « points » dominent le code

- **Fichier / symbole :** ensemble de `src/monl`, notamment `core.py`, `routes.py`, `frontend_contract.py`, `ast_validator.py`.
- **Raison :** de longs commentaires racontent l'historique (« AJOUT », « CORRECTIF », point 76/85/103…) plutôt que l'invariant actuel.
- **Preuve :** références très fréquentes à `docs/design_decisions.md`, qui dépasse 6 000 lignes ; docstrings mentionnant l'ancien monolithe.
- **Impact probable :** bruit cognitif, documentation locale qui vieillit, logique actuelle plus difficile à extraire.
- **Recommandation :** garder dans le code les raisons non évidentes et invariants ; déplacer l'historique détaillé dans ADR/changelog liés par titre stable plutôt que numéro séquentiel.
- **Confiance :** 96 %.

### LOW-10 — Le README contient des métriques statiques à automatiser

- **Fichier / symbole :** `README.md:7-10`.
- **Raison initiale :** badge « 756 tests » alors que 812 passent ; couverture « 88 % » non vérifiée pendant l'audit initial.
- **Preuve de clôture :** exécution `pytest-cov` à 92 % et badges README désormais basés sur le statut CI.
- **Impact probable :** confiance documentaire réduite.
- **Recommandation :** badges alimentés par CI ou formulation sans nombre figé.
- **Confiance :** 100 % pour le nombre de tests, incertaine pour la valeur de couverture.
- **État de clôture :** le nombre « 812 tests validés lors du dernier audit » reste informatif, tandis que les badges et la couverture officielle sont délégués à la CI.

### INFO-01 — Les signalements statiques sur Lark et les mixins ne sont pas du dead code

- **Fichier / symbole :** méthodes de `MonlTransformer` dans `parser.py:384-695`; méthodes `_generate_*` des mixins.
- **Raison :** Lark appelle les méthodes par nom de production ; l'héritage multiple résout les méthodes dynamiquement sur `MonlSecureGenerator`.
- **Preuve :** `MonlTransformer().transform(tree)` et héritage explicite dans `core.py:28-35`; tests parser/générateur réussis.
- **Impact probable :** une suppression automatisée sur résultat Vulture brut casserait le compilateur.
- **Recommandation :** configurer des listes blanches Vulture ou des décorations/annotations adaptées avant de l'ajouter en CI.
- **Confiance :** 100 %.

### INFO-02 — Les dépendances déclarées sont toutes justifiables

- **Fichier / symbole :** `pyproject.toml:17-23`.
- **Raison :** Lark parse ; FastAPI/PyJWT sont requis par les applications produites ; uvicorn sert et teste ; requests sert les fournisseurs IA.
- **Preuve :** usages retrouvés dans `parser.py`, `generator/runtime.py`, `cli.py`, `smoke_test.py`, `frontend_ai.py`.
- **Impact probable :** aucune suppression brute sûre parmi les dépendances runtime de base ; `requests` est désormais optionnelle.
- **Recommandation :** conserver les dépendances essentielles et maintenir la séparation `.[ai]`/`.[dev]` ; ne pas supprimer une dépendance runtime sans changement de distribution.
- **Confiance :** 100 %.

### INFO-03 — La sécurité et le comportement métier ont des tests profonds

- **Fichier / symbole :** `tests/test_*` (paiement, accès, propriété transitive, stock, agrégation, migrations, attaques, rate limit).
- **Raison :** les tests ne se limitent pas à vérifier des chaînes générées : beaucoup compilent, lancent uvicorn et interrogent réellement l'API et SQLite.
- **Preuve :** 812 réussites ; scénarios d'attaque, concurrence, webhooks signés, isolation multi-comptes, migrations, golden artefacts et rollback de publication.
- **Impact probable :** filet de sécurité solide pour un refactoring progressif.
- **Recommandation :** préserver les tests comportementaux tout en mutualisant leur infrastructure.
- **Confiance :** 100 %.

## Gestion des erreurs

Points positifs :

- `MonlSyntaxError` conserve fichier, ligne, colonne et extrait source.
- `ASTValidationError`, `AssetsToolError`, `ContentToolError` et `FrontendAIError` donnent déjà des frontières de domaine.
- Les opérations d'assets tentent une restauration si la revalidation échoue.
- Les routes générées ont de nombreux tests de statuts 401/404/409/422/502 et d'atomicité métier.

Lacunes :

- `compile_monl` expose maintenant `MonlError` ; les erreurs internes non typées de génération sont converties en `CompilationGenerationError`.
- Les commandes CLI historiques contiennent encore des `sys.exit`, ce qui est désormais cantonné à la frontière utilisateur.
- Les outils annexes d'assets/contenu n'ont pas le même rollback global que la compilation projet.
- Les erreurs d'espace disque, permission ou encodage n'ont pas de tests dédiés visibles.
- La majorité des tests d'erreur ciblent le DSL et l'application générée, moins les pannes de l'orchestrateur lui-même.

## Évaluation des tests par composant

| Composant | Tests présents | Qualité comportementale | Lacunes principales |
|---|---|---|---|
| Parser/diagnostics | Oui | Bonne : syntaxe valide et erreurs localisées | Pas de fuzz/property testing ; grammaire entière dans une chaîne difficile à couvrir structurellement |
| Validateur | Très nombreux | Excellente sur refus métier/sécurité | Passes séparées ; migration complète des fonctions pures encore possible |
| Générateur SQL/API | Très nombreux | Excellente : compilation, inspection et exécution réelle | Golden test global ajouté ; fixtures encore dupliquées |
| Runtime généré/auth | Oui | Très bonne : JWT, inscription, révocation, rate limit | Warning volontaire sur clé courte dans un test ; coûts élevés de lancement serveur |
| Paiement/stock/effets | Oui | Très bonne, y compris concurrence et faux prestataire | Infrastructure répétée dans plusieurs fichiers |
| CLI/orchestration | Oui | Bonne sur dispatch, chemins, diff/update | Pannes d'écriture partielles et interruptions peu couvertes |
| Contrat frontend | Oui | Bonne sur champs, routes, prompt et cohérence | Plans partagés ; compatibilité legacy conservée à l'entrée |
| Frontend IA/import | Oui | Bonne : API, agent CLI, zip-slip, artefacts protégés | Tests regroupés dans un fichier de 689 lignes avec imports en sections |
| Assets/contenu | Oui | Bonne, restauration et cohérence testées | Couplage à helpers privés ; peu de tests de panne filesystem réelle |
| Dialogue/TUI/templates | Oui | Bonne sur sortie et interactions simulées | Risque de duplication avec le catalogue sémantique du validateur |
| Smoke test | Oui | Bonne, frontend valide/cassé et UUID | Dépend de réseau local, uvicorn, Node/npm/jsdom ; environnement de test non hermétique |
| Packaging/docs | Minimal | Version/import vérifiés | Liens, commandes et documents obsolètes non vérifiés automatiquement |

Tests probablement redondants : plusieurs fichiers répètent « entité/champ inexistant », « règle dupliquée » et « la spec du banc compile ». Ils ne doivent pas être supprimés en bloc : une partie sert de test de caractérisation local. Une fois les passes séparées, ces cas peuvent devenir paramétrés au niveau du validateur, tandis que chaque test métier conserve seulement un ou deux contrôles d'intégration.

## Dépendances

| Dépendance | Usage réel | Décision recommandée |
|---|---|---|
| `lark` | Parseur du compilateur | Conserver, essentielle |
| `fastapi` | Runtime et serveur statique générés | Conserver si `monl run` reste intégré ; sinon extra `runtime` |
| `uvicorn` | `monl run`, smoke tests, applications | Même décision que FastAPI |
| `PyJWT` | Authentification du backend généré | Conserver dans runtime |
| `requests` | Fournisseurs IA Claude/OpenAI ; nombreux tests | Extra `ai` ; inclus dans `dev` pour les tests, absent du runtime de base |
| `pytest` | Tests seulement | Retirer de `requirements.txt` runtime, conserver dans extra dev |
| `pytest-cov` | Extra dev + CI | Couverture mesurée à 92 %, seuil fixé à 90 % |
| `ruff` | Lint | Conserver en dev/CI |
| Vulture | Extra dev + CI | `vulture src/monl --min-confidence 90`, aucun signalement actuel |
| mypy | Extra dev + CI | Strict sur `src/monl/ir.py`, `errors.py` et `generator/emitters.py` ; extension progressive recommandée |
| Node/npm/jsdom | Téléchargé/utilisé par smoke frontend | Documenter comme dépendance d'outil ; cache et mode sans JS déjà à clarifier |

## Carte simplifiée de l'architecture actuelle

```text
                    ┌──────────────────────┐
templates ─────────►│ dialogue_engine/TUI  │
                    └──────────┬───────────┘
                               ▼
                         source spec.ml
                               │
                               ▼
                    ┌──────────────────────┐
                    │ parser + Lark        │
                    │ dict AST brut        │
                    └──────────┬───────────┘
                               ▼
                    ┌──────────────────────┐
assets ────────────►│ MonlAST              │
                    │ validation + audit   │
                    │ dict normalisé       │
                    └──────────┬───────────┘
                               ▼
                    ┌──────────────────────┐
                    │ SecureGenerator      │
                    │ état dérivé + mixins │
                    └──────┬────────┬──────┘
                           │        │
             backend/SQL ◄─┘        └─► frontend_contract + prompt
                    │                         │
                    └──────────┬──────────────┘
                               ▼
                    cohérence + smoke + run

cli.py orchestre l'ensemble et réutilise désormais le même résultat
parser → MonlAST → SecureGenerator pour une compilation produit.
```

## Architecture cible recommandée

```text
source ─► Parser ─► ParsedSpec typée
                    │
                    ▼
              ValidationPipeline
        schema → relations → sécurité → métier → contenu/UI
                    │
                    ▼
          CompilationModel immuable et typé
          ├── EntityModel / FieldPolicy
          ├── RelationPlan / OwnershipPlan
          ├── RoutePlan / EffectPlan
          └── diagnostics
                    │
          ┌─────────┼─────────────┐
          ▼         ▼             ▼
     SqlEmitter  ApiEmitter  FrontendContractEmitter
          └─────────┼─────────────┘
                    ▼
          ArtifactSet en mémoire/temporaire
                    │
              validation finale
                    │
             publication atomique

CLI / dialogue / assets / contenu restent des adaptateurs autour de ce noyau.
Ils traduisent les erreurs typées en messages, sans porter les règles métier.
```

Cette cible ne recommande pas un réécriture totale. Elle formalise les frontières déjà présentes et permet une migration passe par passe.

## Les 10 principaux problèmes

1. `MonlAST` conserve des méthodes spécialisées mutables malgré le pipeline explicite.
2. IR partiellement typée : plusieurs attributs historiques du générateur restent une seconde représentation.
3. Mixins du générateur encore couplés par état implicite.
4. Exceptions générales dans certains outils et runtime généré, malgré la frontière de compilation typée.
5. `content_tool` importe des helpers privés d'`assets_tool`.
6. Documentation de phases historiques à archiver ou réécrire.
7. Les helpers historiques de tests d'intégration restent partiellement dupliqués malgré le support serveur partagé.
8. Compatibilités historiques (`run_claude_code`, `.yaml`, `landing.mode/template`) désormais documentées mais encore actives.
9. Tests de panne filesystem avancée encore limités au rollback de publication.
10. Vérification automatique des liens, commandes et exemples documentaires encore limitée.

## Suppressions les plus sûres

| Candidat | Classement | Justification |
|---|---|---|
| `MonlSecureGenerator._get_row_column_names` | **SAFE_TO_REMOVE >95 % — déjà supprimé** | Définition unique, aucun appel interne/test, commentaire historique |
| Correction de l'import non trié | N'est pas une suppression | Changement purement mécanique Ruff |
| `pytest` de `requirements.txt` runtime | **SAFE_TO_REMOVE >95 %** de ce fichier seulement | Déjà correctement déclaré dans l'extra dev ; ne pas le retirer du dev |
| `run_claude_code` | **LIKELY_REMOVABLE 70–95 %** | Aucun usage interne, mais compatibilité externe possible |
| `landing.mode/template` | **UNCERTAIN <70 %** | Sans effet, mais compatibilité explicite avec anciennes specs |
| Extension `.yaml` | **UNCERTAIN <70 %** | Dette faible et utilisateurs externes inconnus |

Il n'existe pas de preuve suffisante pour supprimer un module entier. Les mixins, helpers privés appelés une fois et méthodes du Transformer sont du code vivant. La prochaine suppression réellement candidate est `run_claude_code`, mais seulement après une version d'avertissement et une vérification de l'API publiée.

## Refactorings les plus rentables

1. **Extraire progressivement les méthodes de `MonlAST`** en fonctions/passes pures derrière le pipeline existant.
2. **Étendre l'IR typée** aux politiques et attributs encore stockés en dictionnaires internes.
3. **Faire remonter les exceptions typées** et réserver `sys.exit` à la frontière CLI. **Socle fait pour la compilation ; outils historiques à poursuivre.**
4. **Découpler les mixins** au profit d'émetteurs composés une fois l'IR stabilisée.
5. **Archiver la documentation historique** et vérifier les commandes documentées en CI. **Bannières et politique ajoutées.**
6. **Maintenir la fermeture explicite des ressources de test** ; le dernier passage ne laisse qu'un warning JWT intentionnel.
7. **Définir les fenêtres de dépréciation** des wrappers et syntaxes historiques. **Politique publiée.**

## Plan de nettoyage par étapes

### Étape 0 — Baseline et garde-fous — TERMINÉE

- Geler les 812 tests réussis comme baseline CI.
- Mutualiser le démarrage des serveurs d'intégration dans `tests/support/server.py`.
- Corriger Ruff et vérifier `git diff --check`.
- Installer réellement `ruff`, `pytest-cov`, Vulture et mypy dans l'extra dev/CI. **Fait.**
- Ajouter des listes blanches Vulture pour le Transformer Lark et documenter les appels dynamiques. **Aucun signalement à 90 % ; revue manuelle conservée.**
- Produire quelques golden files sur les exemples représentatifs avant tout changement de génération. **Fait : golden global backend/contrat/état.**

### Étape 1 — Nettoyage sans changement architectural — PARTIELLE

- Corriger l'ordre d'import Ruff. **Fait.**
- Retirer `_get_row_column_names` après test complet. **Fait.**
- Déprécier explicitement `run_claude_code` si l'API externe doit être préservée. **Politique et docstring ajoutées.**
- Séparer requirements runtime/dev et corriger les métriques README. **Fait ; l'extra `ai` est séparé.**
- Marquer les documents de phases comme archives ou les mettre à jour. **Bannières historiques ajoutées.**

### Étape 2 — Mutualiser les tests — TERMINÉE EN GRANDE PARTIE

- Créer `tests/support/server.py`. **Fait pour le cycle de vie uvicorn ; les autres supports restent à extraire si le besoin se confirme.**
- Migrer un fichier à la fois, sans fusionner les scénarios métier.
- Ajouter des tests d'interruption et de panne d'écriture de l'orchestrateur. **Rollback et staging incomplet couverts.**
- Mesurer la couverture réelle et définir un seuil réaliste. **92 %, seuil 90 %.**

### Étape 3 — Unifier la compilation — TERMINÉE

- Créer une fonction qui retourne `CompilationResult` (IR + générateur + diagnostics intégrés). **Fait.**
- Faire consommer le même résultat aux émetteurs backend et frontend. **Fait.**
- Retirer le double parcours dans `compile_project`. **Fait.**
- Faire remonter les exceptions ; réserver `sys.exit` à la frontière CLI. **Fait pour `compile_monl`, tests ajoutés.**

### Étape 4 — Formaliser l'IR — SOCLE TERMINÉ, MIGRATION EN COURS

- Introduire les types des entités, champs, relations, politiques et routes. **Socle fait dans `src/monl/ir.py`; `CompilationPlans` calculé une seule fois pour les émetteurs.**
- Migrer d'abord `public`, `ownership`, champs serveur et paiements, concepts aujourd'hui multireprésentés.
- Activer mypy progressivement sur les nouveaux modules.
- Garder un adaptateur de sérialisation compatible avec le JSON actuel.

### Étape 5 — Découper validation et génération — TERMINÉE POUR LE PÉRIMÈTRE ACTUEL

- Extraire des passes de validation derrière `MonlAST`. **Fait : 25 passes explicites et ordre couvert par tests.**
- Construire `RoutePlan` avant tout rendu de code. **Fait et partagé par backend/frontend.**
- Scinder routes CRUD, effets, paiement et post-paiement en émetteurs ciblés. **Fait : cinq renderers d'actions et deux familles métier.**
- Remplacer progressivement les mixins par composition.

### Étape 6 — Robustesse des artefacts — TERMINÉE

- Générer tous les fichiers dans un staging local. **Fait.**
- Valider syntaxe, contrat et empreintes avant publication. **Fait par le pipeline et `monl.json`.**
- Publier avec sauvegarde/manifeste et restauration en cas d'échec. **Fait.**
- Tester interruption, permission refusée et espace disque simulé. **Rollback de remplacement et staging incomplet couverts ; pannes système avancées restent optionnelles.**

### Étape 7 — Dépréciations — POLITIQUE PUBLIÉE

- Mesurer l'usage de `.yaml`, `landing.mode/template` et wrappers historiques.
- Publier une politique de dépréciation compatible avec le statut bêta. **Fait dans `docs/DEPRECATIONS.md`.**
- Supprimer seulement après au moins une version d'avertissement et tests de migration.

## Conclusion

La codebase n'a pas besoin d'une réécriture ni d'une purge agressive. Son comportement est solide : **812 tests passent avec 91,62 % de couverture**, le lint, mypy ciblé et Vulture sont verts, et les contrôles d'intégration couvrent réellement SQLite, HTTP, authentification, paiement, sécurité et génération frontend. Le cycle de nettoyage a traité les risques les plus rentables : pipeline unique, IR de transition, erreurs typées de compilation, passes de validation explicites, renderers de routes, publication transactionnelle, `CompilationPlans`, golden tests et support serveur partagé.

Les suppressions de code ne sont toujours pas suffisamment sûres pour justifier une purge automatique. Les sujets restants sont de la migration progressive — types internes, exceptions CLI, mixins et documentation — et sont séparés des fonctionnalités métier. Ils peuvent être menés par petites étapes protégées par la suite complète et le seuil de couverture CI.
