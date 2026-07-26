<!-- généré par monl — orchestration frontend -->
# AtelierVelo — mémoire de projet pour Claude Code

Ce dossier est un projet monl : le backend (app.py, schema.sql,
sandbox_ai.py) est GÉNÉRÉ depuis la spec `spec.ml` (ou le fichier .ml
présent) — la spec est la source de vérité, le backend un artefact scellé.

## Ton rôle ici : le FRONTEND, rien d'autre

- Lis `FRONTEND_PROMPT.md` : c'est le contrat complet (routes, auth,
  champs, direction de design). Version machine-lisible :
  `frontend_contract.json`.
- Écris UNIQUEMENT dans `frontend/`, point d'entrée `frontend/index.html`.
  HTML/CSS/JS statiques, AUTONOMES (aucun CDN, aucun script externe —
  condition de vérifiabilité du smoke test).
- Pour faire ÉVOLUER un frontend existant après un changement de spec,
  lis `FRONTEND_UPDATE_PROMPT.md` (généré par `monl update`) et modifie
  l'existant, ne réécris pas de zéro.

## Interdits absolus

Ne JAMAIS modifier : la spec `.ml`, `app.py`, `schema.sql`,
`sandbox_ai.py`, `frontend_contract.json`, `FRONTEND_PROMPT.md`,
`monl.json`, `.jwt_secret`. Si le backend semble devoir changer, c'est
la SPEC qu'il faut faire évoluer (par l'utilisateur), puis `monl update`.

## Vérifier ton travail

`monl run . --check` (si `monl` est sur le PATH) exécute la
vérification complète : cohérence statique + smoke test comportemental
(serveur éphémère, routes du contrat éprouvées en HTTP réel, ton
`index.html` exécuté dans jsdom). Corrige jusqu'à ce que ce soit vert —
`monl run .` refusera de lancer tant que le smoke test échoue.
