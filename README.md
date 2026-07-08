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

## Structure du Dépôt
- `docs/` : Notes théoriques et spécifications des phases de cadrage.
  Voir en particulier `docs/design_decisions.md` pour le détail des règles
  strictes du compilateur (collisions de privilèges, restrictions de champ,
  contrôle par propriété, garde-fou IA) et comment les contourner
  légitimement quand c'est prévu.
- `exemples/` : Applications écrites en syntaxe officielle `.monlang`.
- `src/` : Code source du compilateur (Parser, AST, Générateur, Sandbox IA,
  Traducteur langage naturel).
- `tests/` : `test_exploit.py` (audit offensif sur l'exemple Todo),
  `test_exploit_all.py` (même audit généralisé à tous les exemples),
  `test_compile_all.py` (test pytest de non-régression sur tous les exemples).
- `.github/workflows/ci.yml` : intégration continue (compile + audit offensif
  à chaque push/pull request).

## Utiliser l'application générée sans écrire de requêtes HTTP à la main

Deux options, générées automatiquement avec chaque application :

- **`/ui`** : un front minimal auto-généré (formulaire de connexion, puis un
  formulaire par entité pour créer/lire/modifier/supprimer, et un bouton par
  fonction `custom` exécutable). C'est un filet d'utilisabilité, pas un vrai
  front applicatif — pratique pour tester rapidement sans rien écrire.
- **`/docs`** : la documentation Swagger interactive fournie gratuitement par
  FastAPI, plus complète pour explorer chaque route en détail.

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
