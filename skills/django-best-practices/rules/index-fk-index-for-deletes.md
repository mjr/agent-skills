---
title: Keep foreign key indexes that deletes depend on
impact: HIGH
risk: performance
django: ">=5.2"
database: any
tags: foreign-key, index, delete, on_delete, cascade, protect
sources:
  - https://hakibenita.com/django-foreign-keys
tests: test_indexes.py
---

## Keep foreign key indexes that deletes depend on

An index on a column nobody filters by (an audit `created_by`, a `last_edited_by`) looks
safe to drop. But deleting the referenced row makes Django query every referencing table
by that column (`SELECT ... WHERE created_by_id IN (...)`) to apply `CASCADE` or
`PROTECT`, and the database checks the constraint the same way. Without the index each
of those is a full scan of the referencing table.

**Incorrect (drop the "unused" audit index):**

```python
created_by = models.ForeignKey(User, on_delete=models.PROTECT, db_index=False)
```

**What happens:** deleting one user scans the whole products table, in the request and
again inside the database's constraint check; on a large table, deleting a user (or a
GDPR erasure job) times out.

**Correct (keep it, and say why):**

```python
created_by = models.ForeignKey(
    User,
    on_delete=models.PROTECT,
    # Used to speed up user deletion.
    db_index=True,
)
```

If the column is mostly NULL, keep the lookup indexed with a smaller partial index
instead (see `index-partial-sparse`): `WHERE col IN (...)` implies `col IS NOT NULL`, so
the partial index serves it.

**When not to apply:** if the referenced rows are never deleted (and the reference is
`on_delete=PROTECT` on data that is archived, not deleted), the index may truly be
unnecessary; record that reasoning in the comment.

**How to detect:** `scripts/pg_index_report.sql` lists foreign keys with no index that
starts with their column (`fk-without-index`). Before dropping an index reported as
`unused`, check whether its column is a foreign key: deletes may simply not have
happened since the statistics were reset.

Reference: [Django Foreign Keys: Indexes on Foreign Keys](https://hakibenita.com/django-foreign-keys)
