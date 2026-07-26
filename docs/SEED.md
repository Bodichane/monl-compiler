# Données de démonstration (`seed`)

Une application monl est pilotée par les données : sans données, ses pages
publiques (galerie, boutique, fil social, classement…) s'affichent vides.
Le bloc `seed` permet de déclarer des données de démonstration directement
dans la spec, pour qu'un site s'ouvre **déjà rempli** — utile pour les
démos, les captures d'écran et la prise en main.

## Syntaxe

```
seed NomEntité
    champ: valeur, champ: valeur, ...
    champ: valeur, champ: valeur, ...
```

Une ligne indentée = un enregistrement. Les valeurs sont soit des chaînes
entre guillemets, soit des nombres (entiers ou décimaux). Exemple :

```
seed Product
    name: "Chaise Ligne", price: 249.90, stock: 12, imageUrl: "https://picsum.photos/seed/chaise/700/560"
    name: "Table Onde", price: 1200.00, stock: 0, imageUrl: "https://picsum.photos/seed/table/700/560"
```

Plusieurs blocs `seed` peuvent viser la même entité ; leurs lignes sont
concaténées.

## Images

Pour des visuels réels sans rien télécharger ni héberger, on utilise des URLs
publiques stables comme [picsum.photos](https://picsum.photos) :
`https://picsum.photos/seed/<clé>/<largeur>/<hauteur>`. La `<clé>` fixe
l'image (la même clé renvoie toujours la même photo), ce qui garde les démos
reproductibles. Ces images se chargent dans le navigateur de l'utilisateur au
moment où il ouvre le site.

## Insertion au démarrage : idempotente

Les données sont insérées par `init_db()` au lancement du serveur, **et
seulement si la table est vide**. Conséquences :

- au 1er lancement, le site s'affiche peuplé ;
- un redémarrage n'empile PAS de doublons ;
- dès que de vraies données existent (créées via l'API), le seed ne fait
  plus rien — les données réelles ne sont jamais écrasées.

Pour repartir d'un seed frais, supprimer `app.db` avant de redémarrer.

## Validation stricte

Comme le reste du compilateur, le seed est validé à la compilation, pas au
runtime : une entité inexistante, un champ non déclaré, ou un type
incohérent (une chaîne pour un champ numérique, ou l'inverse) **font échouer
la compilation** avec un message clair. Une donnée de démo erronée ne peut
donc pas produire une insertion invalide au démarrage.

## Champs `generated`

Un champ marqué `generated` (par ex. un pseudonyme anonyme d'auteur) est
normalement assigné par le serveur à la création, jamais fourni par le
client. Dans un seed, il n'a donc pas à être renseigné : le compilateur lui
attribue une valeur synthétique stable (`Anon#1000`, `Anon#1001`…) pour que
les enregistrements de démonstration soient complets et cohérents avec le
rendu (fil social anonyme, etc.).
