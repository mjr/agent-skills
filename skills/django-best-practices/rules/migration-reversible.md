---
title: Give every RunSQL and RunPython a reverse operation
impact: HIGH
risk: availability
django: ">=4.2"
database: any
tags: runsql, runpython, reverse, rollback, irreversible
sources:
  - https://hakibenita.com/django-foreign-keys
tests: test_migration_reversible.py, test_migration_fk_db_index_change.py
---

## Give every RunSQL and RunPython a reverse operation

Rolling back a bad deploy usually means `migrate app <previous>`. A `RunSQL` without
`reverse_sql` or a `RunPython` without `reverse_code` makes the whole migration
irreversible, and the rollback stops with `IrreversibleError` exactly when it is needed.

**Incorrect:**

```python
migrations.RunSQL('DROP INDEX CONCURRENTLY "product_category_id_35bf920b"')
migrations.RunPython(backfill_channel)
```

**Correct:**

```python
migrations.RunSQL(
    sql='DROP INDEX CONCURRENTLY "product_category_id_35bf920b"',
    reverse_sql='CREATE INDEX CONCURRENTLY "product_category_id_35bf920b" ON "product" ("category_id")',
)
migrations.RunPython(backfill_channel, reverse_code=clear_channel)
```

For SQL, take the reverse from `sqlmigrate` of the migration that created the object.
For data migrations, the reverse undoes the data change when the forward schema change
is also being undone.

`migrations.RunPython.noop` (and `reverse_sql=migrations.RunSQL.noop`) marks an operation
as reversible with nothing to do. Use it only when that is true: a backfill of a column
that the reverse migration drops anyway needs no reverse; a data fix that the old code
relies on not existing does.

**When not to apply:** some operations cannot be undone (deleting data, irreversible
transformations). Then say so explicitly with a reverse that raises with a clear message,
so the rollback plan accounts for it, instead of omitting it.

**How to detect:** `RunSQL(` calls with a single argument and `RunPython(` calls with a
single function. `Operation.reversible` is `False` for them.

Reference: [Django Foreign Keys: Reversible Migration Operations](https://hakibenita.com/django-foreign-keys)
