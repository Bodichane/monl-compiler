# 🟢 Phase 0 — Cadrage, Vision et Positionnement Sécurisé

> **Document historique.** Cette page décrit une étape de conception ; elle ne
> remplace pas l'architecture courante. Voir `README.md` et `CODEBASE_AUDIT.md`.

## Constat de départ
De nombreux débutants ou développeurs intermédiaires utilisent l’IA (prompts itératifs, “vibe coding”) pour créer des applications. Ils se retrouvent rapidement avec une masse critique de code qu’ils ne comprennent pas et ne peuvent donc pas maintenir, faire évoluer, ou sécuriser correctement. 

## Positionnement de monl
monl n’est pas un générateur d’applications de plus, ni un outil no-code grand public. C’est un langage structuré conçu spécifiquement pour rendre le “vibe coding” traçable et sécurisé. L’utilisateur exprime son besoin via une spécification déclarative claire plutôt qu’un prompt libre non structuré. Cela donne à l’IA une direction vérifiable, limitant son rôle à l'interprétation purement locale et balisée.

## Architecture Cible : Socle Déterministe + Échappatoire IA Balisé
Le pipeline de compilation sépare strictement l'infrastructure de la logique métier arbitraire :

1. **Le Socle (Compilateur classique)** : Génère tout ce qui est standard, répétitif et prévisible (schéma de base de données, routes API, authentification, contrôle d'accès basé sur les rôles et workflows).
   - **Déterministe** : La même spécification produit toujours le même code, bit pour bit.
   - **Sécurisé par défaut** : Requêtes paramétrées, validation stricte, contrôle d'accès systématique appliqués par construction.
   - **Traçable** : Chaque ligne de code générée correspond à une règle fixe et à une portion identifiable de la spécification.

2. **L’Échappatoire IA (Blocs `custom`)** : Intervient uniquement pour la logique métier que le DSL ne peut pas exprimer nativement. L’IA génère alors une fonction isolée et étanche, appelée par le code déterministe sans jamais s’y mélanger, facilitant un contrôle de sécurité renforcé (audit) sur ce code spécifique avant intégration.

## Objectif à Long Terme
Rendre le code généré (Python, SQL…) aussi secondaire pour l’utilisateur final que l’assembleur l’est pour un développeur de haut niveau aujourd’hui, garantissant qu'aucune fuite d'abstraction ne vienne polluer le domaine couvert par monl.
