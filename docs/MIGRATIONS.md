# Schema migrations in monl

This document describes the migration policy for the generated backend. It is the same for SQLite and PostgreSQL: the engine is chosen at startup (`MONL_DATABASE_URL` absent for SQLite, `postgresql://` DSN for PostgreSQL), but the migration decision always comes from the compiled spec.

## Readable history

Each backend creates the internal `_monl_migrations` table if it does not exist. For each operation actually applied, it stores:

- the migration name and operation number;
- the operation (`add_column`, `rename_column`, `alter_column_type`, etc.), table, and direction (`up` or `down`);
- the operation's JSON details and `applied_at`;
- the SHA-256 fingerprint of the resulting schema.

An existing database receives this table without changes to its data. Automatic column additions are also recorded under the name `__auto_add_column__`. The table makes state observable without claiming to replace a backup.

## Automatic addition: the only implicit operation

At startup, `init_db()` compares the columns expected by the spec with the existing columns (`PRAGMA table_info` on SQLite, `information_schema.columns` on PostgreSQL). Each missing column is added with `ALTER TABLE ... ADD COLUMN`, then recorded in the history.

This migration never reads, moves, or fills content. Existing rows receive `NULL` in the new column; no date, default value, or invented data is written (point 89).

Example:

```
entity Note
    title: String
```

becomes:

```
entity Note
    title: String
    body: Text
    priority: Integer
```

`body` and `priority` appear; `title` and all rows remain intact. The server then continues its normal startup.

## Non-additive changes: declared, named, never guessed

A rename cannot be inferred from a resemblance between two names. A type change cannot be inferred from intent. A removed column does not, by itself, indicate whether its data is still needed. The spec must therefore contain an explicit migration, using the smallest language that produces an actual operation:

```
migration note_fields
    rename Note.title to heading
    alter Note.priority from String to Integer
    drop Note.legacy
```

The spec is the target state: `heading` and `priority: Integer` must already exist in it, while `title` and `legacy` must not. This prevents decorative syntax that is never connected to the schema; the compiler also refuses inconsistent or ambiguous migrations.

If a non-additive difference exists without a corresponding named migration, the server displays the affected columns and refuses to serve the application. It therefore does not silently turn a rename into an empty column, leave an old type in place, or pretend that a `drop` occurred. A failed migration is rolled back and the exception propagates; the server does not serve a half-migrated database.

## Explicit command

Non-additive migrations are never applied at server startup. The dedicated command loads the project's `app.py` from its own directory, even when run elsewhere:

```
monl migrate PROJECT --list
monl migrate PROJECT --name note_fields
monl migrate PROJECT --name note_fields --down
```

`--list` only prepares the database and displays the history. `--name` applies the upward direction; `--down` requests the downward direction. Each operation and the final fingerprint are recorded in the same transaction as the schema change. On failure, the whole transaction is rolled back and the command returns an error code.

## Downgrade and irreversibility

`rename` and `alter` are reversible: the previous name or type is checked before being restored, and the data is preserved by the engine's appropriate rewrite.

`drop` is explicitly irreversible without a backup: after `DROP COLUMN`, deleted content cannot be recreated. A migration containing `drop` can be applied upward on request, but `--down` refuses it instead of pretending to restore what no longer exists. Restore a backup before attempting any rollback.

## Required questions

### Does `_contract_signature` see A2?

Yes, for changes that affect the interface: the type of an exposed field is kept in the signature and `monl update` reports, for example, `Note.priority : String → Integer`, with an instruction to review input and display. Migrations, history, SQL fingerprint, and the SQLite/PostgreSQL choice are not included: these are backend details that do not change the frontend contract. A rename or removal already appears as an added/removed field because the target contract really changes.

### Point 100: are tools that read the spec as text affected?

No. `migration` is a top-level block recognized by the parser and by `assets_tool.py` for locating an `assets` block. `content_tool.py` neither rewrites nor interprets migrations: it reads only `seed` blocks and leaves this text intact. Migration declarations therefore do not change seed syntax or the text reading of content.

## Deliberately out of scope

- no automatic content filling and no retroactive defaults;
- no inferred renames;
- no automatic `drop` at startup;
- no recovery promise after a `drop` without a backup;
- no backup or restore produced by monl.

The covered cases are exercised against real SQLite databases. PostgreSQL tests use `MONL_TEST_DATABASE_URL` and are skipped cleanly when this DSN is not provided; a skip is not proof for PostgreSQL.
