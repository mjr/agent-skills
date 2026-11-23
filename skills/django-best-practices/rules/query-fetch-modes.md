---
title: On Django 6.1+, use fetch modes to batch or forbid lazy loads
impact: HIGH
risk: performance
django: ">=6.1"
database: any
tags: fetch_mode, fetch_peers, fetch_raise, n+1, deferred-fields
sources:
  - https://docs.djangoproject.com/en/6.1/ref/models/querysets/#fetch-mode
tests: test_query_relations.py
---

## On Django 6.1+, use fetch modes to batch or forbid lazy loads

Django 6.1 added `QuerySet.fetch_mode()`, which decides what happens when code touches a
forward relation or a deferred field that was not loaded:

- `FETCH_ONE` (the default): one query for that instance, the classic N+1.
- `FETCH_PEERS`: one query that loads the value for every instance that came from the
  same queryset. A loop that would run N queries runs one more.
- `FETCH_RAISE`: raise `FieldFetchBlocked` instead of querying.

**Incorrect (a forgotten select_related becomes N queries):**

```python
for product in Product.objects.all():
    product.category.name
```

**Correct (the first access loads it for all peers):**

```python
from django.db.models import FETCH_PEERS

for product in Product.objects.fetch_mode(FETCH_PEERS):
    product.category.name  # 2 queries in total, whatever the number of rows.
```

In tests and development, `FETCH_RAISE` turns a hidden lazy load into an error that
points at the exact attribute:

```python
from django.db.models import FETCH_RAISE

products = Product.objects.select_related('category').fetch_mode(FETCH_RAISE)
product.created_by  # FieldFetchBlocked: Fetching of Product.created_by blocked.
```

**What fetch modes do not cover:** reverse and many-to-many managers
(`product.tags.all()`) still run one query per row in every mode; they need
`prefetch_related` (see `query-prefetch-related`). Fetch modes are a safety net, not a
replacement for loading what you know you need.

**When not to apply:** on Django 6.0 and earlier the API does not exist; use
`select_related`, `prefetch_related` and query-count tests. `FETCH_RAISE` in production
code turns a slow page into a broken one; keep it for tests or for querysets whose
loading is fully specified.

**How to detect:** on 6.1+, run the list-view tests with querysets in `FETCH_RAISE`
mode, or apply it in a custom manager used by tests, and fix every `FieldFetchBlocked`.

Reference: [QuerySet.fetch_mode()](https://docs.djangoproject.com/en/6.1/ref/models/querysets/#fetch-mode)
