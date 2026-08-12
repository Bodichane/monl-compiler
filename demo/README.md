# CodexShop — la démonstration versionnée

Une papeterie en ligne : catalogue public, panier multi-articles, commandes
réglées puis expédiées. Produite par le parcours complet de monl-compiler, du
dialogue guidé jusqu'à l'interface — celle-ci écrite par Codex contre le
contrat.

**Trois entrées, les seules qui soient écrites :**

| Fichier | Écrit par |
|---|---|
| `spec.ml` | le dialogue guidé, à partir des réponses de l'auteur |
| `frontend/` | une IA d'interface, contre le contrat produit par monl-compiler |
| `assets/` | l'humain — photos des produits et visuel d'accueil (brique 13) |

Tout le reste — backend, contrat, brief, état du projet — se recalcule depuis
`spec.ml` en une seconde, et vit donc dans le dossier de compilation, pas ici.
Le versionner l'a déjà fait vieillir en silence une fois (point 68) : le
contrat livré datait d'avant trois évolutions du compilateur.

## Le refaire tourner

```bash
monl compile demo/spec.ml --output /tmp/codexshop
```

```bash
cp -r demo/frontend demo/assets /tmp/codexshop/
```

```bash
monl run /tmp/codexshop
```

Les photos sont servies parce que `serve.py` monte `assets/` sur
`/site/assets` dès que le dossier existe — le frontend les référence en chemin
RELATIF (`assets/carnet-lin.webp`), jamais par une URL absolue.

## Ce que la suite de tests en fait

`tests/test_demo.py` recompile cette spec, y dépose ce frontend et ces assets,
puis exige que l'ensemble passe la vérification de cohérence **et** le smoke
test comportemental — l'interface est réellement exécutée dans jsdom contre un
serveur éphémère, et le test refuse un frontend qui n'aurait appelé aucune
route. La démo ne peut donc pas pourrir en silence.

Un second test vérifie que le frontend reste AUTONOME : extensions dans la
liste blanche (`.html`, `.css`, `.js`, `.svg`, `.json`), aucun script distant,
aucun CDN. Les photos échappent à cette liste parce qu'elles vivent hors de
`frontend/` — c'est tout l'objet de la brique 13.

## Ce qu'elle montre du langage

C'est la chaîne marchande complète, celle qui a coûté le plus de points au
journal de conception :

- `derivedFrom` puis `sumOf` : le sous-total d'une ligne et le total d'une
  commande sont CALCULÉS par le serveur, jamais écrits par le client
  (points 77 à 82) ;
- `payable` sur ce total, donc sur un montant que personne ne peut fixer
  soi-même, et le verrou qui fige la commande une fois réglée (point 91) ;
- `decrements … by champ` : le stock baisse de ce qui a été commandé, et
  remonte si la ligne disparaît (points 86 et 92) ;
- `oneOf` et `writableAfterPayment` : le statut d'expédition avance après
  paiement, mais par l'administrateur seul et par une route dédiée
  (points 96 et 113) ;
- `numbered` : la référence de commande que l'on dicte au téléphone, attribuée
  par le serveur (point 102) ;
- `requiresOwn` : pas de commande sans fiche client, sous peine d'un colis que
  personne ne peut expédier (point 90) ;
- `releases` : annuler une commande rend le stock qu'elle retenait, une seule
  fois, et l'état annulé est terminal (point 98) ;
- `timestamp` : la date de commande est écrite par le serveur à la création et
  jamais ensuite — une date qu'on se donne à soi-même n'atteste de rien
  (point 89).
