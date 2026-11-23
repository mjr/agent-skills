---
title: Use partial indexes for columns that are mostly NULL or mostly one value
impact: MEDIUM
risk: cost
django: ">=5.2"
database: postgresql
tags: partial-index, null, condition, index-size
sources:
  - https://hakibenita.com/django-foreign-keys
tests: test_indexes.py
---

## Use partial indexes for columns that are mostly NULL or mostly one value

PostgreSQL indexes NULL values. An index on a nullable foreign key that is set on 1% of
rows is nearly as large as one on a column set on every row, and almost all of it
describes rows nobody looks up. A partial index stores only the rows that match its
condition.

**Incorrect (indexes millions of NULLs):**

```python
last_edited_by = models.ForeignKey(User, on_delete=models.PROTECT, null=True)
```

**Correct (index only the rows that have a value):**

```python
class Product(models.Model):
    last_edited_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        null=True,
        # Indexed in Meta, only where set.
        db_index=False,
    )

    class Meta:
        indexes = [
            models.Index(
                fields=['last_edited_by'],
                name='product_last_edited_by_part_ix',
                condition=models.Q(last_edited_by__isnull=False),
            ),
        ]
```

The planner uses a partial index only when the query's condition implies the index's.
`filter(last_edited_by=user)` implies `IS NOT NULL`, so it qualifies, and so do the
lookups Django runs on delete. The same idea applies to "mostly one value" columns: an
index `WHERE status = 'pending'` for a queue where 99% of rows are done.

Converting an existing foreign key index to a partial one is a migration with traps; see
`migration-fk-db-index-change` and `migration-create-before-drop`.

**When not to apply:** if queries filter for the NULL rows (`isnull=True`), the partial
index cannot serve them.

**How to detect:** `scripts/pg_index_report.sql` reports single-column indexes on
columns more than half NULL (`mostly-null`), after `ANALYZE`.

Reference: [Django Foreign Keys: Partial Foreign Key Indexes](https://hakibenita.com/django-foreign-keys)
