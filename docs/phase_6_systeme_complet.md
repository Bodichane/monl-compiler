# 🟢 Phase 6 — Système Complet (Boucle Fermée)

## Objectif
L'objectif de cette phase est de sceller l'intégration de toutes les briques logicielles développées précédemment (`parser.py`, `ast_validator.py`, `generator.py`) au sein d'un orchestrateur central unique. La validation repose sur la capacité du compilateur à reconfigurer instantanément l'intégralité de l'infrastructure logicielle cible dès que le fichier source DSL est modifié.

## Implémentation de l'Orchestrateur (`src/main.py`)
Un point d'entrée centralisé sous forme d'interface en ligne de commande (CLI) a été développé en Python. Il automatise le flux séquentiel :
1. Lecture et validation de la structure syntaxique brute via Lark.
2. Validation des règles métiers et sémantiques de l'AST (sécurité, acteurs, références).
3. Génération des artéfacts techniques physiques (`schema.sql` et `app.py`).

## Test de la Boucle Fermée
La validation a été éprouvée en basculant la compilation d'un cas d'usage à un autre :
- `python3 src/main.py` -> Génère instantanément l'architecture complète pour la `TodoList`.
- `python3 src/main.py exemples/02_blog.ml` -> Écrase et reconfigure immédiatement la base de données et l'API FastAPI pour l'adapter au domaine fonctionnel du `TechBlog`.

Le pipeline est fluide, synchrone et sans aucun effet de bord.
