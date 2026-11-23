---
title: Write many rows with bulk_create and bulk_update
impact: HIGH
risk: performance
django: ">=5.2"
database: any
tags: bulk_create, bulk_update, upsert, update_conflicts
sources:
  - https://docs.sentry.io/product/issues/issue-details/performance-issues/n-one-queries/
tests: test_query_shapes.py
---

## Write many rows with bulk_create and bulk_update

Calling `create()` or `save()` in a loop is one `INSERT` or `UPDATE` per row: the write
side of the N+1 problem. `bulk_create()` inserts in batches, and with
`update_conflicts=True` it becomes an upsert keyed on a unique field.

**Incorrect (twenty round trips):**

```python
for row in rows:
    Job.objects.create(**row)
```

**Correct (one statement per batch):**

```python
Job.objects.bulk_create([Job(**row) for row in rows], batch_size=1000)

# Insert or update by a unique key in one statement:
ShortUrl.objects.bulk_create(
    urls,
    update_conflicts=True,
    unique_fields=['key'],
    update_fields=['target_url'],
)
```

`bulk_update(objs, fields, batch_size=...)` updates existing instances in batches, and
`QuerySet.update()` applies the same change to many rows in one statement.

**When not to apply:** bulk operations skip `save()` overrides and `pre_save`/`post_save`
signals (see `signals-bulk-operations-skip`); when per-row behavior matters, either do
that work explicitly after the bulk call or keep the loop.

**How to detect:** `create(`, `save(` and `get_or_create(` inside loops over input data,
imports and management commands.

Reference: [Sentry: N+1 Queries](https://docs.sentry.io/product/issues/issue-details/performance-issues/n-one-queries/)
