# monl — mémoire de projet pour Claude Code

## Ce qu'est monl

PIVOT (point 40 de docs/design_decisions.md) : monl est désormais une
plateforme d'ORCHESTRATION. `./monl` (src/cli.py) mène un dialogue guidé
sans IA (src/dialogue_engine.py) qui produit la spec, compile le backend,
et génère un contrat frontend (src/frontend_contract.py :
frontend_contract.json + FRONTEND_PROMPT.md) destiné à une IA UI externe.
`monl run` vérifie la cohérence (empreintes dans monl.json) et monte
frontend/ sur /site via un wrapper serve.py — app.py reste scellé.
`monl update` recompile et rapporte le delta du contrat. Le dialogue
ouvre sur un catalogue de 10 modèles d'applications (src/app_templates.py,
point 45 — chaque modèle est testé compilable en tout-non/tout-oui) et
fonctionne en saisie stricte, entièrement déterministe : aucune IA, aucun
appel réseau. La spec produite est revalidée par le vrai parseur avant
d'être écrite.
`monl frontend` appelle l'IA soit par clé API — Anthropic, ou n'importe
quel fournisseur au dialecte OpenAI via la table `OPENAI_COMPATIBLE` et
l'échappatoire `--provider openai-compatible` (point 69) — soit par un
agent en ligne de commande (`--provider claude-code|codex|gemini`, ou
`--agent-command` pour tout autre, point 69 ; authentification par
abonnement — point 43) ; `monl import` couvre le copier/coller claude.ai
(point 42). Dans tous les cas : mêmes garde-fous, même re-vérification
(cohérence + smoke test). Le garde-fou d'empreinte des artefacts protégés
ne dépend PAS de l'agent utilisé — ne jamais le contourner en ajoutant une
voie. ATTENTION : chaque projet compilé reçoit son PROPRE CLAUDE.md
(généré par write_project_claude_md) — ne pas confondre avec ce fichier-ci,
qui est la mémoire du dépôt monl lui-même. Le cœur
ci-dessous est inchangé et reste la source de vérité :

Compilateur DSL (fichiers `.ml` — l'ancienne extension `.yaml` reste acceptée) qui génère des applications
complètes (FastAPI + SQLite + JWT) à partir de specs déclaratives. Pipeline :
grammaire Lark (`src/parser.py`) → validateur + audit de sécurité
(`src/ast_validator.py`) → AST normalisé → générateur (package
`src/generator/`)
→ `app.py` / `schema.sql` / `sandbox_ai.py` + `frontend_contract.json` /
`FRONTEND_PROMPT.md` (couche orchestrateur, voir src/cli.py).

## Documentation à lire avant toute nouvelle brique

**`docs/design_decisions.md`** est le journal détaillé du projet — numéroté
jusqu'à 74, avec sommaire complet en tête de fichier. Deux pièges de
numérotation, tous deux assumés : les numéros **45 et 46 désignent chacun
deux points distincts** (séquelle d'une fusion), et le **point 6 est un
doublon réservé** du point 1, vide, gardé pour ne pas décaler les renvois.
Citer un point par son titre autant que par son numéro. Chaque règle stricte du
compilateur, chaque bug corrigé, chaque décision d'architecture y est
expliquée avec le "pourquoi", pas seulement le "quoi". **Le consulter avant
d'ajouter quoi que ce soit** — plusieurs pièges déjà rencontrés (voir points
23, 26) ne sont pas évidents à deviner depuis le code seul.

## Méthode de travail — non négociable

**Chaque changement est prouvé par exécution réelle, jamais par relecture
de code seule.** Concrètement :
- Compiler réellement (`python3 -m monl.main exemples/03_reseau_social.ml`,
  depuis la racine avec `src/` sur le PYTHONPATH — ou `./monl compile`)
- Relancer un vrai serveur (`python3 -m uvicorn app:app --host 127.0.0.1 --port PORT`)
- Faire de vrais appels (`curl`, ou un script Node+jsdom pour le JS front —
  voir `/tmp/jsdom_test/` dans les sessions précédentes, à recréer si besoin :
  `npm install jsdom` puis charger le HTML généré avec `runScripts: "dangerously"`)
- Lancer la suite de tests : `python3 -m pytest tests/ -q` (260 tests
  actuellement ; `tests/test_demo.py` et `tests/test_design_contract.py`
  s'appuient sur le dossier `demo/` versionné — ne pas le supprimer)

Plusieurs bugs réels (ordre des contraintes `FOREIGN KEY`, collision avec un
mot-clé SQL réservé, `scrollIntoView` absent masquant un vrai succès,
sur-échappement de backslash entre couches de templating Python, un mécanisme
de clé étrangère qui décrémentait le mauvais enregistrement) ne se seraient
JAMAIS révélés par simple lecture — ne pas sauter cette étape pour aller
plus vite.

**Outillage de vérification** (point 63) — trois questions, trois commandes :
```bash
ruff check src tests                                  # zéro attendu : tout
                                                      # signalement est un vrai
python3 -m pytest tests/ -q --cov=src --cov-report=term-missing   # 88 %
python3 -m pytest tests/test_architecture.py -q       # les frontières de ce
                                                      # fichier, vérifiées
```
Les exceptions de `ruff` vivent dans `pyproject.toml` et portent chacune sa
raison — en ajouter une sans raison écrite, c'est rouvrir la porte que le
point 63 ferme. La CI (`.github/workflows/ci.yml`) rejoue lint + suite.

**Toujours nettoyer avant/après compilation** (depuis le point 64, la suite
de tests ne salit plus la racine : ce nettoyage ne concerne que VOS
compilations manuelles) :
```bash
rm -f app.py schema.sql sandbox_ai.py .jwt_secret *.db \
      frontend_contract.json FRONTEND_PROMPT.md FRONTEND_UPDATE_PROMPT.md monl.json serve.py
find . -name "__pycache__" -exec rm -rf {} +
```

**Piège d'environnement récurrent** : les processus lancés en arrière-plan
(`&`) dans un appel d'outil ne survivent PAS à l'appel suivant — démarrer un
serveur ET faire les requêtes de test doivent être dans le MÊME appel bash.

## Vision produit : écosystème de capacités, construit brique par brique

Décision explicite et actée : PAS de multi-DSL ni d'IR multi-cible pour
l'instant (projet d'une tout autre ampleur, à reconsidérer seulement une
fois plusieurs capacités réelles éprouvées). Chaque brique est petite,
testée avant la suivante. Progression du simple au complexe, avec un
réseau social anonyme comme banc d'essai final.

### Briques terminées et testées (points 24-31, puis 74)

> **Où sont passés les fichiers de preuve.** Chaque brique avait à l'origine
> son `exemples/NN_xxx_demo.yaml` dédié. La bêta 3 (commit `2105a1f`) les a
> tous supprimés au profit de 5 exemples thématiques : `01_portfolio.ml`,
> `02_boutique.ml`, `03_reseau_social.ml`, `04_kanban.ml`,
> `05_classement.ml`. **`exemples/03_reseau_social.ml` consolide à lui seul
> les briques 3 à 8** ; `tests/test_compile_all.py` compile chaque exemple à
> chaque exécution de la suite. Les références ci-dessous ont été
> resynchronisées le 26/07/2026 — ne pas les faire pointer vers les anciens
> fichiers, ils n'existent plus.
>
> Attention à la nuance : compiler n'est pas se comporter correctement.
> **Huit briques sur neuf sont désormais éprouvées contre un vrai serveur
> éphémère** : `accessibleBy` (`tests/test_access_parties.py`), le filtrage de
> lecture d'`ownedBy` (`tests/test_lecture_privee.py`), le masquage `hidden`
> (`tests/test_masquage_hidden.py`, point 64), puis `generated`, `increments`,
> `decrements` et `categorized` (`tests/test_briques_comportement.py`,
> point 70), enfin `payable` (`tests/test_paiement.py`, point 74 — avec son
> faux Stripe embarqué). Seule `capability auth` n'a que la couverture de
> compilation — c'est cohérent, elle n'a par construction aucun effet sur la
> génération (brique 1). Toute NOUVELLE brique doit arriver avec son test
> contre serveur : la couverture de compilation, à elle seule, a laissé passer
> cinq briques pendant toute la vie du projet.

1. **`capability auth`** — bloc déclaratif, aucun effet sur la génération
   pour l'instant (prouvé par compilation identique avec/sans le bloc).
2. **`rule Entite.champ hidden`** — masque un champ de toutes les réponses
   de lecture (liste + détail), pour tout le monde. Reste en base, reste
   modifiable en écriture. Implémenté dans `src/parser.py` (`masking_rule`)
   et `src/generator/routes.py`. Couvert depuis le point 64 par
   `tests/test_masquage_hidden.py`, contre un vrai serveur : masquage en
   liste ET en détail, connecté comme anonyme, champ toujours écrivable et
   toujours en base (vérifié par lecture SQLite directe). Reste absent de
   tous les exemples — la couverture vient du test, pas d'une compilation.
3. **`rule Entite.Create decrements Entite.champ [by N]`** — décrémente un
   champ numérique sur une entité liée à la création d'un enregistrement
   (typiquement un signalement). Compilé par `exemples/03_reseau_social.ml`
   (`Report.Create decrements Member.reputation`).
4. **`rule Entite.Create increments Entite.champ [by N]`** — symétrique de
   `decrements`, pour les likes/appréciations. Grammaire : deux productions
   Lark nommées distinctes (`decrement_rule`/`increment_rule`), pas une seule
   règle partagée par mot-clé (évite le piège de filtrage Lark qui avait fait
   annuler le premier essai). `ast_validator.py` valide les deux dans la même
   boucle, chaque règle portant un champ `"direction"`. `generator.py` choisit
   `+`/`-` selon ce champ. Compilé par `exemples/03_reseau_social.ml` et
   `exemples/05_classement.ml`.
5. **`rule Entite.champ categorized: "label" below N, ..., "label" otherwise`**
   — remplace un champ `Integer`/`Float` par un libellé de catégorie dans
   toutes les réponses de lecture (liste + détail), sur le même principe que
   `hidden` mais avec substitution plutôt que suppression. Portée générale
   (n'importe quel champ numérique, pas seulement ceux ciblés par
   `increments`/`decrements`). Incompatible avec `hidden` sur le même champ
   (erreur de compilation explicite). Dernier palier obligatoirement
   `otherwise` (couverture totale garantie). Libellés injectés via `repr()`
   dans le code généré (jamais d'interpolation manuelle entre guillemets).
   Compilé par `exemples/03_reseau_social.ml` (`Post.likes` en peu /
   populaire / viral).

6. **Assemblage final : réseau social anonyme** — toutes les briques
   ci-dessus combinées dans une seule spec (aujourd'hui
   `exemples/03_reseau_social.ml`, héritier de `17_anon_social_network.yaml`),
   chacune dans son rôle le plus naturel plutôt qu'empilées sur la même
   entité (`Post` anonyme/public/catégorisé — auteur en pseudonyme
   `generated`, brique 7 ci-dessous — `Comment` identifié avec `ownedBy`).
   Deux bugs réels découverts en l'assemblant (pas en le
   relisant), tous deux résolus : un commentaire seul sur sa propre ligne
   entre deux blocs de premier niveau faisait planter la compilation
   (`Tree` non transformé) ; un commentaire seul À L'INTÉRIEUR d'un bloc
   indenté (`entity`/`workflow`...) faisait carrément échouer le parsing
   (`UnexpectedToken`). Corrigé à la racine dans `src/parser.py` :
   `parse_monl_string()` retire du texte source toute ligne qui n'est
   QUE du commentaire, avant même que Lark ne la voie — un seul correctif
   couvrant les deux cas, plutôt que 5 règles de grammaire à corriger
   séparément (entity/workflow/custom_block/ui_block/landing_block).
7. **`rule Entite.champ generated`** — retire un champ `String` du schéma
   Pydantic de la route `Create` de son entité ; le serveur le peuple seul
   avec un pseudonyme anonyme stable par compte (`Anon#3821`, généré une
   seule fois à `/register`, porté par le JWT comme `actor`/`user_id`).
   Ferme le trou du point 29 (`Post.author` en `String` libre, sans
   garantie d'intégrité). Incompatible avec `hidden` sur le même champ, et
   avec une action `Create` `public` sur la même entité (pas d'identité
   fiable dont dériver un pseudonyme). Compilé par
   `exemples/03_reseau_social.ml` (`Post.author`).

8. **`rule Entite.Action accessibleBy col1, col2`** — contrôle d'accès à
   deux parties (ou plus) : l'action n'est permise que si l'identifiant JWT
   de l'appelant apparaît dans l'une des colonnes listées (expéditeur via
   la FK de relation auto-peuplée, destinataire via un champ Integer
   déclaré). Liste filtrée par WHERE ... OR ..., détail/Update/Delete en
   403 pour les tiers. Au moins deux colonnes distinctes (sinon `ownedBy`),
   conflit bloquant avec `ownedBy`, `public` l'emporte. Ferme la brique
   « messagerie privée » évoquée dès la brique 1. Éprouvé contre un serveur
   réel éphémère par `tests/test_access_parties.py` (qui embarque sa propre
   spec), et compilé par `exemples/03_reseau_social.ml` (`PrivateMessage`).
   Voir point 31 de `docs/design_decisions.md`.

9. **`rule Entite.champ payable`** — la règle nomme le champ qui porte le
   MONTANT, donc l'entité qu'on encaisse. Ajoute deux colonnes de suivi
   (`payment_status`, `payment_ref`, jamais fournies par le client) et deux
   routes : `POST /entite/{id}/paiement` et `POST /paiement/webhook`.
   **Le montant vient de la BASE, jamais du corps de requête** — la route de
   règlement n'accepte aucun corps, et relit le champ à chaque appel. Six
   refus à la compilation (entité ou champ inexistant, champ non numérique,
   cumul avec `hidden`, deux champs `payable` sur une entité, création
   `public`). Premier appel SORTANT d'un backend monl : secrets par
   l'environnement (`STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`), 503 en
   nommant la variable absente, et le reste du serveur intact — `monl run` et
   le smoke test restent verts hors ligne. Le webhook vérifie la signature du
   prestataire : c'est le SEUL endroit du backend généré où un tiers non
   authentifié écrit en base, ne jamais l'affaiblir. Éprouvé contre un serveur
   réel et un faux Stripe embarqué par `tests/test_paiement.py`. Voir point 74.

### Briques suivantes déjà évoquées, non cadrées
- Rôle superviseur au-dessus d'`accessibleBy` (un modérateur qui lit tous
  les messages privés via `sharedBy`) — exclu volontairement de la première
  version de la brique 8, voir point 31.

### Hors de portée, assumé et documenté
- Algorithme de recommandation basé sur les likes — moteur de scoring/ML,
  pas un compilateur déclaratif.
- (Le mode `template` de l'ancienne landing n'existe plus : tout le
  frontend généré par monl a été retiré au point 41.)

## Repères utiles dans le code

- Depuis le point 65, tout le code vit dans le paquet `src/monl/` :
  les imports internes sont RELATIFS (`from .parser import …`) et les tests
  importent `monl.xxx` sans manipuler `sys.path` (voir `tests/conftest.py`).
  `src/monl/generator/` est un sous-package depuis la bêta 3 (l'ancien module de 1 307
  lignes a été découpé) : `core.py` (état issu de l'AST, orchestration,
  `_compute_route_map`), `runtime.py` (socle du app.py généré : secret,
  `_connect`, init/migrations/seed, register/login/logout, quota),
  `routes.py` (une route par couple action/entité + contrôle d'accès),
  `schemas.py`, `sql_schema.py`, `sandbox.py`, `admin_cli.py`
  (manage.py). La classe est recomposée par mixins dans `core.py` : une
  nouvelle brique de génération s'ajoute dans le module de sa couche, pas
  dans `core.py`. `from generator import MonlSecureGenerator` reste l'import
  public.
- Un rôle n'est inscriptible que s'il porte `selfRegister` dans la spec
  (bêta 3). Toute évolution touchant `/register`, le contrat frontend ou le
  smoke test doit conserver cette frontière : c'est elle qui empêche un
  client anonyme de s'attribuer un rôle privilégié. Chemin légitime pour les
  autres rôles : le `manage.py` généré.
- `_compute_route_map` (generator/core.py) : source unique de vérité pour le
  regroupement des routes, partagée entre la génération FastAPI et le
  contrat frontend (src/frontend_contract.py) — ne pas dupliquer cette
  logique ailleurs. Un test (tests/test_orchestrator.py) confronte le
  contrat aux décorateurs réellement écrits dans app.py.
- `src/tui.py` : présentation du dialogue. Le moteur ne l'importe QUE via
  l'interface `PlainDialogueUI` (rendu nu = chaînes historiques) ; le rendu
  stylé n'est injecté que par `run_interactive_dialogue`. Ne jamais mettre de
  logique de dialogue dans tui.py, ni de mise en forme dans dialogue_engine.py.
- Direction de design (point 72) : le compilateur ne décide RIEN du visuel —
  ni palette, ni typographie, ni rayon. Le bloc `ui … theme:` reste accepté
  par la grammaire mais n'a plus aucun effet, `.monl_theme_seed` a disparu, et
  `_verifier_palette` avec elle. La direction vient du DIALOGUE (registre
  visuel, place des images) et voyage par le brief. Ne pas réintroduire de
  suggestion « facultative » dans le contrat : elle oriente quand même.
- Paiement (point 74) : `_generate_payment_routes` (generator/routes.py) est
  la seule couche qui parle à l'extérieur. Trois invariants à ne jamais
  assouplir — le montant est lu en base et la route n'accepte AUCUN corps ;
  la signature du webhook est vérifiée avant toute écriture (seul endroit du
  backend généré où un tiers non authentifié écrit) ; une clé absente donne
  503 en la nommant, sans empêcher le reste du serveur de fonctionner.
  `MONL_STRIPE_BASE_URL` existe pour que la brique soit éprouvable sans
  appeler le vrai Stripe (`tests/test_paiement.py` embarque son prestataire).
- Deux garde-fous d'empreinte dans src/frontend_ai.py, complémentaires
  (point 73) : `_fingerprint_protected` vérifie ce qui NE DOIT PAS bouger
  (app.py & consorts, point 69), `_fingerprint_frontend` vérifie ce qui DOIT
  bouger. Sans le second, un frontend valide préexistant franchissait tous les
  contrôles et monl annonçait une construction qui n'avait pas eu lieu.
- Le smoke test (src/smoke_test.py) démarre un serveur ÉPHÉMÈRE dans un
  dossier temporaire : il ne touche jamais app.db du projet. Le fetch de
  jsdom DOIT être injecté via beforeParse (bug réel : assigné après
  construction, il n'est jamais vu par les scripts de la page).
- Le contrat annonce `api.base_url = ""` — MÊME ORIGINE, jamais d'URL absolue
  ni de port codé en dur : `monl run` monte frontend/ sur /site du serveur qui
  porte déjà l'API. Y remettre une base absolue casserait `monl run --port` et
  ferait recaler par le smoke test (port éphémère) tout frontend obéissant.
  Le shim jsdom refuse explicitement les URL absolues plutôt que de les
  réécrire : les réécrire serait un faux positif. Point 51.

## Commandes de référence

```bash
pip install -e . --break-system-packages   # point 65 : vrai paquet, commande 'monl'
./monl compile exemples/01_portfolio.ml --output build/portfolio
python3 -m uvicorn app:app --reload        # jamais `python3 app.py` directement
python3 -m pytest tests/ -v
```
