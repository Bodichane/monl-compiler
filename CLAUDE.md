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
`monl frontend` appelle l'IA via API (ANTHROPIC_API_KEY) ou via Claude
Code (`--provider claude-code`, authentification par abonnement — point
43) ; `monl import` couvre le copier/coller claude.ai (point 42). Dans
tous les cas : mêmes garde-fous, même re-vérification (cohérence + smoke
test). ATTENTION : chaque projet compilé reçoit son PROPRE CLAUDE.md
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

**`docs/design_decisions.md`** est le journal détaillé du projet — 39 points
à ce jour, avec sommaire en tête de fichier. Chaque règle stricte du
compilateur, chaque bug corrigé, chaque décision d'architecture y est
expliquée avec le "pourquoi", pas seulement le "quoi". **Le consulter avant
d'ajouter quoi que ce soit** — plusieurs pièges déjà rencontrés (voir points
23, 26) ne sont pas évidents à deviner depuis le code seul.

## Méthode de travail — non négociable

**Chaque changement est prouvé par exécution réelle, jamais par relecture
de code seule.** Concrètement :
- Compiler réellement (`python3 src/main.py exemples/XX.ml`)
- Relancer un vrai serveur (`python3 -m uvicorn app:app --host 127.0.0.1 --port PORT`)
- Faire de vrais appels (`curl`, ou un script Node+jsdom pour le JS front —
  voir `/tmp/jsdom_test/` dans les sessions précédentes, à recréer si besoin :
  `npm install jsdom` puis charger le HTML généré avec `runScripts: "dangerously"`)
- Lancer la suite de tests : `python3 -m pytest tests/ -q` (56 tests actuellement)

Plusieurs bugs réels (ordre des contraintes `FOREIGN KEY`, collision avec un
mot-clé SQL réservé, `scrollIntoView` absent masquant un vrai succès,
sur-échappement de backslash entre couches de templating Python, un mécanisme
de clé étrangère qui décrémentait le mauvais enregistrement) ne se seraient
JAMAIS révélés par simple lecture — ne pas sauter cette étape pour aller
plus vite.

**Toujours nettoyer avant/après compilation** :
```bash
rm -f app.py schema.sql sandbox_ai.py .jwt_secret .monl_theme_seed *.db \
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

### Briques terminées et testées (points 24-30)
1. **`capability auth`** — bloc déclaratif, aucun effet sur la génération
   pour l'instant (prouvé par compilation identique avec/sans le bloc).
2. **`rule Entite.champ hidden`** — masque un champ de toutes les réponses
   de lecture (liste + détail), pour tout le monde. Reste en base, reste
   modifiable en écriture. Testé sur `exemples/13_anon_forum_demo.ml`.
3. **`rule Entite.Create decrements Entite.champ [by N]`** — décrémente un
   champ numérique sur une entité liée à la création d'un enregistrement
   (typiquement un signalement). Testé sur `exemples/14_reputation_demo.ml`.
4. **`rule Entite.Create increments Entite.champ [by N]`** — symétrique de
   `decrements`, pour les likes/appréciations. Grammaire : deux productions
   Lark nommées distinctes (`decrement_rule`/`increment_rule`), pas une seule
   règle partagée par mot-clé (évite le piège de filtrage Lark qui avait fait
   annuler le premier essai). `ast_validator.py` valide les deux dans la même
   boucle, chaque règle portant un champ `"direction"`. `generator.py` choisit
   `+`/`-` selon ce champ. Testé sur `exemples/15_likes_demo.ml`.
5. **`rule Entite.champ categorized: "label" below N, ..., "label" otherwise`**
   — remplace un champ `Integer`/`Float` par un libellé de catégorie dans
   toutes les réponses de lecture (liste + détail), sur le même principe que
   `hidden` mais avec substitution plutôt que suppression. Portée générale
   (n'importe quel champ numérique, pas seulement ceux ciblés par
   `increments`/`decrements`). Incompatible avec `hidden` sur le même champ
   (erreur de compilation explicite). Dernier palier obligatoirement
   `otherwise` (couverture totale garantie). Libellés injectés via `repr()`
   dans le code généré (jamais d'interpolation manuelle entre guillemets).
   Testé sur `exemples/16_likes_categories_demo.ml`.

6. **Assemblage final : réseau social anonyme** — toutes les briques
   ci-dessus combinées dans une seule spec (`exemples/17_anon_social_network.ml`),
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
   fiable dont dériver un pseudonyme). Testé sur
   `exemples/18_generated_pseudonym_demo.ml`.

8. **`rule Entite.Action accessibleBy col1, col2`** — contrôle d'accès à
   deux parties (ou plus) : l'action n'est permise que si l'identifiant JWT
   de l'appelant apparaît dans l'une des colonnes listées (expéditeur via
   la FK de relation auto-peuplée, destinataire via un champ Integer
   déclaré). Liste filtrée par WHERE ... OR ..., détail/Update/Delete en
   403 pour les tiers. Au moins deux colonnes distinctes (sinon `ownedBy`),
   conflit bloquant avec `ownedBy`, `public` l'emporte. Ferme la brique
   « messagerie privée » évoquée dès la brique 1. Testé sur
   `exemples/19_private_messages.ml` (`tests/test_access_parties.py`,
   serveur réel éphémère). Voir point 31 de `docs/design_decisions.md`.

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

- `src/generator/` est un PACKAGE depuis la bêta 3 (l'ancien module de 1 307
  lignes a été découpé) : `core.py` (état issu de l'AST, orchestration,
  `_compute_route_map`), `runtime.py` (socle du app.py généré : secret,
  `_connect`, init/migrations/seed, register/login/logout, quota),
  `routes.py` (une route par couple action/entité + contrôle d'accès),
  `schemas.py`, `sql_schema.py`, `theme.py`, `sandbox.py`, `admin_cli.py`
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
- Direction de design (bêta 3) : un thème épinglé par un bloc `ui … theme:`
  est CONTRAIGNANT (palette exacte, sans variation de teinte, vérifiée par
  `_verifier_palette` dans src/smoke_test.py) ; un thème déduit du vocabulaire
  reste une proposition (écart = avertissement). Ne pas inverser cette
  asymétrie : strict sur ce qui est déclaré, tolérant sur ce qui est deviné.
- `_select_theme` / `_load_or_create_theme_seed` (generator/theme.py) : identité
  visuelle déterministe par projet — plus aucun HTML n'en dérive depuis le
  point 41, elle est transmise à l'IA frontend comme direction de design
  via le contrat.
- Le smoke test (src/smoke_test.py) démarre un serveur ÉPHÉMÈRE dans un
  dossier temporaire : il ne touche jamais app.db du projet. Le fetch de
  jsdom DOIT être injecté via beforeParse (bug réel : assigné après
  construction, il n'est jamais vu par les scripts de la page).

## Commandes de référence

```bash
pip install -r requirements.txt --break-system-packages
cd src && python3 main.py ../exemples/01_todo_list.ml
cd .. && python3 -m uvicorn app:app --reload   # jamais `python3 app.py` directement
python3 -m pytest tests/ -v
```
