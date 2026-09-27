# monl — plugin Claude Code

monl compile une spécification déclarative (un fichier `.ml`) en backend
complet : schéma SQLite, API REST FastAPI, authentification JWT, contrôle
d'accès par rôle et par enregistrement, et un contrat qui décrit l'interface à
construire. Le compilateur est déterministe et n'utilise aucune IA.

Ce plugin apprend à Claude à écrire cette spécification à partir d'un besoin,
à la compiler, à prouver le résultat contre un vrai serveur, puis à construire
l'interface de l'application.

## Compétences

- **`monl-spec`** — du besoin à un backend vérifié : écrire `spec.ml`, le
  compiler, lire les refus du compilateur, lancer la vérification, faire
  évoluer. Invocation : `/monl-compiler:monl-spec <ce que l'application doit faire>`.
- **`monl-showcase`**, **`monl-design-system`**, **`monl-ui-patterns`**,
  **`monl-commerce`**, **`monl-operations`** — construire l'interface d'un
  projet compilé en respectant son contrat.

## Ce que le plugin exécute, écrit et télécharge

Le plugin ne contient ni hook, ni serveur MCP, ni script. La compétence
`monl-spec` demande à Claude de lancer la ligne de commande du compilateur :

- `monl`, si l'utilisateur l'a déjà installé ; sinon
  `uvx --from monl-compiler==0.9.0b10 monl`, qui **télécharge depuis PyPI** le
  paquet `monl-compiler` à cette version exacte, et ses dépendances ;
- elle écrit `spec.ml` et le dossier compilé **dans le projet de
  l'utilisateur** ;
- la vérification (`monl run --check`) démarre un serveur **local** éphémère
  sur une base neuve, le temps d'un test, puis l'arrête.

Aucune donnée n'est envoyée ailleurs : le compilateur ne fait aucun appel
réseau. Le dossier `reference/` contient une copie exacte des exemples et de
la grammaire du langage, que la compétence lit.

## Prérequis

Un environnement qui peut exécuter des commandes — Claude Code, typiquement —
avec [uv](https://docs.astral.sh/uv/) ou Python 3.10+ et `pip`.

## Licence et source

Functional Source License 1.1, Apache 2.0 Future License
(`LicenseRef-FSL-1.1-ALv2`). Code source, documentation et exemples :
<https://github.com/Bodichane/monl-compiler>.
