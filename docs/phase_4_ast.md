# 🟢 Phase 4 — L'Arbre de Syntaxe Abstraite (AST) et Validations

## Objectif
Le dictionnaire JSON produit en Phase 3 est purement structurel. La Phase 4 introduit l'intelligence métier du compilateur (Analyse Sémantique). Son but est de valider la cohérence logique de l'application déclarée et de générer un arbre de syntaxe abstraite (AST) normalisé, propre et totalement indépendant de la technologie cible.

## Règles de Cohérence Validées (`src/ast_validator.py`)
Le validateur d'AST agit comme un garde-fou architectural en appliquant trois tests critiques :
1. **Validation des Relations** : Vérification stricte que chaque entité source et cible déclarée dans un bloc `relation` existe bel et bien.
2. **Validation des Règles (`rules`)** : Vérification que la cible (format `Entite.attribut`) pointe vers une entité existante et un attribut effectivement présent dans cette entité.
3. **Validation des Workflows** : Vérification que l'acteur (`actor`) lié au processus est déclaré, et que les actions CRUD ciblent des entités réelles.

## Résilience aux Erreurs (Crash-Test)
Le système lève une exception explicite `ASTValidationError` et bloque immédiatement la compilation si une incohérence est détectée (ex: application d'une contrainte sur une entité imaginaire `FakeEntity`).

## Structure de l'AST Normalisé
Une fois validé, l'AST sépare proprement l'application en trois piliers universels, prêts pour le moteur de génération de la Phase 5 :
- `meta` : Informations globales de l'application.
- `schema` : Structure pure des données (Entités, Attributs, Types, Relations).
- `security` : Règles de filtrage, profils d'acteurs et cas d'usage (Workflows).
