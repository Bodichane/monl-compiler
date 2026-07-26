# Démonstration complète — AtelierVélo

Ce document déroule le cycle de vie ENTIER d'un projet monl, tel qu'il a
réellement été exécuté (chaque sortie ci-dessous est authentique, pas
rédigée). Le projet final est livré dans `demo/` et un test le verrouille :
`tests/test_demo.py` recompile la spec livrée, installe le frontend livré et
exige un smoke test vert — la démo ne peut pas pourrir en silence.

## 1. Création par dialogue (8 réponses)

```
$ monl
Quel type d'application construisez-vous ?
  [1] Portfolio / site vitrine — …  [3] Boutique en ligne — catalogue public,
  commandes des clients  …  [11] Partir de zéro
> 3
Nom de l'application > AtelierVelo
Décrivez le projet en une phrase > Une boutique d'accessoires vélo,
réparation et pièces détachées.
Classer les produits par catégorie ? (o/n) > o
Suivre le stock de chaque produit ? (o/n) > o
Ajouter une entité personnalisée en plus du modèle ? (o/n) > n
Pré-remplir le site avec les données de démonstration du modèle ? (o/n) > o
Transmettre votre description à l'IA frontend comme brief ? (o/n) > o
```

Le dialogue émet une spec de 63 lignes — lisible, c'est la source de vérité
(`demo/spec.ml`) — puis compile tout : backend (`app.py`, `schema.sql`,
`sandbox_ai.py`), contrat frontend (`frontend_contract.json` +
`FRONTEND_PROMPT.md`), mémoire Claude Code (`CLAUDE.md`) et état
(`monl.json`). Le modèle « Boutique » a mobilisé les briques avancées
sans une question technique : `ownedBy` (chaque client ne voit et ne gère
que SES commandes), lecture publique du catalogue, données de démonstration
réalistes — et les options « catégories » et « stock » ont ajouté les champs
ET leurs valeurs dans les seeds.

## 2. Frontend par IA

Le brief `FRONTEND_PROMPT.md` a été donné à une IA (dans cette démo :
Claude, jouant réellement le rôle — pas un agent factice). Elle a produit
`demo/frontend/` : `index.html`, `style.css`, `app.js` — autonome (aucun
CDN), suivant la direction de design du contrat (système « market », fond
`#EFEDE4`, accent `#0B6E4F`) et n'appelant QUE les routes du contrat :
catalogue public avec filtres par catégorie, création de compte client,
commande en un clic, liste « mes commandes ».

```
$ monl run demo --check
 ✅ Cohérence statique vérifiée (spec ↔ backend ↔ contrat ↔ frontend).
 -> Smoke test comportemental (serveur éphémère, base neuve)…
 ✅ Smoke test réussi : l'API répond conformément au contrat et le
    frontend s'exécute sans erreur.
```

Le smoke test a réellement démarré un serveur, créé un compte, éprouvé
chaque route (publiques → 200, protégées → refus sans jeton), et exécuté
`index.html` dans jsdom contre ce serveur.

## 3. Utilisation réelle

```
$ monl run demo          # http://127.0.0.1:8000/site
POST /register {"username":"lea","password":"…","actor":"Customer"}
  → {"status":"success","user_id":1}
POST /order (JWT) {"total":34.5,"status":"en attente"}
  → {"status":"success","id":1}
GET /order (JWT)
  → {"total":1, "data":[{"id":1,"total":34.5,"status":"en attente",…}]}
```

## 4. Évolution avec `monl update`

On ajoute un champ à la spec (`note: Text` sur `Order`) :

```
$ monl run demo --check
 ❌ La spec a été modifiée depuis la dernière compilation — lancer
    'monl update' pour resynchroniser backend et contrat.

$ monl update demo
─── Delta du contrat frontend ───
  + champ ajouté : Order.note
  → Consigne prête pour l'IA frontend : FRONTEND_UPDATE_PROMPT.md
La base de données existante est préservée : les nouvelles colonnes sont
ajoutées par migration additive au démarrage.
```

L'IA frontend applique `FRONTEND_UPDATE_PROMPT.md` (« intégrer
`Order.note` ») en DEUX retouches ciblées — le champ à la création, la note
à l'affichage — sans rien réécrire. Puis :

```
$ monl run demo --check
 ✅ Smoke test réussi…

$ monl run demo   # la commande de Léa a survécu à la migration :
GET /order → {"id":1, "total":34.5, "status":"en attente", "note":null}
```

La commande créée AVANT l'évolution est toujours là, la nouvelle colonne
arrive à `null` : migration additive, zéro perte.

## Rejouer la démo chez vous

```bash
monl compile demo/spec.ml     # régénère backend + contrat depuis la spec
monl run demo                 # → http://127.0.0.1:8000/site
```

Puis refaites l'étape 4 : modifiez `demo/spec.ml`, constatez le refus de
`run`, lancez `update`, lisez le brief, et donnez-le à votre IA.
