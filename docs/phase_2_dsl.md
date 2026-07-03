# 🟡 Phase 2 — Conception du DSL

## Principes de Syntaxe
- **Déclaratif & Lisible** : Compréhensible immédiatement sans explication technique.
- **Indentation propre** : Utilisation stricte de 4 espaces pour la hiérarchie.
- **Épuré** : Aucune accolade `{}`, aucun point-virgule `;`, une seule instruction par ligne.

## Conventions de Nommage
- **PascalCase** : Entités (`User`), Acteurs (`ShopManager`), Workflows (`ManageTodo`), Types primitives (`String`).
- **camelCase** : Attributs (`publishedAt`, `totalAmount`).

## Types Primitifs Supportés
- `String`, `Text`, `Integer`, `Float`, `Boolean`
- `Date`, `DateTime`, `Email`, `UUID`, `Money`
