---
title: Consider BRIN for large tables filtered by an append-ordered column
impact: LOW-MEDIUM
risk: cost
django: ">=5.2"
database: postgresql
tags: brin, index, timestamp, append-only, index-size
sources:
  - https://hakibenita.com/9-django-tips-for-working-with-databases
tests: test_indexes.py
---

## Consider BRIN for large tables filtered by an append-ordered column

A B-tree index has one entry per row. A BRIN index stores only the minimum and maximum
of each range of table pages, so when the column's values follow the physical order of
the rows (a `created` timestamp on an append-only log or events table), it is orders of
magnitude smaller and still narrows range queries to the right pages.

**Incorrect (a large B-tree for range scans on insert time):**

```python
class Event(models.Model):
    created = models.DateTimeField(auto_now_add=True, db_index=True)
```

**Correct:**

```python
from django.contrib.postgres.indexes import BrinIndex


class Event(models.Model):
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [BrinIndex(fields=['created'], name='event_created_brin_ix')]
```

Range filters (`created__gte=...`) then use a bitmap scan on the BRIN index.

**When not to apply:** BRIN only helps while values correlate with physical order;
updates, deletes followed by reuse of space, or backfilled old timestamps break the
correlation. It does not serve equality lookups of single rows, ordering, or uniqueness.
Keep a B-tree for those. Requires `django.contrib.postgres` in `INSTALLED_APPS`.

**How to detect:** large B-tree indexes on timestamps of append-only tables;
`pg_stats.correlation` close to 1 for the column.

Reference: [9 Django Tips for Working with Databases](https://hakibenita.com/9-django-tips-for-working-with-databases)
