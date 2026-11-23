---
title: Build and drop indexes concurrently on busy tables
impact: HIGH
risk: availability
django: ">=4.2"
database: postgresql
tags: index, concurrently, addindexconcurrently, invalid-index, locks
sources:
  - https://hakibenita.com/django-foreign-keys
tests: test_migration_concurrent_indexes.py
---

## Build and drop indexes concurrently on busy tables

`CREATE INDEX` holds a lock that blocks inserts, updates and deletes on the table, and in
an atomic migration it keeps that lock until the whole migration commits. `DROP INDEX`
takes an `ACCESS EXCLUSIVE` lock that blocks reads too. The concurrent variants take a
weaker lock and let the application keep writing while they run.

**Incorrect (writes wait for the build):**

```python
operations = [
    migrations.AddIndex(
        model_name='order',
        index=models.Index(fields=['created_at'], name='order_created_ix'),
    ),
]
```

**Correct (a non-atomic migration with the concurrent operation):**

```python
from django.contrib.postgres.operations import AddIndexConcurrently


class Migration(migrations.Migration):
    atomic = False

    operations = [
        AddIndexConcurrently(
            model_name='order',
            index=models.Index(fields=['created_at'], name='order_created_ix'),
        ),
    ]
```

`RemoveIndexConcurrently` is the counterpart for `RemoveIndex`. Both refuse to run in an
atomic migration (`NotSupportedError: ... set atomic = False on the migration`). Keep
them in a migration of their own; see `migration-isolate-non-atomic`.

**A failed concurrent build leaves an invalid index.** If the build is cancelled (a
statement timeout, a deadlock, a duplicate in a unique index), PostgreSQL keeps the index
as `INVALID`: it is not used by queries but is still updated on every write, and
re-running the migration fails with "relation already exists". Drop it before retrying:

```sql
SELECT indexrelid::regclass FROM pg_index WHERE NOT indisvalid;
DROP INDEX CONCURRENTLY IF EXISTS order_created_ix;
```

A concurrent build also waits for every open transaction that has written to the table,
so a long transaction elsewhere makes the migration hang (harmlessly) until it ends.

**When not to apply:** indexes on tables created in the same migration, or on small
tables, can use the plain operations. `AddIndexConcurrently` only handles indexes in
`Meta.indexes`; for the implicit index of a `ForeignKey` see
`migration-fk-db-index-change`. These operations are PostgreSQL-only.

**How to detect:** `AddIndex`, `RemoveIndex`, `AddConstraint` with a `UniqueConstraint`
and `AlterField(..., db_index=True)` on existing large tables; `CREATE INDEX` or
`DROP INDEX` without `CONCURRENTLY` in `sqlmigrate` output.

Reference: [Django Foreign Keys: Concurrent Index Operations](https://hakibenita.com/django-foreign-keys)
