# Publier monl-compiler par Trusted Publishing

Cette procédure publie `monl-compiler` sans secret de longue durée. Un tag
`v*` déclenche `.github/workflows/publication.yml`, qui teste et lint le commit
du tag, construit les distributions une seule fois, les envoie d'abord à
TestPyPI, puis attend l'approbation de l'environnement protégé `pypi` avant
l'envoi à PyPI.

Le workflow n'a ni identifiant, ni mot de passe, ni jeton enregistré. L'action
PyPA demande à GitHub une identité OIDC de courte durée ; PyPI la vérifie et
émet alors le droit d'envoi temporaire. Les tests locaux ne font aucun envoi.

## Prérequis des comptes

PyPI n'accepte plus le mot de passe pour un envoi. Pour publier, le mainteneur
doit utiliser Trusted Publishing ou, uniquement en secours, un jeton API.

La 2FA est exigée sur le compte qui administre ou publie sur PyPI. Il faut
l'activer avant de configurer l'éditeur de confiance.

TestPyPI est une instance séparée de PyPI :

- autre compte et autre inscription sur `test.pypi.org` ;
- autre adresse de vérification, ou au minimum une vérification séparée de
  l'adresse dans cette instance ;
- autre projet, autre éditeur de confiance et autre environnement ;
- la 2FA doit aussi être active sur le compte TestPyPI qui le configure.

Une inscription ou une adresse vérifiée sur PyPI ne donne donc aucun accès à
TestPyPI, et inversement.

## Déclarer l'éditeur de confiance côté PyPI

Le mainteneur fait cette configuration dans son navigateur, avec la 2FA
activée. Il ne crée ni copie ni saisie de jeton.

Pour un projet déjà créé, ouvrir **Your projects → Manage → Publishing** sur
l'instance concernée. Pour `monl-compiler` avant son premier envoi, ouvrir
**Account → Publishing**, choisir un éditeur en attente (**pending publisher**)
et remplir aussi le nom du projet à créer. Un éditeur en attente permet de
créer le projet au premier envoi réussi, sans aucun jeton ; il ne réserve pas
le nom entre-temps.

Sur PyPI, ajouter un éditeur **GitHub Actions** avec les champs suivants :

| Champ PyPI | Valeur à saisir |
| --- | --- |
| Projet | `monl-compiler` |
| Propriétaire du dépôt | `Bodichane` |
| Dépôt | `monl-compiler` |
| Workflow | `publication.yml` |
| Environnement | `pypi` |

Le champ Workflow est le nom du fichier sous `.github/workflows`, pas le nom
lisible `Publication` affiché par GitHub Actions. Le mainteneur répète la
même démarche sur `test.pypi.org` (compte TestPyPI séparé), avec exactement :

| Champ TestPyPI | Valeur à saisir |
| --- | --- |
| Projet | `monl-compiler` |
| Propriétaire du dépôt | `Bodichane` |
| Dépôt | `monl-compiler` |
| Workflow | `publication.yml` |
| Environnement | `testpypi` |

Les valeurs `pypi` et `testpypi` sont les noms déclarés dans le workflow. Une
faute dans le propriétaire, le dépôt, le fichier ou l'environnement produit
un refus `invalid-publisher` sans que l'action puisse le corriger.

Enfin, dans **GitHub → Settings → Environments**, créer ou vérifier
l'environnement `pypi` et ajouter le mainteneur comme **required reviewer**.
L'environnement `testpypi` peut avoir ses propres règles, mais l'approbation
manuelle obligatoire est la porte qui protège l'envoi définitif à PyPI.

## Avant la construction

Le nom de distribution reste `monl-compiler`. Le vérifier ne demande aucune
authentification :

```bash
curl -sS -o /dev/null -w '%{http_code}\n' \
  https://pypi.org/pypi/monl-compiler/json
```

`404` signifie que l'API ne retourne pas encore de projet pour ce nom ; `200`
signifie qu'il est déjà occupé. Dans ce second cas, arrêter et décider d'un
autre nom : `twine` ne crée pas un second projet.

## Ce que le workflow vérifie

Le workflow est volontairement déclenché par `push.tags: ["v*"]`, jamais par
un push de branche : fusionner sur `main` ne publie pas. Le job de vérification
compare le tag à la version de `pyproject.toml` avec
`packaging.version.Version`. Ainsi `0.9.0-beta.8` et `0.9.0b8` sont reconnus
comme la même version Python ; une égalité de chaînes refuserait à tort cette
publication correcte. Une divergence nomme les deux valeurs et arrête la
chaîne avant la construction.

Les tests et `ruff check src tests` tournent dans ce workflow sur le commit
désigné par le tag, avant le job de construction. La CI de `main` n'est pas une
preuve suffisante : elle peut avoir testé un autre commit.

Le job `build` exécute dans cet ordre `rm -rf dist/`, puis construit une seule
fois avec `python -m build`. Il valide la roue et l'archive source, puis
transmet les mêmes fichiers par `upload-artifact`. Les jobs de publication
utilisent `download-artifact`.

Ne pas reconstruire entre les deux envois, TestPyPI et PyPI. Une version envoyée est
définitive et ne peut plus être réutilisée, même après suppression ; un
artefact périmé dans `dist/` pourrait donc publier la mauvaise version.

## Voie manuelle de secours uniquement

Cette voie reste documentée pour le cas exceptionnel où Trusted Publishing
serait indisponible. Elle ne fait pas partie du workflow normal. Le mot de
passe ne convient pas à un envoi PyPI : il faut un jeton API, avec le nom
d'utilisateur littéral `__token__` et une valeur de jeton commençant par
`pypi-`. Le jeton reste uniquement dans le trousseau du mainteneur ou dans
son `~/.pypirc` personnel, jamais dans ce dépôt, un ticket, un journal ou une
commande copiée. Ce guide n'utilise aucune valeur de secret et la voie OIDC
n'utilise ni `TWINE_PASSWORD`, ni option `--password`.

Si cette voie de secours est réellement choisie, `~/.pypirc` peut contenir les
adresses publiques des deux index, sans secret dans cet extrait :

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

Depuis la racine du dépôt, contrôler d'abord le nom et la version. Le
nettoyage doit précéder la construction : `dist/` est ignoré par git mais
survit d'une construction à l'autre sur une machine de publication.

```bash
rm -rf dist/
python -m build
python -m twine check dist/*
unzip -l dist/*.whl
```

**`rm -rf dist/` n'est pas une précaution de style, et c'est mesuré.** `dist/`
est ignoré par git, donc il n'existe pas dans un dépôt fraîchement cloné —
mais il survit sur la machine qui a déjà construit, qui est précisément celle
qui publie. Relevé sur celle du mainteneur au moment d'écrire ces lignes :
`dist/` contenait `monl_compiler-0.9.0b7` alors que la version à publier est
`0.9.0b8`, et `dist/anciens/` portait encore des artefacts nommés
`monl-0.9.0b5`, c'est-à-dire l'ANCIEN nom de distribution. Construire sans
nettoyer laisse les deux côte à côte, et `dist/*` développe alors les quatre
fichiers : **`twine upload` publierait une version qu'on ne voulait pas
envoyer, et qu'on ne peut plus retirer d'un index** — PyPI ne permet pas de
republier un numéro de version, même après suppression. Les artefacts
`monl-0.9.0b5` créeraient en plus un SECOND projet sur l'index. `twine check`
et `unzip -l dist/*.whl` deviennent au passage ambigus, donc leur contrôle ne
dit plus sur quoi il a porté.

Dans le workflow, `dist/` n'existe pas au départ — chaque exécution part d'une
machine neuve. Le `rm -rf dist/` y est conservé quand même : le jour où
quelqu'un ajoute un cache entre deux étapes, la garantie doit déjà être là.

La première commande de construction doit produire une archive source
(`.tar.gz`) et une roue (`.whl`). `twine check` doit valider les deux et la
roue doit notamment contenir `monl_platform/static/`, les modules, la
grammaire, les gabarits, les modèles d'applications et
`*.dist-info/licenses/LICENSE`.

Ne pas utiliser `dist/anciens/` : ce dossier peut contenir des artefacts de
l'ancien nom de distribution `monl-0.9.0b5`. Les envoyer créerait un second
projet sur l'index.

Les mêmes fichiers de `dist/` sont ensuite utilisés pour les deux index. Ne
pas reconstruire entre les deux envois :

```bash
python -m twine upload --repository testpypi dist/*
python -m pip install \
  --index-url https://test.pypi.org/simple/ \
  --extra-index-url https://pypi.org/simple/ \
  monl-compiler==0.9.0-beta.8
python -m twine upload dist/*
```

Le premier envoi est TestPyPI. Après l'installation d'essai, exécuter hors du
dépôt le parcours de preuve : `monl --version`, `monl --help`, compilation
d'une spécification sans asset, démarrage et requêtes du backend, puis
`monl-platform` sur `/health`, `/ready` et `/favicon.ico`. Le second envoi est
PyPI et ne doit avoir lieu qu'après cette validation. Aucun de ces deux envois
réels n'est exécuté par la suite de tests du dépôt.

Une publication réussie peut ensuite être vérifiée sans authentification avec :

```bash
python -m pip index versions monl-compiler
```
