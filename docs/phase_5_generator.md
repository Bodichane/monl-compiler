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

## ⚠️ Avertissement Crucial de Sécurité — Modèle de Menace & Limite du Prototype

Bien que le générateur porte le nom de `MonLangSecureGenerator`, la structure actuelle de l'API générée (`app.py`) présente une limite architecturale majeure héritée de son statut de prototype (PoC) :

### L'illusion du contrôle d'accès par Header
Les routes FastAPI générées appliquent le contrôle d'accès en lisant directement la valeur brute d'un en-tête HTTP personnalisé (`x_actor = Header(...)`). 
- **Le Risque** : Cet en-tête n'est protégé par aucune signature cryptographique, aucune session serveur et aucun mécanisme d'authentification (ex: token JWT signé). N'importe quel utilisateur ou attaquant peut usurper l'identité de l'acteur de son choix (y compris le rôle `Admin`) en modifiant simplement la valeur de l'en-tête dans sa requête HTTP.

### Conséquence sur la responsabilité de la Sécurité
Tant qu'un mécanisme d'authentification cryptographique fort n'est pas implémenté côté serveur :
1. **La sécurité de l'application dépend entièrement du client**, ce qui viole les bonnes pratiques de développement où le serveur ne doit jamais faire confiance aux données en provenance du client.
2. Un déploiement direct en production dans cet état exposerait l'intégralité des données et des actions critiques (comme la suppression d'entités) à des élévations de privilèges triviales.

### Condition d'honnêteté du terme "SecureGenerator"
L'implémentation d'un intercepteur (Middleware) dans FastAPI pour valider et décoder un **jeton JWT signé cryptographiquement par le serveur** (contenant le rôle vérifié de l'acteur) n'est pas une amélioration de confort. **C'est la condition obligatoire pour que la mention "Sécurisé par défaut" du générateur soit techniquement honnête.** En l'état, ce fichier `app.py` doit être traité uniquement comme une maquette d'architecture et non comme un backend sécurisé prêt pour la production.
