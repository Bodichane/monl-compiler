# MonLang — mémoire de projet pour Claude Code

## Ce qu'est MonLang

Compilateur DSL (fichiers `.monlang`/`.yaml`) qui génère des applications
complètes (FastAPI + SQLite + JWT) à partir de specs déclaratives. Pipeline :
grammaire Lark (`src/parser.py`) → validateur + audit de sécurité
(`src/ast_validator.py`) → AST normalisé → générateur (`src/generator.py`)
→ `app.py` / `schema.sql` / `sandbox_ai.py` / `landing.html` / `dashboard.html`.

## Documentation à lire avant toute nouvelle brique

**`docs/design_decisions.md`** est le journal détaillé du projet — 26 points
à ce jour, avec sommaire en tête de fichier. Chaque règle stricte du
compilateur, chaque bug corrigé, chaque décision d'architecture y est
expliquée avec le "pourquoi", pas seulement le "quoi". **Le consulter avant
d'ajouter quoi que ce soit** — plusieurs pièges déjà rencontrés (voir points
23, 26) ne sont pas évidents à deviner depuis le code seul.

## Méthode de travail — non négociable

**Chaque changement est prouvé par exécution réelle, jamais par relecture
de code seule.** Concrètement :
- Compiler réellement (`python3 src/main.py exemples/XX.yaml`)
- Relancer un vrai serveur (`python3 -m uvicorn app:app --host 127.0.0.1 --port PORT`)
- Faire de vrais appels (`curl`, ou un script Node+jsdom pour le JS front —
  voir `/tmp/jsdom_test/` dans les sessions précédentes, à recréer si besoin :
  `npm install jsdom` puis charger le HTML généré avec `runScripts: "dangerously"`)
- Lancer la suite de tests : `python3 -m pytest tests/ -q` (20 tests actuellement)

Plusieurs bugs réels (ordre des contraintes `FOREIGN KEY`, collision avec un
mot-clé SQL réservé, `scrollIntoView` absent masquant un vrai succès,
sur-échappement de backslash entre couches de templating Python, un mécanisme
de clé étrangère qui décrémentait le mauvais enregistrement) ne se seraient
JAMAIS révélés par simple lecture — ne pas sauter cette étape pour aller
plus vite.

**Toujours nettoyer avant/après compilation** :
```bash
rm -f app.py schema.sql sandbox_ai.py landing.html dashboard.html .jwt_secret .monlang_theme_seed *.db
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

### Briques terminées et testées (points 24-29)
1. **`capability auth`** — bloc déclaratif, aucun effet sur la génération
   pour l'instant (prouvé par compilation identique avec/sans le bloc).
2. **`rule Entite.champ hidden`** — masque un champ de toutes les réponses
   de lecture (liste + détail), pour tout le monde. Reste en base, reste
   modifiable en écriture. Testé sur `exemples/13_anon_forum_demo.yaml`.
3. **`rule Entite.Create decrements Entite.champ [by N]`** — décrémente un
   champ numérique sur une entité liée à la création d'un enregistrement
   (typiquement un signalement). Testé sur `exemples/14_reputation_demo.yaml`.
4. **`rule Entite.Create increments Entite.champ [by N]`** — symétrique de
   `decrements`, pour les likes/appréciations. Grammaire : deux productions
   Lark nommées distinctes (`decrement_rule`/`increment_rule`), pas une seule
   règle partagée par mot-clé (évite le piège de filtrage Lark qui avait fait
   annuler le premier essai). `ast_validator.py` valide les deux dans la même
   boucle, chaque règle portant un champ `"direction"`. `generator.py` choisit
   `+`/`-` selon ce champ. Testé sur `exemples/15_likes_demo.yaml`.
5. **`rule Entite.champ categorized: "label" below N, ..., "label" otherwise`**
   — remplace un champ `Integer`/`Float` par un libellé de catégorie dans
   toutes les réponses de lecture (liste + détail), sur le même principe que
   `hidden` mais avec substitution plutôt que suppression. Portée générale
   (n'importe quel champ numérique, pas seulement ceux ciblés par
   `increments`/`decrements`). Incompatible avec `hidden` sur le même champ
   (erreur de compilation explicite). Dernier palier obligatoirement
   `otherwise` (couverture totale garantie). Libellés injectés via `repr()`
   dans le code généré (jamais d'interpolation manuelle entre guillemets).
   Testé sur `exemples/16_likes_categories_demo.yaml`.

6. **Assemblage final : réseau social anonyme** — toutes les briques
   ci-dessus combinées dans une seule spec (`exemples/17_anon_social_network.yaml`),
   chacune dans son rôle le plus naturel plutôt qu'empilées sur la même
   entité (`Post` anonyme/public/catégorisé, `Comment` identifié avec
   `ownedBy`). Bug réel découvert en l'assemblant (pas en le relisant) :
   un commentaire seul sur sa propre ligne entre deux blocs de premier
   niveau faisait planter la compilation (`Tree` non transformé qui
   traverse jusqu'à `app()`) — corrigé dans `src/parser.py`. Limite
   assumée : un commentaire seul À L'INTÉRIEUR d'un bloc indenté
   (`entity`/`workflow`...) échoue encore (`UnexpectedToken`), non corrigé.

### Briques suivantes déjà évoquées, non cadrées
- Identifiant généré automatiquement (probablement côté `capability auth`)

### Hors de portée, assumé et documenté
- Algorithme de recommandation basé sur les likes — moteur de scoring/ML,
  pas un compilateur déclaratif.
- Mode `template` (import HTML utilisateur) n'a pas la même richesse
  fonctionnelle que le mode `ai` pour l'instant (pas de tableau de bord
  généré dans le gabarit lui-même — juste un widget d'auth minimal injecté).

## Repères utiles dans le code

- `_compute_actor_capabilities` (generator.py) : ce qu'un acteur connecté
  peut faire, dérivé des vrais `workflow` — alimente le tableau de bord
  `/app`.
- `_compute_landing_functional_context` : détecte les entités avec action
  publique pour brancher aperçu/contact réels sur la landing.
- `_compute_route_map` : source unique de vérité pour le "tag" de route
  (nom du workflow), partagée entre la génération FastAPI et les capacités
  du tableau de bord — ne pas dupliquer cette logique ailleurs.
- Le widget d'auth du mode `template` est injecté avant `</body>`, styles
  scopés `monlang-auth-*` pour ne jamais entrer en collision avec les
  classes du gabarit importé.

## Commandes de référence

```bash
pip install fastapi uvicorn lark pyjwt requests pytest --break-system-packages
cd src && python3 main.py ../exemples/01_todo_list.yaml
cd .. && python3 -m uvicorn app:app --reload   # jamais `python3 app.py` directement
python3 -m pytest tests/ -v
```
