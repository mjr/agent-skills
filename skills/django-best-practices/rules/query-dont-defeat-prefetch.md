---
title: Work on the prefetched objects, not on a new query
impact: HIGH
risk: performance
django: ">=4.2"
database: any
tags: prefetch, cache, n+1, related-manager
sources:
  - https://hakibenita.com/all-you-need-to-know-about-prefetching-in-django
tests: test_query_relations.py
---

## Work on the prefetched objects, not on a new query

A prefetch fills the cache of `relation.all()`. Any other queryset method on the related
manager builds a new query and ignores that cache, so the N+1 comes back while the code
still says `prefetch_related`.

**Incorrect (each of these runs a query per product despite the prefetch):**

```python
for product in Product.objects.prefetch_related('tags'):
    fruit = product.tags.filter(kind='fruit')
    ordered = product.tags.order_by('name')
    names = product.tags.values_list('name', flat=True)
    first = product.tags.first()
```

**Correct (use the cached rows):**

```python
for product in Product.objects.prefetch_related('tags'):
    tags = product.tags.all()                       # Cached.
    fruit = [t for t in tags if t.kind == 'fruit']
    ordered = sorted(tags, key=lambda t: t.name)
    names = [t.name for t in tags]
    first = tags[0] if tags else None
```

Measured on Django 5.2 to 6.1: `.all()`, `.count()` and `.exists()` use the prefetched
rows; `.filter()`, `.order_by()`, `.values_list()` and `.first()` query again. When the
filter or order is known in advance, put it in a `Prefetch` queryset instead (see
`query-prefetch-object`).

**When not to apply:** filtering in Python over a very large prefetched set can be slower
than a targeted query for one parent; prefetch is for many parents with modest children.

**How to detect:** related-manager calls other than `.all()` inside loops over a
prefetched queryset, often hidden in model methods and properties used by templates or
serializers.

Reference: [All You Need to Know About Prefetching in Django](https://hakibenita.com/all-you-need-to-know-about-prefetching-in-django)
