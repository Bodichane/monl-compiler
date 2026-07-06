# 🟢 Phase 4 — L'Arbre de Syntaxe Abstraite (AST) & Audit Statique de Sécurité

## Objectif
L'Arbre de Syntaxe Abstraite (AST) normalise le dictionnaire brut issu du Parser (Phase 3). Cette phase implémente le moteur d'**Analyse Statique de Sécurité** (Axe : "Sécurisé et audité") conçu pour intercepter les vulnérabilités d'architecture directement au moment de la compilation, avant la génération des fichiers d'infrastructure.

## Validations de Cohérence Structurelle (`src/ast_validator.py`)
Le validateur résout les dépendances logiques et intercepte les incohérences de spécification :
1. **Déclarations d'Acteurs** : Vérification stricte que chaque profil d'acteur attaché à un workflow a été préalablement recensé dans le bloc global `actor`.
2. **Résolution des Notations Pointées** : Prise en charge chirurgicale des cibles de champs imbriqués (ex: `Order.status`). L'analyseur isole dynamiquement l'entité maîtresse (`Order`) pour valider son existence dans le schéma de données avant de valider l'attribut, évitant tout crash de compilation sur les applications complexes.

## Algorithme d'Audit Statique de Sécurité
L'analyseur statique traque activement deux vulnérabilités architecturales majeures :

### 1. Détection des Privilèges Destructeurs Non Protégés (Orphan Delete)
Le moteur scanne l'intégralité des workflows. Si une action de type `Delete` est détectée sur une entité alors que le workflow est rattaché à un acteur générique autre que l'administrateur (`Admin`), le compilateur émet une alerte critique `[CRITICAL_WARNING]` pour forcer l'équipe technique à valider la sécurité de cette faille de spécification.

### 2. Audit d'Isolation des Blocs IA & Résolution Dynamique des Acteurs
Pour sécuriser l'utilisation de la donnée au sein de l'échappatoire IA (blocs `custom`), le compilateur applique un algorithme de graphe d'appels :
- **Problématique résolue** : Les blocs `custom` n'ont pas d'acteur attitré nativement. L'analyseur cartographie l'arbre des dépendances en identifiant chaque workflow qui invoque la fonction IA via une instruction `Execute`.
- **Analyse des Fuites** : Si un bloc `custom` reçoit en paramètre (`input`) un champ protégé par une contrainte de confidentialité stricte (`restrictedTo`), le moteur compare cette restriction à l'ensemble des acteurs ayant le droit d'exécuter ce bloc.
- **Alerte** : Si un acteur non autorisé est capable de déclencher indirectement le bloc IA, un log de sécurité `[SECURITY_AUDIT]` est généré. Le compilateur ordonne alors l'injection de filtres d'anonymisation automatiques au niveau de la Sandbox pour protéger la donnée.

## Structure de l'AST Normalisé Sécurisé
Une fois l'audit validé, l'AST produit un objet structuré en quatre piliers étanches prêts pour le générateur déterministe :
- `meta` : Métadonnées et historique des logs d'audit de sécurité.
- `schema` : Structure relationnelle pure des données (Entités, Attributs, Relations).
- `security` : Profils d'acteurs, règles de filtrage de champs et droits d'accès CRUD.
- `sandbox_ai` : Signatures d'I/O et consignes d'isolation pour le remplissage automatisé du LLM.
