---
title: Stream large querysets with iterator(chunk_size=...)
impact: MEDIUM
risk: availability
django: ">=4.2"
database: any
tags: iterator, chunk_size, memory, server-side-cursor, pgbouncer
sources:
  - https://docs.djangoproject.com/en/stable/ref/models/querysets/#iterator
tests: test_query_shapes.py
---

## Stream large querysets with iterator(chunk_size=...)

Iterating a queryset loads every row into memory and keeps them in the queryset's result
cache until it is garbage collected. Exports, backfills and management commands over
large tables then use as much memory as the table is large. `iterator()` streams rows in
chunks without caching them.

**Incorrect (the whole table in memory):**

```python
for product in Product.objects.prefetch_related('tags'):
    export(product)
```

**Correct (bounded memory, prefetch per chunk):**

```python
for product in Product.objects.prefetch_related('tags').iterator(chunk_size=2000):
    export(product)
```

With `chunk_size`, `prefetch_related` still works: it runs one prefetch query per chunk
(Django 4.1+). On PostgreSQL, `iterator()` uses a server-side cursor (`DECLARE ...
CURSOR`), which streams rows from the database instead of fetching them all.

**When not to apply:** server-side cursors outlive the transaction in autocommit mode,
so through PgBouncer in transaction pooling mode a later fetch can land on another
connection and fail. Options, from Django's PostgreSQL notes: wrap the iteration in
`transaction.atomic()` so the cursor lives inside one transaction, use a separate
connection that bypasses the pooler, or set `DISABLE_SERVER_SIDE_CURSORS = True`. With the
last one the driver receives the whole result set at once, so `iterator()` only saves
the instance cache; for real streaming, paginate by primary key
(`filter(pk__gt=last_pk).order_by('pk')[:2000]`). Small querysets gain nothing from
`iterator()`.

**How to detect:** loops over unbounded querysets in commands, exports, data migrations
and Celery or queue tasks; memory spikes in those processes.

Reference: [QuerySet.iterator()](https://docs.djangoproject.com/en/stable/ref/models/querysets/#iterator)
