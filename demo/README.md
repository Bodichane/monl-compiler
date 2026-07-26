# AtelierVélo — projet de démonstration

Le parcours complet qui a produit ce dossier (dialogue → backend → frontend
IA → utilisation → évolution avec données préservées) est raconté, sorties
réelles à l'appui, dans `docs/DEMO.md`.

Pour le faire tourner :

    monl compile demo/spec.ml
    monl run demo        # → http://127.0.0.1:8000/site

Ce dossier ne contient que ce qui fait foi : `spec.ml` (la source de
vérité) et `frontend/` (écrit par une IA contre le contrat). Tout le reste
se régénère. Un test (`tests/test_demo.py`) garantit que cet ensemble
compile et passe le smoke test à chaque CI.
