---
title: Load reverse and many-to-many relations with prefetch_related
impact: HIGH
risk: performance
django: ">=4.2"
database: any
tags: n+1, prefetch_related, manytomany, reverse-foreignkey
sources:
  - https://hakibenita.com/all-you-need-to-know-about-prefetching-in-django
tests: test_query_relations.py
---

## Load reverse and many-to-many relations with prefetch_related

A many-to-many or reverse foreign key cannot be joined into the parent query without
repeating the parent row once per child, so `select_related()` refuses them. Accessing
them per row in a loop runs one query per parent. `prefetch_related()` runs one extra
query per relation for all parents and attaches the results in Python.

**Incorrect (one query per product for its tags):**

```python
for product in Product.objects.all():
    names = [tag.name for tag in product.tags.all()]
```

**Correct (one query for products, one for all their tags):**

```python
for product in Product.objects.prefetch_related('tags', 'order_set'):
    names = [tag.name for tag in product.tags.all()]
    orders = product.order_set.all()
```

Each prefetched relation adds exactly one query, regardless of the number of rows. Chain
with `__` (`'tags__group'`); each level adds another query, which a `Prefetch` object can
reduce (see `query-prefetch-object`).

**When not to apply:** the prefetch query uses `WHERE ... IN (<all parent ids>)`; for
tens of thousands of parents, iterate in chunks (see `query-iterator-large-sets`). If you
only need a count or a boolean, annotate instead (see `query-annotate-aggregates`).

**How to detect:** `.all()` on related managers inside loops, templates and nested
serializers; a query count that grows with the number of rows.

Reference: [All You Need to Know About Prefetching in Django](https://hakibenita.com/all-you-need-to-know-about-prefetching-in-django)
