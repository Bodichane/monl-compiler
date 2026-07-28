# MonL

**Un compilateur qui transforme une spécification déclarative en backend complet, déterministe et sûr.**

[![CI](https://github.com/Bodichane/MonL/actions/workflows/ci.yml/badge.svg)](https://github.com/Bodichane/MonL/actions/workflows/ci.yml)
[![Version](https://img.shields.io/badge/version-0.9.0--beta.3-blue)](CHANGELOG.md)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](pyproject.toml)
[![Tests](https://img.shields.io/badge/tests-153-brightgreen)](tests/)
[![Couverture](https://img.shields.io/badge/couverture-85%25-brightgreen)](#qualité-et-vérification)
[![Licence](https://img.shields.io/badge/licence-propriétaire-lightgrey)](LICENSE)

On décrit l'intention d'une application dans un DSL dédié ; MonL en génère la base
de données, l'API REST, l'authentification et le contrôle d'accès — puis produit un
contrat que le frontend doit respecter. **La spécification est l'unique source de
vérité** : on ne maintient pas le code d'infrastructure à la main.

Un dialogue guidé aide à rédiger cette spécification sans connaître la syntaxe. Le
seul recours à l'IA se situe au bout de la chaîne, pour construire le frontend à
partir du contrat garanti par le compilateur — **jamais** pour le backend ni la
logique métier.

---

## Sommaire

- [Démarrage rapide](#démarrage-rapide)
- [Pourquoi MonL ?](#pourquoi-monl-)
- [Architecture](#architecture)
- [Commandes](#commandes)
- [La spécification](#la-spécification)
- [Le backend généré](#le-backend-généré)
- [Le frontend : contrat et IA spécialisée](#le-frontend--contrat-et-ia-spécialisée)
- [Qualité et vérification](#qualité-et-vérification)
- [Structure du dépôt](#structure-du-dépôt)
- [Documentation](#documentation)

---

## Démarrage rapide

**1. Installer**

```bash
pip install .
```

**2. Décrire l'application.** `monl` sans argument ouvre le dialogue guidé : des
questions fermées, aucune IA, aucun appel réseau. Il écrit la spécification, en
dérive le backend et le contrat frontend dans un dossier au nom du projet.

```bash
monl
```

**3. Lancer.** La cohérence et le smoke test sont vérifiés avant tout démarrage.

```bash
monl run MonProjet
```

L'API répond alors sur `http://127.0.0.1:8000`, sa documentation sur `/docs`.

> **Ubuntu / Debian.** Le Python système est protégé (PEP 668). Préférez
> `pipx install .`, qui isole l'outil dans son propre environnement, plutôt que
> `pip install . --break-system-packages`.

Le parcours complet — y compris l'ajout d'une interface — est détaillé dans
[QUICKSTART.md](QUICKSTART.md).

## Pourquoi MonL ?

| | Framework classique<br><sub>Django, Rails, FastAPI…</sub> | Générateur d'IA<br><sub>v0, Bolt, assistants de code</sub> | **MonL** |
|---|---|---|---|
| **Code d'infrastructure** | écrit et maintenu à la main | produit une fois, à reprendre ensuite | **dérivé de la spec, jamais maintenu** |
| **Deux compilations identiques** | sans objet | résultat différent à chaque fois | **le même backend, à l'octet près** |
| **Contrôle d'accès** | vérifié route par route, à la vigilance | ce que le modèle a compris | **vérifié à la compilation : une collision de privilèges empêche de compiler** |
| **Cohérence schéma / API / règles** | trois endroits à synchroniser | aucune garantie | **une source unique, propagée à la recompilation** |
| **Sécurité** | dépend de l'auteur | espérée | **acquise par construction : requêtes paramétrées, rôle issu du compte réel, secret hors du code** |
| **Rôle de l'IA** | aucun | écrit tout, backend compris | **cantonnée au frontend, encadrée par un contrat et un smoke test** |
| **Évolution du schéma** | migrations à écrire | à reprendre à la main | **additive et non destructive, données préservées** |

**Ce que vous écrivez :** une spécification d'une page. **Ce que vous
modifiez, ensuite :** la même page. Le code produit se recompile ; il n'est
jamais un point de départ à retoucher.

## Architecture

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/images/architecture-sombre.svg">
  <img alt="Dialogue guidé → spec.ml → backend et contrat frontend → frontend écrit par une IA, le tout vérifié par monl run" src="docs/images/architecture-clair.svg" width="100%">
</picture>

Le dialogue produit la spécification ; le compilateur en dérive **à la fois** le
backend et le contrat frontend ; l'IA écrit l'interface contre ce contrat ;
`monl run` vérifie que les trois restent cohérents avant de lancer l'application.

## Commandes

| Commande | Ce qu'elle fait |
|---|---|
| `monl` | Dialogue guidé → `spec.ml` + backend + contrat frontend |
| `monl compile <spec.ml> --output <dir>` | Compile une spécification existante |
| `monl frontend <App>` | L'IA écrit l'interface dans `frontend/` |
| `monl import <zip\|html\|dossier> <App>` | Installe un frontend obtenu sans clé API |
| `monl run <App>` | Vérifie la cohérence, joue le smoke test, puis lance |
| `monl update <App>` | Recompile après évolution de la spec, préserve les données |

Chaque projet se compile dans son propre dossier via `--output`, afin de ne pas
écraser le précédent. Les spécifications portent l'extension `.ml`.

## La spécification

Une spec décrit des **entités** (tables et champs), des **acteurs** (rôles) et des
**règles** d'accès. Le compilateur en dérive le schéma, les routes CRUD et le
contrôle d'accès. Les identifiants sont contraints par la grammaire, ce qui exclut
toute injection par les noms de tables ou de colonnes.

**Le contrôle d'accès s'exprime au niveau de l'enregistrement, lecture comprise :**

| Règle | Effet |
|---|---|
| `rule Entite.Action ownedBy Acteur` | Seul le propriétaire (relation auto-peuplée à la création) peut agir — **le filtrage couvre aussi la lecture**, liste et accès direct |
| `rule Entite.Action accessibleBy col1, col2` | Réservé aux parties référencées par l'enregistrement (messagerie privée : expéditeur et destinataire) |
| `rule Entite.Action public` | Retire l'authentification d'une action précise (galerie publique, formulaire de contact) |

D'autres marqueurs affinent champs et comportement : `hidden`, `generated`,
`categorized`, `increments` / `decrements` (compteurs transactionnels), ainsi qu'un
bloc `seed` idempotent qui pré-remplit la base au démarrage. Une règle sans effet
est **refusée à la compilation** plutôt qu'ignorée en silence.

<details>
<summary><b>Inscription : pourquoi un rôle ne s'obtient pas en un appel HTTP</b></summary>

<br>

Un acteur n'est pas inscriptible par défaut. `actor Client selfRegister` ouvre
`POST /register` à ce rôle ; un `actor Admin` sans marqueur ne peut être obtenu que
par provisionnement hors ligne (`manage.py`, généré à côté du backend). Laisser le
client choisir son rôle à l'inscription serait une élévation de privilège en un
appel HTTP.

</details>

**Cinq spécifications de référence**, commentées, dans
[`exemples/`](exemples/) : un fichier `.ml` d'une page par application —
portfolio, boutique, réseau social, kanban, classement — dont MonL dérive tout
le reste.

<details>
<summary><b>Direction visuelle : contraignante si déclarée, indicative si déduite</b></summary>

<br>

Un thème épinglé dans la spec (`ui <Entité>` + `theme: <nom>`) est **contraignant** :
sa palette est vérifiée dans le frontend au smoke test. Un thème déduit du
vocabulaire des entités n'est qu'une **proposition**, dont l'interface peut
s'écarter. Le compilateur ne fait échouer un build que sur ce que l'auteur a
réellement déclaré.

</details>

## Le backend généré

**Comptes et rôles.** `POST /register` n'accepte que les rôles marqués
`selfRegister` ; tout autre est refusé (403). Les comptes privilégiés se créent
avec le `manage.py` généré, sur la machine qui héberge la base :
`python3 manage.py adduser <utilisateur> <role>`. La même commande gère rôle, mot
de passe, liste des comptes et révocation globale des sessions.

**Authentification.** Registre d'utilisateurs propre à chaque application (table
`_monl_users`, mots de passe en PBKDF2-HMAC-SHA256, sel unique par compte,
comparaison à temps constant). Flux : `POST /register` → `POST /login` (jeton JWT)
→ `POST /logout` (révocation avant expiration). **Le rôle et l'identité portés par
le jeton proviennent du compte réel**, jamais d'une déclaration du client.

**Secret JWT.** Généré aléatoirement à la première compilation, stocké dans
`.jwt_secret` (jamais versionné). En production, `MONL_JWT_SECRET` est prioritaire
et permet de livrer un projet sans secret sur le disque.

**Multi-workers.** Révocation de jetons et limitation de débit (5 tentatives /
60 s / IP sur `/register` et `/login`) sont persistées en base, donc partagées :
`uvicorn app:app --workers N` n'en démultiplie pas les quotas. Derrière un reverse
proxy de confiance, `MONL_TRUST_PROXY=1` fait lire l'IP réelle dans
`X-Forwarded-For` ; sans ce réglage l'en-tête est ignoré, pour empêcher toute
usurpation.

**Migrations.** Recompiler dans le même dossier, en conservant `app.db`, ajoute les
colonnes par `ALTER TABLE ADD COLUMN` sans toucher aux données. Les changements
destructifs ne sont pas automatisés, à dessein — voir [docs/MIGRATIONS.md](docs/MIGRATIONS.md).

**Routes servies.** `/docs` (Swagger, toujours disponible) · `/` (redirige vers
`/docs`) · `/site` (l'interface, si `frontend/` existe et que l'app est lancée par
`monl run`).

## Le frontend : contrat et IA spécialisée

L'interface est écrite par une IA, à partir de deux documents que chaque
compilation produit :

- `frontend_contract.json` — description exhaustive et machine-lisible des routes,
  de l'authentification et des règles de champ, dont un test garantit qu'elle ne
  peut pas diverger du backend ;
- `FRONTEND_PROMPT.md` — un brief prêt à confier à une IA d'interface, avec une
  direction de design stable propre au projet.

L'IA écrit dans `frontend/` (point d'entrée `index.html`), que `monl run` sert sur
`/site` sans jamais toucher au backend. Trois voies, mêmes garde-fous :

| Voie | Commande | Authentification |
|---|---|---|
| Manuelle | déposer les fichiers dans `frontend/` | — |
| Agent local | `monl frontend <App> --provider claude-code` | abonnement Claude |
| API | `monl frontend <App> --provider claude` | `ANTHROPIC_API_KEY` |
| Copier-coller | `monl import <zip\|html\|dossier> <App>` | aucune |

Garde-fous communs : extensions en liste blanche, protection contre le zip-slip,
frontend autonome sans CDN, et re-vérification systématique.

**Avant tout lancement**, `monl run` exécute un smoke test comportemental sur un
serveur éphémère à base neuve : chaque route du contrat est éprouvée en HTTP réel
et, si Node.js est présent, `frontend/index.html` est exécuté dans jsdom contre ce
serveur. Toute exception ou tout appel hors contrat bloque le lancement
(`--skip-smoke` pour outrepasser en connaissance de cause).

## Qualité et vérification

| | |
|---|---|
| **153 tests** | Serveurs réels et éphémères, pas de simulacre du pipeline |
| **85 % de couverture** | `pytest --cov=src` |
| **Audit offensif** | Usurpation de rôle, JWT forgé, élévation de privilège |
| **Frontières d'architecture** | Six contrats d'import vérifiés par un test, pas par la mémoire |
| **Lint** | `ruff check src tests` — zéro signalement, exceptions justifiées dans `pyproject.toml` |
| **CI** | Python 3.10 et 3.12 à chaque push ; `main` protégée par ces vérifications |

```bash
python3 -m pytest tests/ -q --cov=src --cov-report=term-missing
```

```bash
ruff check src tests
```

MonL ne dépend d'aucun modèle d'IA et ne fait aucun appel réseau :
dialogue, spécification et génération du backend sont entièrement déterministes.
Les blocs `custom` produisent des coquilles vides sûres dans `sandbox_ai.py`, dont
la logique métier est écrite à la main — aucune génération de code n'est
automatisée.

## Structure du dépôt

| Dossier | Contenu |
|---|---|
| `src/monl/` | Le paquet : parseur, validateur, dialogue, contrat frontend, CLI |
| `src/monl/generator/` | Le générateur de backend, une couche par module |
| `exemples/` | Cinq spécifications `.ml` d'une page, compilées à chaque test |
| `demo/` | La démo StudioNova : sa spécification et son frontend |
| `tests/` | Non-régression, audit offensif, frontières d'architecture |
| `docs/` | Décisions de conception, sécurité, migrations |

## Documentation

| Fichier | Contenu |
|---|---|
| [QUICKSTART.md](QUICKSTART.md) | Le parcours complet, en trois étapes |
| [docs/design_decisions.md](docs/design_decisions.md) | Le journal du projet : 66 points, chacun avec son *pourquoi* |
| [docs/SECURITE.md](docs/SECURITE.md) | Modèle de sécurité |
| [docs/MIGRATIONS.md](docs/MIGRATIONS.md) | Évolution du schéma sans perte |
| [docs/BETA.md](docs/BETA.md) | État de la bêta et feuille de route |
| [CHANGELOG.md](CHANGELOG.md) | Historique des versions |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Méthode de travail, règles du dépôt, checklist avant PR |

## Licence

Dépôt **public**, logiciel **propriétaire** — tous droits réservés
([LICENSE](LICENSE)). Le code est visible pour lecture et évaluation ; il n'est
pas sous licence libre. Les applications *produites* par MonL à partir de vos
propres spécifications vous appartiennent.

Les rapports de bug et remarques sont bienvenus dans les *issues*.

---

**MonL 0.9.0-beta.3**
