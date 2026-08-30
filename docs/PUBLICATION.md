# Publier monl-compiler

Cette procédure est destinée au mainteneur du projet. Elle prépare et vérifie
les deux artefacts, puis les envoie d'abord sur TestPyPI et ensuite sur PyPI.
Elle ne contient aucun identifiant et ne doit pas en recevoir.

## Avant la construction

La version à publier est celle de `pyproject.toml`. Une version déjà publiée
ne peut pas être remplacée : si la version ou le nom doivent changer, le
mainteneur tranche avant de construire. Pour vérifier le nom sans
authentification :

```bash
curl -sS -o /dev/null -w '%{http_code}\n' \
  https://pypi.org/pypi/monl-compiler/json
```

`404` signifie que le nom n'a pas encore de projet PyPI retourné par cette
API ; `200` signifie qu'il est déjà occupé. Dans ce second cas, arrêter et
décider d'un autre nom — `twine` ne crée pas un second projet.

## Identifiants

Les identifiants appartiennent uniquement au mainteneur. Il les configure sur
sa propre machine, dans son trousseau de clés ou dans son fichier personnel
`~/.pypirc` (jamais dans ce dépôt, un ticket, un journal ou une commande
copiée). Il peut aussi laisser `twine` les demander interactivement. Ce guide
n'utilise ni `TWINE_PASSWORD`, ni option `--password`, ni valeur de jeton en
clair : personne d'autre ne doit toucher à ces identifiants.

Pour que `--repository testpypi` vise le bon index, son `~/.pypirc` personnel
peut contenir cette configuration, sans aucun secret dans l'extrait :

```ini
[distutils]
index-servers =
    testpypi
    pypi

[testpypi]
repository = https://test.pypi.org/legacy/

[pypi]
repository = https://upload.pypi.org/legacy/
```

## Construire et contrôler

Depuis la racine du dépôt, avec l'environnement de publication du mainteneur :

```bash
rm -rf dist/
python -m build
python -m twine check dist/*
unzip -l dist/*.whl
```

**`rm -rf dist/` n'est pas une précaution de style.** `dist/` est ignoré par
git, donc il n'existe pas dans un dépôt fraîchement cloné — mais il survit sur
la machine qui a déjà construit. Mesuré sur celle du mainteneur au moment
d'écrire ces lignes : `dist/` contenait `monl_compiler-0.9.0b7` alors que la
version à publier est `0.9.0b8`. Construire sans nettoyer laisse les DEUX côte
à côte, et `dist/*` développe alors les quatre fichiers : **`twine upload`
publierait une version qu'on ne voulait pas envoyer, et qu'on ne peut plus
retirer d'un index** (PyPI ne permet pas de republier un numéro de version, même
après suppression). `unzip -l dist/*.whl` et `twine check dist/*` deviennent au
passage ambigus, donc leur contrôle ne dit plus sur quoi il a porté.

`dist/anciens/` sur cette même machine porte encore des artefacts nommés
`monl-0.9.0b5`, c'est-à-dire l'ANCIEN nom de distribution : les envoyer
créerait un second projet sur l'index.

La première commande doit produire une archive source (`.tar.gz`) et une roue
(`.whl`). `twine check` doit valider les deux et notamment le rendu Markdown
du README. La liste de la roue doit contenir les fichiers de
`monl_platform/static/`, ainsi que les modules qui portent la grammaire, les
gabarits et les modèles d'applications ; elle doit aussi contenir
`*.dist-info/licenses/LICENSE`.

## TestPyPI puis PyPI

Les mêmes fichiers de `dist/` sont utilisés pour les deux index. Ne pas reconstruire entre les deux envois.

```bash
python -m twine upload --repository testpypi dist/*
python -m pip install \
  --index-url https://test.pypi.org/simple/ \
  --extra-index-url https://pypi.org/simple/ \
  monl-compiler==0.9.0-beta.8
python -m twine upload dist/*
```

Le premier `upload` demande les identifiants TestPyPI du mainteneur. Après
l'installation d'essai, exécuter hors du dépôt le parcours de preuve :
`monl --version`, `monl --help`, compilation d'une spécification sans asset,
démarrage et requêtes du backend, puis `monl-platform` sur `/health`,
`/ready` et `/favicon.ico`. Le second `upload` demande les identifiants PyPI
du mainteneur et ne doit être lancé qu'après validation de TestPyPI. Aucun de
ces deux envois n'est exécuté par la suite de tests du dépôt.

Une publication réussie est ensuite vérifiable sans authentification avec :

```bash
python -m pip index versions monl-compiler
```
