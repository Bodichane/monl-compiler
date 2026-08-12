# Migrations de schéma dans monl

Ce document décrit la politique de migration du backend généré. Elle est la
même pour SQLite et PostgreSQL : le moteur est choisi au démarrage
(`MONL_DATABASE_URL` absent pour SQLite, DSN `postgresql://` pour PostgreSQL),
mais la décision de migration vient toujours de la spec compilée.

## Historique lisible

Chaque backend crée la table interne `_monl_migrations` si elle n'existe pas.
Elle conserve, pour chaque opération effectivement appliquée :

- le nom de la migration et son numéro d'opération ;
- l'opération (`add_column`, `rename_column`, `alter_column_type`, etc.), la
  table, et le sens (`up` ou `down`) ;
- les détails JSON de l'opération et `applied_at` ;
- l'empreinte SHA-256 du schéma résultant.

Une ancienne base reçoit cette table sans modification de ses données. Les
ajouts automatiques de colonnes y sont aussi inscrits sous le nom
`__auto_add_column__`. La table rend donc l'état observable sans prétendre
remplacer une sauvegarde.

## Ajout automatique : la seule opération implicite

Au démarrage, `init_db()` compare les colonnes attendues par la spec aux
colonnes existantes (`PRAGMA table_info` sur SQLite,
`information_schema.columns` sur PostgreSQL). Chaque colonne manquante est
ajoutée par `ALTER TABLE ... ADD COLUMN`, puis enregistrée dans l'historique.

Cette migration ne lit, ne déplace et ne remplit jamais le contenu. Les lignes
existantes reçoivent `NULL` dans la nouvelle colonne ; aucune date, valeur par
défaut ou donnée inventée n'est écrite (point 89).

Exemple :

```
entity Note
    title: String
```

devient :

```
entity Note
    title: String
    body: Text
    priority: Integer
```

`body` et `priority` apparaissent, le `title` et toutes les lignes restent
intacts. Le serveur continue ensuite son démarrage normal.

## Changements non additifs : déclarés, nommés, jamais devinés

Un renommage ne peut pas être déduit d'une ressemblance entre deux noms. Un
changement de type ne peut pas être déduit d'une intention. Une colonne
retirée n'indique pas, à elle seule, si ses données sont encore nécessaires.
La spec doit donc porter une migration explicite, avec le plus petit langage
qui produit effectivement une opération :

```
migration note_fields
    rename Note.title to heading
    alter Note.priority from String to Integer
    drop Note.legacy
```

La spec est l'état cible : `heading` et `priority: Integer` doivent déjà y
exister, tandis que `title` et `legacy` n'y figurent plus. Cela empêche une
syntaxe décorative qui ne serait jamais reliée au schéma ; le compilateur
refuse également les migrations incohérentes ou ambiguës.

Si une différence non additive existe sans migration nommée correspondante,
le serveur affiche les colonnes concernées et refuse de servir l'application.
Il ne transforme donc pas silencieusement un renommage en colonne vide, ne
laisse pas un ancien type en place et ne fait pas croire qu'un `drop` a eu
lieu. Une migration qui échoue est rollbackée et l'exception remonte ; le
serveur ne sert pas une base à moitié migrée.

## Commande explicite

Les migrations non additives ne s'appliquent jamais au démarrage d'un serveur.
La commande dédiée charge le `app.py` du projet depuis son propre dossier,
même si elle est lancée ailleurs :

```
monl migrate PROJET --list
monl migrate PROJET --name note_fields
monl migrate PROJET --name note_fields --down
```

`--list` prépare seulement la base et affiche l'état historique. `--name`
applique le sens montant ; `--down` demande le sens descendant. Chaque
opération et l'empreinte finale sont enregistrées dans la même transaction
que le changement de schéma. En cas d'échec, toute la transaction est
rollbackée et la commande retourne un code d'erreur.

## Descente et irréversibilité

Les opérations `rename` et `alter` sont descendantes : le nom ou le type
précédent est vérifié avant d'être restauré, et les données sont conservées
par la réécriture appropriée du moteur.

`drop` est explicitement irréversible sans sauvegarde : après un
`DROP COLUMN`, le contenu supprimé ne peut pas être recréé. Une migration qui
contient un `drop` peut monter sur demande, mais `--down` la refuse au lieu de
prétendre restaurer ce qui n'existe plus. Il faut restaurer une sauvegarde
avant toute tentative de retour.

## Questions obligatoires

### `_contract_signature` voit-il A2 ?

Oui pour ce qui change l'interface : le type d'un champ exposé est conservé
dans la signature et `monl update` signale par exemple
`Note.priority : String → Integer`, avec une consigne de revoir la saisie et
l'affichage. Les migrations, l'historique, l'empreinte SQL et le choix
SQLite/PostgreSQL n'y entrent pas : ce sont des détails backend qui ne
changent pas le contrat frontend. Un renommage ou une suppression apparaît
déjà comme champ ajouté/retiré, puisque le contrat cible change réellement.

### Point 100 : les outils qui lisent textuellement la spec sont-ils gênés ?

Non. `migration` est un bloc de premier niveau reconnu par le parseur et par
`assets_tool.py` pour positionner un bloc `assets`. `content_tool.py` ne
réécrit ni n'interprète les migrations : il ne lit que les blocs `seed` et
laisse ce texte intact. Les déclarations de migration ne changent donc pas
la syntaxe des seeds, ni la lecture textuelle des contenus.

## Ce qui reste volontairement hors périmètre

- aucun remplissage automatique de contenu et aucun défaut rétroactif ;
- aucune déduction de renommage ;
- aucun `drop` automatique au démarrage ;
- aucune promesse de récupération après un `drop` sans sauvegarde ;
- aucune sauvegarde ou restauration produite par monl.

Les cas couverts sont éprouvés contre de vraies bases SQLite. Les tests
PostgreSQL utilisent `MONL_TEST_DATABASE_URL` et sont sautés proprement quand
ce DSN n'est pas fourni ; un saut n'est pas une preuve PostgreSQL.
