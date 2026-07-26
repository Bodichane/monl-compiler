# 🟢 Phase 1 — Modèle Conceptuel et Axes de Sécurité

Le modèle mental de monl s'étend pour soutenir l'isolation de la logique IA et l'analyse statique de la sécurité.

## Les Deux Axes de Sécurité Évolutifs
1. **Sécurisé par défaut** : Le générateur applique systématiquement les bonnes pratiques de l'industrie (protection contre les injections SQL, validations de types Pydantic, isolation des scopes). Aucune faille ne peut être introduite par négligence de l'utilisateur.
2. **Sécurisé et audité** : Le compilateur embarque un moteur d'analyse statique de sécurité directement intégré au pipeline. Il scanne activement la spécification déclarée pour détecter les structures dangereuses (permissions manquantes, élévations de privilèges implicites, actions sensibles mal protégées).

## Les Concepts Étendus
- **Entity & Attribute** : Définition des structures de données et contraintes de types.
- **Relation** : Liens logiques induisant des contraintes d'intégrité en base de données.
- **Actor & Workflow** : Définition stricte des profils et des routes d'API associées.
- **Custom Block (Échappatoire IA)** : Déclaration explicite des frontières d'entrées/sorties d'une fonction qui sera générée par un LLM dans une sandbox isolée.
