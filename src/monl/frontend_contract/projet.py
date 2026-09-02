"""Les deux documents d'accueil déposés dans le projet compilé.

`AGENTS.md` cadre la session d'une IA qui travaille SUR un site produit —
à ne pas confondre avec le CLAUDE.md du dépôt monl lui-même. `README.md`
s'adresse à l'humain qui vient d'ouvrir l'archive et cherche comment la
démarrer : la page d'accueil de la plateforme le PROMET depuis toujours dans
son aperçu d'arborescence, et il n'existait pas.

Le nom `AGENTS.md` remplace `CLAUDE.md` : le frontend peut être écrit par
claude-code, codex ou gemini (point 69), et nommer ce fichier d'après un seul
d'entre eux en fait un fichier que les deux autres ne lisent pas.
"""

import os

from .fondations import AGENTS_FILENAME, README_FILENAME

PROJECT_CLAUDE_MD_MARKER = "<!-- généré par monl — orchestration frontend -->"
PROJECT_README_MARKER = "<!-- généré par monl — démarrage du projet -->"

#: L'ancien nom, gardé pour le déplacement des projets déjà compilés. Il ne
#: doit PAS disparaître de la source : sans lui, un CLAUDE.md produit par une
#: version antérieure resterait à côté d'AGENTS.md, périmé et sans un mot.
LEGACY_AGENTS_FILENAME = "CLAUDE.md"

PROJECT_CLAUDE_MD = """{marker}
# {app} — mémoire de projet pour les agents

Ce dossier est un projet monl : le backend (app.py, schema.sql) est GÉNÉRÉ
depuis la spec `spec.ml` (ou le fichier .ml présent) — la spec est la source
de vérité, le backend un artefact scellé.

## Ton rôle ici : le FRONTEND, rien d'autre

- Lis `docs/FRONTEND_PROMPT.md` : c'est le contrat complet (routes, auth,
  champs, direction de design). Version machine-lisible :
  `frontend_contract.json`, à la racine.
- Écris UNIQUEMENT dans `frontend/`, point d'entrée `frontend/index.html`.
  HTML/CSS/JS statiques, AUTONOMES (aucun CDN, aucun script externe —
  condition de vérifiabilité du smoke test).
- Pour faire ÉVOLUER un frontend existant après un changement de spec,
  lis `docs/FRONTEND_UPDATE_PROMPT.md` (généré par `monl update`) et modifie
  l'existant, ne réécris pas de zéro.

## Interdits absolus

Ne JAMAIS modifier : la spec `.ml`, `app.py`, `schema.sql`, `sandbox_ai.py`
(s'il existe), `frontend_contract.json`, `monl.json`, `.jwt_secret`, ni rien
dans `docs/`. Si le backend semble devoir changer, c'est la SPEC qu'il faut
faire évoluer (par l'utilisateur), puis `monl update`.

## Vérifier ton travail

`monl run . --check` (si `monl` est sur le PATH) exécute la
vérification complète : cohérence statique + smoke test comportemental
(serveur éphémère, routes du contrat éprouvées en HTTP réel, ton
`index.html` exécuté dans jsdom). Corrige jusqu'à ce que ce soit vert —
`monl run .` refusera de lancer tant que le smoke test échoue.
"""

PROJECT_README = """{marker}
# {app}

Application produite par [monl](https://github.com/Bodichane/monl-compiler) depuis la
spec `{spec}`. Le backend est **compilé** : il ne s'écrit pas à la main.

## Démarrer

```bash
pip install -r requirements.txt
uvicorn serve:app --host 127.0.0.1 --port 8000
```

L'API répond sur <http://127.0.0.1:8000> — la racine redirige vers `/docs`,
sa documentation interactive, où chaque route est essayable. Le frontend est
servi sur `/site` s'il existe ; sinon `/site` renvoie 404 et l'API, elle,
fonctionne.

Au premier démarrage, le serveur écrit lui-même `.jwt_secret` (permissions
0600). **En production**, posez `MONL_ENV=production` et fournissez
`MONL_JWT_SECRET` : le serveur refuse alors de démarrer sans lui, plutôt que
de fabriquer un secret qui changerait à chaque redémarrage et invaliderait
toutes les sessions.

## Administrer

```bash
python3 manage.py --help
```

Créer les comptes des rôles qui ne s'inscrivent pas en ligne, lister,
supprimer. C'est le seul chemin légitime pour ces rôles.

## Ce qu'il y a dans le dossier

| Fichier | Rôle |
| --- | --- |
| `{spec}` | **la source de vérité** — c'est elle qu'on modifie |
| `app.py`, `schema.sql`, `manage.py`, `serve.py` | générés, scellés |
| `frontend_contract.json` | l'interface machine : routes, champs, droits |
| `docs/` | ce qui se lit — brief frontend et direction visuelle |
| `frontend/` | l'interface, écrite par vous ou par une IA |
| `requirements.txt`, `Dockerfile` | déploiement, éditables |

## Faire évoluer

Modifiez la spec, puis `monl update .` : le backend est recompilé et le
rapport nomme ce qui change pour le frontend (routes, champs, accès,
verrous). Ne modifiez jamais `app.py` directement — la prochaine
compilation l'écraserait.
"""


def _ecrire_si_a_nous(path, marker, contenu):
    """N'écrase jamais un document repris en main par l'utilisateur.

    L'absence du marqueur signe un fichier que quelqu'un a écrit ou réécrit :
    le remplacer effacerait son travail sans le dire.
    """
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            if marker not in fh.read():
                return False
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(contenu)
    return True


def write_project_claude_md(app_name, output_dir, spec_name="spec.ml"):
    """Écrit AGENTS.md et README.md du PROJET (pas ceux du dépôt monl)."""
    _ecrire_si_a_nous(
        os.path.join(output_dir, AGENTS_FILENAME),
        PROJECT_CLAUDE_MD_MARKER,
        PROJECT_CLAUDE_MD.format(marker=PROJECT_CLAUDE_MD_MARKER, app=app_name))
    _ecrire_si_a_nous(
        os.path.join(output_dir, README_FILENAME),
        PROJECT_README_MARKER,
        PROJECT_README.format(marker=PROJECT_README_MARKER, app=app_name,
                              spec=spec_name))
