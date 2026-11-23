---
title: Skip heavy columns with only()/defer() or values(), and never read them later
impact: MEDIUM
risk: performance
django: ">=5.2"
database: any
tags: only, defer, values, deferred-fields, n+1
sources:
  - https://hakibenita.com/things-you-must-know-about-django-admin-as-your-app-gets-bigger
tests: test_query_shapes.py
---

## Skip heavy columns with only()/defer() or values(), and never read them later

A model with large text or JSON columns transfers all of them on every query, even for a
list that shows two fields. `only()` and `defer()` leave columns out, but reading a
deferred field later runs one query for that instance: in a loop it becomes an N+1 that
is harder to spot than a missing `select_related`.

**Incorrect (description is deferred, then read for every row):**

```python
for product in Product.objects.only('name'):
    summary = product.description[:100]  # One query per product.
```

**Correct (load exactly what is used):**

```python
for product in Product.objects.only('name', 'description'):
    summary = product.description[:100]

# Or, when model methods are not needed, plain dictionaries:
Product.objects.values('name', 'category__name')
```

`values()` and `values_list(..., named=True)` return only the listed columns, follow
relations with `__` without loading the related objects, and cannot trigger lazy loads.

**When not to apply:** deferring saves little on narrow tables and adds a trap; use it
for genuinely heavy columns. Passing deferred instances to code you do not control
(serializers, templates, `save()`) risks the per-row loads. On Django 6.1+,
`fetch_mode(FETCH_PEERS)` turns those loads into one query (see `query-fetch-modes`).

**How to detect:** `only()`/`defer()` querysets whose instances flow into templates,
serializers or loops; query counts that grow with rows on pages that use them.

Reference: [Things You Must Know About Django Admin As Your App Gets Bigger](https://hakibenita.com/things-you-must-know-about-django-admin-as-your-app-gets-bigger)
