# QuickStart — monl

Trois étapes : le dialogue génère le backend, le frontend est ajouté au dossier
cible, puis l'application est lancée. Le fonctionnement est déterministe et
hors-ligne par défaut.

## 1. Installation

```bash
pip install -e .
```

Installe les dépendances et la commande `monl`.
Pour utiliser les fournisseurs frontend par API, installer aussi l'extra
optionnel : `pip install -e '.[ai]'`.

## 2. Génération du projet (dialogue guidé)

```bash
monl
```

Le dialogue guidé pose une série de questions, puis crée un dossier portant le
nom de l'application. Ce dossier contient le backend (`app.py`, `schema.sql`),
l'architecture et le contrat (`monl.json`, `frontend_contract.json`), ainsi que
le brief `FRONTEND_PROMPT.md` destiné à l'interface.

## 3. Ajout du frontend dans `<App>/frontend/`

Quatre méthodes, au choix. Le brief `FRONTEND_PROMPT.md` sert de consigne à l'IA
dans les trois dernières.

- **Manuellement** : placer les fichiers directement dans `<App>/frontend/`.
- **Sans aucune clé API** — coller le contenu de `FRONTEND_PROMPT.md` dans
  n'importe quel assistant accessible par navigateur, récupérer le résultat, puis :
  ```bash
  monl import <fichier-ou-zip> <App>
  ```
  Le résultat passe exactement les mêmes garde-fous qu'une réponse d'API
  (liste blanche, refus des CDN, cohérence, smoke test).
- **Avec un agent en ligne de commande** (authentification par abonnement),
  dans le dossier cible :
  ```bash
  monl frontend <App> --provider claude-code
  ```
- **Avec une clé API Anthropic** :
  ```bash
  export ANTHROPIC_API_KEY="sk-…"
  monl frontend <App> --provider claude
  ```

Rappel : les étapes 1 et 2 ci-dessus n'appellent jamais le réseau. Seule cette
étape-ci fait intervenir une IA, et elle a une voie sans clé.

## 3 bis. Comptes privilégiés

`POST /register` n'accepte que les rôles marqués `selfRegister` dans la spec.
Les autres se créent sur la machine qui héberge la base, dans le dossier du
projet :

```bash
python3 manage.py adduser patron Admin     # mot de passe demandé
python3 manage.py users                    # inventaire des comptes
```

## 4. Vérification et lancement

```bash
monl run <App>
```

`monl run` contrôle la cohérence entre backend, contrat et frontend (smoke test
comportemental inclus), puis démarre le serveur sur http://127.0.0.1:8000 —
interface sur `/site`, documentation de l'API sur `/docs`.

---

**Évolution de la spécification.** Après modification de la spec, `monl update
<App>` resynchronise le backend et le contrat et régénère le brief de mise à
jour. Déploiement et modèle de sécurité : `docs/SECURITE.md`. Guide complet :
`README.md`.
