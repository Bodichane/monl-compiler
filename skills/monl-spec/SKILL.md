---
name: monl-spec
description: Décrire une application en spécification monl (.ml), la compiler en backend FastAPI + SQLite + JWT déterministe, et la vérifier contre un vrai serveur. À utiliser quand on demande de créer, modifier ou vérifier le backend d'une application avec monl, ou d'écrire/corriger un fichier .ml.
when_to_use: « crée-moi une API pour… », « un backend avec comptes et rôles », « ajoute un champ/une règle à ma spec monl », « pourquoi monl refuse ma spec ».
argument-hint: "[ce que l'application doit faire]"
---

# Écrire et compiler une spécification monl

monl compile une spec déclarative en backend complet : schéma SQL, API REST,
authentification JWT, contrôle d'accès, et un contrat frontend. Le compilateur
est **déterministe et sans IA** : ton travail est d'écrire la spec juste, le
sien est de refuser ce qui ne tient pas.

Demande de l'utilisateur : $ARGUMENTS

## 1. Trouver la commande

Dans l'ordre, garde la première qui répond :

```bash
monl --version                                      # installé par pip
uvx --from monl-compiler==0.9.0b10 monl --version   # sinon, sans rien installer
```

Si aucune ne répond, propose `pip install monl-compiler==0.9.0b10` à
l'utilisateur ; ne l'installe pas d'office. Dans la suite, `monl` désigne la
commande retenue.

## 2. Apprendre le langage sur les exemples, pas de mémoire

Le langage n'a pas de référence séparée : ses exemples sont compilés par la
suite de tests à chaque changement, ils ne peuvent donc pas mentir.

1. Lis `${CLAUDE_PLUGIN_ROOT}/exemples/README.md` : il dit ce que chaque exemple
   démontre.
2. Lis en entier l'exemple le plus proche du besoin
   (`${CLAUDE_PLUGIN_ROOT}/exemples/*.ml`). Chacun explique en commentaire
   **pourquoi** chaque règle est là.
3. En cas de doute sur une syntaxe, la grammaire fait foi :
   `${CLAUDE_PLUGIN_ROOT}/grammaire.py`. N'invente aucun
   mot-clé qui n'y figure pas.

## 3. Écrire la spec dans le projet de l'utilisateur

Écris `spec.ml` à la racine du projet (ou là où l'utilisateur le demande) —
jamais dans le dossier du plugin. `monl update` relira ce fichier à cet
emplacement.

Trois questions à trancher avec l'utilisateur plutôt qu'à deviner :
- **Qui a un compte, et qui s'inscrit seul ?** Seuls les rôles `selfRegister`
  s'inscrivent en ligne ; les autres se créent par le `manage.py` généré.
- **Qui voit et modifie quoi ?** `ownedBy`, `sharedBy`, `accessibleBy`,
  `public` : un choix de sécurité, donc celui de l'utilisateur.
- **Un montant est-il encaissé ?** `payable` exige que le montant soit calculé
  par le serveur (`derivedFrom` ou `sumOf`) : un montant que le client écrit
  est refusé à la compilation, à dessein.

## 4. Compiler, et lire les refus

```bash
monl compile spec.ml --output backend
```

Un refus sort avec le code 1 et une ligne `❌` qui nomme la règle fautive et
explique pourquoi. **Corrige la spec ; ne contourne jamais un refus** (en
retirant la règle de sécurité qui gêne, par exemple) sans l'accord explicite
de l'utilisateur : chaque refus protège d'un défaut réel.

## 5. Prouver par exécution

```bash
monl run backend --check
```

Cohérence spec ↔ backend ↔ contrat, puis smoke test contre un serveur
éphémère sur une base neuve. Tant que cette commande n'est pas verte, la
tâche n'est pas finie — ne l'annonce pas comme faite.

Pour lancer l'application : `monl run backend` (API sur `/`, documentation
sur `/docs`).

## 6. Faire évoluer

- `monl diff backend` : ce qu'un changement de `spec.ml` ferait au contrat,
  **sans rien écrire**. À montrer à l'utilisateur avant d'appliquer.
- `monl update backend` : recompile et rapporte le delta (routes, champs,
  accès, verrous). Refais ensuite `monl run backend --check`.

## 7. L'interface

Le backend compilé porte `AGENTS.md`, `frontend_contract.json` et
`docs/FRONTEND_PROMPT.md`. Pour construire l'interface, lis-les d'abord, puis
applique les compétences `monl-showcase`, `monl-design-system`,
`monl-ui-patterns`, et `monl-commerce` ou `monl-operations` selon le métier.
Ne modifie jamais `app.py`, `schema.sql` ni `manage.py` : ils sont scellés par
empreinte, et `monl run --check` le détecte.
