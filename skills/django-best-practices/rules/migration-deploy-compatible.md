---
title: Remove and rename columns across releases, not in one
impact: HIGH
risk: availability
django: ">=5.2"
database: any
tags: deploy, removefield, rename, expand-contract, zero-downtime
sources:
  - https://docs.djangoproject.com/en/stable/ref/migration-operations/#separatedatabaseandstate
tests: test_migration_deploy_compatible.py
---

## Remove and rename columns across releases, not in one

During a deploy, old and new code run against the same database: migrations run before
(or while) the new code starts, and the old processes keep serving requests until they
are replaced. A migration that drops or renames a column the old code still uses breaks
every request it serves; Django selects every column a model declares, so even code that
never reads the field fails.

**Incorrect (the field is removed from the model and the column dropped together):**

```python
operations = [migrations.RemoveField('order', 'legacy_code')]
```

**What happens:** after the migration, the old processes fail on every query of the
model with "column order.legacy_code does not exist". The other order fails too: if the
new code is deployed first, its inserts fail while the column is still `NOT NULL`.

**Correct (expand, then contract):**

1. **Release 1:** stop using the field in code, make the column nullable (or give it a
   `db_default`), and remove it from the model state only:

   ```python
   migrations.AlterField('order', 'legacy_code', models.CharField(max_length=20, null=True)),
   migrations.SeparateDatabaseAndState(
       state_operations=[migrations.RemoveField('order', 'legacy_code')],
   ),
   ```

2. **Release 2**, once no running code knows the field: drop the column.

   ```python
   migrations.RunSQL(
       'ALTER TABLE orders_order DROP COLUMN legacy_code',
       'ALTER TABLE orders_order ADD COLUMN legacy_code varchar(20) NULL',
   )
   ```

Renames follow the same pattern: add the new column, write both, backfill, move reads,
stop writing the old one, then drop it. A `RenameField` breaks the running code the same
way a `RemoveField` does.

**When not to apply:** if deploys stop all old processes before migrating (planned
downtime), or the model is only used by code that is deployed atomically with the
migration, a single release is fine.

**How to detect:** `RemoveField`, `RenameField`, `RenameModel`, `DeleteModel` and
`AlterField` changes that tighten constraints (`null=True` to `False`) in the same
release as the code that stops using the field; `DROP COLUMN` and `RENAME` in
`sqlmigrate` output.

Reference: [SeparateDatabaseAndState](https://docs.djangoproject.com/en/stable/ref/migration-operations/#separatedatabaseandstate)
