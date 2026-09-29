# Demo Data (`seed`)

A monl application is driven by data: without data, its public pages (gallery, shop, social feed, leaderboard…) appear empty. The `seed` block lets you declare demo data directly in the spec, so a site opens **already populated** — useful for demos, screenshots, and getting started.

## Syntax

```
seed NomEntité
    champ: valeur, champ: valeur, ...
    champ: valeur, champ: valeur, ...
```

An indented line is one record. Values are either quoted strings or numbers (integers or decimals). Example:

```
seed Product
    name: "Chaise Ligne", price: 249.90, stock: 12, imageUrl: "https://picsum.photos/seed/chaise/700/560"
    name: "Table Onde", price: 1200.00, stock: 0, imageUrl: "https://picsum.photos/seed/table/700/560"
```

Multiple `seed` blocks can target the same entity; their rows are concatenated.

## Images

For real visuals without downloading or hosting anything, use stable public URLs such as [picsum.photos](https://picsum.photos): `https://picsum.photos/seed/<key>/<width>/<height>`. The `<key>` fixes the image (the same key always returns the same photo), keeping demos reproducible. These images load in the user's browser when they open the site.

## Inserted at startup: idempotent

Data is inserted by `init_db()` when the server starts, **and only if the table is empty**. Consequences:

- on the first launch, the site appears populated;
- a restart does NOT add duplicates;
- once real data exists (created through the API), the seed does nothing — real data is never overwritten.

To start again with a fresh seed, delete `app.db` before restarting.

## Strict validation

Like the rest of the compiler, the seed is validated at compilation, not at runtime: a nonexistent entity, undeclared field, or inconsistent type (a string for a numeric field, or the reverse) **causes compilation to fail** with a clear message. Invalid demo data therefore cannot cause an invalid insertion at startup.

## `generated` fields

A field marked `generated` (e.g. an anonymous author pseudonym) is normally assigned by the server on creation, never supplied by the client. It therefore does not need to be specified in a seed: the compiler assigns it a stable synthetic value (`Anon#1000`, `Anon#1001`…) so the demo records are complete and consistent with rendering (anonymous social feed, etc.).
