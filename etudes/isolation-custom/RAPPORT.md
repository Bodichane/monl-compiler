# Isolation du code `custom` — étude mesurée (issue #123)

Mesuré le 08/10/2026 sur la machine du mainteneur (Fedora 44, noyau 7.2,
Python 3.14, bubblewrap 0.12.0, podman). Codex a écrit la spec et le code
hostile, puis le filtre cybersécurité d'OpenAI l'a coupé ; les mesures
ci-dessous ont été rejouées et complétées à la main.

## Fichiers

- `spec.ml` : une note et un bloc `custom Publier`.
- `prepare.py` : compile la spec dans `backend/`, remplace la coquille par
  `hostile.py`, puis pose un secret JWT et une table témoin dans `app.db`.
- `hostile_abs.py` : le même code hostile, avec le chemin absolu du backend
  (l'attaquant le connaît).
- `mesure.py` : exécute le code hostile sous chaque option et écrit
  `mesures.json`.

## Référence : sur un vrai serveur, aujourd'hui

Uvicorn sur `backend/`, avec un compte `Auteur` et un appel
`POST /workflow/ecrire/publier`. Réponse :

```
{"jwt_file":{"ok":true},"environment":{"ok":true},"database":{"ok":true},"socket":{"ok":true}}
```

Le code `custom` lit le secret JWT (fichier ET variable d'environnement),
lit la base entière et ouvre le réseau.

## Mesures

Cinq tentatives par option. La colonne « Coût » donne la médiane du temps
par appel (50 appels, 15 pour podman).

| Option | Secret (fichier) | `MONL_JWT_SECRET` | `app.db` | Connexion à l'hôte | Coût |
|---|---|---|---|---|---|
| a. Dans le processus (aujourd'hui) | lu | lu | lue | oui | 0,5 ms |
| b. Sous-processus `-I`, env vide, cwd temporaire, RLIMIT | **lu** | bloqué | **lue** | **oui** | 38 ms |
| c. bubblewrap (`--unshare-all`, FS vide hors `/usr`) | bloqué | bloqué | bloquée | bloquée | 41 ms |
| d. podman `--network none --read-only --cap-drop ALL` | bloqué | bloqué | bloquée | bloquée | 397 ms |
| e. WASM | non mesuré | | | | |

- **Le `bind` local réussit partout** : sous (c) et (d), il se fait sur la
  boucle locale d'un espace de noms réseau vide. Il ne mène nulle part, c'est
  pourquoi la colonne « Connexion à l'hôte » est la mesure qui compte.
- **(b) ne protège pas** : le processus fils a le même utilisateur, donc les
  mêmes fichiers. Vider l'environnement ne retire que la variable.
- **Contre-épreuve de (c)** : en montant `backend/` dans le bac à sable, le
  secret et la base redeviennent lisibles. Le blocage vient donc bien du
  montage, pas d'une erreur du script.
- **(e) WASM** : aucun runtime n'est installé (ni `wasmtime`, ni `wasmer`, ni
  Pyodide), et en installer un demande le réseau. Rien n'a été mesuré, plutôt
  que d'inventer un chiffre.

**Ce qu'impose toute option hors processus** : le contexte passé et le
résultat doivent être sérialisables en JSON. C'est déjà le cas, car l'appel
généré est `sandbox_ai.Publier(payload.model_dump())`. Le code `custom` perd
en revanche tout accès direct à la base : s'il en a besoin, c'est au backend
de lui passer les données.

## La question qui décide de l'urgence : la plateforme exécute-t-elle le Python d'autrui ?

**Non, aujourd'hui.** `src/monl_platform` n'écrit que des **specs**
(`service.py`, `evolution.py`, `builder_runtime.py`). Aucune route, aucun
outil MCP et aucun import n'écrit `sandbox_ai.py`. Un site hébergé n'exécute
donc que la coquille générée par le compilateur.

Il reste à savoir si une `description` peut injecter du code dans cette
coquille. Vérifié en compilant réellement :

- un guillemet nu, ou `"""`, est refusé par le parseur ;
- `\"\"\"` reste inerte dans la docstring ;
- **défaut trouvé**, sans injection : `\N`, `\u12` ou `\x` compilent, mais
  rendent `sandbox_ai.py` invalide (`SyntaxError`), et le backend ne démarre
  plus. Le correctif est apporté à la PR #134 (#119, même module).

Le risque multi-locataire visé par l'issue n'existe donc pas tant que la
plateforme ne laisse pas un utilisateur fournir du Python.

## Recommandation

**Ne pas isoler maintenant.** Le dire, et poser la règle pour plus tard.

1. Dans `SECURITE.md`, écrire qu'un projet mono-auteur exécute le code
   `custom` sous la responsabilité de son auteur, dans le processus du
   backend, avec accès au secret et à la base. Ajouter que la plateforme
   n'accepte pas de Python, et qu'un test le garde : aucune route ne doit
   écrire `sandbox_ai.py`.
2. **Le jour où la plateforme acceptera du Python d'un utilisateur**,
   choisir bubblewrap (c) : seule option mesurée qui bloque les cinq
   tentatives, sans droits root, pour 41 ms par appel. Podman bloque autant
   mais coûte dix fois plus. Le sous-processus simple (b) donne une fausse
   sécurité.

**Ce que coûterait (c)** :
- un sous-processus par appel `custom`, soit environ 40 ms ;
- un résultat obligatoirement en JSON ;
- Linux uniquement, avec les espaces de noms utilisateur non privilégiés.
  macOS et Windows n'ont pas d'équivalent : il faudrait un repli explicite,
  jamais silencieux.

## Questions pour le mainteneur

1. La plateforme acceptera-t-elle un jour du code `custom` écrit par un
   utilisateur ? Si non, l'issue se ferme avec la documentation et le test de
   garde du point 1.
2. Sinon : bubblewrap fonctionne-t-il **dans le conteneur** de la plateforme
   (podman, `--cap-drop ALL`) ? Ce n'est pas mesuré ici. Les espaces de noms
   imbriqués y sont souvent interdits, et c'est le premier point à vérifier.
3. Faut-il activer l'isolation aussi pour un projet mono-auteur téléchargé ?
   Elle casse tout code `custom` qui lit la base directement.
