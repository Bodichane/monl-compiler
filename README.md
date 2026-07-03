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
| **6 — Boucle complète** | Modification DSL → Changement automatique de l'app | ⬜ En attente |
| **7 — IA** | Traduction Langage Naturel → DSL MonLang | ⬜ En attente |

## Structure du Dépôt
- `docs/` : Notes théoriques et spécifications des phases de cadrage.
- `exemples/` : Applications écrites en syntaxe officielle `.monlang`.
- `src/` : Code source du futur compilateur (Parser, AST, Générateur).
