# 🟢 Phase 5 — Moteur de Génération de Code

## Objectif
L'objectif de cette phase est de concevoir le moteur de transformation final (le générateur). Il prend en entrée l'Arbre de Syntaxe Abstraite (AST) normalisé et validé en Phase 4, puis produit automatiquement les livrables d'infrastructure (Base de données et API Backend) sans aucune écriture de code métier à la main.

## Composants Générés (`src/generator.py`)
Le générateur produit deux fichiers autonomes et exploitables à la racine du projet :
1. **Couche de Persistance (`schema.sql`)** : 
   - Traduction des types sémantiques MonLang en types SQL natifs (ex: `Money` -> `NUMERIC(10,2)`, `Email` -> `VARCHAR(255)`).
   - Génération des requêtes `CREATE TABLE` et gestion automatique des relations d'intégrité référentielle par injection de clés étrangères (`ALTER TABLE`).
2. **Couche Logique et API (`app.py`)** :
   - Initialisation d'une architecture moderne basée sur **FastAPI**.
   - Génération de modèles de typage et de validation de données stricts via **Pydantic** pour chaque entité.
   - Création de routes CRUD dynamiques et typées, isolées selon les permissions et cas d'usage décrits dans les `workflows`.

## Validation
Le test de génération sur l'application `TodoApp` prouve la viabilité du pipeline. Les structures générées sont normalisées, standardisées et prêtes pour le déploiement ou l'exécution en production.

