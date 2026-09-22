# Consolidation du compilateur

Ce chantier reprend les améliorations issues de la revue du projet. Le produit
de référence est le compilateur ; CodexShop reste un exemple d'intégration.
Les fonctionnalités de plateforme ou de génération d'interface ne sont pas
étendues dans ce chantier.

## Critères de fin

- [x] Extraire l'analyse des routes et relations dans un module indépendant des émetteurs.
- [x] Typer et isoler les dérivations `derivedFrom`, partager leurs plans entre backend et contrat.
- [x] Typer et isoler les agrégations `sumOf` et les effets de stock/compteurs.
- [x] Réduire l'état implicite des mixins : analyses métier et politiques de champs/d'accès composables, avec interfaces explicites.
- [x] Renforcer les types aux frontières des analyses migrées et les vérifier en CI.
- [x] Clarifier les garanties et limites dans le README, synchroniser les commandes de vérification et la documentation d'architecture.
- [x] Alléger les commentaires historiques des zones refondues en conservant les invariants et leurs raisons.
- [x] Vérifier les comportements métier, la compatibilité des sorties et la suite complète ; documenter les éventuelles limites d'environnement.

Les cases cochées décrivent le périmètre effectivement livré. La validation
finale a été rejouée sur l'état courant : Ruff, mypy strict, Vulture, tests
ciblés et suite complète. Aucun résultat d'utilisateurs réels ni audit externe
n'est déduit des tests locaux.

## Invariants

La syntaxe du DSL, les routes HTTP, le schéma généré et le contrat frontend
restent compatibles. Toute différence de sortie doit être expliquée et testée.
La sélection des parents, l'isolation des propriétaires, les montants serveur,
le stock, les transactions et les données lors d'une mise à jour restent
protégés par leurs tests métier. Les analyses ne doivent pas dépendre des
émetteurs ni changer lorsque les dictionnaires d'entrée sont modifiés après
leur construction.

## Vérifications finales

- `python -m pytest tests/ -rs --cov=src/monl --cov-report=term-missing` :
  suite complète réussie ; les scénarios PostgreSQL restent conditionnés à
  `MONL_TEST_DATABASE_URL`. Le nombre de cas et la couverture courants sont
  publiés par la CI plutôt que figés dans ce document.
- `ruff check src tests`, `mypy --strict` sur les frontières IR et
  `vulture src/monl --min-confidence 90` : aucun signalement.
- Les huit spécifications de référence (cinq exemples, la démo et les bancs
  de dérivation/agrégation) produisent les mêmes empreintes SHA-256 de sources
  backend et de contrats qu'avant la refonte.
- Chaque module Python généré est parsé pendant la non-régression des exemples,
  et un golden compare aussi deux répertoires de sortie indépendants.
- Les plans sont immuables et indépendants des dictionnaires d'entrée après
  construction ; leurs identités sont partagées entre émetteurs backend et
  contrat frontend.

La seule limite d'environnement constatée est l'absence de PostgreSQL de test,
qui explique les scénarios ignorés ; les parcours SQLite et les contrôles de
compilation restent entièrement exercés.
