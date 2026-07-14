# MonLang — Compilateur d'Intention Logicielle

Transformer une spécification textuelle structurée en une application complète générée automatiquement, sans écrire de code technique.

## STATUT DU PROJET

| Phase | Objectif | Statut |
| :--- | :--- | :--- |
| **0 — Cadrage** | Vision, Problème & Objectifs | 🟢 Validé |
| **1 — Modèle conceptuel** | Définition des 6 concepts piliers | 🟢 Validé |
| **2 — DSL** | Syntaxe officielle & 5 Apps de validation | 🟢 Validé |
| **3 — Parser** | Traduction DSL → JSON | 🟢 Validé |
| **4 — AST** | Modèle intermédiaire & Validation cohérence | 🟢 Validé |
| **5 — Génération** | Production DB, API & App fonctionnelle | 🟢 Validé |
| **6 — Boucle complète** | Modification DSL → Changement automatique de l'app | 🟢 Validé |
| **7 — IA** | Traduction Langage Naturel → DSL MonLang | 🟢 Validé |

## Authentification

Chaque application générée possède un vrai registre d'utilisateurs (table
`_monlang_users`, mot de passe haché — voir `docs/design_decisions.md`
point 7) :
1. `POST /register` avec `{"username", "password", "actor"}` pour créer un
   compte (mot de passe : 8 caractères minimum)
2. `POST /login` avec `{"username", "password"}` pour obtenir un token JWT
3. `POST /logout` (avec le token en en-tête `Authorization`) pour le révoquer
   avant son expiration naturelle
4. Le rôle (`actor`) et l'identifiant (`user_id`) portés par le token
   viennent du compte réel, pas d'une déclaration libre du client

`/login` et `/register` sont protégées par une limitation de débit (5
tentatives / 60 secondes / IP, par route).

**Secret JWT :** un secret aléatoire unique est généré à la première
compilation d'un projet et stocké dans `.jwt_secret` à la racine (fichier
exclu de `.gitignore` — ne jamais le committer). Recompiler la spec ne le
régénère pas ; le supprimer manuellement force le renouvellement (invalide
alors toutes les sessions actives).

## Contenu public sans compte, et identité visuelle personnalisée

Deux ajouts pour des cas d'usage comme un portfolio (contenu public + zone
d'administration) :

- **`rule Entite.Action public`** retire l'obligation d'authentification
  d'une action précise (ex. `rule Project.Read public` pour un portfolio
  lisible sans compte, `rule Message.Create public` pour un formulaire de
  contact ouvert). Voir `docs/design_decisions.md` point 16.
- **`ui NomEntite / theme: ...`** permet de forcer explicitement l'identité
  visuelle (palette/typographie) utilisée par `landing.html` (voir section
  suivante) plutôt que de la laisser se déduire automatiquement du domaine.
  Voir `docs/design_decisions.md` points 17 et 22.

Exemple complet : `exemples/10_portfolio_public.yaml`.

## Landing marketing sur `/` (IA ou template importé) — seul front généré

MonLang ne génère plus aucun back-office CRUD (voir point 22 de
`docs/design_decisions.md` : le front React `/ui` a été retiré). Par défaut,
`/` redirige simplement vers `/docs`. Un bloc optionnel `landing` active une
vraie page d'accueil marketing sur `/`, sur le même principe d'échappatoire
balisée que `custom` :

```
landing
    mode: ai
    brief: "Un portfolio en ligne pour partager vos projets." # optionnel
```

écrit d'abord un gabarit 100% déterministe (thème calculé pour le projet),
puis une étape IA séparée et non bloquante (Ollama local) rédige le texte —
titre, sous-titre, CTA, 3 points forts — jamais le HTML/CSS. Si l'IA est
indisponible, le gabarit déterministe déjà écrit reste utilisable tel quel.

```
landing
    mode: template
    template: "templates/signal.html"
```

importe à la place un fichier HTML fourni par vous (designer, export
Framer...), et y remplit les emplacements que vous avez balisés avec
`data-monlang="clé"` — voir `templates/signal.html` pour un exemple
commenté des clés reconnues. Aucun appel IA dans ce mode.

Détail complet, garde-fou anti-injection, et exemples : `docs/design_decisions.md`
point 22, `exemples/11_landing_ai_demo.yaml`, `exemples/12_landing_template_demo.yaml`.

## Structure du Dépôt
- `docs/` : Notes théoriques et spécifications des phases de cadrage.
  Voir en particulier `docs/design_decisions.md` pour le détail des règles
  strictes du compilateur (collisions de privilèges, restrictions de champ,
  contrôle par propriété, garde-fou IA) et comment les contourner
  légitimement quand c'est prévu.
- `exemples/` : Applications écrites en syntaxe officielle `.monlang`.
- `templates/` : gabarits HTML importables pour le bloc `landing / mode: template`
  (voir `templates/signal.html`).
- `src/` : Code source du compilateur (Parser, AST, Générateur, Sandbox IA
  des fonctions `custom`, Sandbox IA de la landing (`ai_landing_filler.py`),
  Traducteur langage naturel).
- `tests/` : `test_exploit.py` (audit offensif sur l'exemple Todo),
  `test_exploit_all.py` (même audit généralisé à tous les exemples),
  `test_compile_all.py` (test pytest de non-régression sur tous les exemples).
- `.github/workflows/ci.yml` : intégration continue (compile + audit offensif
  à chaque push/pull request).

## Utiliser l'application générée sans écrire de requêtes HTTP à la main

- **`/docs`** : la documentation Swagger interactive fournie gratuitement par
  FastAPI — toujours disponible, sans rien configurer, pour explorer et
  tester chaque route.
- **`/`** : si la spec contient un bloc `landing`, une vraie page d'accueil
  marketing (voir section précédente) ; sinon, redirige vers `/docs`.

MonLang ne génère plus de back-office CRUD auto-généré (voir point 22 de
`docs/design_decisions.md`) : c'est une décision volontaire, pas une
limitation en attente d'être comblée.

La racine `/` redirige automatiquement vers `/docs`.

## Générer une application depuis une description en langage naturel

En plus d'écrire directement un fichier `.yaml`, il est possible de décrire
l'application en français et de laisser un modèle IA local produire la
spécification MonLang correspondante (celle-ci est ensuite validée par le
vrai parseur avant compilation — si elle ne compile pas, une correction est
retentée automatiquement une fois) :
```bash
python3 src/main.py --prompt "une todo-list simple avec des utilisateurs"
```
Nécessite un serveur Ollama local (voir section suivante).

## Configurer le modèle IA local (échappatoire des blocs `custom` et `--prompt`)

Le remplissage automatique des blocs `custom` (`sandbox_ai.py`) et la
traduction langage naturel → spec (`--prompt`) s'appuient tous les deux sur
un serveur [Ollama](https://ollama.com) tournant en local, à l'adresse
`http://localhost:11434`. Aucun modèle n'est fourni dans ce dépôt (les
fichiers de modèle pèsent plusieurs gigaoctets) — le choix du modèle est
laissé à l'utilisateur, selon la puissance de sa machine :

1. Installer Ollama : voir https://ollama.com/download
2. Télécharger un modèle adapté à du code, par exemple :
   - `ollama pull qwen2.5-coder:3b` — léger, adapté à un ordinateur portable
     sans GPU dédié (c'est le modèle utilisé par défaut)
   - `ollama pull qwen2.5-coder:7b` ou plus — meilleure qualité de code
     généré, nécessite davantage de RAM/VRAM
3. Si un autre modèle est utilisé, adapter la valeur `"model"` dans
   `generate_custom_logic_with_ai()` (`src/ai_sandbox_filler.py`), ou passer
   `--model nom-du-modele` pour la commande `--prompt`.

**Si aucun serveur Ollama n'est disponible**, la compilation d'un fichier
`.yaml` existant aboutit quand même : le socle déterministe (schéma DB,
routes API, contrôle d'accès) est généré normalement, et chaque bloc
`custom` reste disponible sous forme de coquille vide sécurisée à compléter
manuellement dans `sandbox_ai.py`. (L'option `--prompt`, elle, nécessite
évidemment Ollama puisqu'elle sert justement à produire la spec de départ.)

## Intégration continue

`.github/workflows/ci.yml` compile automatiquement tous les exemples de
`exemples/` et rejoue l'audit offensif (`tests/test_exploit_all.py`) contre
chacun à chaque push/pull request, pour détecter une régression avant
qu'elle ne s'accumule sur plusieurs versions.
