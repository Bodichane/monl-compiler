# Migrations de schéma dans monl

Ce document décrit ce que fait monl quand la spec d'une application
évolue et qu'une base de données existe déjà, et surtout ce qu'il ne fait
**pas**, volontairement.

## Le principe : migration additive, sans perte de données

Le schéma généré (`schema.sql`) crée les tables avec
`CREATE TABLE IF NOT EXISTS` : une table déjà présente n'est jamais
recréée ni écrasée. Mais `IF NOT EXISTS` ne suffit pas dès qu'on **ajoute
un champ** à une entité existante — la table est déjà là, donc le nouveau
champ n'apparaîtrait jamais.

Au démarrage du serveur, après avoir exécuté `schema.sql`, `init_db()`
rattrape cet écart :

1. pour chaque table métier, il lit les colonnes réellement présentes
   (`PRAGMA table_info`) ;
2. il les compare aux colonnes attendues par la spec courante (constante
   `_EXPECTED_COLUMNS`, figée dans `app.py` à la compilation) ;
3. pour chaque colonne manquante, il exécute
   `ALTER TABLE <table> ADD COLUMN <col> <type>`.

Cette opération est **purement additive** : aucune donnée existante n'est
lue, déplacée, réécrite ou supprimée. Les lignes déjà en base reçoivent
simplement `NULL` sur les nouvelles colonnes. Un message
`🔧 Migration : colonne ... ajoutée` est affiché pour chaque ajout.

### Exemple

Spec v1 :

```
entity Note
    title: String
```

On crée quelques notes, puis on fait évoluer la spec :

```
entity Note
    title: String
    body: Text
    priority: Integer
```

En recompilant **dans le même dossier** (donc en conservant `app.db`) et en
redémarrant, les colonnes `body` et `priority` sont ajoutées, les notes
existantes sont intactes (leur `title` est préservé, `body`/`priority`
valent `NULL`), et les nouvelles notes peuvent renseigner les nouveaux
champs.

## Ce qui n'est PAS fait (et pourquoi)

- **Supprimer une colonne retirée de la spec.** SQLite ne supporte pas
  `DROP COLUMN` sans reconstruire toute la table, et surtout : supprimer
  une colonne détruit les données qu'elle contient. monl laisse donc
  les colonnes orphelines en place. Elles sont inertes (plus aucune route
  ne les lit ni ne les écrit) mais leurs données restent récupérables.
- **Changer le type d'une colonne existante.** Un changement de type peut
  être destructif (troncature, échec de conversion). monl ne tente
  aucune conversion automatique. Si un changement de type est nécessaire,
  c'est une migration manuelle, à faire hors monl.
- **Renommer une colonne.** Indistinguable, pour le moteur, d'une
  suppression suivie d'un ajout — donc traité comme tel (ancienne colonne
  conservée inerte, nouvelle colonne ajoutée vide). Un vrai renommage
  préservant les données est une opération manuelle.

En résumé : monl automatise le seul cas qui est **toujours sûr**
(ajouter), et refuse d'automatiser les cas qui peuvent détruire des
données. Ceux-ci restent du ressort d'une intervention explicite.

## Repartir de zéro

Pour réinitialiser complètement une application (perte de toutes les
données assumée), il suffit de supprimer `app.db` avant de redémarrer : le
`CREATE TABLE` recrée alors tout le schéma à neuf.
