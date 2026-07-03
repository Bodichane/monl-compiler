# 🟢 Phase 3 — Le Parser Syntaxique

## Objectif
L'objectif de cette phase est de concevoir un analyseur syntaxique (Parser) capable de lire un fichier brut écrit en DSL MonLang (extension `.yaml`) et de le convertir en une structure de données informatique brute au format JSON.

## Choix Techniques
- **Langage** : Python 3.14+
- **Bibliothèque** : `lark` (Analyseur syntaxique LALR)
- **Gestion de l'indentation** : Utilisation du module natif `PythonIndenter` réadapté pour MonLang (`MonLangIndenter`) afin de capturer proprement les blocs logiques de 4 espaces sans accolades.

## Implémentation (`src/parser.py`)
Le parser utilise une grammaire formelle définissant de manière stricte les mots-clés du langage (`app`, `entity`, `relation`, `actor`, `rule`, `workflow`) et s'appuie sur la classe `Transformer` pour extraire les jetons (tokens).

## Critères de Validation et Test
Le test de validation a été exécuté avec succès sur le fichier d'entrée `exemples/01_todo_list.yaml`. 
L'analyseur produit un dictionnaire stable de ce type :
- Extraction correcte des entités (`User`, `Todo`) et de leurs types primitifs sémantiques.
- Capture des liaisons de relations (`hasMany`).
- Isolation des workflows et des listes d'actions CRUD associées.

Le résultat est parfaitement prédictible : un même fichier source produit systématiquement le même dictionnaire JSON.
