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
  garde-fou IA) et comment les contourner légitimement quand c'est prévu.
- `exemples/` : Applications écrites en syntaxe officielle `.monlang`.
- `src/` : Code source du compilateur (Parser, AST, Générateur, Sandbox IA).
- `tests/` : `test_exploit.py` (audit offensif sur l'exemple Todo) et
  `test_exploit_all.py` (même audit généralisé à tous les exemples).

## Utiliser l'application générée sans écrire de requêtes HTTP à la main

Chaque application générée expose automatiquement une documentation Swagger
interactive (fournie gratuitement par FastAPI), accessible directement dans
un navigateur à l'adresse `/docs` du serveur lancé — la racine `/` y redirige
automatiquement. Ça permet de tester les routes générées (créer, lire,
modifier, supprimer une entité, s'authentifier) sans écrire de code, en
attendant un éventuel front dédié.

## Configurer le modèle IA local (échappatoire des blocs `custom`)

Le remplissage automatique des blocs `custom` (dossier `sandbox_ai.py`)
s'appuie sur un serveur [Ollama](https://ollama.com) tournant en local, à
l'adresse `http://localhost:11434`. Aucun modèle n'est fourni dans ce dépôt
(les fichiers de modèle pèsent plusieurs gigaoctets) — le choix du modèle est
laissé à l'utilisateur, selon la puissance de sa machine :

1. Installer Ollama : voir https://ollama.com/download
2. Télécharger un modèle adapté à du code, par exemple :
   - `ollama pull qwen2.5-coder:3b` — léger, adapté à un ordinateur portable
     sans GPU dédié (c'est le modèle utilisé par défaut par
     `src/ai_sandbox_filler.py`)
   - `ollama pull qwen2.5-coder:7b` ou plus — meilleure qualité de code
     généré, nécessite davantage de RAM/VRAM
3. Si un autre modèle est utilisé, adapter la valeur `"model"` dans
   `generate_custom_logic_with_ai()` (`src/ai_sandbox_filler.py`) en
   conséquence.

**Si aucun serveur Ollama n'est disponible**, la compilation aboutit quand
même : le socle déterministe (schéma DB, routes API, contrôle d'accès) est
généré normalement, et chaque bloc `custom` reste disponible sous forme de
coquille vide sécurisée à compléter manuellement dans `sandbox_ai.py`.
