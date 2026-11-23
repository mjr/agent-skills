---
title: Create the replacement index before dropping the old one
impact: HIGH
risk: availability
django: ">=5.2"
database: postgresql
tags: index, partial-index, non-atomic, ordering
sources:
  - https://hakibenita.com/django-foreign-keys
tests: test_migration_non_atomic.py
---

## Create the replacement index before dropping the old one

Replacing an index (a full index by a partial one, a single-column index by a composite
one) uses concurrent operations, so the migration is not atomic and every step takes
effect immediately. Dropping first leaves the table without an index until the new one is
built, and if the migration fails in between, it stays that way until someone notices.

**Incorrect (drop, then build):**

```python
operations = [
    migrations.SeparateDatabaseAndState(  # Drops the implicit FK index.
        state_operations=[migrations.AlterField(...)],
        database_operations=[migrations.RunSQL('DROP INDEX CONCURRENTLY ...', '...')],
    ),
    AddIndexConcurrently('product', models.Index(..., condition=models.Q(...))),
]
```

**What happens:** while the partial index builds, queries on that column scan the
table; if the build fails, there is no index at all.

**Correct (build, then drop):**

```python
operations = [
    AddIndexConcurrently('product', models.Index(..., condition=models.Q(...))),
    migrations.SeparateDatabaseAndState(
        state_operations=[migrations.AlterField(...)],
        database_operations=[migrations.RunSQL('DROP INDEX CONCURRENTLY ...', '...')],
    ),
]
```

At any point of failure at least one index exists. The cost is temporary disk space for
both indexes and slightly slower writes while both exist.

**When not to apply:** when the old index is unique and the new one is not, or the
reverse, think about which constraint must hold during the transition; dropping a unique
index first allows duplicates in the window.

**How to detect:** non-atomic migrations whose operations remove an index before adding
one on the same columns.

Reference: [Django Foreign Keys: Order Migration Operations](https://hakibenita.com/django-foreign-keys)
